"""Atomic risk → internal PaperBroker fill → positions → audit. No real broker route exists."""

from typing import Any

import polars as pl

from adaptive_alpha.data import SYMBOLS, synthetic_daily
from adaptive_alpha.domain import OrderIntent, digest, now
from adaptive_alpha.risk.engine import assess
from adaptive_alpha.store import Store


class Execution:
    def __init__(self, store: Store):
        self.store = store
        self.frame = synthetic_daily(42)
        self.returns = {}
        for symbol in SYMBOLS:
            prices = self.frame.filter(pl.col("symbol") == symbol)["close"].to_numpy()
            self.returns[symbol] = list(prices[1:] / prices[:-1] - 1)

    def initialize(self) -> None:
        with self.store.transaction() as conn:
            if not self.store.state(conn, "account"):
                account = {
                    "cash": 100_000.0,
                    "positions": {},
                    "high_watermark": 100_000.0,
                    "day_start_nav": 100_000.0,
                }
                self.store.set_state(conn, "account", account)
                self.store.set_state(conn, "broker", {"cash": 100_000.0, "positions": {}})
                self.store.set_state(
                    conn, "kill", {"halted": False, "reason": "", "timestamp": now()}
                )
                self.store.audit(
                    conn, "paper.initialized", "system", {"nav": 100_000, "mode": "synthetic-demo"}
                )
        self.refresh_quotes("system")

    def refresh_quotes(self, actor: str) -> dict[str, Any]:
        prices = {
            symbol: round(float(self.frame.filter(pl.col("symbol") == symbol)["close"][-1]), 2)
            for symbol in SYMBOLS
        }
        quotes = {"prices": prices, "timestamp": now(), "source": "synthetic-demo-fixed-snapshot"}
        with self.store.transaction() as conn:
            self.store.set_state(conn, "quotes", quotes)
            self.store.audit(
                conn, "market.demo_snapshot_refreshed", actor, {"source": quotes["source"]}
            )
        return quotes

    @staticmethod
    def reconciled(account: dict[str, Any], broker: dict[str, Any]) -> bool:
        return (
            account.get("positions") == broker.get("positions")
            and abs(account.get("cash", 0) - broker.get("cash", -1)) < 0.00001
        )

    def portfolio(self) -> dict[str, Any]:
        with self.store.transaction() as conn:
            account = self.store.state(conn, "account")
            quotes = self.store.state(conn, "quotes")
            broker = self.store.state(conn, "broker")
            nav = account["cash"] + sum(
                q * quotes["prices"][s] for s, q in account["positions"].items()
            )
            return {
                **account,
                "nav": nav,
                "pnl": nav - 100_000,
                "gross_exposure": sum(
                    abs(q * quotes["prices"][s]) for s, q in account["positions"].items()
                )
                / nav
                if nav > 0
                else None,
                "quotes": quotes,
                "reconciled": self.reconciled(account, broker),
                "mode": "demo-paper",
            }

    def check(self, intent: OrderIntent, submit: bool, actor: str) -> dict[str, Any]:
        # Single database mutex serializes check/fill/kill across server processes.
        # Real broker I/O requires an outbox and signed, expiring approvals; not enabled here.
        with self.store.transaction() as conn:
            fingerprint = digest(intent.model_dump())
            if submit:
                existing = self.store.state(conn, f"order:{intent.order_intent_id}")
                if existing:
                    if existing["fingerprint"] != fingerprint:
                        raise ValueError("IDEMPOTENCY_CONFLICT")
                    return dict(existing["result"])
            spec = self.store.get(conn, intent.strategy_id, "strategy")
            if intent.instrument not in spec["universe"]:
                raise ValueError("INSTRUMENT_OUTSIDE_STRATEGY_UNIVERSE")
            strategy_state = self.store.state(conn, f"strategy:{intent.strategy_id}")
            if strategy_state.get("status") != "PAPER":
                raise ValueError("STRATEGY_NOT_IN_PAPER")
            account = self.store.state(conn, "account")
            broker = self.store.state(conn, "broker")
            quotes = self.store.state(conn, "quotes")
            kill = self.store.state(conn, "kill")
            owned = self.store.state(conn, f"holdings:{intent.strategy_id}")
            decision = assess(
                intent,
                account,
                quotes,
                self.returns,
                owned,
                halted=kill.get("halted", True),
                reconciled=self.reconciled(account, broker),
            )
            result: dict[str, Any] = {
                "id": intent.order_intent_id,
                "intent": intent.model_dump(),
                "decision": decision,
                "timestamp": now(),
                "status": "REJECTED",
                "mode": "demo-paper",
            }
            if not submit:
                return result
            if decision["status"] == "HALT":
                self.store.set_state(
                    conn,
                    "kill",
                    {
                        "halted": True,
                        "reason": "Critical pretrade check failed",
                        "timestamp": now(),
                    },
                )
            if decision["status"] == "APPROVE":
                price = quotes["prices"][intent.instrument]
                signed = intent.quantity if intent.side == "BUY" else -intent.quantity
                cost = round(intent.quantity * price * 0.001, 4)
                account["cash"] = round(account["cash"] - signed * price - cost, 4)
                account["positions"][intent.instrument] = (
                    account["positions"].get(intent.instrument, 0) + signed
                )
                owned[intent.instrument] = owned.get(intent.instrument, 0) + signed
                nav = account["cash"] + sum(
                    q * quotes["prices"][s] for s, q in account["positions"].items()
                )
                account["high_watermark"] = max(nav, account["high_watermark"])
                self.store.set_state(conn, "account", account)
                self.store.set_state(
                    conn, "broker", {"cash": account["cash"], "positions": account["positions"]}
                )
                self.store.set_state(conn, f"holdings:{intent.strategy_id}", owned)
                result.update(
                    status="FILLED",
                    fill_price=price,
                    costs=cost,
                    approved_quantity=decision["approved_quantity"],
                )
                self.store.append(conn, "fill", result)
            self.store.append(conn, "order", result, intent.order_intent_id)
            self.store.set_state(
                conn,
                f"order:{intent.order_intent_id}",
                {"fingerprint": fingerprint, "result": result},
            )
            self.store.audit(
                conn,
                f"risk.{decision['status'].lower()}",
                actor,
                {"order_id": intent.order_intent_id, "decision": decision},
            )
            self.store.audit(conn, "execution." + result["status"].lower(), actor, result)
            return result

    def kill(self, halted: bool, reason: str, actor: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            if not halted and not self.reconciled(
                self.store.state(conn, "account"), self.store.state(conn, "broker")
            ):
                raise ValueError("RECONCILIATION_REQUIRED")
            state = {"halted": halted, "reason": reason, "timestamp": now()}
            self.store.set_state(conn, "kill", state)
            self.store.audit(conn, "risk.halt" if halted else "risk.resumed", actor, state)
            return state
