"""Ordinary API/worker requests cannot select a combined or fixture generator."""

from unittest.mock import Mock

import pytest
from test_autonomous import candidate, dataset, evidence
from test_campaign_recovery import prepared

from adaptive_alpha.domain import new_id, now
from adaptive_alpha.research import campaigns as module
from adaptive_alpha.research.contracts import CampaignRequest
from adaptive_alpha.research.datasets import import_dataset


def test_default_api_path_and_server_owned_scope(client):
    data = import_dataset(client.app.state.store, dataset(), "test")
    request = dict(
        objective="Research a falsifiable effect",
        query="momentum",
        dataset_id=data["id"],
        model="fixture",
    )
    response = client.post("/api/campaigns", json=request)
    assert response.status_code == 202
    campaign = response.json()
    assert campaign["engineer"] == "ouroboros"
    assert campaign["generation_path"] == "research-spec-ouroboros-v1"
    assert campaign["scope"] == "internal-paper" and not campaign["capital_eligible"]
    for override in (
        {"engineer": "openai"},
        {"generation_path": "controlled-fixture"},
        {"scope": "live"},
        {"capital_eligible": True},
        {"generate": "arbitrary"},
    ):
        assert client.post("/api/campaigns", json={**request, **override}).status_code == 422


@pytest.mark.parametrize("engineer", ["openai", "unknown", None])
def test_persisted_retired_request_fails_before_any_external_call(settings, monkeypatch, engineer):
    store, pipeline, _, _ = prepared(settings)
    identity = new_id()
    with store.transaction() as conn:
        dataset_id = store.list_records(conn, "dataset")[0]["manifest"]["id"]
        legacy = {
            "id": identity,
            **CampaignRequest(
                objective="Preserve historical request",
                query="momentum",
                dataset_id=dataset_id,
                model="fixture",
            ).model_dump(),
            "engineer": engineer,
            "created_at": now(),
        }
        store.append(conn, "campaign", legacy, identity)
        store.set_state(
            conn,
            "campaign:" + identity,
            {"status": "QUEUED", "attempts": 0, "tokens_charged": 0, "lease": None},
        )
    blocked = Mock(side_effect=AssertionError("External call on retired request"))
    monkeypatch.setattr(module, "search_sources", blocked)
    monkeypatch.setattr(module, "implement_research", blocked)
    monkeypatch.setattr(module.OpenAIProvider, "generate", blocked)
    claimed = pipeline.claim()
    assert claimed[0]["id"] == identity
    outcome = pipeline.run(*claimed)
    assert outcome["status"] == "FAILED" and outcome["reason"] == "RETIRED_GENERATION_PATH"
    assert outcome["attempts"] == outcome["tokens_charged"] == 0
    blocked.assert_not_called()
    with store.transaction() as conn:
        assert store.get(conn, identity, "campaign") == legacy
        assert store.verify_audit(conn)


def test_controlled_fixture_is_labelled_in_retained_artifacts(settings):
    ev = evidence()
    store, pipeline, campaign, claimed = prepared(settings, generations=1)
    assert (
        pipeline.run(
            *claimed,
            generate=lambda *_: (candidate(ev.id), {}),
            search=lambda _: [ev],
            hidden=lambda *_: {"verdict": "FAIL", "score": 0},
        )["status"]
        == "COMPLETED"
    )
    with store.transaction() as conn:
        for kind in ("candidate", "autonomous-attempt"):
            record = store.related(conn, kind, "campaign_id", campaign["id"])[0]
            assert record["generation_path"] == "controlled-fixture"
        artifact = store.list_records(conn, "candidate")[0]
        assert not artifact["capital_eligible"] and artifact["scope"] == "internal-paper"


def test_missing_ouroboros_never_falls_back_to_combined_openai(settings, monkeypatch):
    _, pipeline, _, claimed = prepared(settings, generations=1)
    ev = evidence()
    forbidden = Mock(side_effect=AssertionError("Unexpected model call"))
    monkeypatch.setattr(module.OpenAIProvider, "generate", forbidden)
    monkeypatch.setattr(module.OpenAIProvider, "structured", forbidden)
    result = pipeline.run(*claimed, search=lambda _: [ev])
    assert result["reason"] == "ISOLATED_OUROBOROS_NOT_CONFIGURED"
    forbidden.assert_not_called()
