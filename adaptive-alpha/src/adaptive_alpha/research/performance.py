"""Frozen empirical performance monitoring for internal paper champions only.

The qualification return is a reference, not a forecast or a statistical alpha
estimate. Two disjoint loss windows trigger a simulation stop, never a trade.
Only lifecycle's retained-observation hook writes measurements.
"""

from typing import Any

from sqlalchemy.engine import Connection

from adaptive_alpha.domain import digest, now
from adaptive_alpha.research.datasets import timestamp
from adaptive_alpha.store import Store

PERFORMANCE_POLICY: dict[str, Any] = {
    "version": "paper-performance-v1",
    "returns_per_window": 10,
    "maximum_calendar_days": 21,
    "loss_threshold": 0.005,
    "reference_shortfall": 0.01,
    "consecutive_breaches": 2,
    "daily_sample": "first-retained-observation",
}


class PerformanceMonitor:
    def __init__(self, store: Store):
        self.store = store

    def start(self, conn: Connection, transition: dict[str, Any]) -> None:
        comparison = transition["evidence"]["comparison"]
        candidate_id = transition["candidate_id"]
        admission = {
            "id": "performance-" + transition["id"],
            "candidate_id": candidate_id,
            "transition_id": transition["id"],
            "activated_at": transition["at"],
            "source_hash": transition["source_hash"],
            "dataset_id": transition["dataset_id"],
            "comparison_hash": digest(comparison),
            "origin": comparison["origin"],
            "forward_protocol": comparison["policy"]["forward_protocol"],
            "cost_rate": comparison["policy"]["cost_rate"],
            "reference_window_return": (1 + comparison["net_return"])
            ** (PERFORMANCE_POLICY["returns_per_window"] / (comparison["matched_days"] - 1))
            - 1,
            "policy": dict(PERFORMANCE_POLICY),
            "policy_hash": digest(PERFORMANCE_POLICY),
            "scope": "internal-paper",
            "capital_eligible": False,
        }
        self.store.append(conn, "performance-admission", admission, admission["id"])
        self.store.set_state(
            conn,
            "performance:" + candidate_id,
            {
                "admission_id": admission["id"],
                "status": "WARMUP",
                "window": 1,
                "consecutive_breaches": 0,
                "samples": [],
                "last_day": None,
                "last_report_id": None,
            },
        )
        self.store.audit(conn, "performance.registered", "risk", admission)

    def observe(self, conn: Connection, observation_id: str) -> None:
        observation = self.store.get(conn, observation_id, "lifecycle-observation")
        candidate_id = observation["candidate_id"]
        key = "performance:" + candidate_id
        state = self.store.state(conn, key)
        if not state or state["status"] == "HALT":
            return
        admission = self.store.get(conn, state["admission_id"], "performance-admission")
        start = timestamp(admission["activated_at"])
        if (
            timestamp(observation["bar"]) <= start
            or timestamp(observation["observed_at"]) <= start
            or timestamp(observation["recorded_at"]) <= start
            or (state["last_day"] and observation["day"] <= state["last_day"])
        ):
            return
        # Each day's first retained sample is sealed. Retries, intraday updates
        # and late historical arrivals cannot rewrite a completed window.
        state["samples"].append(observation_id)
        state["last_day"] = observation["day"]
        policy = admission["policy"]
        if len(state["samples"]) == policy["returns_per_window"] + 1:
            samples = [self.store.get(conn, i, "lifecycle-observation") for i in state["samples"]]
            comparable = (
                all(
                    r["origin"] == admission["origin"]
                    and r["source_hash"] == admission["source_hash"]
                    and r["dataset_id"] == admission["dataset_id"]
                    and r["protocol"] == admission["forward_protocol"]
                    and r["cost_rate"] == admission["cost_rate"]
                    for r in samples
                )
                and (
                    timestamp(samples[-1]["bar"]).date() - timestamp(samples[0]["bar"]).date()
                ).days
                <= policy["maximum_calendar_days"]
            )
            net_return = samples[-1]["nav"] / samples[0]["nav"] - 1
            shortfall = admission["reference_window_return"] - net_return
            breach = (
                comparable
                and net_return <= -policy["loss_threshold"]
                and shortfall >= policy["reference_shortfall"]
            )
            state["consecutive_breaches"] = state["consecutive_breaches"] + 1 if breach else 0
            status = (
                "HALT"
                if state["consecutive_breaches"] >= policy["consecutive_breaches"]
                else "WARNING"
                if breach
                else "HEALTHY"
                if comparable
                else "INCONCLUSIVE"
            )
            report = {
                "id": "performance-report-" + digest([admission["id"], state["window"]]),
                "candidate_id": candidate_id,
                "admission_id": admission["id"],
                "admission_hash": digest(admission),
                "window": state["window"],
                "window_start": samples[0]["bar"],
                "window_end": samples[-1]["bar"],
                "observation_ids": list(state["samples"]),
                "evidence_ids": [r["evidence_id"] for r in samples],
                "samples_hash": digest(samples),
                "net_return": net_return,
                "reference_window_return": admission["reference_window_return"],
                "shortfall": shortfall,
                "comparable": comparable,
                "consecutive_breaches": state["consecutive_breaches"],
                "status": status,
                "at": now(),
                "scope": "internal-paper",
                "capital_eligible": False,
            }
            self.store.append(conn, "performance-report", report, report["id"])
            self.store.audit(conn, "performance.evaluated", "risk", report)
            state.update(
                status=status,
                last_report_id=report["id"],
                window=state["window"] + 1,
                samples=[observation_id],
            )
        self.store.set_state(conn, key, state)

    def report(self, candidate_id: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            lifecycle = self.store.state(conn, "lifecycle:" + candidate_id)
            if not lifecycle:
                raise KeyError(candidate_id)
            state = self.store.state(conn, "performance:" + candidate_id)
            return {
                "candidate_id": candidate_id,
                "monitor": state or {"status": "NOT_ACTIVATED"},
                "admission": self.store.get(conn, state["admission_id"], "performance-admission")
                if state
                else None,
                "reports": self.store.related(
                    conn, "performance-report", "candidate_id", candidate_id
                ),
                "lifecycle_status": lifecycle["status"],
                "scope": "internal-paper",
                "capital_eligible": False,
            }
