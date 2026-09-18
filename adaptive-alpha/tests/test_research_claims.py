"""Passage-bound claims and department-aware economic-mechanism identity."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_autonomous import SOURCE, candidate, dataset, evidence
from test_engineering import spec
from test_evidence_packets import packet_for, paper, store_packet

import adaptive_alpha.research.campaigns as campaign_module
from adaptive_alpha.config import Settings
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import CampaignRequest
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.engineering import EngineeringRegistry
from adaptive_alpha.research.knowledge import (
    MechanismDescriptor,
    claim_record,
    mechanism_duplicate_reason,
    mechanism_identity,
)
from adaptive_alpha.research.roles import NoveltyAgent
from adaptive_alpha.store import Store


def bound_spec(packet, item):
    return spec(
        evidence_ids=[item.id],
        source_hashes=[item.content_hash],
        evidence_packet_id=packet.id,
        citation_anchors=[{"evidence_id": item.id, "passage_id": packet.passages[0].id}],
        evidence_gaps=list(packet.gaps),
    )


def claim_store(path: Path):
    store = Store(f"sqlite:///{path}")
    store.initialize()
    item = paper()
    packet = packet_for("campaign-claims")
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
    store_packet(store, packet, item)
    return store, item, packet


def test_claim_graph_is_bound_to_passages_and_work_order(tmp_path: Path) -> None:
    store, item, packet = claim_store(tmp_path / "claims.db")
    registry = EngineeringRegistry(store)
    research = bound_spec(packet, item)
    work = registry.create_work_order(research, "research", work_id="work-claims")
    expected = claim_record(work.id, work.spec_hash, research.evidence_claims[0])
    with store.transaction() as conn:
        claims = store.list_records(conn, "research-claim")
        mechanisms = store.list_records(conn, "research-mechanism")
        edges = store.list_records(conn, "knowledge-edge")
    assert claims == [expected]
    assert expected["anchor_verified"] and not expected["verified"]
    assert expected["semantic_status"] == "researcher_asserted"
    assert any(
        edge["from"] == research.evidence_claims[0].passage_id
        and edge["to"] == expected["id"]
        and edge["relation"] == "supports"
        and edge["anchor_verified"]
        and not edge["verified"]
        for edge in edges
    )
    assert any(
        edge["from"] == expected["id"]
        and edge["to"] == work.id
        and edge["relation"] == "specified_by"
        for edge in edges
    )
    assert mechanisms[0]["work_order_id"] == work.id
    assert mechanisms[0]["mechanism_family"] == "trend_continuation"
    assert not mechanisms[0]["verified"] and not mechanisms[0]["capital_eligible"]
    assert registry.create_work_order(research, "research", work_id=work.id) == work
    with store.transaction() as conn:
        assert len(store.list_records(conn, "research-claim")) == 1
        assert store.verify_audit(conn)
    store.engine.dispose()


def test_unbound_or_ambiguous_claims_fail_closed(tmp_path: Path) -> None:
    store, item, packet = claim_store(tmp_path / "invalid-claims.db")
    anchor = {"evidence_id": item.id, "passage_id": packet.passages[0].id}
    support = {
        "statement": "The retained passage supports continuation after estimated costs",
        "relation": "supports",
        **anchor,
    }
    invalid = (
        (
            {"evidence_packet_id": packet.id, "citation_anchors": [anchor], "evidence_claims": []},
            "EVIDENCE_CLAIMS_REQUIRED",
        ),
        (
            {
                "evidence_packet_id": packet.id,
                "citation_anchors": [anchor],
                "evidence_claims": [{**support, "passage_id": "c" * 64}],
            },
            "CLAIM_ANCHOR_UNBOUND",
        ),
        (
            {
                "evidence_packet_id": packet.id,
                "citation_anchors": [anchor],
                "evidence_claims": [support, support],
            },
            "EVIDENCE_CLAIM_DUPLICATE",
        ),
        (
            {
                "evidence_packet_id": packet.id,
                "citation_anchors": [anchor],
                "evidence_claims": [support],
                "contradictions": ["The effect disappears after realistic trading costs"],
            },
            "CONTRADICTION_CLAIM_REQUIRED",
        ),
        (
            {
                "evidence_packet_id": packet.id,
                "citation_anchors": [anchor],
                "evidence_claims": [{**support, "relation": "contradicts"}],
            },
            "CONTRADICTION_TEXT_REQUIRED",
        ),
        ({"evidence_claims": [support]}, "EVIDENCE_PACKET_REQUIRED_FOR_CLAIMS"),
        (
            {
                "mechanism": {
                    **spec().mechanism.model_dump(mode="json"),
                    "inputs": ["price", "price"],
                }
            },
            "MECHANISM_INPUT_DUPLICATE",
        ),
    )
    for updates, error in invalid:
        with pytest.raises(ValidationError, match=error):
            spec(
                evidence_ids=[item.id],
                source_hashes=[item.content_hash],
                evidence_gaps=list(packet.gaps),
                **updates,
            )

    research = bound_spec(packet, item)
    invented = research.model_copy(
        update={
            "citation_anchors": (
                research.citation_anchors[0].model_copy(update={"passage_id": "d" * 64}),
            ),
            "evidence_claims": (
                research.evidence_claims[0].model_copy(update={"passage_id": "d" * 64}),
            ),
        }
    )
    with pytest.raises(ValueError, match="SPEC_CITATION_ANCHOR_MISMATCH"):
        EngineeringRegistry(store).create_work_order(invented, "research")
    with store.transaction() as conn:
        assert store.list_records(conn, "work-order") == []
        assert store.list_records(conn, "research-claim") == []
    store.engine.dispose()


def test_mechanism_identity_drives_department_duplicate_policy(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = MechanismDescriptor(
        family="trend_continuation",
        premise="Slow information diffusion: trends persist!",
        inputs=("price", "return"),
        formation_horizon_bars=20,
        holding_horizon_bars=1,
    )
    cosmetic = first.model_copy(
        update={
            "premise": "  SLOW information diffusion — trends persist.  ",
            "inputs": ("return", "price"),
        }
    )
    changed_horizon = first.model_copy(update={"formation_horizon_bars": 60})
    identity = mechanism_identity(first)
    assert (
        mechanism_identity(cosmetic)["mechanism_fingerprint"] == identity["mechanism_fingerprint"]
    )
    assert (
        mechanism_identity(changed_horizon)["mechanism_fingerprint"]
        != identity["mechanism_fingerprint"]
    )
    assert (
        mechanism_identity(changed_horizon)["mechanism_family_fingerprint"]
        == identity["mechanism_family_fingerprint"]
    )
    generated = candidate("evidence")
    prior = [
        {
            "id": "prior-candidate",
            "hypothesis": generated.hypothesis,
            "novelty_diagnostic": identity,
        }
    ]
    diagnostic = NoveltyAgent().compare(generated, prior, cosmetic)
    assert diagnostic["mechanism_matches"] == ["prior-candidate"]
    assert diagnostic["mechanism_family_matches"] == ["prior-candidate"]
    assert mechanism_duplicate_reason("novel", diagnostic) is None
    diagnostic["external_mechanism_matches"] = ["prior-candidate"]
    assert mechanism_duplicate_reason("novel", diagnostic) == "DUPLICATE_MECHANISM"
    assert mechanism_duplicate_reason("replication", diagnostic) is None

    store = Store(settings.database_url)
    store.initialize()
    with store.transaction() as conn:
        store.append(conn, "research-claim", {"id": "claim-controlled"}, "claim-controlled")
        store.append(
            conn,
            "candidate-mechanism",
            {
                "id": "candidate-mechanism-prior",
                "candidate_id": "prior-external-candidate",
                "campaign_id": "prior-campaign",
                "mechanism_fingerprint": identity["mechanism_fingerprint"],
                "mechanism_family_fingerprint": identity["mechanism_family_fingerprint"],
            },
            "candidate-mechanism-prior",
        )
    snapshot = import_dataset(store, dataset(), "operator")
    pipeline = Campaigns(store, settings)
    pipeline.create(
        CampaignRequest(
            objective="Find a mechanism distinct from retained market hypotheses",
            query="trend continuation",
            dataset_id=snapshot["id"],
            model="fixture",
            generations=1,
            token_budget=4000,
            department="novel",
        ),
        "operator",
    )
    claimed = pipeline.claim()
    assert claimed is not None
    item = evidence()

    def implement(*_):
        created = candidate(item.id)
        created = created.model_copy(update={"source": SOURCE})
        return created, {}, {**identity, "research_claim_ids": ["claim-controlled"]}

    monkeypatch.setattr(campaign_module, "implement_research", implement)
    result = pipeline.run(
        *claimed,
        search=lambda _: [item],
        hidden=lambda *_: {"verdict": "PASS", "score": 1.0},
    )
    assert result["status"] == "COMPLETED"
    with store.transaction() as conn:
        outcomes = store.list_records(conn, "candidate-result")
        artifacts = store.list_records(conn, "candidate")
        indexed = store.list_records(conn, "candidate-mechanism")
        edges = store.list_records(conn, "knowledge-edge")
    duplicate = [item for item in outcomes if item.get("reason") == "DUPLICATE_MECHANISM"]
    assert len(duplicate) == 1 and duplicate[0]["status"] == "DUPLICATE"
    assert artifacts[0]["novelty_diagnostic"]["mechanism_matches"] == ["prior-external-candidate"]
    assert artifacts[0]["novelty_diagnostic"]["external_mechanism_matches"] == [
        "prior-external-candidate"
    ]
    assert {entry["candidate_id"] for entry in indexed} == {
        "prior-external-candidate",
        artifacts[0]["id"],
    }
    assert any(edge["relation"] == "motivates" for edge in edges)
    store.engine.dispose()


def test_claims_and_mechanisms_are_visible_to_operator(client) -> None:
    store = client.app.state.store
    item = paper()
    packet = packet_for("campaign-api-claims")
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
    store_packet(store, packet, item)
    research = bound_spec(packet, item)
    work = EngineeringRegistry(store).create_work_order(
        research, "research", work_id="work-api-claims"
    )
    response = client.get("/api/knowledge")
    assert response.status_code == 200
    body = response.json()
    assert body["claims"][0]["work_order_id"] == work.id
    assert body["claims"][0]["relation"] == "supports"
    assert body["claims"][0]["semantic_status"] == "researcher_asserted"
    assert body["mechanisms"][0]["mechanism_family"] == "trend_continuation"
    assert body["candidate_mechanisms"] == []
    javascript = client.get("/assets/app.js").text
    assert "semantic_status" in javascript
    assert "mechanism_family" in javascript and "research_claim_ids" in javascript
