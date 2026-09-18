"""Renewed diagnostic proof, fenced evaluation and preservation of paper capital."""

import json
from unittest.mock import Mock

import pytest
from test_api_workflows import seed_candidate
from test_operations import move
from test_strategy_lifecycle import Laboratory

from adaptive_alpha.research import revalidation as module
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.forward import ForwardPaper
from adaptive_alpha.research.lifecycle import StrategyLifecycle
from adaptive_alpha.research.revalidation import Revalidation


@pytest.fixture
def stopped(client):
    store = client.app.state.store
    seed_candidate(store)
    client.post("/api/candidates/forward/paper").raise_for_status()
    move(client, "forward", "DEMOTED").raise_for_status()
    move(client, "forward", "RESEARCH").raise_for_status()
    return client, store, StrategyLifecycle(store).get("forward")["version"]


def public_pass(*args, **kwargs):
    return {"verdict": "PASS", "grammar": "signal-python-v1", "protocol": "generated-research-v1"}


def service(stopped, monkeypatch, hidden=None):
    monkeypatch.setattr(module, "backtest", public_pass)
    return Revalidation(stopped[1], hidden or (lambda *_: {"verdict": "PASS", "score": 1}))


def run(revalidator, version, request="once"):
    return revalidator.run("forward", "operator", request, version, "Renewed diagnostic validation")


def test_http_revalidation_then_recovery_preserves_account(stopped, monkeypatch):
    client, store, version = stopped
    hidden = Mock(return_value={"verdict": "PASS", "score": 1})
    monkeypatch.setattr(module, "backtest", public_pass)
    monkeypatch.setattr(Campaigns, "hidden", lambda *args: hidden(*args))
    with store.transaction() as conn:
        before = store.state(conn, "forward:forward")
        before.update(cash=97000, positions={"SPY": 1}, high_watermark=100000, day_start_nav=99500)
        store.set_state(conn, "forward:forward", before)
    request = {
        "expected_version": version,
        "request_id": "retry",
        "reason": "Request a renewed independent check",
    }
    result = client.post("/api/lifecycle/forward/revalidate", json=request)
    assert result.status_code == 200 and result.json()["status"] == "PASS"
    assert client.post("/api/lifecycle/forward/revalidate", json=request).json() == result.json()
    assert hidden.call_count == 1
    assert StrategyLifecycle(store).get("forward")["status"] == "RESEARCH"
    assert move(client, "forward", "LAB_VALIDATED").status_code == 200
    assert move(client, "forward", "SHADOW").status_code == 200
    assert move(client, "forward", "PAPER").status_code == 200
    assert move(client, "forward", "CHALLENGER").status_code == 409
    with store.transaction() as conn:
        after = store.state(conn, "forward:forward")
        assert after == {**before, "status": "PAPER", "halt_reason": None}
        assert store.list_records(conn, "forward-recovery")[0]["prior_account"] == before
        assert store.verify_audit(conn)


@pytest.mark.parametrize("mode", ["wrong_actor", "version", "stage", "source", "dataset"])
def test_revalidation_rejects_invalid_authority_state_or_input(stopped, monkeypatch, mode):
    client, store, version = stopped
    evaluate = Mock(return_value={"verdict": "PASS", "score": 1})
    check = service(stopped, monkeypatch, evaluate)
    if mode == "stage":
        move(client, "forward", "RETIRED")
        version += 1
    if mode in {"source", "dataset"}:
        original = store.get

        def corrupt(conn, identity, kind=None):
            item = original(conn, identity, kind)
            if kind == "candidate" and mode == "source":
                item["source"] += "\n# tampered"
            if kind == "dataset" and mode == "dataset":
                item["manifest"]["content_hash"] = "wrong"
            return item

        monkeypatch.setattr(store, "get", corrupt)
    with pytest.raises(
        ValueError,
        match={
            "wrong_actor": "OPERATOR_REQUIRED",
            "version": "VERSION_CONFLICT",
            "stage": "STAGE_REQUIRED",
            "source": "INPUT_INTEGRITY",
            "dataset": "INPUT_INTEGRITY",
        }[mode],
    ):
        check.run(
            "forward",
            "research" if mode == "wrong_actor" else "operator",
            "once",
            version + (mode == "version"),
            "Revalidate immutable candidate",
        )
    evaluate.assert_not_called()


@pytest.mark.parametrize("mode", ["public_fail", "hidden_fail", "error", "state_changed"])
def test_failed_or_stale_results_never_enable_recovery(stopped, monkeypatch, mode):
    client, store, version = stopped

    def hidden(*_):
        if mode == "error":
            raise RuntimeError("secret provider body")
        if mode == "state_changed":
            move(client, "forward", "RETIRED")
        return {"verdict": "FAIL" if mode == "hidden_fail" else "PASS", "score": 1}

    check = service(stopped, monkeypatch, hidden)
    if mode == "public_fail":
        monkeypatch.setattr(
            module, "backtest", lambda *a, **k: {**public_pass(), "verdict": "FAIL"}
        )
    outcome = run(check, version)
    assert (
        outcome["status"]
        == {
            "public_fail": "FAIL",
            "hidden_fail": "FAIL",
            "error": "ERROR",
            "state_changed": "STALE",
        }[mode]
    )
    assert move(client, "forward", "LAB_VALIDATED").status_code == 409
    with store.transaction() as conn:
        assert "secret" not in json.dumps(store.audit_events(conn))
        assert store.state(conn, "forward:forward")["status"] == "HALTED"


def test_revalidation_runs_outside_transaction_and_fences_expired_response(stopped, monkeypatch):
    _, store, version = stopped
    clock = [0.0]
    monkeypatch.setattr(module.time, "time", lambda: clock[0])
    attempts = []
    check = None

    def hidden(attempt, *_):
        attempts.append(attempt)
        with store.transaction() as conn:
            assert store.state(conn, "forward:forward")["status"] == "HALTED"
        if len(attempts) == 1:
            with pytest.raises(ValueError, match="IN_PROGRESS"):
                run(check, version)
            with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
                run(check, version + 1)
            clock[0] = 91
            assert run(check, version)["status"] == "PASS"
        return {"verdict": "PASS", "score": 1}

    check = service(stopped, monkeypatch, hidden)
    with pytest.raises(ValueError, match="OWNERSHIP_LOST"):
        run(check, version)
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert run(check, version)["status"] == "PASS"
    with store.transaction() as conn:
        assert len(store.list_records(conn, "revalidation-request")) == 1
        assert (
            len(
                [
                    r
                    for r in store.list_records(conn, "candidate-result")
                    if r.get("revalidation_id")
                ]
            )
            == 1
        )


def test_expired_evaluation_cannot_commit_without_new_owner(stopped, monkeypatch):
    _, _, version = stopped
    clock = [0.0]
    monkeypatch.setattr(module.time, "time", lambda: clock[0])

    def late(*_):
        clock[0] = 91
        return {"verdict": "PASS", "score": 1}

    check = service(stopped, monkeypatch, late)
    with pytest.raises(ValueError, match="OWNERSHIP_LOST"):
        run(check, version)


def test_recovery_cannot_bypass_stage_or_global_stop(stopped, monkeypatch):
    client, store, version = stopped
    with pytest.raises(ValueError, match="RENEWED_FORWARD_ADMISSION_REQUIRED"):
        ForwardPaper(store).admit("forward", "operator")
    run(service(stopped, monkeypatch), version)
    move(client, "forward", "LAB_VALIDATED").raise_for_status()
    with store.transaction() as conn:
        store.set_state(conn, "kill", {"halted": True})
    assert move(client, "forward", "SHADOW").json()["detail"] == "RISK_HALTED"
    assert StrategyLifecycle(store).get("forward")["status"] == "LAB_VALIDATED"


def test_previous_comparison_and_observations_cannot_requalify_new_episode(tmp_path, monkeypatch):
    lab = Laboratory(tmp_path, monkeypatch)
    lab.paper()
    comparison = lab.service.register_comparison(None, "a", "operator")
    lab.window("a")
    lab.service.transition("a", "DEMOTED", "operator", "Stop old episode")
    lab.service.transition("a", "RESEARCH", "operator", "Request new validation")
    lab.advance()
    lab.validate("a", validation_after="wrong")
    with pytest.raises(ValueError, match="INDEPENDENT_VALIDATION_REQUIRED"):
        lab.service.transition("a", "LAB_VALIDATED", "operator", "Incorrect proof epoch")
    lab.validate("a")
    for stage in ("LAB_VALIDATED", "SHADOW", "PAPER"):
        lab.service.transition("a", stage, "operator", "Renewed operator permission")
    with lab.store.transaction() as conn:
        lab.store.set_state(conn, "forward:a", {"status": "PAPER"})
    with pytest.raises(ValueError, match="FORWARD_EVIDENCE_REQUIRED"):
        lab.service.transition("a", "CHALLENGER", "operator", "Old observations only")
    lab.observe("a")
    lab.service.transition("a", "CHALLENGER", "operator", "New observation")
    with pytest.raises(ValueError, match="STALE_COMPARISON_EPISODE"):
        lab.service.transition(
            "a", "ACTIVE_LIMITED", "operator", "Old comparison", comparison_id=comparison["id"]
        )
    fresh = lab.service.register_comparison(None, "a", "operator")
    assert fresh["challenger_validation_after"] == lab.service.get("a")["validation_after"]
    assert lab.service.comparison(fresh["id"])["matched_days"] == 0


def test_reactivated_baseline_invalidates_old_challenger_comparison(tmp_path, monkeypatch):
    lab = Laboratory(tmp_path, monkeypatch)
    lab.paper("a")
    lab.activate("a")
    lab.paper("b")
    old = lab.service.register_comparison("a", "b", "operator")
    lab.window("b", "a")
    lab.service.transition("b", "CHALLENGER", "operator", "Forward observations")
    lab.service.transition("a", "DEMOTED", "operator", "Stop baseline")
    lab.service.transition("a", "RESEARCH", "operator", "New baseline episode")
    lab.advance()
    lab.validate("a")
    for stage in ("LAB_VALIDATED", "SHADOW", "PAPER"):
        lab.service.transition("a", stage, "operator", "Renewed validation")
    with lab.store.transaction() as conn:
        account = lab.store.state(conn, "forward:a")
        lab.store.set_state(conn, "forward:a", {**account, "status": "PAPER"})
    lab.activate("a")
    with pytest.raises(ValueError, match="STALE_COMPARISON_EPISODE"):
        lab.service.transition(
            "b", "ACTIVE_LIMITED", "operator", "Old baseline episode", comparison_id=old["id"]
        )
