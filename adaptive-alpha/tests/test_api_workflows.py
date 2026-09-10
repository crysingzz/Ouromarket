"""Operator workflows exercise actual HTTP handlers and persistent domain state."""

from datetime import datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from conftest import EVALUATOR, OPERATOR, RESEARCH, PassingEvaluator
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from test_api import create_job, paper_strategy
from test_autonomous import SOURCE, dataset
from test_evaluation import spec

from adaptive_alpha.api.app import create_app
from adaptive_alpha.domain import OrderIntent, digest
from adaptive_alpha.evaluation import service
from adaptive_alpha.evaluation.engine import PROTOCOL
from adaptive_alpha.research import setup
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.forward import ForwardPaper
from adaptive_alpha.store import Store


def test_reference_api_read_mutate_and_check_without_submission(client):
    job = create_job(client, 1)
    assert client.get(f"/api/research/jobs/{job}").json()["id"] == job
    strategy_id = paper_strategy(client)
    strategy = client.get(f"/api/strategies/{strategy_id}").json()
    assert client.get(f"/api/hypotheses/{strategy['hypothesis_id']}").json()["statement"] == "Test"
    assert client.get(f"/api/strategies/{strategy_id}/lineage").json()["parents"] == []
    child = client.post(
        "/api/evolution/mutate", json={"strategy_id": strategy_id, "second_parent_id": strategy_id}
    )
    assert child.status_code == 201 and child.json()["parent_strategies"] == [
        strategy_id,
        strategy_id,
    ]
    intent = OrderIntent(
        strategy_id=strategy_id, instrument="SPY", side="BUY", quantity=1
    ).model_dump()
    assert client.post("/api/risk/check", json=intent).json()["decision"]["status"] == "APPROVE"
    assert client.get("/api/orders").json() == []
    intent["strategy_id"] = child.json()["id"]
    assert client.post("/api/orders", json=intent).json()["detail"] == "STRATEGY_NOT_IN_PAPER"
    assert (
        client.post("/api/market/demo-refresh").json()["source"] == "synthetic-demo-fixed-snapshot"
    )
    assert client.get("/api/dashboard").json()["real_capital_enabled"] is False
    assert "/api/campaigns" in client.get("/api/openapi.json").json()["paths"]
    assert client.get("/api/strategies/missing").status_code == 404


def test_database_errors_are_redacted(client, monkeypatch):
    monkeypatch.setattr(
        client.app.state.store,
        "list_records",
        Mock(side_effect=SQLAlchemyError("database password: secret")),
    )
    response = client.get("/api/orders")
    assert response.status_code == 503 and "secret" not in response.text


def test_provider_setup_http_preserves_secret_boundary(client, monkeypatch):
    original = httpx.Client
    monkeypatch.setattr(
        setup.httpx,
        "Client",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": [{"id": "gpt-fixture"}]})
            ),
            **kwargs,
        ),
    )
    result = client.post("/api/provider/setup", json={"api_key": "s" * 40, "model": "gpt-fixture"})
    assert result.status_code == 200 and result.json()["connection_verified"]
    assert "s" * 40 not in client.get("/api/audit").text
    assert client.get("/api/research/readiness").json()["default_model"] == "gpt-fixture"


def test_autonomous_api_bundles_cancel_and_operator_benchmark_adoption(client):
    ds = client.post("/api/datasets/demo").json()
    assert client.get("/api/datasets").json()[0]["id"] == ds["id"]
    assert client.get(f"/api/datasets/{ds['id']}/features").json()["version"] == "world-daily-v1"
    common = {
        "objective": "Test complete HTTP research workflow",
        "query": "momentum",
        "dataset_id": ds["id"],
        "model": "fixture",
    }
    job = client.post("/api/campaigns", json=common).json()
    assert client.get("/api/campaigns").json()[0]["id"] == job["id"]
    assert client.get(f"/api/campaigns/{job['id']}/bundle").json()["dataset"]["id"] == ds["id"]
    assert (
        client.get(f"/api/campaigns/{job['id']}/population").json()["allocation_proposal"]["cash"]
        == 1
    )
    assert client.post(f"/api/campaigns/{job['id']}/cancel").json()["status"] == "CANCELLED"
    assert client.get("/api/knowledge").json() == {"evidence": [], "edges": []}
    body = {
        "name": "Revised research",
        "research_instructions": "Seek evidence contradicting the mechanism",
        "openspec_rationale": "Test whether public counterexamples improve research efficiency",
    }
    revision = client.post("/api/agents/revisions", json=body).json()
    child = client.post("/api/agents/revisions", json={**body, "parent_id": revision["id"]}).json()
    assert len(client.get("/api/agents/revisions").json()) == 2
    benchmark = client.post(
        "/api/agents/benchmarks", json={**common, "challenger_revision_id": child["id"]}
    ).json()
    assert client.get("/api/agents/benchmarks").json()["benchmarks"][0]["id"] == benchmark["id"]
    assert client.post(f"/api/agents/benchmarks/{benchmark['id']}/promote").status_code == 409
    # Trusted evaluator fixture: the HTTP client cannot write these outcomes.
    store = client.app.state.store
    with store.transaction() as conn:
        for key in ("baseline_id", "challenger_id"):
            store.set_state(
                conn,
                "campaign:" + benchmark[key],
                {"status": "COMPLETED", "attempts": 3, "tokens_charged": 90000},
            )
        store.append(
            conn,
            "candidate-result",
            {
                "campaign_id": benchmark["challenger_id"],
                "status": "PASS",
                "public": {"verdict": "PASS"},
                "hidden": {"verdict": "PASS", "score": 1},
            },
        )
    client.headers["Authorization"] = "Bearer " + RESEARCH
    assert client.post(f"/api/agents/benchmarks/{benchmark['id']}/promote").status_code == 403
    client.headers["Authorization"] = "Bearer " + OPERATOR
    assert (
        client.post(f"/api/agents/benchmarks/{benchmark['id']}/promote").json()["revision_id"]
        == child["id"]
    )
    assert client.post("/api/campaigns", json=common).json()["agent_revision_id"] == child["id"]


def test_artifact_http_auth_integrity_and_absent_storage(settings, tmp_path):
    with TestClient(create_app(settings, PassingEvaluator())) as client:
        client.headers["Authorization"] = "Bearer " + OPERATOR
        assert client.get("/api/artifacts/" + "a" * 64).status_code == 503
    settings.artifact_dir = tmp_path / "artifacts"
    with TestClient(create_app(settings, PassingEvaluator())) as client:
        client.headers["Authorization"] = "Bearer " + OPERATOR
        manifest = client.post("/api/datasets", json=dataset().model_dump(mode="json")).json()
        identity = manifest["parquet"]["id"]
        response = client.get("/api/artifacts/" + identity)
        assert (
            response.content.startswith(b"PAR1")
            and identity in response.headers["content-disposition"]
        )
        assert client.get("/api/artifacts/" + "a" * 64).status_code == 404
        assert client.get("/api/artifacts/invalid").status_code == 409
        client.headers.clear()
        assert client.get("/api/artifacts/" + identity).status_code == 401


def seed_candidate(store, *, symbol="SPY", passed=True, source_hash=None):
    data = dataset().model_copy(update={"symbol": symbol})
    ds = import_dataset(store, data, "test")
    with store.transaction() as conn:
        store.append(
            conn,
            "candidate",
            {
                "id": "forward",
                "source": SOURCE,
                "source_hash": source_hash or digest(SOURCE),
                "dataset_id": ds["id"],
            },
            "forward",
        )
        if passed:
            store.append(
                conn,
                "candidate-result",
                {
                    "id": "forward",
                    "status": "PASS",
                    "at": "2026-09-10T00:00:00Z",
                    "public": {
                        "verdict": "PASS",
                        "protocol": "generated-research-v1",
                        "grammar": "signal-python-v1",
                    },
                    "hidden": {"verdict": "PASS", "score": 1},
                },
            )
    return data


def test_forward_admission_status_api_is_idempotent(client):
    seed_candidate(client.app.state.store)
    first = client.post("/api/candidates/forward/paper")
    assert first.status_code == 200
    assert client.post("/api/candidates/forward/paper").json() == first.json()
    assert len(client.get("/api/forward").json()["accounts"]) == 1


@pytest.mark.parametrize(
    "mode,error",
    [
        ("unvalidated", "INDEPENDENT_VALIDATION_REQUIRED"),
        ("universe", "FORWARD_UNIVERSE_NOT_ADMITTED"),
        ("history", "FORWARD_HISTORY_REQUIRED"),
        ("no_admission", "FORWARD_ADMISSION_REQUIRED"),
        ("hash", "SOURCE_HASH_MISMATCH"),
        ("price", "INVALID_FEED_PRICE"),
    ],
)
def test_forward_rejects_untrusted_or_incomplete_state(settings, mode, error):
    store = Store(settings.database_url)
    store.initialize()
    data = seed_candidate(
        store,
        symbol="AAPL" if mode == "universe" else "SPY",
        passed=mode != "unvalidated",
        source_hash="bad" if mode == "hash" else None,
    )
    paper = ForwardPaper(store)
    with pytest.raises(ValueError, match=error):
        if mode != "no_admission":
            paper.admit("forward", "operator")
        clock = datetime.fromisoformat(data.bars[-1].available_at) + timedelta(seconds=1)
        quote = {
            "timestamp": clock.isoformat(),
            "prices": {"SPY": -1 if mode == "price" else data.bars[-1].close},
        }
        paper.step(
            "forward",
            data.model_copy(update={"bars": data.bars[:100]}) if mode == "history" else data,
            quote,
            clock=clock,
        )


def test_hidden_service_invalid_candidates_private_dataset_and_query_limit(
    settings, tmp_path, monkeypatch
):
    private = tmp_path / "hidden.json"
    private.write_text(dataset().model_dump_json())
    settings.hidden_dataset_path = private
    with TestClient(service.create_evaluator(settings)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        client.headers["Authorization"] = "Bearer " + EVALUATOR
        payload = {"experiment_id": "private", "source": SOURCE, "symbol": "SPY"}
        assert set(client.post("/evaluate-program", json=payload).json()) == {"verdict", "score"}
        assert client.post(
            "/evaluate-program", json={**payload, "experiment_id": "wrong-symbol", "symbol": "QQQ"}
        ).json() == {"verdict": "FAIL", "score": -10}
        monkeypatch.setattr(service, "evaluate", Mock(side_effect=ValueError("invalid data")))
        assert client.post(
            "/evaluate", json={"experiment_id": "invalid", "spec": spec().model_dump(mode="json")}
        ).json() == {"verdict": "FAIL", "score": -10}
        store = Store(settings.evaluator_database_url)
        with store.transaction() as conn:
            store.set_state(conn, "query-budget", {"used": PROTOCOL.query_limit})
        assert (
            client.post(
                "/evaluate-program", json={**payload, "experiment_id": "over-budget"}
            ).status_code
            == 429
        )
