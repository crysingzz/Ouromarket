"""HTTP authority, atomic paper admission and researcher/engineer integration."""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from conftest import OPERATOR, RESEARCH
from pydantic import SecretStr
from test_api_workflows import seed_candidate
from test_autonomous import evidence
from test_engineering import SOURCE, proposal, spec

from adaptive_alpha.domain import new_id
from adaptive_alpha.research import workflow
from adaptive_alpha.research.engineering import EngineeringRegistry, ImplementationBundle
from adaptive_alpha.research.forward import ForwardPaper


def move(client, identity, target):
    state = client.get(f"/api/lifecycle/{identity}").json()
    return client.post(
        f"/api/lifecycle/{identity}/transitions",
        json={
            "target": target,
            "expected_version": state["version"],
            "request_id": new_id(),
            "reason": "Operator reviewed retained evidence",
        },
    )


def test_lifecycle_http_gate_atomic_shadow_and_manual_demotion(client):
    store = client.app.state.store
    seed_candidate(store)
    assert client.get("/api/lifecycle").json()["unregistered"][0]["candidate_id"] == "forward"
    assert client.post("/api/lifecycle/forward/register").json()["status"] == "RESEARCH"
    assert (
        client.get("/api/lifecycle/forward/performance").json()["monitor"]["status"]
        == "NOT_ACTIVATED"
    )
    assert client.get("/api/lifecycle/missing/performance").status_code == 404
    assert move(client, "forward", "ACTIVE_LIMITED").status_code == 409
    assert move(client, "forward", "LAB_VALIDATED").json()["status"] == "LAB_VALIDATED"
    assert move(client, "forward", "SHADOW").json()["status"] == "SHADOW"
    assert len(client.get("/api/forward").json()["accounts"]) == 1
    assert move(client, "forward", "PAPER").json()["status"] == "PAPER"
    comparison = client.post("/api/strategy-comparisons", json={"challenger_id": "forward"})
    assert comparison.status_code == 201
    report = client.get(f"/api/strategy-comparisons/{comparison.json()['id']}").json()
    assert report["verdict"] == "PENDING" and report["matched_days"] == 0
    assert move(client, "forward", "CHALLENGER").status_code == 409
    assert client.post("/api/lifecycle/forward/monitor").json()["status"] == "PAPER"
    assert move(client, "forward", "DEMOTED").json()["status"] == "DEMOTED"
    assert client.post("/api/candidates/forward/paper").status_code == 409
    assert client.get("/api/rollback/SPY").json()["automatic_activation"] is False
    overview = client.get("/api/lifecycle").json()
    assert overview["unregistered"] == [] and len(overview["transitions"]) == 4
    assert overview["capital_eligible"] is False


@pytest.mark.parametrize(
    "path,method",
    [
        ("/lifecycle", "GET"),
        ("/lifecycle/x", "GET"),
        ("/lifecycle/x/register", "POST"),
        ("/lifecycle/x/transitions", "POST"),
        ("/strategy-comparisons", "POST"),
        ("/strategy-comparisons/x", "GET"),
        ("/lifecycle/x/monitor", "POST"),
        ("/lifecycle/x/performance", "GET"),
        ("/lifecycle/x/revalidate", "POST"),
        ("/rollback/SPY", "GET"),
        ("/engineering", "GET"),
        ("/engineering/artifacts/x", "GET"),
        ("/engineering/work-orders/x", "GET"),
        ("/engineering/bundles/x/benchmark", "POST"),
        ("/engineering/artifacts/x/promote", "POST"),
    ],
)
def test_research_identity_cannot_control_lifecycle_or_artifact_review(client, path, method):
    client.headers["Authorization"] = "Bearer " + RESEARCH
    response = client.request(method, "/api" + path, json={})
    assert response.status_code == 403
    client.headers["Authorization"] = "Bearer " + OPERATOR


def test_engineering_http_uses_retained_contract_not_supplied_score(client):
    store = client.app.state.store
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        store.append(conn, "evidence", {"content_hash": "b" * 64}, "paper")
    registry = EngineeringRegistry(store)
    work = registry.create_work_order(spec(), "research")
    bundle = registry.accept(
        ImplementationBundle(
            work_order_id=work.id, spec_hash=work.spec_hash, source=SOURCE, artifacts=(proposal(),)
        ),
        "ouroboros",
    )
    benchmark = client.post(f"/api/engineering/bundles/{bundle['id']}/benchmark").json()
    assert benchmark["passed"]
    assert (
        client.get(f"/api/engineering/work-orders/{work.id}").json()["spec_hash"] == work.spec_hash
    )
    artifact = bundle["artifact_ids"][1]
    assert (
        client.get(f"/api/engineering/artifacts/{artifact}").json()["execution"] == "inert_proposal"
    )
    assert (
        client.post(
            f"/api/engineering/artifacts/{artifact}/promote",
            json={
                "benchmark_id": benchmark["id"],
                "passed": True,
            },
        ).status_code
        == 422
    )
    review = client.post(
        f"/api/engineering/artifacts/{artifact}/promote", json={"benchmark_id": benchmark["id"]}
    ).json()
    assert review["status"] == "REVIEWED_PROPOSAL" and review["capital_eligible"] is False
    view = client.get("/api/engineering").json()
    assert (
        len(view["artifacts"]) == 2
        and view["attempts"] == []
        and view["arbitrary_execution_enabled"] is False
    )


@pytest.mark.parametrize("mode", ["valid", "wrong_dataset", "failed_contract"])
def test_researcher_frozen_spec_drives_ouroboros_implementation(
    client, settings, monkeypatch, mode
):
    store = client.app.state.store
    settings.ouroboros_url, settings.ouroboros_workspace = "https://isolated.test", "/workspace"
    settings.openai_api_key = SecretStr("fixture-key")
    ev = evidence()
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        store.append(conn, "evidence", ev.model_dump(), ev.id)
    research = spec(
        dataset_id="other" if mode == "wrong_dataset" else "dataset",
        evidence_ids=[ev.id],
        source_hashes=[ev.content_hash],
    )

    def produce(self, model, context, budget, response_type, instructions):
        assert "not code" in instructions and context["dataset_hash"] == "a" * 64
        assert (
            response_type is type(research) and context["source_hashes"][ev.id] == ev.content_hash
        )
        return research, {"reserved": budget, "input_tokens": 50}

    def implement(self, order, timeout):
        assert order.spec == research and timeout == 100
        return ImplementationBundle(
            work_order_id=order.id,
            spec_hash=order.spec_hash,
            source=SOURCE if mode == "valid" else "def signal(history):\n    return 0.0\n",
        )

    monkeypatch.setattr(workflow.OpenAIProvider, "structured", produce)
    monkeypatch.setattr(workflow.OuroborosEngineer, "implement", implement)
    check = Mock()
    args = (
        store,
        settings,
        "fixture",
        {"evidence": [{"id": ev.id}], "campaign_id": "campaign", "attempt_id": "attempt"},
        "dataset",
        40000,
        100,
        check,
    )
    if mode != "valid":
        with pytest.raises(
            ValueError, match="INPUT_MISMATCH" if mode == "wrong_dataset" else "CONTRACT_FAILED"
        ):
            workflow.implement_research(*args)
        if mode == "failed_contract":
            attempt = EngineeringRegistry(store).list_attempts()[0]
            assert attempt["status"] == "FAILED"
            assert attempt["reason"] == "IMPLEMENTATION_CONTRACT_FAILED"
        return
    result, usage, artifact = workflow.implement_research(*args)
    assert result.hypothesis == research.hypothesis and result.source == SOURCE
    assert usage["implementation_provider"] == "ouroboros" and check.call_count == 3
    registry = EngineeringRegistry(store)
    assert registry.get_work_order(artifact["work_order_id"]).spec == research
    attempt = registry.list_attempts()[0]
    assert artifact["engineering_attempt_id"] == attempt["id"]
    assert attempt["status"] == "SUCCEEDED" and attempt["benchmark_id"]


@pytest.mark.parametrize("mode", ["normal", "stale", "crash"])
def test_forward_observations_and_risk_demotion_are_connected(client, mode):
    store = client.app.state.store
    data = seed_candidate(store)
    assert client.post("/api/candidates/forward/paper").status_code == 200
    paper = ForwardPaper(store)
    with pytest.raises(ValueError, match="OPERATOR_REQUIRED"):
        paper.admit("forward", "research")
    clock = datetime.fromisoformat(data.bars[-1].time) + timedelta(seconds=1)
    quote = {"timestamp": clock.isoformat(), "prices": {"SPY": data.bars[-1].close}}
    assert paper.step("forward", data, quote, clock=clock)["status"] in {"FILLED", "NO_TRADE"}
    with store.transaction() as conn:
        assert len(store.list_records(conn, "lifecycle-observation")) == 1
    if mode == "normal":
        assert paper.step("forward", data, quote, clock=clock)["status"] == "NO_NEW_BAR"
        with store.transaction() as conn:
            store.set_state(conn, "kill", {"halted": True})
        paper.step("forward", data, quote, clock=clock)
    elif mode == "stale":
        assert (
            paper.step("forward", data, quote, clock=clock + timedelta(seconds=61))["status"]
            == "HALT"
        )
    else:
        with store.transaction() as conn:
            account = store.state(conn, "forward:forward")
            account.update(cash=80000, positions={"SPY": 100}, nav=100000)
            store.set_state(conn, "forward:forward", account)
        assert (
            paper.step("forward", data, {**quote, "prices": {"SPY": 1}}, clock=clock)["status"]
            == "HALT"
        )
    assert client.get("/api/lifecycle/forward").json()["status"] == "DEMOTED"
    with pytest.raises(ValueError, match="FORWARD_ADMISSION_REQUIRED"):
        paper.step("forward", data, quote, clock=clock)
