"""Generated-strategy forward paper engine with mandatory independent risk admission.

Market snapshots are supplied by trusted feed adapters, never by generated code.
Each bar is consumed at most once. Every fill and state change is atomic.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Connection

from adaptive_alpha.domain import OrderIntent, digest, new_id, now
from adaptive_alpha.research.contracts import DatasetImport
from adaptive_alpha.research.datasets import timestamp
from adaptive_alpha.research.lifecycle import StrategyLifecycle
from adaptive_alpha.research.program import Program
from adaptive_alpha.risk.engine import assess, monitor_account
from adaptive_alpha.store import Store


class ForwardPaper:
    def __init__(self, store: Store):
        self.store = store

    def admit(self, candidate_id: str, actor: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self.create_account(conn, candidate_id, actor)

    def create_account(self, conn: Connection, candidate_id: str, actor: str) -> dict[str, Any]:
        """Use the caller's transaction so lifecycle admission and account are atomic."""
        if actor != "operator":
            raise ValueError("OPERATOR_REQUIRED")
        candidate = self.store.get(conn, candidate_id, "candidate")
        outcomes = self.store.related(conn, "candidate-result", "id", candidate_id)
        if not any(
            r.get("status") == "PASS"
            and r.get("hidden", {}).get("verdict") == "PASS"
            and r.get("public", {}).get("verdict") == "PASS"
            for r in outcomes
        ):
            raise ValueError("INDEPENDENT_VALIDATION_REQUIRED")
        dataset = self.store.get(conn, candidate["dataset_id"], "dataset")
        symbol = dataset["data"]["symbol"]
        if symbol not in {"SPY", "QQQ", "IWM"}:
            raise ValueError("FORWARD_UNIVERSE_NOT_ADMITTED")
        state = self.store.state(conn, "forward:" + candidate_id)
        if state:
            return state
        state = {
            "candidate_id": candidate_id,
            "symbol": symbol,
            "status": "PAPER",
            "cash": 100000.0,
            "positions": {},
            "high_watermark": 100000.0,
            "day_start_nav": 100000.0,
            "last_bar": None,
            "last_day": None,
            "capital_eligible": False,
        }
        self.store.append(
            conn,
            "forward-admission",
            {
                "id": candidate_id,
                "source_hash": candidate["source_hash"],
                "actor": actor,
                "at": now(),
            },
        )
        self.store.set_state(conn, "forward:" + candidate_id, state)
        self.store.audit(conn, "forward.paper_admitted", actor, {"candidate_id": candidate_id})
        return state

    def step(
        self,
        candidate_id: str,
        dataset: DatasetImport,
        quote: dict[str, Any],
        *,
        clock: datetime | None = None,
    ) -> dict[str, Any]:
        clock = clock or datetime.now(UTC)
        # Filter by actual receipt time; no future bar can be passed to the strategy.
        available = [b for b in dataset.bars if timestamp(b.available_at) <= clock]
        if len(available) < 120:
            raise ValueError("FORWARD_HISTORY_REQUIRED")
        last = available[-1]
        with self.store.transaction() as conn:
            candidate = self.store.get(conn, candidate_id, "candidate")
            state = self.store.state(conn, "forward:" + candidate_id)
            lifecycle = StrategyLifecycle(self.store)
            tracked = self.store.state(conn, "lifecycle:" + candidate_id)
            if tracked and not lifecycle.get_in_transaction(conn, candidate_id)["forward_eligible"]:
                raise ValueError("FORWARD_ADMISSION_REQUIRED")
            if state.get("status") != "PAPER" or dataset.symbol != state.get("symbol"):
                raise ValueError("FORWARD_ADMISSION_REQUIRED")
            if digest(candidate["source"]) != candidate["source_hash"]:
                raise ValueError("SOURCE_HASH_MISMATCH")
            quote_age = (clock - timestamp(str(quote["timestamp"]))).total_seconds()
            if not 0 <= quote_age <= 60:
                self.store.set_state(
                    conn,
                    "kill",
                    {"halted": True, "reason": "Stale forward quote", "timestamp": now()},
                )
                self.store.audit(
                    conn,
                    "forward.stale_data",
                    "risk",
                    {"candidate_id": candidate_id, "age": quote_age},
                )
                if tracked:
                    lifecycle.monitor_in_transaction(conn, candidate_id)
                return {"status": "HALT", "reason": "STALE_QUOTE", "candidate_id": candidate_id}
            # A feed can only update an admitted strategy's historical inputs.
            symbol = state["symbol"]
            price = float(quote["prices"][symbol])
            if not 0 < price < 1e9:
                raise ValueError("INVALID_FEED_PRICE")
            nav = state["cash"] + state["positions"].get(symbol, 0) * price
            if state["last_day"] != clock.date().isoformat():
                state["day_start_nav"] = state.get("nav", nav)
            returns = [
                b.close / a.close - 1 for a, b in zip(available[:-1], available[1:], strict=True)
            ]
            monitoring = monitor_account(state, quote["prices"], {symbol: returns})
            state.update(nav=nav, last_day=clock.date().isoformat(), updated_at=now())
            state["high_watermark"] = max(state["high_watermark"], nav)
            self.store.set_state(conn, "forward:" + candidate_id, state)
            if monitoring["status"] == "HALT":
                self.store.set_state(
                    conn,
                    "kill",
                    {
                        "halted": True,
                        "reason": "Forward held-position risk breach",
                        "timestamp": now(),
                    },
                )
                event = {
                    "status": "HALT",
                    "candidate_id": candidate_id,
                    "risk": monitoring,
                    "at": now(),
                }
                self.store.append(conn, "live-evidence", event)
                self.store.audit(conn, "forward.holding_risk_halt", "risk", event)
                if tracked:
                    lifecycle.monitor_in_transaction(conn, candidate_id)
                return event
            if state["last_bar"] and timestamp(state["last_bar"]) >= timestamp(last.time):
                if tracked:
                    lifecycle.monitor_in_transaction(conn, candidate_id)
                return {"status": "NO_NEW_BAR", "candidate_id": candidate_id, "nav": nav}
            signal = Program(candidate["source"]).signal([b.close for b in available])
            target = int(max(0, nav) * signal / price)
            delta = target - state["positions"].get(symbol, 0)
            outcome: dict[str, Any] = {
                "status": "NO_TRADE",
                "candidate_id": candidate_id,
                "signal": signal,
            }
            if delta:
                intent = OrderIntent(
                    strategy_id=candidate_id,
                    instrument=symbol,
                    side="BUY" if delta > 0 else "SELL",
                    quantity=abs(delta),
                )
                risk = assess(
                    intent,
                    state,
                    quote,
                    {symbol: returns},
                    state["positions"],
                    halted=self.store.state(conn, "kill", {"halted": True}).get("halted", True),
                    reconciled=True,
                    clock=clock,
                )
                outcome.update(
                    status="FILLED" if risk["status"] == "APPROVE" else "REJECTED",
                    risk=risk,
                    intent=intent.model_dump(),
                )
                if risk["status"] == "APPROVE":
                    costs = abs(delta) * price * 0.001
                    state["cash"] -= delta * price + costs
                    state["positions"][symbol] = target
                    outcome.update(fill_price=price, quantity=abs(delta), costs=costs)
                    self.store.append(
                        conn, "forward-fill", {**outcome, "id": new_id(), "at": now()}
                    )
                elif risk["status"] == "HALT":
                    self.store.set_state(
                        conn,
                        "kill",
                        {"halted": True, "reason": "Forward paper risk halt", "timestamp": now()},
                    )
            if outcome["status"] != "REJECTED":
                state["last_bar"] = last.time
            state["last_day"] = clock.date().isoformat()
            state["nav"] = state["cash"] + state["positions"].get(symbol, 0) * price
            state["high_watermark"] = max(state["high_watermark"], state["nav"])
            state["updated_at"] = now()
            self.store.set_state(conn, "forward:" + candidate_id, state)
            evidence = {
                **outcome,
                "bar": last.time,
                "nav": state["nav"],
                "at": clock.isoformat(),
                "source": "trusted-feed/internal-paper",
                "source_hash": candidate["source_hash"],
                "dataset_id": candidate["dataset_id"],
                "snapshot_hash": digest(
                    {"dataset": dataset.model_dump(mode="json"), "quote": quote}
                ),
                "origin": "synthetic" if dataset.adjustment == "synthetic" else "alpaca",
                "protocol": "forward-paper-v1",
                "cost_rate": 0.001,
            }
            evidence_id = self.store.append(conn, "live-evidence", evidence)
            if tracked:
                if outcome["status"] in {"FILLED", "NO_TRADE"}:
                    lifecycle.record_observation(conn, evidence_id)
                lifecycle.monitor_in_transaction(conn, candidate_id)
            self.store.audit(conn, "forward.observed", "forward-worker", evidence)
            return evidence
