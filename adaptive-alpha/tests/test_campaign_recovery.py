"""Controller fencing, budget accounting and independent evaluator transport."""

import json
import time
from unittest.mock import Mock

import httpx
import pytest
from conftest import PassingEvaluator
from pydantic import SecretStr
from test_autonomous import candidate, dataset, evidence
from test_evaluation import spec

from adaptive_alpha import orchestrator as legacy
from adaptive_alpha.domain import JobRequest
from adaptive_alpha.orchestrator import Orchestrator, RemoteEvaluator
from adaptive_alpha.research import campaigns as module
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import CampaignRequest
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.store import Store


def prepared(settings, **options):
    store = Store(settings.database_url)
    store.initialize()
    ds = import_dataset(store, dataset(), "test")
    pipeline = Campaigns(store, settings)
    job = pipeline.create(
        CampaignRequest(
            objective="Test bounded campaign recovery",
            query="momentum",
            dataset_id=ds["id"],
            model="fixture",
            **options,
        ),
        "operator",
    )
    claimed = pipeline.claim()
    assert claimed is not None
    return store, pipeline, job, claimed


def test_spec_engineering_default_path_and_three_generation_lineage(settings, monkeypatch):
    settings.openai_api_key = SecretStr("test-key")
    ev = evidence()
    contexts = []

    def implement(store, settings, model, context, dataset_id, allowance, timeout, checkpoint):
        contexts.append(context)
        return (
            candidate(ev.id).model_copy(
                update={
                    "source": f"def signal(history):\n    return {0.05 + context['generation'] * 0.01}\n"
                }
            ),
            {"input_tokens": 10, "output_tokens": 20},
            {"work_order_id": "bound-spec"},
        )

    monkeypatch.setattr(module, "implement_research", implement)
    forbidden = Mock(side_effect=AssertionError("Combined generation must not run"))
    monkeypatch.setattr(module.OpenAIProvider, "generate", forbidden)
    monkeypatch.setattr(module, "search_sources", lambda *_: ([ev], {"openalex": "available"}))
    original = httpx.Client
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"verdict": "PASS", "score": 1})
            ),
            **kwargs,
        ),
    )
    store, pipeline, job, claimed = prepared(settings, generations=3)
    assert pipeline.run(*claimed)["status"] == "COMPLETED"
    assert "crossover_parent" in contexts[2]
    with store.transaction() as conn:
        artifacts = store.related(conn, "candidate", "campaign_id", job["id"])
        assert len(artifacts) == 3 and artifacts[2]["parent_ids"]
        assert all(a["generation_path"] == "research-spec-ouroboros-v1" for a in artifacts)
        assert store.verify_audit(conn)
    forbidden.assert_not_called()


def test_ouroboros_campaign_retains_external_accounting(settings, monkeypatch):
    settings.ouroboros_url, settings.ouroboros_workspace = "https://isolated.test", "/sandbox"
    ev = evidence()
    monkeypatch.setattr(
        module,
        "implement_research",
        lambda *_: (
            candidate(ev.id),
            {"tokens": "externally_accounted"},
            {"work_order_id": "isolated-work"},
        ),
    )
    store, pipeline, job, claimed = prepared(settings, engineer="ouroboros", generations=1)
    result = pipeline.run(
        *claimed, search=lambda _: [ev], hidden=lambda *_: {"verdict": "FAIL", "score": 0}
    )
    assert result["status"] == "COMPLETED"
    with store.transaction() as conn:
        assert store.list_records(conn, "candidate")[0]["usage"]["tokens"] == "externally_accounted"


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("no_evidence", "NO_RESEARCH_EVIDENCE"),
        ("deadline", "CAMPAIGN_DEADLINE"),
        ("missing_provider", "RETIRED_GENERATION_PATH"),
    ],
)
def test_campaign_early_failures_are_explicit(settings, monkeypatch, mode, reason):
    ev = evidence()
    store, pipeline, job, claimed = prepared(settings, generations=1)

    def generation(*_):
        return (candidate(ev.id), {})

    if mode == "deadline":
        times = iter([0, 10000])
        monkeypatch.setattr(module.time, "monotonic", lambda: next(times))
    if mode == "missing_provider":
        # Corrupted persisted/legacy request must fail closed, not choose a fallback.
        claimed[0]["engineer"] = "missing"
        generation = None
    outcome = pipeline.run(
        *claimed, generate=generation, search=lambda _: [] if mode == "no_evidence" else [ev]
    )
    assert outcome["status"] == "FAILED" and outcome["reason"] == reason


@pytest.mark.parametrize("mode", ["operator_cancel", "expired_lease"])
def test_in_flight_result_loses_ownership_and_attempt_closes_once(settings, mode):
    ev = evidence()
    store, pipeline, job, claimed = prepared(settings, generations=1)

    def generate(*_):
        if mode == "operator_cancel":
            pipeline.cancel(job["id"])
        else:
            with store.transaction() as conn:
                state = store.state(conn, "campaign:" + job["id"])
                state["lease_until"] = time.time() - 1
                store.set_state(conn, "campaign:" + job["id"], state)
            assert pipeline.claim() is None
        return candidate(ev.id), {}

    result = pipeline.run(*claimed, generate=generate, search=lambda _: [ev])
    assert result["status"] == ("CANCELLED" if mode == "operator_cancel" else "INTERRUPTED")
    assert result["tokens_charged"] > 0
    with store.transaction() as conn:
        outcomes = store.related(conn, "candidate-result", "campaign_id", job["id"])
        assert len(outcomes) == 1 and not store.list_records(conn, "candidate")


def test_reflection_failure_preserves_reserved_attempt(settings, monkeypatch):
    ev = evidence()
    settings.openai_api_key = SecretStr("fixture-key")
    monkeypatch.setattr(
        module.OpenAIProvider,
        "structured",
        Mock(side_effect=httpx.ReadTimeout("sensitive provider response")),
    )
    store, pipeline, job, claimed = prepared(settings, generations=1, propose_agent_revision=True)
    result = pipeline.run(
        *claimed,
        generate=lambda *_: (candidate(ev.id), {}),
        search=lambda _: [ev],
        hidden=lambda *_: {"verdict": "FAIL", "score": 0},
    )
    assert result["status"] == "FAILED" and result["tokens_charged"] == job["token_budget"]
    with store.transaction() as conn:
        outcomes = store.list_records(conn, "agent-evolution-result")
        assert len(outcomes) == 1 and outcomes[0]["status"] == "ERROR"
        assert "sensitive" not in json.dumps(outcomes)


def test_campaign_uses_selected_research_revision(settings):
    from adaptive_alpha.research.benchmark import AgentRevision, propose_revision

    store, pipeline, job, claimed = prepared(settings, generations=1)
    revision = propose_revision(
        store,
        AgentRevision(
            name="Revised",
            research_instructions="Seek contradictory empirical evidence",
            openspec_rationale="Improve public scientific testing of the candidate",
        ),
        "operator",
    )
    claimed[0]["agent_revision_id"] = revision["id"]
    ev = evidence()

    def generate(model, context, budget):
        assert context["research_method"] == revision["research_instructions"]
        return candidate(ev.id), {}

    assert (
        pipeline.run(
            *claimed,
            generate=generate,
            search=lambda _: [ev],
            hidden=lambda *_: {"verdict": "FAIL", "score": 0},
        )["status"]
        == "COMPLETED"
    )


def test_reference_remote_evaluator_transport(settings, monkeypatch):
    original = httpx.Client

    def respond(request):
        assert request.headers["Authorization"] == "Bearer " + settings.token("evaluator_token")
        assert json.loads(request.content)["experiment_id"] == "attempt"
        return httpx.Response(200, json={"verdict": "FAIL", "score": -2})

    monkeypatch.setattr(
        legacy.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    assert RemoteEvaluator(settings).evaluate("attempt", spec()).score == -2


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("cancel", "CANCELLED"),
        ("budget", "BUDGET_EXHAUSTED"),
        ("exception", "FAILED"),
        ("invalid", "COMPLETED"),
        ("cancel_in_evaluator", "CANCELLED"),
    ],
)
def test_reference_job_stop_and_failure_paths(settings, monkeypatch, mode, expected):
    store = Store(settings.database_url)
    store.initialize()
    controller = Orchestrator(store, PassingEvaluator(), settings)
    job = controller.create(JobRequest(objective="Test reference controller recovery"), "operator")
    original = legacy.propose_hypothesis
    if mode == "cancel":

        def cancel(request):
            controller.cancel(job["id"], "operator")
            return original(request)

        monkeypatch.setattr(legacy, "propose_hypothesis", cancel)
    elif mode == "budget":
        ticks = iter([0, 1000, 1001])
        monkeypatch.setattr(legacy.time, "monotonic", lambda: next(ticks))
    elif mode == "exception":
        monkeypatch.setattr(legacy, "propose_hypothesis", Mock(side_effect=RuntimeError("secret")))
    elif mode == "invalid":
        monkeypatch.setattr(legacy, "evaluate", Mock(side_effect=ValueError("invalid")))
    elif mode == "cancel_in_evaluator":

        def cancel_evaluator(*_):
            controller.cancel(job["id"], "operator")
            return PassingEvaluator().evaluate("a", spec())

        controller.evaluator.evaluate = cancel_evaluator
    result = controller.run(job["id"], "operator")
    assert result["status"] == expected
    with store.transaction() as conn:
        assert store.verify_audit(conn)
        assert "secret" not in json.dumps(store.audit_events(conn))
