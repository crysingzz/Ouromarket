"""Crash-safe campaign reconstruction from retained engineering evidence."""

import time
from unittest.mock import Mock

import pytest
from test_autonomous import candidate, dataset, evidence
from test_campaign_recovery import prepared
from test_engineering import SOURCE
from test_engineering import spec as engineering_spec

from adaptive_alpha.research import campaigns as module
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.engineering import EngineeringRegistry, ImplementationBundle


class WorkerCrash(BaseException):
    """Simulate process loss outside the campaign's ordinary exception boundary."""


def expire(store, campaign_id):
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + campaign_id)
        state["lease_until"] = time.time() - 1
        store.set_state(conn, "campaign:" + campaign_id, state)


def research_spec(store, dataset_id, item):
    with store.transaction() as conn:
        dataset_hash = store.get(conn, dataset_id, "dataset")["manifest"]["content_hash"]
    return engineering_spec(
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        evidence_ids=[item.id],
        source_hashes=[item.content_hash],
    )


def complete_engineering(
    store,
    context,
    dataset_id,
    item,
    *,
    valid_benchmark=True,
    research_usage=None,
):
    registry = EngineeringRegistry(store)
    work = registry.create_work_order(
        research_spec(store, dataset_id, item), "research", token_budget=5000, max_seconds=30
    )
    with store.transaction() as conn:
        store.append(
            conn,
            "engineering-link",
            {
                "work_order_id": work.id,
                "campaign_id": context["campaign_id"],
                "attempt_id": context["attempt_id"],
                "research_usage": research_usage
                if research_usage is not None
                else {"input_tokens": 21, "output_tokens": 8},
            },
        )
    attempt = registry.create_attempt(
        work.id, context["campaign_id"], context["attempt_id"], "worker"
    )
    registry.transition_attempt(attempt["id"], "RUNNING", "ouroboros", "worker")
    bundle = registry.accept(
        ImplementationBundle(work_order_id=work.id, spec_hash=work.spec_hash, source=SOURCE),
        "ouroboros",
    )
    registry.transition_attempt(attempt["id"], "VALIDATING", "contract", "worker")
    if valid_benchmark:
        benchmark = registry.benchmark(bundle["id"], "worker")
    else:
        benchmark = {
            "id": "tampered-benchmark",
            "bundle_id": bundle["id"],
            "work_order_id": work.id,
            "spec_hash": work.spec_hash,
            "runtime_digest": work.runtime_digest,
            "input_digest": work.input_digest,
            "producer": "untrusted-worker",
            "passed": True,
        }
        with store.transaction() as conn:
            store.append(conn, "artifact-benchmark", benchmark, benchmark["id"])
    registry.transition_attempt(
        attempt["id"],
        "SUCCEEDED",
        "complete",
        "worker",
        bundle_id=bundle["id"],
        benchmark_id=benchmark["id"],
    )


def test_reuses_completed_engineering_result_without_second_model_call(settings, monkeypatch):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()

    def crash_after_engineering(store, settings, model, context, dataset_id, *args):
        complete_engineering(store, context, dataset_id, item)
        raise WorkerCrash

    monkeypatch.setattr(module, "implement_research", crash_after_engineering)
    with pytest.raises(WorkerCrash):
        pipeline.run(
            *claimed,
            search=lambda _: [item],
            hidden=lambda *_: {"verdict": "PASS", "score": 1},
        )
    expire(store, job["id"])
    resumed = pipeline.claim()
    assert resumed is not None
    forbidden = Mock(side_effect=AssertionError("research and runtime must not run again"))
    monkeypatch.setattr(module, "implement_research", forbidden)
    outcome = pipeline.run(
        *resumed,
        search=lambda _: [item],
        hidden=lambda *_: {"verdict": "PASS", "score": 1},
    )
    assert outcome["status"] == "COMPLETED" and outcome["attempts"] == 1
    forbidden.assert_not_called()
    with store.transaction() as conn:
        assert len(store.related(conn, "autonomous-attempt", "campaign_id", job["id"])) == 1
        candidates = store.related(conn, "candidate", "campaign_id", job["id"])
        assert len(candidates) == 1 and candidates[0]["usage"]["recovered"] is True
        assert len(store.list_records(conn, "engineering-bundle")) == 1
        events = store.related(conn, "campaign-event", "campaign_id", job["id"])
        assert events[-1]["status"] == "RECOVERING"


def test_finalizes_closed_generation_without_generating_another_candidate(settings, monkeypatch):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()
    original_audit = store.audit

    def crash_after_diagnostics(conn, topic, actor, data):
        if topic == "campaign.finished":
            raise WorkerCrash
        return original_audit(conn, topic, actor, data)

    monkeypatch.setattr(store, "audit", crash_after_diagnostics)
    with pytest.raises(WorkerCrash):
        pipeline.run(
            *claimed,
            generate=lambda *_: (candidate(item.id), {}),
            search=lambda _: [item],
            hidden=lambda *_: {"verdict": "PASS", "score": 1},
        )
    expire(store, job["id"])
    resumed = pipeline.claim()
    assert resumed is not None
    monkeypatch.setattr(store, "audit", original_audit)
    forbidden = Mock(side_effect=AssertionError("closed generation must not run again"))
    outcome = pipeline.run(
        *resumed,
        generate=forbidden,
        search=lambda _: [item],
        hidden=lambda *_: {"verdict": "PASS", "score": 1},
    )
    assert outcome["status"] == "COMPLETED"
    forbidden.assert_not_called()
    with store.transaction() as conn:
        assert len(store.related(conn, "candidate", "campaign_id", job["id"])) == 1
        assert len(store.related(conn, "candidate-result", "campaign_id", job["id"])) == 1
        assert len(store.related(conn, "campaign-diagnostics", "campaign_id", job["id"])) == 1


def test_resumes_candidate_persisted_before_evaluation(settings, monkeypatch):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()

    def implemented(store, settings, model, context, dataset_id, *args):
        complete_engineering(store, context, dataset_id, item)
        return module.resume_research(store, context["attempt_id"])

    monkeypatch.setattr(module, "implement_research", implemented)
    original = module.backtest
    monkeypatch.setattr(module, "backtest", Mock(side_effect=WorkerCrash))
    with pytest.raises(WorkerCrash):
        pipeline.run(
            *claimed,
            search=lambda _: [item],
            hidden=lambda *_: {"verdict": "PASS", "score": 1},
        )
    expire(store, job["id"])
    resumed = pipeline.claim()
    assert resumed is not None
    monkeypatch.setattr(module, "backtest", original)
    outcome = pipeline.run(
        *resumed,
        search=lambda _: [item],
        hidden=lambda *_: {"verdict": "PASS", "score": 1},
    )
    assert outcome["status"] == "COMPLETED"
    with store.transaction() as conn:
        assert len(store.related(conn, "candidate", "campaign_id", job["id"])) == 1


def test_recovered_candidate_mismatch_fails_closed(settings, monkeypatch):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()

    def implemented(store, settings, model, context, dataset_id, *args):
        complete_engineering(store, context, dataset_id, item)
        return module.resume_research(store, context["attempt_id"])

    monkeypatch.setattr(module, "implement_research", implemented)
    monkeypatch.setattr(module, "backtest", Mock(side_effect=WorkerCrash))
    with pytest.raises(WorkerCrash):
        pipeline.run(*claimed, search=lambda _: [item])
    expire(store, job["id"])
    resumed = pipeline.claim()
    assert resumed is not None
    actual_resume = module.resume_research

    def mismatched(store, attempt_id):
        candidate_value, usage, engineering = actual_resume(store, attempt_id)
        return candidate_value.model_copy(update={"name": "Different"}), usage, engineering

    monkeypatch.setattr(module, "resume_research", mismatched)
    outcome = pipeline.run(*resumed, search=lambda _: [item])
    assert outcome["status"] == "FAILED"
    assert outcome["reason"] == "CAMPAIGN_RECOVERY_CANDIDATE_MISMATCH"


def test_invalid_closed_generation_restores_failure_context(settings, monkeypatch):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()
    original = module.pbo
    monkeypatch.setattr(module, "pbo", Mock(side_effect=WorkerCrash))
    with pytest.raises(WorkerCrash):
        pipeline.run(
            *claimed,
            generate=lambda *_: (
                candidate(item.id).model_copy(
                    update={"source": "def signal(history):\n    return history.missing\n"}
                ),
                {},
            ),
            search=lambda _: [item],
        )
    expire(store, job["id"])
    resumed = pipeline.claim()
    assert resumed is not None
    monkeypatch.setattr(module, "pbo", original)
    forbidden = Mock(side_effect=AssertionError("invalid closed generation must not repeat"))
    outcome = pipeline.run(*resumed, generate=forbidden, search=lambda _: [item])
    assert outcome["status"] == "COMPLETED"
    forbidden.assert_not_called()


def test_unknown_outcome_is_interrupted_instead_of_replayed(settings):
    store, pipeline, job, _ = prepared(settings, generations=1)
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + job["id"])
        state.update(attempts=1, tokens_charged=5000)
        store.set_state(conn, "campaign:" + job["id"], state)
        store.append(
            conn,
            "autonomous-attempt",
            {
                "id": "unknown-provider-attempt",
                "campaign_id": job["id"],
                "generation": 0,
                "reserved_tokens": 5000,
                "started_at": "2026-09-13T00:00:00+00:00",
                "generation_path": "research-spec-ouroboros-v1",
            },
            "unknown-provider-attempt",
        )
    expire(store, job["id"])
    assert pipeline.claim() is None
    assert pipeline.list()[0]["status"] == "INTERRUPTED"


def test_tampered_result_is_rejected_instead_of_resumed(settings):
    store, pipeline, job, _ = prepared(settings, generations=1)
    item = evidence()
    with store.transaction() as conn:
        store.append(conn, "evidence", item.model_dump(mode="json"), item.id)
        state = store.state(conn, "campaign:" + job["id"])
        state.update(attempts=1, tokens_charged=5000)
        store.set_state(conn, "campaign:" + job["id"], state)
        store.append(
            conn,
            "autonomous-attempt",
            {
                "id": "tampered-attempt",
                "campaign_id": job["id"],
                "generation": 0,
                "reserved_tokens": 5000,
                "started_at": "2026-09-13T00:00:00+00:00",
                "generation_path": "research-spec-ouroboros-v1",
            },
            "tampered-attempt",
        )
    complete_engineering(
        store,
        {"campaign_id": job["id"], "attempt_id": "tampered-attempt"},
        job["dataset_id"],
        item,
        valid_benchmark=False,
    )
    expire(store, job["id"])
    assert pipeline.claim() is None
    with store.transaction() as conn:
        results = store.related(conn, "candidate-result", "campaign_id", job["id"])
        assert results[0]["status"] == "INTERRUPTED"


def test_recovery_planner_rejects_closed_errors_open_evolution_and_multiple_calls(settings):
    store, pipeline, first, _ = prepared(settings, generations=1)
    with store.transaction() as conn:
        store.append(
            conn,
            "autonomous-attempt",
            {"id": "closed-error", "campaign_id": first["id"], "generation": 0},
            "closed-error",
        )
        store.append(
            conn,
            "candidate-result",
            {
                "id": "closed-error-result",
                "campaign_id": first["id"],
                "attempt_id": "closed-error",
                "status": "ERROR",
            },
        )
        assert pipeline._recovery_attempt(conn, first["id"]) is None

    second_settings = settings.model_copy(update={"database_url": settings.database_url + "-2"})
    store, pipeline, second, _ = prepared(second_settings, generations=1)
    with store.transaction() as conn:
        store.append(
            conn,
            "autonomous-attempt",
            {"id": "closed-pass", "campaign_id": second["id"], "generation": 0},
            "closed-pass",
        )
        store.append(
            conn,
            "candidate-result",
            {
                "id": "closed-pass-result",
                "campaign_id": second["id"],
                "attempt_id": "closed-pass",
                "status": "PASS",
            },
        )
        store.append(
            conn,
            "agent-evolution-attempt",
            {"id": "open-evolution", "campaign_id": second["id"]},
            "open-evolution",
        )
        assert pipeline._recovery_attempt(conn, second["id"]) is None

    third_settings = settings.model_copy(update={"database_url": settings.database_url + "-3"})
    store, pipeline, third, _ = prepared(third_settings, generations=2)
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + third["id"])
        state["attempts"] = 2
        store.set_state(conn, "campaign:" + third["id"], state)
        for generation, identity in enumerate(("open-one", "open-two")):
            store.append(
                conn,
                "autonomous-attempt",
                {
                    "id": identity,
                    "campaign_id": third["id"],
                    "generation": generation,
                    "generation_path": "research-spec-ouroboros-v1",
                },
                identity,
            )
        assert pipeline._recovery_attempt(conn, third["id"]) is None

    fourth_settings = settings.model_copy(update={"database_url": settings.database_url + "-4"})
    store, pipeline, fourth, _ = prepared(fourth_settings, generations=1)
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + fourth["id"])
        state["attempts"] = 1
        store.set_state(conn, "campaign:" + fourth["id"], state)
        store.append(
            conn,
            "autonomous-attempt",
            {
                "id": "known-attempt",
                "campaign_id": fourth["id"],
                "generation": 0,
                "generation_path": "research-spec-ouroboros-v1",
            },
            "known-attempt",
        )
        store.append(
            conn,
            "candidate-result",
            {
                "id": "foreign-result",
                "campaign_id": fourth["id"],
                "attempt_id": "foreign-attempt",
                "status": "PASS",
            },
        )
        assert pipeline._recovery_attempt(conn, fourth["id"]) is None


def test_recovery_rejects_malformed_history_and_foreign_dataset(settings):
    malformed_settings = settings.model_copy(update={"database_url": settings.database_url + "-m"})
    store, pipeline, malformed, _ = prepared(malformed_settings, generations=1)
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + malformed["id"])
        state["attempts"] = 1
        store.set_state(conn, "campaign:" + malformed["id"], state)
        store.append(
            conn,
            "autonomous-attempt",
            {"id": "malformed-attempt", "campaign_id": malformed["id"]},
            "malformed-attempt",
        )
        assert pipeline._recovery_attempt(conn, malformed["id"]) is None

    candidate_settings = settings.model_copy(update={"database_url": settings.database_url + "-c"})
    store, pipeline, candidate_job, _ = prepared(candidate_settings, generations=1)
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + candidate_job["id"])
        state["attempts"] = 1
        store.set_state(conn, "campaign:" + candidate_job["id"], state)
        store.append(
            conn,
            "autonomous-attempt",
            {
                "id": "candidate-attempt",
                "campaign_id": candidate_job["id"],
                "generation": 0,
                "generation_path": "research-spec-ouroboros-v1",
            },
            "candidate-attempt",
        )
        store.append(
            conn,
            "candidate",
            {
                "id": "damaged-candidate",
                "campaign_id": candidate_job["id"],
                "attempt_id": "candidate-attempt",
                "generation": 0,
                "generation_path": "research-spec-ouroboros-v1",
                "source": SOURCE,
                "source_hash": "wrong",
            },
            "damaged-candidate",
        )
        assert pipeline._recovery_attempt(conn, candidate_job["id"]) is None

    dataset_settings = settings.model_copy(update={"database_url": settings.database_url + "-d"})
    store, pipeline, dataset_job, _ = prepared(dataset_settings, generations=1)
    item = evidence()
    registry = EngineeringRegistry(store)
    foreign_dataset = import_dataset(
        store, dataset().model_copy(update={"name": "foreign-dataset"}), "test"
    )
    with store.transaction() as conn:
        store.append(conn, "evidence", item.model_dump(mode="json"), item.id)
    foreign_spec = research_spec(store, foreign_dataset["id"], item)
    work = registry.create_work_order(foreign_spec, "research", token_budget=5000, max_seconds=30)
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + dataset_job["id"])
        state["attempts"] = 1
        store.set_state(conn, "campaign:" + dataset_job["id"], state)
        store.append(
            conn,
            "autonomous-attempt",
            {
                "id": "foreign-dataset-attempt",
                "campaign_id": dataset_job["id"],
                "generation": 0,
                "generation_path": "research-spec-ouroboros-v1",
            },
            "foreign-dataset-attempt",
        )
        store.append(
            conn,
            "engineering-link",
            {
                "work_order_id": work.id,
                "campaign_id": dataset_job["id"],
                "attempt_id": "foreign-dataset-attempt",
                "research_usage": {},
            },
        )
    engineering_attempt = registry.create_attempt(
        work.id, dataset_job["id"], "foreign-dataset-attempt", "worker"
    )
    registry.transition_attempt(engineering_attempt["id"], "RUNNING", "ouroboros", "worker")
    bundle = registry.accept(
        ImplementationBundle(work_order_id=work.id, spec_hash=work.spec_hash, source=SOURCE),
        "ouroboros",
    )
    registry.transition_attempt(engineering_attempt["id"], "VALIDATING", "contract", "worker")
    benchmark = registry.benchmark(bundle["id"], "worker")
    registry.transition_attempt(
        engineering_attempt["id"],
        "SUCCEEDED",
        "complete",
        "worker",
        bundle_id=bundle["id"],
        benchmark_id=benchmark["id"],
    )
    with store.transaction() as conn:
        assert pipeline._recovery_attempt(conn, dataset_job["id"]) is None


def test_recovery_rejects_terminal_result_without_candidate(settings):
    store, pipeline, job, _ = prepared(settings, generations=1)
    with store.transaction() as conn:
        state = store.state(conn, "campaign:" + job["id"])
        state.update(attempts=1, tokens_charged=5000)
        store.set_state(conn, "campaign:" + job["id"], state)
        store.append(
            conn,
            "autonomous-attempt",
            {
                "id": "closed-without-candidate",
                "campaign_id": job["id"],
                "generation": 0,
                "generation_path": "research-spec-ouroboros-v1",
            },
            "closed-without-candidate",
        )
        store.append(
            conn,
            "candidate-result",
            {
                "id": "missing-candidate",
                "campaign_id": job["id"],
                "attempt_id": "closed-without-candidate",
                "status": "PASS",
            },
            "missing-candidate",
        )
    expire(store, job["id"])
    assert pipeline.claim() is None
    assert pipeline.list()[0]["status"] == "INTERRUPTED"


def test_recovery_rejects_any_retained_agent_evolution(settings, monkeypatch):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()
    original_audit = store.audit

    def crash_after_diagnostics(conn, topic, actor, data):
        if topic == "campaign.finished":
            raise WorkerCrash
        return original_audit(conn, topic, actor, data)

    monkeypatch.setattr(store, "audit", crash_after_diagnostics)
    with pytest.raises(WorkerCrash):
        pipeline.run(
            *claimed,
            generate=lambda *_: (candidate(item.id), {}),
            search=lambda _: [item],
            hidden=lambda *_: {"verdict": "PASS", "score": 1},
        )
    with store.transaction() as conn:
        store.append(
            conn,
            "agent-evolution-attempt",
            {"id": "retained-evolution", "campaign_id": job["id"]},
            "retained-evolution",
        )
        store.append(
            conn,
            "agent-evolution-result",
            {
                "id": "retained-evolution-result",
                "campaign_id": job["id"],
                "attempt_id": "retained-evolution",
                "status": "PROPOSED",
            },
            "retained-evolution-result",
        )
    expire(store, job["id"])
    assert pipeline.claim() is None
    assert pipeline.list()[0]["status"] == "INTERRUPTED"


def test_conflicting_evidence_and_fixture_recovery_are_rejected(settings):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()
    with store.transaction() as conn:
        store.append(
            conn, "evidence", {**item.model_dump(mode="json"), "title": "Changed"}, item.id
        )
    outcome = pipeline.run(
        *claimed, generate=lambda *_: (candidate(item.id), {}), search=lambda _: [item]
    )
    assert outcome["status"] == "FAILED" and outcome["reason"] == "EVIDENCE_IDENTITY_CONFLICT"

    second_settings = settings.model_copy(update={"database_url": settings.database_url + "-2"})
    store2, pipeline2, job2, claimed2 = prepared(second_settings, generations=1)
    item2 = evidence()
    with store2.transaction() as conn:
        store2.append(conn, "evidence", item2.model_dump(mode="json"), item2.id)
        store2.append(
            conn,
            "autonomous-attempt",
            {"id": "fixture-resume", "campaign_id": job2["id"], "generation": 0},
            "fixture-resume",
        )
        state = store2.state(conn, "campaign:" + job2["id"])
        state.update(resume_attempt_id="fixture-resume", attempts=1)
        store2.set_state(conn, "campaign:" + job2["id"], state)
    outcome = pipeline2.run(
        *claimed2, generate=lambda *_: (candidate(item2.id), {}), search=lambda _: [item2]
    )
    assert outcome["status"] == "FAILED"
    assert outcome["reason"] == "CONTROLLED_FIXTURE_RECOVERY_FORBIDDEN"


def test_conflicting_retained_diagnostics_fail_closed(settings):
    store, pipeline, job, claimed = prepared(settings, generations=1)
    item = evidence()
    with store.transaction() as conn:
        store.append(
            conn,
            "campaign-diagnostics",
            {"id": "foreign-diagnostics", "campaign_id": job["id"], "pbo": 99},
            "foreign-diagnostics",
        )
    outcome = pipeline.run(
        *claimed,
        generate=lambda *_: (candidate(item.id), {}),
        search=lambda _: [item],
        hidden=lambda *_: {"verdict": "PASS", "score": 1},
    )
    assert outcome["status"] == "FAILED"
    assert outcome["reason"] == "CAMPAIGN_DIAGNOSTICS_CONFLICT"


def test_completed_result_rejects_invalid_binding_state_and_usage(settings):
    store, _, job, _ = prepared(settings, generations=1)
    item = evidence()
    with store.transaction() as conn:
        store.append(conn, "evidence", item.model_dump(mode="json"), item.id)
    registry = EngineeringRegistry(store)
    work = registry.create_work_order(research_spec(store, job["dataset_id"], item), "research")

    mismatch = registry.create_attempt(work.id, job["id"], "binding-mismatch", "worker")
    with store.transaction() as conn:
        store.append(
            conn,
            "engineering-link",
            {"work_order_id": "different", "attempt_id": "binding-mismatch", "research_usage": {}},
        )
        with pytest.raises(ValueError, match="BINDING_INVALID"):
            registry.completed_result(conn, "binding-mismatch")

    waiting = registry.create_attempt(work.id, job["id"], "not-ready", "worker")
    with store.transaction() as conn:
        store.append(
            conn,
            "engineering-link",
            {
                "work_order_id": work.id,
                "campaign_id": job["id"],
                "attempt_id": "not-ready",
                "research_usage": {},
            },
        )
        with pytest.raises(ValueError, match="RESULT_NOT_READY"):
            registry.completed_result(conn, "not-ready")

    incomplete = registry.create_attempt(work.id, job["id"], "incomplete", "worker")
    with store.transaction() as conn:
        store.append(
            conn,
            "engineering-link",
            {
                "work_order_id": work.id,
                "campaign_id": job["id"],
                "attempt_id": "incomplete",
                "research_usage": {},
            },
        )
    registry.transition_attempt(incomplete["id"], "RUNNING", "ouroboros", "worker")
    registry.transition_attempt(incomplete["id"], "VALIDATING", "contract", "worker")
    registry.transition_attempt(incomplete["id"], "SUCCEEDED", "complete", "worker")
    with store.transaction() as conn, pytest.raises(ValueError, match="RESULT_INCOMPLETE"):
        registry.completed_result(conn, "incomplete")

    complete_engineering(
        store,
        {"campaign_id": job["id"], "attempt_id": "invalid-usage"},
        job["dataset_id"],
        item,
        research_usage="not-accounting-data",
    )
    with store.transaction() as conn, pytest.raises(ValueError, match="USAGE_INVALID"):
        registry.completed_result(conn, "invalid-usage")
    assert mismatch and waiting
