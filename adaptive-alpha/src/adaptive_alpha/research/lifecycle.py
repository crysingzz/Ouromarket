"""Audited strategy lifecycle and preregistered, internal-paper comparisons.

This service never authorizes capital. Observations enter only through the trusted
forward engine, referencing an already retained live-evidence record. Generated
agents cannot submit scores or modify this frozen evaluation policy.
"""

from __future__ import annotations

import builtins
import math
from datetime import timedelta
from typing import Any

from sqlalchemy.engine import Connection

from adaptive_alpha.domain import digest, new_id, now
from adaptive_alpha.research.datasets import timestamp
from adaptive_alpha.research.performance import PerformanceMonitor
from adaptive_alpha.store import Store

TRANSITIONS = {
    "RESEARCH": {"LAB_VALIDATED", "RETIRED"},
    "LAB_VALIDATED": {"SHADOW", "RETIRED"},
    "SHADOW": {"PAPER", "DEMOTED", "RETIRED"},
    "PAPER": {"CHALLENGER", "DEMOTED", "RETIRED"},
    "CHALLENGER": {"ACTIVE_LIMITED", "DEMOTED", "RETIRED"},
    "ACTIVE_LIMITED": {"DEMOTED"},
    "DEMOTED": {"RESEARCH", "RETIRED"},
    "RETIRED": set(),
}
FORWARD_STATES = {"SHADOW", "PAPER", "CHALLENGER", "ACTIVE_LIMITED"}
POLICY: dict[str, Any] = {
    "version": "paper-challenger-v1",
    "minimum_days": 20,
    "minimum_observations": 20,
    "maximum_calendar_days": 60,
    "minimum_excess_return": 0.001,
    "max_drawdown": 0.10,
    "max_daily_loss": 0.03,
    "forward_protocol": "forward-paper-v1",
    "cost_rate": 0.001,
}


class StrategyLifecycle:
    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _operator(actor: str) -> None:
        if actor != "operator":
            raise ValueError("OPERATOR_REQUIRED")

    def get_in_transaction(self, conn: Connection, candidate_id: str) -> dict[str, Any]:
        state = self.store.state(conn, "lifecycle:" + candidate_id)
        if not state:
            raise KeyError(candidate_id)
        return {**state, "forward_eligible": state["status"] in FORWARD_STATES}

    def get(self, candidate_id: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self.get_in_transaction(conn, candidate_id)

    def list(self) -> list[dict[str, Any]]:
        with self.store.transaction() as conn:
            return [
                self.get_in_transaction(conn, item["candidate_id"])
                for item in self.store.list_records(conn, "lifecycle-registration", 10000)
            ]

    def register(self, candidate_id: str, actor: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self.register_in_transaction(conn, candidate_id, actor)

    def register_in_transaction(
        self, conn: Connection, candidate_id: str, actor: str
    ) -> dict[str, Any]:
        candidate = self.store.get(conn, candidate_id, "candidate")
        if self.store.state(conn, "lifecycle:" + candidate_id):
            return self.get_in_transaction(conn, candidate_id)
        if digest(candidate["source"]) != candidate["source_hash"]:
            raise ValueError("SOURCE_HASH_MISMATCH")
        dataset = self.store.get(conn, candidate["dataset_id"], "dataset")
        state = {
            "candidate_id": candidate_id,
            "name": candidate.get("name", candidate_id),
            "symbol": dataset["data"]["symbol"],
            "dataset_id": candidate["dataset_id"],
            "source_hash": candidate["source_hash"],
            "parent_ids": candidate.get("parent_ids", []),
            "status": "RESEARCH",
            "version": 1,
            "scope": "internal-paper",
            "capital_eligible": False,
            "created_at": now(),
            "updated_at": now(),
        }
        self.store.append(conn, "lifecycle-registration", state)
        self.store.set_state(conn, "lifecycle:" + candidate_id, state)
        self.store.audit(conn, "lifecycle.registered", actor, state)
        return {**state, "forward_eligible": False}

    def _lab(self, conn: Connection, state: dict[str, Any]) -> dict[str, Any]:
        results = self.store.related(conn, "candidate-result", "id", state["candidate_id"])
        valid = [
            r
            for r in results
            if r.get("status") == "PASS"
            and r.get("public", {}).get("verdict") == "PASS"
            and r.get("hidden", {}).get("verdict") == "PASS"
            and r.get("public", {}).get("protocol") == "generated-research-v1"
            and r.get("public", {}).get("grammar") == "signal-python-v1"
            and timestamp(r["at"])
            > timestamp(state.get("validation_after", "1970-01-01T00:00:00Z"))
            and (
                not state.get("validation_after")
                or (
                    r.get("validation_after") == state["validation_after"]
                    and r.get("source_hash") == state["source_hash"]
                    and r.get("dataset_id") == state["dataset_id"]
                )
            )
        ]
        if not valid:
            raise ValueError("INDEPENDENT_VALIDATION_REQUIRED")
        return valid[-1]

    def transition(
        self,
        candidate_id: str,
        target: str,
        actor: str,
        reason: str,
        *,
        expected_version: int | None = None,
        request_id: str | None = None,
        comparison_id: str | None = None,
    ) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self.transition_in_transaction(
                conn,
                candidate_id,
                target,
                actor,
                reason,
                expected_version=expected_version,
                request_id=request_id,
                comparison_id=comparison_id,
            )

    def transition_in_transaction(
        self,
        conn: Connection,
        candidate_id: str,
        target: str,
        actor: str,
        reason: str,
        *,
        expected_version: int | None = None,
        request_id: str | None = None,
        comparison_id: str | None = None,
    ) -> dict[str, Any]:
        self._operator(actor)
        if not reason.strip() or len(reason) > 2000:
            raise ValueError("TRANSITION_REASON_REQUIRED")
        fingerprint = digest(
            {
                "candidate_id": candidate_id,
                "target": target,
                "actor": actor,
                "reason": reason,
                "comparison_id": comparison_id,
                "expected_version": expected_version,
            }
        )
        receipt_key = "lifecycle-request:" + digest(request_id) if request_id else None
        if receipt_key and (receipt := self.store.state(conn, receipt_key)):
            if receipt["fingerprint"] != fingerprint:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            return dict(receipt["result"])
        state = self.get_in_transaction(conn, candidate_id)
        if expected_version is not None and expected_version != state["version"]:
            raise ValueError("LIFECYCLE_VERSION_CONFLICT")
        if target not in TRANSITIONS[state["status"]]:
            raise ValueError("ILLEGAL_LIFECYCLE_TRANSITION")
        proof: dict[str, Any] = {}
        if target in {"LAB_VALIDATED", "SHADOW", "PAPER", "CHALLENGER", "ACTIVE_LIMITED"}:
            proof["lab_result_hash"] = digest(self._lab(conn, state))
        if target == "CHALLENGER":
            observations = self.store.related(
                conn, "lifecycle-observation", "candidate_id", candidate_id
            )
            observations = [
                o
                for o in observations
                if timestamp(o["bar"])
                > timestamp(state.get("validation_after", "1970-01-01T00:00:00Z"))
            ]
            if (
                not observations
                or self.store.state(conn, "forward:" + candidate_id).get("status") != "PAPER"
            ):
                raise ValueError("FORWARD_EVIDENCE_REQUIRED")
        if target == "ACTIVE_LIMITED":
            if self.store.state(conn, "kill", {"halted": True}).get("halted", True):
                raise ValueError("RISK_HALTED")
            if comparison_id is None:
                raise ValueError("MATCHED_COMPARISON_REQUIRED")
            comparison = self._comparison(conn, comparison_id)
            if comparison["challenger_id"] != candidate_id or comparison["verdict"] != "PASS":
                raise ValueError("MATCHED_COMPARISON_REQUIRED")
            if comparison.get("challenger_validation_after") != state.get("validation_after"):
                raise ValueError("STALE_COMPARISON_EPISODE")
            active_key = "active-paper:" + state["symbol"]
            active_id = self.store.state(conn, active_key).get("candidate_id")
            if active_id != comparison["active_id"]:
                raise ValueError("ACTIVE_BASELINE_CHANGED")
            if active_id:
                if comparison.get("active_validation_after") != self.get_in_transaction(
                    conn, active_id
                ).get("validation_after"):
                    raise ValueError("STALE_COMPARISON_EPISODE")
                self._change(
                    conn,
                    self.get_in_transaction(conn, active_id),
                    "DEMOTED",
                    actor,
                    "Replaced by qualified paper challenger",
                    {"replacement_id": candidate_id},
                )
            proof["comparison"] = comparison
            self.store.set_state(
                conn,
                active_key,
                {
                    "candidate_id": candidate_id,
                    "scope": "internal-paper",
                    "capital_eligible": False,
                },
            )
        result = self._change(conn, state, target, actor, reason, proof)
        if receipt_key:
            self.store.set_state(conn, receipt_key, {"fingerprint": fingerprint, "result": result})
        return result

    def _change(
        self,
        conn: Connection,
        state: dict[str, Any],
        target: str,
        actor: str,
        reason: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        candidate_id = state["candidate_id"]
        event = {
            "id": new_id(),
            "candidate_id": candidate_id,
            "from": state["status"],
            "to": target,
            "version": state["version"] + 1,
            "reason": reason,
            "actor": actor,
            "at": now(),
            "source_hash": state["source_hash"],
            "dataset_id": state["dataset_id"],
            "parent_ids": state["parent_ids"],
            "evidence": evidence,
            "scope": "internal-paper",
            "capital_eligible": False,
        }
        state.update(
            status=target,
            version=event["version"],
            updated_at=event["at"],
            last_transition_id=event["id"],
            forward_eligible=target in FORWARD_STATES,
        )
        if target in {"DEMOTED", "RETIRED"}:
            state["validation_after"] = event["at"]
            active_key = "active-paper:" + state["symbol"]
            if self.store.state(conn, active_key).get("candidate_id") == candidate_id:
                self.store.set_state(
                    conn,
                    active_key,
                    {"candidate_id": None, "scope": "internal-paper", "capital_eligible": False},
                )
            forward = self.store.state(conn, "forward:" + candidate_id)
            if forward:
                forward.update(status="HALTED", halt_reason=reason)
                self.store.set_state(conn, "forward:" + candidate_id, forward)
        self.store.append(conn, "lifecycle-transition", event, event["id"])
        if target == "ACTIVE_LIMITED":
            PerformanceMonitor(self.store).start(conn, event)
        self.store.set_state(conn, "lifecycle:" + candidate_id, state)
        self.store.audit(conn, "lifecycle.transitioned", actor, event)
        return state

    def register_comparison(
        self, active_id: str | None, challenger_id: str, actor: str
    ) -> dict[str, Any]:
        self._operator(actor)
        with self.store.transaction() as conn:
            challenger = self.get_in_transaction(conn, challenger_id)
            if challenger["status"] not in {"SHADOW", "PAPER", "CHALLENGER"}:
                raise ValueError("COMPARISON_STAGE_REQUIRED")
            if (
                self.store.state(conn, "active-paper:" + challenger["symbol"]).get("candidate_id")
                != active_id
            ):
                raise ValueError("ACTIVE_BASELINE_CHANGED")
            self._lab(conn, challenger)
            active = self.get_in_transaction(conn, active_id) if active_id else None
            if active and (
                active["dataset_id"] != challenger["dataset_id"]
                or active["status"] != "ACTIVE_LIMITED"
            ):
                raise ValueError("INCOMPARABLE_BASELINE")
            dataset = self.store.get(conn, challenger["dataset_id"], "dataset")
            item = {
                "id": new_id(),
                "active_id": active_id,
                "challenger_id": challenger_id,
                "symbol": challenger["symbol"],
                "dataset_id": challenger["dataset_id"],
                "dataset_hash": digest(dataset["data"]),
                "registered_at": now(),
                "challenger_source_hash": challenger["source_hash"],
                "active_source_hash": active["source_hash"] if active else "cash-zero-return",
                "challenger_validation_after": challenger.get("validation_after"),
                "active_validation_after": active.get("validation_after") if active else None,
                "lab_protocol": "generated-research-v1",
                "runtime": "signal-python-v1",
                "baseline": "active-paper" if active else "cash-zero-return",
                "policy": dict(POLICY),
                "policy_hash": digest(POLICY),
                "scope": "internal-paper",
                "capital_eligible": False,
            }
            self.store.append(conn, "lifecycle-comparison", item, item["id"])
            self.store.audit(conn, "lifecycle.comparison_registered", actor, item)
            return {**item, "verdict": "PENDING", "matched_days": 0}

    def record_observation(self, conn: Connection, evidence_id: str) -> dict[str, Any] | None:
        """Internal forward-worker hook; never expose this method as a write API."""
        evidence = self.store.get(conn, evidence_id, "live-evidence")
        candidate_id = evidence["candidate_id"]
        if not self.store.state(conn, "lifecycle:" + candidate_id):
            return None
        identity = "lifecycle-observation-" + digest(evidence_id)
        try:
            return self.store.get(conn, identity, "lifecycle-observation")
        except KeyError:
            pass
        state = self.get_in_transaction(conn, candidate_id)
        if not state["forward_eligible"]:
            raise ValueError("FORWARD_ADMISSION_REQUIRED")
        nav = float(evidence.get("nav", float("nan")))
        if (
            evidence.get("source") != "trusted-feed/internal-paper"
            or evidence.get("source_hash") != state["source_hash"]
            or evidence.get("dataset_id") != state["dataset_id"]
            or evidence.get("protocol") != POLICY["forward_protocol"]
            or evidence.get("cost_rate") != POLICY["cost_rate"]
            or evidence.get("origin") not in {"alpaca", "synthetic"}
            or not evidence.get("snapshot_hash")
            or evidence.get("status") not in {"FILLED", "NO_TRADE"}
            or not math.isfinite(nav)
            or nav <= 0
        ):
            raise ValueError("UNTRUSTED_FORWARD_EVIDENCE")
        bar = timestamp(evidence["bar"])
        observed = timestamp(evidence["at"])
        if bar > observed:
            raise ValueError("FUTURE_FORWARD_EVIDENCE")
        item = {
            "id": identity,
            "candidate_id": candidate_id,
            "evidence_id": evidence_id,
            "evidence_hash": digest(evidence),
            "source_hash": state["source_hash"],
            "dataset_id": state["dataset_id"],
            "nav": nav,
            "bar": evidence["bar"],
            "day": bar.date().isoformat(),
            "observed_at": evidence["at"],
            "recorded_at": now(),
            "snapshot_hash": evidence["snapshot_hash"],
            "origin": evidence["origin"],
            "protocol": evidence["protocol"],
            "cost_rate": evidence["cost_rate"],
            "capital_eligible": False,
        }
        self.store.append(conn, "lifecycle-observation", item, identity)
        if state["status"] == "ACTIVE_LIMITED":
            PerformanceMonitor(self.store).observe(conn, identity)
        return item

    def list_comparisons(self) -> builtins.list[dict[str, Any]]:
        with self.store.transaction() as conn:
            return [
                self._comparison(conn, r["id"])
                for r in self.store.list_records(conn, "lifecycle-comparison", 1000)
            ]

    def comparison(self, identity: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self._comparison(conn, identity)

    def _comparison(self, conn: Connection, identity: str) -> dict[str, Any]:
        item = self.store.get(conn, identity, "lifecycle-comparison")
        start = timestamp(item["registered_at"])
        deadline = start + timedelta(days=item["policy"]["maximum_calendar_days"])

        def observations(
            candidate_id: str, source_hash: str
        ) -> dict[tuple[str, str, str], dict[str, Any]]:
            return {
                (r["day"], r["snapshot_hash"], r["origin"]): r
                for r in self.store.related(
                    conn, "lifecycle-observation", "candidate_id", candidate_id
                )
                if timestamp(r["recorded_at"]) > start
                and timestamp(r["bar"]) > start
                and timestamp(r["bar"]) <= deadline
                and timestamp(r["observed_at"]) > start
                and r["source_hash"] == source_hash
                and r["dataset_id"] == item["dataset_id"]
                and r["protocol"] == item["policy"]["forward_protocol"]
                and r["cost_rate"] == item["policy"]["cost_rate"]
            }

        challenger = observations(item["challenger_id"], item["challenger_source_hash"])
        active = (
            observations(item["active_id"], item["active_source_hash"])
            if item["active_id"]
            else challenger
        )
        daily: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for key in sorted(
            challenger.keys() & active.keys(), key=lambda key: challenger[key]["observed_at"]
        ):
            daily.setdefault(key[0], (challenger[key], active[key]))
        required = max(item["policy"]["minimum_days"], item["policy"]["minimum_observations"])
        # Freeze the first required matched days: additional runs cannot rescue a
        # failed experiment by choosing a more favourable observation window.
        pairs = [daily[day] for day in sorted(daily)[:required]]
        origins = {pair[0]["origin"] for pair in pairs}
        result = {
            **item,
            "matched_days": len(pairs),
            "verdict": "PENDING",
            "origin": next(iter(origins)) if len(origins) == 1 else "mixed-or-unobserved",
        }
        if len(pairs) < required:
            result["verdict"] = "EXPIRED" if timestamp(now()) > deadline else "PENDING"
            return result
        challenger_nav = [pair[0]["nav"] for pair in pairs]
        active_nav = [pair[1]["nav"] for pair in pairs] if item["active_id"] else [1.0] * len(pairs)
        gain = challenger_nav[-1] / challenger_nav[0] - 1
        baseline_gain = active_nav[-1] / active_nav[0] - 1
        peak, drawdown = challenger_nav[0], 0.0
        for value in challenger_nav:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        daily_loss = max(
            0.0,
            max(1 - b / a for a, b in zip(challenger_nav[:-1], challenger_nav[1:], strict=True)),
        )
        gates = {
            "positive_net_return": gain > 0,
            "excess_return": gain - baseline_gain >= item["policy"]["minimum_excess_return"],
            "drawdown": drawdown <= item["policy"]["max_drawdown"],
            "daily_loss": daily_loss <= item["policy"]["max_daily_loss"],
            "consistent_origin": len(origins) == 1,
        }
        return {
            **result,
            "verdict": "PASS" if all(gates.values()) else "FAIL",
            "gates": gates,
            "net_return": gain,
            "baseline_return": baseline_gain,
            "max_drawdown": drawdown,
            "max_daily_loss": daily_loss,
            "evidence_ids": [
                [a["evidence_id"], b["evidence_id"] if item["active_id"] else None]
                for a, b in pairs
            ],
            "window_start": pairs[0][0]["bar"],
            "window_end": pairs[-1][0]["bar"],
        }

    def monitor(self, candidate_id: str, actor: str = "risk") -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self.monitor_in_transaction(conn, candidate_id, actor)

    def monitor_in_transaction(
        self, conn: Connection, candidate_id: str, actor: str = "risk"
    ) -> dict[str, Any]:
        if actor not in {"risk", "operator", "forward-worker"}:
            raise ValueError("MONITOR_AUTHORITY_REQUIRED")
        state = self.get_in_transaction(conn, candidate_id)
        if not state["forward_eligible"]:
            return state
        forward = self.store.state(conn, "forward:" + candidate_id)
        breach = None
        if self.store.state(conn, "kill").get("halted"):
            breach = "GLOBAL_RISK_HALT"
        elif forward.get("status") == "HALTED":
            breach = "FORWARD_RISK_HALT"
        elif forward:
            nav = float(forward["nav"] if "nav" in forward else forward["cash"])
            peak = float(forward["high_watermark"])
            day_start = float(forward["day_start_nav"])
            if not all(math.isfinite(n) and n > 0 for n in (nav, peak, day_start)):
                breach = "INVALID_ACCOUNT_STATE"
            elif 1 - nav / peak > POLICY["max_drawdown"]:
                breach = "DRAWDOWN_LIMIT"
            elif 1 - nav / day_start > POLICY["max_daily_loss"]:
                breach = "DAILY_LOSS_LIMIT"
        performance = self.store.state(conn, "performance:" + candidate_id)
        if (
            not breach
            and state["status"] == "ACTIVE_LIMITED"
            and performance.get("status") == "HALT"
        ):
            breach = "SUSTAINED_NET_DEGRADATION"
        if breach:
            return self._change(
                conn,
                state,
                "DEMOTED",
                actor,
                breach,
                {
                    "policy_hash": digest(POLICY),
                    "forward_state_hash": digest(forward),
                    "performance_report_id": performance.get("last_report_id"),
                },
            )
        return state

    def select_rollback(self, symbol: str, actor: str) -> dict[str, Any]:
        self._operator(actor)
        with self.store.transaction() as conn:
            candidates = [
                self.get_in_transaction(conn, r["candidate_id"])
                for r in self.store.list_records(conn, "lifecycle-registration", 10000)
            ]
            eligible = [r for r in candidates if r["symbol"] == symbol and r["status"] == "DEMOTED"]
            promoted = {
                r["candidate_id"]
                for r in self.store.list_records(conn, "lifecycle-transition", 10000)
                if r["to"] == "ACTIVE_LIMITED"
            }
            choices = sorted(
                [r for r in eligible if r["candidate_id"] in promoted],
                key=lambda r: r["updated_at"],
                reverse=True,
            )
            report = {
                "symbol": symbol,
                "candidate_id": choices[0]["candidate_id"] if choices else None,
                "candidates": [r["candidate_id"] for r in choices],
                "revalidation_required": True,
                "automatic_activation": False,
                "capital_eligible": False,
            }
            self.store.audit(conn, "lifecycle.rollback_selected", actor, report)
            return report
