"""Lifecycle authorization, immutable evidence and actual matched paper observations."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from adaptive_alpha.domain import digest
from adaptive_alpha.research import lifecycle as module
from adaptive_alpha.research.lifecycle import StrategyLifecycle
from adaptive_alpha.store import Store


class Laboratory:
    def __init__(self, path: Path, monkeypatch: pytest.MonkeyPatch):
        self.clock = datetime(2026, 1, 1, tzinfo=UTC)
        monkeypatch.setattr(module, "now", lambda: self.clock.isoformat())
        self.store = Store(f"sqlite:///{path}/lifecycle.db")
        self.store.initialize()
        self.service = StrategyLifecycle(self.store)
        with self.store.transaction() as conn:
            self.store.set_state(conn, "kill", {"halted": False})

    def advance(self, days: int = 1) -> None:
        self.clock += timedelta(days=days)

    def candidate(self, identity: str = "a", dataset_id: str = "data", **changes: Any) -> str:
        source = f"def signal(prices):\n    return 0.05  # {identity}\n"
        with self.store.transaction() as conn:
            try:
                self.store.get(conn, dataset_id, "dataset")
            except KeyError:
                self.store.append(
                    conn,
                    "dataset",
                    {"data": {"symbol": "SPY", "adjustment": "synthetic"}},
                    dataset_id,
                )
            self.store.append(
                conn,
                "candidate",
                {
                    "id": identity,
                    "name": identity,
                    "source": source,
                    "source_hash": digest(source),
                    "dataset_id": dataset_id,
                    "parent_ids": ["parent"],
                    **changes,
                },
                identity,
            )
        return identity

    def validate(self, identity: str, **changes: Any) -> None:
        with self.store.transaction() as conn:
            self.store.append(
                conn,
                "candidate-result",
                {
                    "id": identity,
                    "status": "PASS",
                    "validation_after": self.store.state(conn, "lifecycle:" + identity).get(
                        "validation_after"
                    ),
                    "source_hash": self.store.get(conn, identity, "candidate")["source_hash"],
                    "dataset_id": self.store.get(conn, identity, "candidate")["dataset_id"],
                    "hidden": {"verdict": "PASS"},
                    "public": {
                        "verdict": "PASS",
                        "grammar": "signal-python-v1",
                        "protocol": "generated-research-v1",
                    },
                    "at": self.clock.isoformat(),
                    **changes,
                },
            )

    def paper(self, identity: str = "a", dataset_id: str = "data") -> str:
        self.candidate(identity, dataset_id)
        self.validate(identity)
        self.service.register(identity, "worker")
        for target in ["LAB_VALIDATED", "SHADOW", "PAPER"]:
            self.service.transition(identity, target, "operator", "Verified laboratory evidence")
        with self.store.transaction() as conn:
            self.store.set_state(
                conn,
                "forward:" + identity,
                {
                    "status": "PAPER",
                    "cash": 100000.0,
                    "nav": 100000.0,
                    "high_watermark": 100000.0,
                    "day_start_nav": 100000.0,
                    "capital_eligible": False,
                },
            )
        return identity

    def evidence(self, identity: str, nav: float = 100000, **changes: Any) -> str:
        with self.store.transaction() as conn:
            candidate = self.store.get(conn, identity, "candidate")
            evidence_id = self.store.append(
                conn,
                "live-evidence",
                {
                    "candidate_id": identity,
                    "status": "NO_TRADE",
                    "nav": nav,
                    "bar": (self.clock - timedelta(minutes=1)).isoformat(),
                    "at": self.clock.isoformat(),
                    "snapshot_hash": digest(self.clock.isoformat()),
                    "source": "trusted-feed/internal-paper",
                    "source_hash": candidate["source_hash"],
                    "dataset_id": candidate["dataset_id"],
                    "origin": "synthetic",
                    "protocol": "forward-paper-v1",
                    "cost_rate": 0.001,
                    **changes,
                },
            )
            return evidence_id

    def observe(self, identity: str, nav: float = 100000, **changes: Any) -> dict[str, Any] | None:
        evidence_id = self.evidence(identity, nav, **changes)
        with self.store.transaction() as conn:
            return self.service.record_observation(conn, evidence_id)

    def window(self, challenger: str, active: str | None = None, *, falling: bool = False) -> None:
        for day in range(20):
            self.advance()
            self.observe(challenger, 100000 * (1 + (-0.002 if falling else 0.002) * day))
            if active:
                self.observe(active, 100000 * (1 + 0.0001 * day))

    def activate(self, identity: str, active: str | None = None) -> dict[str, Any]:
        comparison = self.service.register_comparison(active, identity, "operator")
        self.window(identity, active)
        self.service.transition(identity, "CHALLENGER", "operator", "Trusted forward observation")
        return self.service.transition(
            identity,
            "ACTIVE_LIMITED",
            "operator",
            "Matched paper promotion",
            comparison_id=comparison["id"],
        )


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Laboratory:
    return Laboratory(tmp_path, monkeypatch)


def test_registration_lineage_and_authorized_versioned_transitions(lab: Laboratory) -> None:
    service = lab.service
    with pytest.raises(KeyError):
        service.get("missing")
    lab.candidate()
    first = service.register("a", "worker")
    assert service.register("a", "worker") == first
    assert first["parent_ids"] == ["parent"] and not first["capital_eligible"]
    assert service.list() == [first]
    for actor, reason, target, error in [
        ("ouroboros", "lab proof", "LAB_VALIDATED", "OPERATOR_REQUIRED"),
        ("operator", " ", "LAB_VALIDATED", "TRANSITION_REASON_REQUIRED"),
        ("operator", "proof", "ACTIVE_LIMITED", "ILLEGAL_LIFECYCLE_TRANSITION"),
        ("operator", "proof", "LAB_VALIDATED", "INDEPENDENT_VALIDATION_REQUIRED"),
    ]:
        with pytest.raises(ValueError, match=error):
            service.transition("a", target, actor, reason)
    lab.validate("a", hidden={"verdict": "FAIL"})
    with pytest.raises(ValueError, match="INDEPENDENT_VALIDATION_REQUIRED"):
        service.transition("a", "LAB_VALIDATED", "operator", "cannot trust public result")
    lab.validate("a")
    with pytest.raises(ValueError, match="LIFECYCLE_VERSION_CONFLICT"):
        service.transition("a", "LAB_VALIDATED", "operator", "proof", expected_version=99)
    result = service.transition(
        "a", "LAB_VALIDATED", "operator", "proof", expected_version=1, request_id="same"
    )
    assert (
        service.transition(
            "a", "LAB_VALIDATED", "operator", "proof", expected_version=1, request_id="same"
        )
        == result
    )
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        service.transition("a", "RETIRED", "operator", "proof", request_id="same")
    service.transition("a", "RETIRED", "operator", "finished")
    with lab.store.transaction() as conn:
        candidate = lab.store.get(conn, "a", "candidate")
        assert candidate["parent_ids"] == ["parent"]
        assert lab.store.verify_audit(conn)
        assert len(lab.store.related(conn, "lifecycle-transition", "candidate_id", "a")) == 2
    lab.candidate("corrupt", source_hash="wrong")
    with pytest.raises(ValueError, match="SOURCE_HASH_MISMATCH"):
        service.register("corrupt", "worker")


def test_cash_bootstrap_then_atomic_champion_switch_and_rollback(lab: Laboratory) -> None:
    lab.paper("first")
    first = lab.activate("first")
    assert first["status"] == "ACTIVE_LIMITED"
    assert first["scope"] == "internal-paper" and not first["capital_eligible"]
    lab.paper("next")
    replacement = lab.activate("next", "first")
    assert replacement["status"] == "ACTIVE_LIMITED"
    assert lab.service.get("first")["status"] == "DEMOTED"
    with lab.store.transaction() as conn:
        assert lab.store.state(conn, "forward:first")["status"] == "HALTED"
        assert lab.store.state(conn, "active-paper:SPY")["candidate_id"] == "next"
        assert lab.store.verify_audit(conn)
    comparisons = lab.service.list_comparisons()
    assert all(c["verdict"] == "PASS" and c["origin"] == "synthetic" for c in comparisons)
    rollback = lab.service.select_rollback("SPY", "operator")
    assert rollback["candidate_id"] == "first" and rollback["revalidation_required"]
    assert not rollback["automatic_activation"]
    assert lab.service.select_rollback("QQQ", "operator")["candidate_id"] is None
    lab.service.transition("first", "RESEARCH", "operator", "Request renewed validation")
    with pytest.raises(ValueError, match="INDEPENDENT_VALIDATION_REQUIRED"):
        lab.service.transition("first", "LAB_VALIDATED", "operator", "Old proof is insufficient")
    lab.advance()
    lab.validate("first")
    assert (
        lab.service.transition("first", "LAB_VALIDATED", "operator", "Renewed independent proof")[
            "status"
        ]
        == "LAB_VALIDATED"
    )


def test_comparison_preregistration_stage_and_dataset_binding(lab: Laboratory) -> None:
    lab.candidate()
    lab.service.register("a", "worker")
    with pytest.raises(ValueError, match="COMPARISON_STAGE_REQUIRED"):
        lab.service.register_comparison(None, "a", "operator")
    lab.paper("b")
    with pytest.raises(ValueError, match="ACTIVE_BASELINE_CHANGED"):
        lab.service.register_comparison("a", "b", "operator")
    with pytest.raises(ValueError, match="FORWARD_EVIDENCE_REQUIRED"):
        lab.service.transition("b", "CHALLENGER", "operator", "No forward evidence")
    lab.observe("b")
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "forward:b", {"status": "HALTED"})
    with pytest.raises(ValueError, match="FORWARD_EVIDENCE_REQUIRED"):
        lab.service.transition("b", "CHALLENGER", "operator", "Simulation is stopped")
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "active-paper:SPY", {"candidate_id": "b"})
    lab.paper("other-data", "unmatched")
    with pytest.raises(ValueError, match="INCOMPARABLE_BASELINE"):
        lab.service.register_comparison("b", "other-data", "operator")


def test_promotion_requires_real_comparison_and_current_active_pointer(lab: Laboratory) -> None:
    lab.paper()
    comparison = lab.service.register_comparison(None, "a", "operator")
    lab.observe("a")
    lab.service.transition("a", "CHALLENGER", "operator", "Observed")
    for comparison_id in (None, comparison["id"]):
        with pytest.raises(ValueError, match="MATCHED_COMPARISON_REQUIRED"):
            lab.service.transition(
                "a",
                "ACTIVE_LIMITED",
                "operator",
                "No completed comparison",
                comparison_id=comparison_id,
            )
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "kill", {"halted": True})
    with pytest.raises(ValueError, match="RISK_HALTED"):
        lab.service.transition(
            "a", "ACTIVE_LIMITED", "operator", "Risk gate", comparison_id=comparison["id"]
        )
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "kill", {"halted": False})
    lab.window("a")
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "active-paper:SPY", {"candidate_id": "changed"})
    with pytest.raises(ValueError, match="ACTIVE_BASELINE_CHANGED"):
        lab.service.transition(
            "a", "ACTIVE_LIMITED", "operator", "Stale baseline", comparison_id=comparison["id"]
        )
    assert lab.service.get("a")["status"] == "CHALLENGER"


@pytest.mark.parametrize(
    "change",
    [
        {"source": "model"},
        {"source_hash": "wrong"},
        {"dataset_id": "wrong"},
        {"protocol": "unknown"},
        {"cost_rate": 0},
        {"origin": "unverified"},
        {"snapshot_hash": ""},
        {"status": "REJECTED"},
        {"nav": 0},
    ],
)
def test_untrusted_or_unbound_observations_are_rejected(
    lab: Laboratory, change: dict[str, Any]
) -> None:
    lab.paper()
    with pytest.raises(ValueError, match="UNTRUSTED_FORWARD_EVIDENCE"):
        lab.observe("a", **change)


def test_observation_receipt_idempotency_legacy_and_future_rejection(lab: Laboratory) -> None:
    lab.candidate("legacy")
    assert lab.observe("legacy") is None
    lab.paper()
    evidence_id = lab.evidence("a")
    with lab.store.transaction() as conn:
        first = lab.service.record_observation(conn, evidence_id)
        assert lab.service.record_observation(conn, evidence_id) == first
    with pytest.raises(ValueError, match="FUTURE_FORWARD_EVIDENCE"):
        lab.observe("a", bar=(lab.clock + timedelta(days=1)).isoformat())
    lab.service.transition("a", "DEMOTED", "operator", "Operator stopped simulation")
    with pytest.raises(ValueError, match="FORWARD_ADMISSION_REQUIRED"):
        lab.observe("a")


def test_fixed_window_rejects_repeated_days_historical_replay_and_cherry_picking(
    lab: Laboratory,
) -> None:
    lab.paper()
    lab.observe("a")
    comparison = lab.service.register_comparison(None, "a", "operator")
    lab.advance()
    for _ in range(25):
        lab.observe("a")
    assert lab.service.comparison(comparison["id"])["matched_days"] == 1
    lab.observe("a", bar="2025-12-25T00:00:00Z")
    assert lab.service.comparison(comparison["id"])["matched_days"] == 1
    lab.window("a", falling=True)
    failed = lab.service.comparison(comparison["id"])
    assert failed["verdict"] == "FAIL" and failed["matched_days"] == 20
    lab.advance()
    lab.observe("a", nav=1000000)
    assert lab.service.comparison(comparison["id"]) == failed
    lab.paper("expire")
    empty = lab.service.register_comparison(None, "expire", "operator")
    lab.advance(61)
    lab.observe("expire")
    report = lab.service.comparison(empty["id"])
    assert report["verdict"] == "EXPIRED" and report["matched_days"] == 0


def test_matching_snapshot_origin_and_risk_gates(lab: Laboratory) -> None:
    lab.paper("active")
    lab.activate("active")
    lab.paper("challenger")
    comparison = lab.service.register_comparison("active", "challenger", "operator")
    lab.advance()
    lab.observe("active")
    lab.observe("challenger", snapshot_hash="different")
    assert lab.service.comparison(comparison["id"])["matched_days"] == 0
    for day in range(20):
        lab.advance()
        origin = "synthetic" if day == 0 else "alpaca"
        lab.observe("active", origin=origin)
        lab.observe("challenger", 80000 if day == 10 else 100000 + day * 100, origin=origin)
    report = lab.service.comparison(comparison["id"])
    assert report["verdict"] == "FAIL"
    assert not report["gates"]["drawdown"] and not report["gates"]["daily_loss"]
    assert not report["gates"]["consistent_origin"]


@pytest.mark.parametrize(
    ("patch", "halt", "reason"),
    [
        ({}, True, "GLOBAL_RISK_HALT"),
        ({"status": "HALTED"}, False, "FORWARD_RISK_HALT"),
        ({"nav": 0}, False, "INVALID_ACCOUNT_STATE"),
        ({"nav": 80000}, False, "DRAWDOWN_LIMIT"),
        ({"nav": 95000, "high_watermark": 96000}, False, "DAILY_LOSS_LIMIT"),
    ],
)
def test_monitor_demotes_and_halts_forward_account_atomically(
    lab: Laboratory, patch: dict[str, Any], halt: bool, reason: str
) -> None:
    lab.paper()
    with lab.store.transaction() as conn:
        forward = lab.store.state(conn, "forward:a")
        lab.store.set_state(conn, "forward:a", {**forward, **patch})
        lab.store.set_state(conn, "kill", {"halted": halt})
    result = lab.service.monitor("a")
    assert result["status"] == "DEMOTED"
    assert lab.service.monitor("a") == result
    with lab.store.transaction() as conn:
        event = lab.store.get(conn, result["last_transition_id"], "lifecycle-transition")
        assert event["reason"] == reason
        assert lab.store.state(conn, "forward:a")["status"] == "HALTED"
        assert lab.store.verify_audit(conn)


def test_monitor_noop_empty_account_and_unauthorized_request(lab: Laboratory) -> None:
    lab.paper()
    assert lab.service.monitor("a")["status"] == "PAPER"
    with pytest.raises(ValueError, match="MONITOR_AUTHORITY_REQUIRED"):
        lab.service.monitor("a", "research")
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "forward:a", {})
    assert lab.service.monitor("a")["status"] == "PAPER"
