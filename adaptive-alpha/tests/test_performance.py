"""Retained forward evidence drives frozen monitoring and atomic paper demotion."""

from datetime import timedelta

import pytest
from test_strategy_lifecycle import Laboratory

from adaptive_alpha.domain import digest
from adaptive_alpha.research.performance import PERFORMANCE_POLICY, PerformanceMonitor


@pytest.fixture
def lab(tmp_path, monkeypatch):
    laboratory = Laboratory(tmp_path, monkeypatch)
    laboratory.paper()
    laboratory.activate("a")
    return laboratory


def observe(lab, index, *, rate=-0.001, days=1, **changes):
    lab.advance(days)
    lab.observe("a", 100000 * (1 + rate) ** index, **changes)
    return lab.service.monitor("a")


def test_two_disjoint_loss_windows_demote_atomically_and_retain_replay(lab):
    monitor = PerformanceMonitor(lab.store)
    admission = monitor.report("a")["admission"]
    assert admission["policy_hash"] == digest(PERFORMANCE_POLICY)
    for index in range(21):
        state = observe(lab, index)
        if index == 10:
            report = monitor.report("a")
            assert report["monitor"]["status"] == "WARNING"
            assert state["status"] == "ACTIVE_LIMITED"
    assert state["status"] == "DEMOTED"
    report = monitor.report("a")
    first, second = report["reports"]
    assert first["status"] == "WARNING" and second["status"] == "HALT"
    assert first["observation_ids"][-1] == second["observation_ids"][0]
    assert len(set(first["observation_ids"]) & set(second["observation_ids"])) == 1
    with lab.store.transaction() as conn:
        event = lab.store.get(conn, state["last_transition_id"], "lifecycle-transition")
        assert event["reason"] == "SUSTAINED_NET_DEGRADATION"
        assert event["evidence"]["performance_report_id"] == second["id"]
        assert lab.store.state(conn, "forward:a")["status"] == "HALTED"
        assert lab.store.state(conn, "active-paper:SPY")["candidate_id"] is None
        for window in (first, second):
            samples = [
                lab.store.get(conn, i, "lifecycle-observation") for i in window["observation_ids"]
            ]
            assert digest(samples) == window["samples_hash"]
            assert samples[-1]["nav"] / samples[0]["nav"] - 1 == window["net_return"]
        monitor.observe(conn, second["observation_ids"][-1])
        assert lab.store.verify_audit(conn)
    assert lab.service.monitor("a") == state
    assert monitor.report("a") == report
    assert not report["capital_eligible"]


def test_frozen_policy_daily_sealing_and_retries(lab, monkeypatch):
    monitor = PerformanceMonitor(lab.store)
    monkeypatch.setitem(PERFORMANCE_POLICY, "returns_per_window", 2)
    monkeypatch.setitem(PERFORMANCE_POLICY, "loss_threshold", 0.99)
    lab.advance()
    lab.observe("a", bar=(lab.clock - timedelta(days=2)).isoformat())
    assert monitor.report("a")["monitor"]["samples"] == []
    for index in range(11):
        observe(lab, index)
        sealed = monitor.report("a")
        lab.observe("a", 10000000)
        assert monitor.report("a") == sealed
    assert sealed["monitor"]["status"] == "WARNING"
    assert len(sealed["reports"]) == 1
    assert sealed["admission"]["policy"]["returns_per_window"] == 10


@pytest.mark.parametrize("rate", [0, 0.0001, 0.002])
def test_flat_positive_and_healthy_windows_do_not_imply_alpha_failure(lab, rate):
    for index in range(21):
        assert observe(lab, index, rate=rate)["status"] == "ACTIVE_LIMITED"
    report = PerformanceMonitor(lab.store).report("a")
    assert report["monitor"]["status"] == "HEALTHY"
    assert all(r["consecutive_breaches"] == 0 for r in report["reports"])


@pytest.mark.parametrize("mode", ["origin", "calendar_gap"])
def test_incomparable_window_breaks_consecutive_breaches(lab, mode):
    for index in range(21):
        changes = {"origin": "alpaca"} if mode == "origin" and index > 10 else {}
        days = 3 if mode == "calendar_gap" and index > 10 else 1
        assert observe(lab, index, days=days, **changes)["status"] == "ACTIVE_LIMITED"
    report = PerformanceMonitor(lab.store).report("a")
    assert report["reports"][0]["status"] == "WARNING"
    assert report["reports"][1]["status"] == "INCONCLUSIVE"
    assert report["monitor"]["consecutive_breaches"] == 0


def test_healthy_window_resets_warning_and_restart_keeps_evidence(lab):
    for index in range(11):
        observe(lab, index)
    for index in range(1, 11):
        lab.advance()
        lab.observe("a", 99000 + 100 * index)
        lab.service.monitor("a")
    restarted = PerformanceMonitor(lab.store)
    assert restarted.report("a")["monitor"]["status"] == "HEALTHY"
    for index in range(1, 11):
        lab.advance()
        lab.observe("a", 100000 * 0.999**index)
        lab.service.monitor("a")
    assert restarted.report("a")["monitor"]["status"] == "WARNING"
    assert lab.service.get("a")["status"] == "ACTIVE_LIMITED"


def test_missing_inactive_and_unconfigured_monitor(lab):
    monitor = PerformanceMonitor(lab.store)
    with pytest.raises(KeyError):
        monitor.report("missing")
    lab.paper("b")
    assert monitor.report("b")["monitor"]["status"] == "NOT_ACTIVATED"
    observation = lab.observe("b")
    with lab.store.transaction() as conn:
        monitor.observe(conn, observation["id"])
    assert monitor.report("b")["reports"] == []


def test_risk_stop_takes_priority_over_performance(lab):
    for index in range(20):
        observe(lab, index)
    lab.advance()
    lab.observe("a", 98000)
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "kill", {"halted": True})
    state = lab.service.monitor("a")
    with lab.store.transaction() as conn:
        event = lab.store.get(conn, state["last_transition_id"], "lifecycle-transition")
        assert event["reason"] == "GLOBAL_RISK_HALT"
        assert event["evidence"]["performance_report_id"]
