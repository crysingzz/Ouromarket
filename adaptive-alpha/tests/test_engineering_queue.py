"""Durable engineering delivery, recovery and worker lifecycle."""

import runpy
import signal
import time
from unittest.mock import Mock

import pytest
from pydantic import SecretStr
from test_engineering import SOURCE, spec

from adaptive_alpha import config
from adaptive_alpha.research import engineering_queue as queue_module
from adaptive_alpha.research import engineering_worker
from adaptive_alpha.research.engineering import (
    EngineeringRegistry,
    ImplementationBundle,
)
from adaptive_alpha.research.engineering_queue import EngineeringQueue
from adaptive_alpha.store import Store

TOKEN = "t" * 48


def prepared(settings, *, attempts=1):
    store = Store(settings.database_url)
    store.initialize()
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        store.append(conn, "evidence", {"content_hash": "b" * 64}, "paper")
    registry = EngineeringRegistry(store)
    work = registry.create_work_order(spec(), "research", max_seconds=10)
    created = [
        registry.create_attempt(work.id, "campaign", f"research-{index}", "worker")
        for index in range(attempts)
    ]
    settings.ouroboros_url = "https://isolated.test"
    settings.ouroboros_workspace = "/workspaces"
    settings.ouroboros_token = SecretStr(TOKEN)
    return store, registry, work, created


def test_queue_uses_independent_fenced_lease_and_resumes_expired_delivery(settings):
    store, _, work, attempts = prepared(settings)
    queue = EngineeringQueue(store)
    first = queue.claim(lease_seconds=10)
    assert first is not None and first[1] == work
    assert queue.claim() is None
    queue.checkpoint(attempts[0]["id"], first[2])
    with store.transaction() as conn:
        state = store.state(conn, "engineering-attempt:" + attempts[0]["id"])
        state["lease_until"] = time.time() - 1
        store.set_state(conn, "engineering-attempt:" + attempts[0]["id"], state)
    second = queue.claim()
    assert second is not None and second[2] != first[2]
    with pytest.raises(ValueError, match="OWNERSHIP_LOST"):
        queue.checkpoint(attempts[0]["id"], first[2])
    assert queue.snapshot(attempts[0]["id"])["deliveries"] == 2
    with store.transaction() as conn:
        events = store.related(
            conn, "engineering-queue-event", "engineering_attempt_id", attempts[0]["id"]
        )
    assert [event["action"] for event in events] == ["CLAIMED", "RESUMED"]


@pytest.mark.parametrize("duration", [0, -1, float("inf"), 1831])
def test_queue_rejects_unbounded_lease(settings, duration):
    store, _, _, _ = prepared(settings)
    with pytest.raises(ValueError, match="LEASE_BOUND"):
        EngineeringQueue(store).claim(lease_seconds=duration)


def test_cancel_is_idempotent_for_queued_and_visible_to_running_delivery(settings):
    store, _, _, attempts = prepared(settings, attempts=2)
    queue = EngineeringQueue(store)
    running = queue.claim(attempt_id=attempts[0]["id"])
    assert running is not None
    queue.request_cancel(attempts[0]["id"], "operator")
    with pytest.raises(ValueError, match="ENGINEERING_CANCELLED"):
        queue.checkpoint(attempts[0]["id"], running[2])
    with store.transaction() as conn:
        state = store.state(conn, "engineering-attempt:" + attempts[0]["id"])
        state["lease_until"] = 0
        store.set_state(conn, "engineering-attempt:" + attempts[0]["id"], state)
    assert queue.claim(attempt_id=attempts[0]["id"]) is None
    assert queue.snapshot(attempts[0]["id"])["status"] == "CANCELLED"
    cancelled = queue.request_cancel(
        attempts[1]["id"], "operator", reason="CAMPAIGN_OWNERSHIP_LOST"
    )
    assert cancelled["status"] == "CANCELLED"
    assert queue.request_cancel(attempts[1]["id"], "operator")["status"] == "CANCELLED"
    assert queue.cancel_campaign("campaign", "operator")
    with pytest.raises(ValueError, match="CANCEL_REASON_INVALID"):
        queue.request_cancel(attempts[0]["id"], "operator", reason="secret detail")
    with pytest.raises(ValueError, match="OWNERSHIP_LOST"):
        queue.finish(attempts[0]["id"], "wrong", "FAILED")


def test_engineering_worker_completes_and_waiter_reads_immutable_result(settings, monkeypatch):
    store, registry, work, attempts = prepared(settings)

    def implement(self, received, timeout, **kwargs):
        kwargs["checkpoint"]()
        return ImplementationBundle(
            work_order_id=received.id, spec_hash=received.spec_hash, source=SOURCE
        )

    monkeypatch.setattr(engineering_worker.OuroborosEngineer, "implement", implement)
    assert engineering_worker.run_once(store, settings, attempts[0]["id"])
    queue = EngineeringQueue(store)
    record, benchmark = queue.wait(attempts[0]["id"], 1, lambda: None, poll_seconds=0)
    assert record["work_order_id"] == work.id and benchmark["passed"]
    assert queue.snapshot(attempts[0]["id"])["status"] == "SUCCEEDED"
    assert engineering_worker.run_once(store, settings, attempts[0]["id"]) is False
    assert registry.list_attempts()[0]["status"] == "SUCCEEDED"


def test_worker_recovers_bundle_without_second_model_execution(settings, monkeypatch):
    store, registry, work, attempts = prepared(settings)
    queue = EngineeringQueue(store)
    claim = queue.claim()
    assert claim is not None
    registry.transition_attempt(attempts[0]["id"], "RUNNING", "ouroboros", "worker")
    bundle = registry.accept(
        ImplementationBundle(work_order_id=work.id, spec_hash=work.spec_hash, source=SOURCE),
        "ouroboros",
    )
    registry.transition_attempt(attempts[0]["id"], "VALIDATING", "contract-validation", "worker")
    with store.transaction() as conn:
        state = store.state(conn, "engineering-attempt:" + attempts[0]["id"])
        state["lease_until"] = 0
        store.set_state(conn, "engineering-attempt:" + attempts[0]["id"], state)
    blocked = Mock(side_effect=AssertionError("model must not be called"))
    monkeypatch.setattr(engineering_worker.OuroborosEngineer, "implement", blocked)
    assert engineering_worker.run_once(store, settings)
    result, benchmark = queue.wait(attempts[0]["id"], 1, lambda: None, poll_seconds=0)
    assert result["id"] == bundle["id"] and benchmark["passed"]
    blocked.assert_not_called()


def test_worker_records_bounded_failure_and_lost_lease(settings, monkeypatch):
    store, _, _, attempts = prepared(settings, attempts=2)
    monkeypatch.setattr(
        engineering_worker.OuroborosEngineer,
        "implement",
        Mock(side_effect=RuntimeError("provider secret response")),
    )
    assert engineering_worker.run_once(store, settings, attempts[0]["id"])
    failed = EngineeringQueue(store).snapshot(attempts[0]["id"])
    assert failed["status"] == "FAILED" and failed["attempt"]["reason"] == "RUNTIMEERROR"
    original = EngineeringQueue.checkpoint
    monkeypatch.setattr(
        EngineeringQueue,
        "checkpoint",
        Mock(side_effect=ValueError("ENGINEERING_OWNERSHIP_LOST")),
    )
    assert engineering_worker.run_once(store, settings, attempts[1]["id"]) is False
    monkeypatch.setattr(EngineeringQueue, "checkpoint", original)


def test_worker_turns_running_cancel_request_into_atomic_terminal(settings, monkeypatch):
    store, _, _, attempts = prepared(settings)
    queue = EngineeringQueue(store)

    def cancelled(self, received, timeout, **kwargs):
        queue.request_cancel(attempts[0]["id"], "operator")
        kwargs["checkpoint"]()

    monkeypatch.setattr(engineering_worker.OuroborosEngineer, "implement", cancelled)
    assert engineering_worker.run_once(store, settings, attempts[0]["id"])
    snapshot = queue.snapshot(attempts[0]["id"])
    assert snapshot["status"] == "CANCELLED"
    assert snapshot["attempt"]["reason"] == "ENGINEERING_CANCELLED"


def test_wait_rejects_bad_budget_timeout_and_incomplete_terminal(settings, monkeypatch):
    store, registry, _, attempts = prepared(settings, attempts=2)
    queue = EngineeringQueue(store)
    for timeout in (0, -1, float("inf"), 1801):
        with pytest.raises(ValueError, match="WAIT_BOUND"):
            queue.wait(attempts[0]["id"], timeout, lambda: None)
    registry.transition_attempt(attempts[0]["id"], "FAILED", "queue", "worker", reason="FAIL")
    with pytest.raises(ValueError, match="FAIL"):
        queue.wait(attempts[0]["id"], 1, lambda: None, poll_seconds=0)
    registry.transition_attempt(attempts[1]["id"], "RUNNING", "ouroboros", "worker")
    registry.transition_attempt(attempts[1]["id"], "VALIDATING", "contract", "worker")
    registry.transition_attempt(attempts[1]["id"], "SUCCEEDED", "complete", "worker")
    with pytest.raises(ValueError, match="RESULT_INCOMPLETE"):
        queue.wait(attempts[1]["id"], 1, lambda: None, poll_seconds=0)

    store2, _, _, pending = prepared(
        settings.model_copy(update={"database_url": settings.database_url + "2"})
    )
    times = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(queue_module.time, "monotonic", lambda: next(times))
    with pytest.raises(ValueError, match="ENGINEERING_DEADLINE"):
        EngineeringQueue(store2).wait(pending[0]["id"], 1, lambda: None, poll_seconds=0)


def test_claim_reconciles_terminal_history_after_worker_crash(settings):
    store, registry, _, attempts = prepared(settings)
    registry.transition_attempt(
        attempts[0]["id"], "FAILED", "dispatch", "engineering-worker", reason="RUNTIMEERROR"
    )
    queue = EngineeringQueue(store)
    assert queue.claim() is None
    snapshot = queue.snapshot(attempts[0]["id"])
    assert snapshot["status"] == "FAILED" and snapshot["reason"] == "RUNTIMEERROR"


def test_atomic_finish_rejects_cancel_race_and_prior_terminal_event(settings):
    store, registry, _, attempts = prepared(settings, attempts=2)
    queue = EngineeringQueue(store)
    first = queue.claim(attempt_id=attempts[0]["id"])
    assert first is not None
    queue.request_cancel(attempts[0]["id"], "operator")
    with pytest.raises(ValueError, match="ENGINEERING_CANCELLED"):
        queue.finish(attempts[0]["id"], first[2], "SUCCEEDED")

    second = queue.claim(attempt_id=attempts[1]["id"])
    assert second is not None
    registry.transition_attempt(
        attempts[1]["id"], "FAILED", "dispatch", "engineering-worker", reason="RUNTIMEERROR"
    )
    with pytest.raises(ValueError, match="TRANSITION_INVALID"):
        queue.finish(attempts[1]["id"], second[2], "FAILED")


def test_engineering_worker_entrypoint_heartbeats_and_stops(settings, monkeypatch):
    store = Store(settings.database_url)
    store.initialize()
    handlers = {}
    monkeypatch.setattr(engineering_worker, "Settings", lambda: settings)
    monkeypatch.setattr(engineering_worker, "Store", lambda *args, **kwargs: store)
    monkeypatch.setattr(
        engineering_worker.signal,
        "signal",
        lambda kind, handler: handlers.__setitem__(kind, handler),
    )
    monkeypatch.setattr(engineering_worker, "run_once", Mock(return_value=False))
    monkeypatch.setattr(
        engineering_worker.time,
        "sleep",
        lambda _: handlers[signal.SIGTERM](signal.SIGTERM, None),
    )
    engineering_worker.main()
    with store.transaction() as conn:
        assert store.state(conn, "engineering-worker")["queue"] == "durable-v1"


def test_engineering_worker_module_entrypoint(settings, monkeypatch):
    handlers = {}
    monkeypatch.setattr(config, "Settings", lambda: settings)
    monkeypatch.setattr(signal, "signal", lambda kind, handler: handlers.__setitem__(kind, handler))
    monkeypatch.setattr(
        time,
        "sleep",
        lambda _: handlers[signal.SIGTERM](signal.SIGTERM, None),
    )
    runpy.run_module("adaptive_alpha.research.engineering_worker", run_name="__main__")
