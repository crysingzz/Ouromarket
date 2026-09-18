from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import OPERATOR, RESEARCH
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from adaptive_alpha.api.app import create_app
from adaptive_alpha.domain import OrderIntent, StrategySpec


def create_job(client, count=3):
    response = client.post(
        "/api/research/jobs",
        json={
            "objective": "Test daily momentum after costs",
            "budget": {"max_experiments": count, "compute_seconds": 30, "llm_tokens": 0},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def paper_strategy(client):
    h = client.post(
        "/api/hypotheses",
        json={
            "statement": "Test",
            "economic_rationale": "Test",
            "supporting_evidence": [],
            "contradictory_evidence": [],
            "expected_regime": "Trend",
            "expected_failure_modes": [],
            "proposed_test": "Test",
        },
    ).json()
    s = StrategySpec(name="Test paper", hypothesis_id=h["id"], thesis="Test")
    assert client.post("/api/strategies", json=s.model_dump(mode="json")).status_code == 201
    # Test fixture only: simulate the trusted evaluator's state transition.
    store = client.app.state.store
    with store.transaction() as conn:
        store.set_state(
            conn, f"strategy:{s.id}", {"status": "VALIDATED", "capital_eligible": False}
        )
    assert client.post(f"/api/strategies/{s.id}/paper", json={}).status_code == 200
    return s.id


def test_full_research_generations_and_duplicates(client):
    job_id = create_job(client)
    run = client.post(f"/api/research/jobs/{job_id}/run", json={})
    assert run.status_code == 200
    assert run.json()["status"] == "COMPLETED"
    assert run.json()["experiments"] == 3
    experiments = client.get("/api/experiments").json()
    assert len(experiments) == 3
    assert {e["generation"] for e in experiments} == {0, 1, 2}
    assert all(e["dataset_versions"][0]["content_hash"] for e in experiments)
    assert all(e["hidden"] == {"verdict": "PASS", "score": 1.5} for e in experiments)
    assert all(e["capital_eligible"] is False for e in experiments)
    assert client.post(f"/api/research/jobs/{job_id}/run", json={}).status_code == 409
    next_id = create_job(client, 1)
    client.post(f"/api/research/jobs/{next_id}/run", json={})
    assert any(e["status"] == "DUPLICATE" for e in client.get("/api/experiments").json())
    assert client.get("/api/audit").json()["verified"] is True


def test_auth_and_agent_capital_boundaries(client):
    client.headers.clear()
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/healthz").status_code == 200
    client.headers["Authorization"] = f"Bearer {RESEARCH}"
    assert client.get("/api/risk/limits").status_code == 200
    assert client.get("/api/strategies").status_code == 200
    for path in (
        "/api/orders",
        "/api/risk/halt",
        "/api/risk/resume",
        "/api/risk/check",
        "/api/market/demo-refresh",
    ):
        assert client.post(path, json={}).status_code == 403
    assert client.get("/api/portfolio").status_code == 403
    assert client.get("/api/audit").status_code == 403
    assert client.get("/api/openapi.json").status_code == 403


def test_immutable_records_and_audit(client):
    create_job(client)
    store = client.app.state.store
    for statement in (
        "UPDATE records SET payload='{}'",
        "DELETE FROM records",
        "DELETE FROM events",
        "UPDATE events SET hash='x'",
    ):
        with pytest.raises(DatabaseError), store.transaction() as conn:
            conn.execute(text(statement))


def test_order_idempotency_concurrency_and_risk(client):
    strategy_id = paper_strategy(client)
    intent = OrderIntent(
        strategy_id=strategy_id, instrument="SPY", side="BUY", quantity=2
    ).model_dump()
    execution = client.app.state.execution
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: execution.check(OrderIntent(**intent), True, "operator"), range(4))
        )
    assert all(result == results[0] for result in results)
    assert results[0]["status"] == "FILLED"
    assert client.get("/api/portfolio").json()["positions"]["SPY"] == 2
    assert len(client.get("/api/fills").json()) == 1
    assert client.post("/api/orders", json={**intent, "quantity": 3}).status_code == 409
    rejected = client.post(
        "/api/orders", json={**intent, "order_intent_id": "too-large", "quantity": 100000}
    ).json()
    assert rejected["decision"]["status"] == "REJECT"
    assert len(client.get("/api/fills").json()) == 1


def test_kill_switch_and_resume(client):
    strategy_id = paper_strategy(client)
    client.post("/api/risk/halt", json={"reason": "Test emergency stop"})
    intent = OrderIntent(
        strategy_id=strategy_id, instrument="SPY", side="BUY", quantity=1
    ).model_dump()
    assert client.post("/api/orders", json=intent).json()["decision"]["status"] == "HALT"
    assert client.post("/api/risk/resume", json={"reason": "Operator recovery"}).status_code == 200
    assert (
        client.post("/api/orders", json={**intent, "order_intent_id": "new-order"}).json()["status"]
        == "FILLED"
    )


def test_stale_data_and_reconciliation_fail_closed(client):
    strategy_id = paper_strategy(client)
    store = client.app.state.store
    with store.transaction() as conn:
        quotes = store.state(conn, "quotes")
        quotes["timestamp"] = "2000-01-01T00:00:00+00:00"
        store.set_state(conn, "quotes", quotes)
    intent = OrderIntent(
        strategy_id=strategy_id, instrument="SPY", side="BUY", quantity=1
    ).model_dump()
    assert client.post("/api/orders", json=intent).json()["decision"]["status"] == "HALT"
    with store.transaction() as conn:
        store.set_state(conn, "broker", {"cash": 99999, "positions": {}})
    assert client.post("/api/risk/resume", json={"reason": "Test recovery"}).status_code == 409


def test_cancel_created_job(client):
    job_id = create_job(client)
    assert (
        client.post(f"/api/research/jobs/{job_id}/cancel", json={}).json()["status"] == "CANCELLED"
    )
    assert client.post(f"/api/research/jobs/{job_id}/run", json={}).status_code == 409


def test_strict_inputs_and_security_headers(client):
    assert (
        client.post(
            "/api/research/jobs", json={"objective": "Test hypothesis", "risk_limits": {}}
        ).status_code
        == 422
    )
    with pytest.raises(ValidationError):
        OrderIntent(strategy_id="s", instrument="SPY", side="BUY", quantity=-1)
    with pytest.raises(ValidationError):
        StrategySpec(name="Test", hypothesis_id="h", thesis="Test", position_fraction=float("nan"))
    response = client.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.post("/api/research/jobs", content="x" * 65537).status_code == 413


def test_evaluator_outage_preserves_attempts(settings):
    from fastapi.testclient import TestClient

    class Down:
        def evaluate(self, experiment_id, spec):
            raise ConnectionError("secret must never be returned")

    with TestClient(create_app(settings, Down())) as client:
        client.headers["Authorization"] = f"Bearer {OPERATOR}"
        job_id = create_job(client, 1)
        client.post(f"/api/research/jobs/{job_id}/run", json={})
        experiments = client.get("/api/experiments").json()
        assert experiments[0]["status"] == "ERROR"
        assert "secret must" not in str(experiments)
        assert len(client.get("/api/attempts").json()) == 1


def test_restart_preserves_kill_and_records(settings):
    from conftest import PassingEvaluator
    from fastapi.testclient import TestClient

    with TestClient(create_app(settings, PassingEvaluator())) as client:
        client.headers["Authorization"] = f"Bearer {OPERATOR}"
        create_job(client, 1)
        client.post("/api/risk/halt", json={"reason": "Persistent stop"})
    with TestClient(create_app(settings, PassingEvaluator())) as client:
        client.headers["Authorization"] = f"Bearer {OPERATOR}"
        assert client.get("/api/risk/status").json()["halted"] is True
        assert len(client.get("/api/research/jobs").json()) == 1


def test_order_must_belong_to_strategy_universe(client):
    strategy_id = paper_strategy(client)
    response = client.post(
        "/api/orders",
        json=OrderIntent(
            strategy_id=strategy_id, instrument="QQQ", side="BUY", quantity=1
        ).model_dump(),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "INSTRUMENT_OUTSIDE_STRATEGY_UNIVERSE"
    assert client.get("/api/fills").json() == []


def test_identities_must_not_share_tokens(settings):
    from conftest import PassingEvaluator
    from pydantic import SecretStr

    settings.evaluator_token = SecretStr(RESEARCH)
    with pytest.raises(ValueError, match="distinct tokens"):
        create_app(settings, PassingEvaluator())


def test_unvalidated_strategy_cannot_enter_paper(client):
    job_id = create_job(client, 1)
    client.post(f"/api/research/jobs/{job_id}/run", json={})
    strategy = client.get("/api/strategies").json()[0]
    assert strategy["status"] == "REJECTED"
    assert client.post(f"/api/strategies/{strategy['id']}/paper", json={}).status_code == 409
