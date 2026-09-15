from conftest import EVALUATOR, RESEARCH
from fastapi.testclient import TestClient

from adaptive_alpha.domain import StrategySpec
from adaptive_alpha.evaluation.service import create_evaluator


def test_hidden_is_minimal_authenticated_durable_and_bounded(settings):
    payload = {
        "experiment_id": "e1",
        "spec": StrategySpec(name="Hidden test", hypothesis_id="h", thesis="Test").model_dump(
            mode="json"
        ),
    }
    with TestClient(create_evaluator(settings)) as client:
        assert client.post("/evaluate", json=payload).status_code == 401
        client.headers["Authorization"] = f"Bearer {RESEARCH}"
        assert client.post("/evaluate", json=payload).status_code == 401
        client.headers["Authorization"] = f"Bearer {EVALUATOR}"
        response = client.post("/evaluate", json=payload)
        assert response.status_code == 200
        assert set(response.json()) == {"verdict", "score"}
        assert client.get("/docs").status_code == 404
        assert client.get("/datasets").status_code == 404
        assert client.post("/evaluate", json=payload).json() == response.json()
        assert (
            client.post(
                "/evaluate", json={**payload, "spec": {**payload["spec"], "lookback": 21}}
            ).status_code
            == 409
        )
    with TestClient(create_evaluator(settings)) as client:
        client.headers["Authorization"] = f"Bearer {EVALUATOR}"
        assert client.post("/evaluate", json=payload).json() == response.json()
        from adaptive_alpha.store import Store

        store = Store(settings.evaluator_database_url)
        with store.transaction() as conn:
            store.set_state(conn, "query-budget", {"used": 50})
        assert client.post("/evaluate", json={**payload, "experiment_id": "new"}).status_code == 429
