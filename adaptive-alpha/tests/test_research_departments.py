"""Separate replication and novel research workflow acceptance."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_autonomous import candidate, dataset, evidence
from test_evidence_packets import packet_for

from adaptive_alpha.domain import digest
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import CampaignRequest
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.departments import (
    DepartmentPolicy,
    append_memory,
    frozen_policy,
    memory_context,
    policy_for,
    queue_counts,
    validate_department_packet,
)
from adaptive_alpha.research.evidence import Department
from adaptive_alpha.store import Store


def request(dataset_id: str, department: Department, objective: str) -> CampaignRequest:
    return CampaignRequest.model_validate(
        {
            "objective": objective,
            "query": "momentum trading costs",
            "dataset_id": dataset_id,
            "model": "fixture",
            "generations": 1,
            "token_budget": 4000,
            "department": department,
        }
    )


def test_separate_department_workers_claim_only_own_queue(settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    snapshot = import_dataset(store, dataset(), "operator")
    campaigns = Campaigns(store, settings)
    novel = campaigns.create(
        request(snapshot["id"], "novel", "Find a distinct falsifiable market mechanism"),
        "operator",
    )
    replication = campaigns.create(
        request(snapshot["id"], "replication", "Reproduce a published market mechanism"),
        "operator",
    )

    replication_claim = campaigns.claim("replication")
    assert replication_claim is not None and replication_claim[0]["id"] == replication["id"]
    assert campaigns.claim("replication") is None
    novel_claim = campaigns.claim("novel")
    assert novel_claim is not None and novel_claim[0]["id"] == novel["id"]
    with store.transaction() as conn:
        assert store.state(conn, "campaign:" + replication["id"])["worker_department"] == (
            "replication"
        )
        assert store.state(conn, "campaign:" + novel["id"])["worker_department"] == "novel"
        store.append(
            conn,
            "campaign",
            {
                "id": "legacy-unbound",
                "department": "replication",
                "max_seconds": 30,
            },
            "legacy-unbound",
        )
        store.set_state(
            conn,
            "campaign:legacy-unbound",
            {"status": "QUEUED", "attempts": 0, "tokens_charged": 0, "lease": None},
        )
        store.set_state(
            conn,
            "campaign:000-orphan",
            {"status": "QUEUED", "attempts": 0, "tokens_charged": 0, "lease": None},
        )
    assert campaigns.claim("replication") is None
    assert campaigns.claim("novel") is None
    with store.transaction() as conn:
        assert store.state(conn, "campaign:legacy-unbound")["status"] == "QUEUED"
        assert store.verify_audit(conn)
        store.set_state(conn, "campaign:legacy-unbound", {"status": "CANCELLED"})
        store.append(
            conn,
            "campaign",
            {"id": "legacy-weird", "department": "invalid", "max_seconds": 30},
            "legacy-weird",
        )
        store.set_state(conn, "campaign:legacy-weird", {"status": "CANCELLED"})
        assert queue_counts(conn, store) == {
            "replication": {"queued": 0, "running": 1},
            "novel": {"queued": 0, "running": 1},
        }
    assert campaigns.claim() is None
    store.engine.dispose()


def test_department_budget_memory_and_result_policy_are_isolated(settings, monkeypatch) -> None:
    store = Store(settings.database_url)
    store.initialize()
    snapshot = import_dataset(store, dataset(), "operator")
    campaigns = Campaigns(store, settings)
    item = evidence()
    contexts = {}

    def run(department: Department, objective: str):
        created = campaigns.create(request(snapshot["id"], department, objective), "operator")
        claimed = campaigns.claim(department)
        assert claimed is not None

        def generate(_model, context, _budget):
            contexts[created["id"]] = context
            return candidate(item.id), {"input_tokens": 10, "output_tokens": 20}

        outcome = campaigns.run(
            *claimed,
            generate=generate,
            search=lambda _: [item],
            hidden=lambda *_: {"verdict": "PASS", "score": 1},
        )
        assert outcome["status"] == "COMPLETED"
        return created

    first_replication = run("replication", "Reproduce the retained momentum publication")
    second_replication = run("replication", "Recheck the publication under another sample")
    first_novel = run("novel", "Find a distinct mechanism after scoped literature search")

    assert contexts[first_replication["id"]]["department_memory"] == []
    replication_memory = contexts[second_replication["id"]]["department_memory"]
    assert len(replication_memory) == 1
    assert contexts[first_novel["id"]]["department_memory"] == []
    with store.transaction() as conn:
        attempts = store.related(
            conn, "autonomous-attempt", "campaign_id", second_replication["id"]
        )
        assert attempts[0]["department_memory_ids"] == [replication_memory[0]["id"]]
        records = store.list_records(conn, "research-memory")
        serialized = json.dumps(records)
        assert "hidden" not in serialized and "def signal" not in serialized
        assert "instruction" not in serialized and all(
            record["authority"] == "research-only" and not record["capital_eligible"]
            for record in records
        )
        with pytest.raises(ValueError, match="DEPARTMENT_MEMORY_NAMESPACE_MISMATCH"):
            memory_context(
                conn,
                store,
                "novel",
                identities=[replication_memory[0]["id"]],
            )
        first_candidate = store.related(conn, "candidate", "campaign_id", first_replication["id"])[
            0
        ]
        first_result = store.related(
            conn, "candidate-result", "campaign_id", first_replication["id"]
        )[0]
        retained_memory = append_memory(
            conn, store, first_replication, first_candidate, first_result
        )
        assert append_memory(conn, store, first_replication, first_candidate, first_result) == (
            retained_memory
        )
        counts = queue_counts(conn, store)
        assert counts == {
            "replication": {"queued": 0, "running": 0},
            "novel": {"queued": 0, "running": 0},
        }

    original_get = store.get

    def conflicting_memory(conn, identity, kind=None):
        if identity == retained_memory["id"]:
            return {**retained_memory, "outcome": "CONFLICT"}
        return original_get(conn, identity, kind)

    monkeypatch.setattr(store, "get", conflicting_memory)
    with (
        store.transaction() as conn,
        pytest.raises(ValueError, match="DEPARTMENT_MEMORY_IDENTITY_CONFLICT"),
    ):
        append_memory(conn, store, first_replication, first_candidate, first_result)
    monkeypatch.setattr(store, "get", original_get)

    for campaign in (first_replication, second_replication, first_novel):
        policy = frozen_policy(campaign)
        assert campaign["budget"] == {
            "id": campaign["budget"]["id"],
            "campaign_id": campaign["id"],
            "department_policy_id": policy.id,
            "scope": "campaign",
            "token_limit": 4000,
        }
        assert campaign["capital_eligible"] is False and policy.capital_eligible is False
    assert (
        validate_department_packet(
            policy_for("replication"), packet_for("replication-policy", "replication")
        )
        == "source_bound_replication"
    )
    assert (
        validate_department_packet(policy_for("novel"), packet_for("novel-policy", "novel"))
        == "scoped_distinct_mechanism"
    )
    with pytest.raises(ValueError, match="DEPARTMENT_EVIDENCE_POLICY_MISMATCH"):
        validate_department_packet(
            policy_for("novel"), packet_for("wrong-department", "replication")
        )

    replication_policy = policy_for("replication")
    policy_payload = replication_policy.model_dump(mode="json")
    with pytest.raises(ValidationError, match="DEPARTMENT_POLICY_NAMESPACE_MISMATCH"):
        DepartmentPolicy.model_validate({**policy_payload, "queue": "novel"})
    with pytest.raises(ValidationError, match="DEPARTMENT_POLICY_IDENTITY_INVALID"):
        DepartmentPolicy.model_validate({**policy_payload, "id": "department-policy-" + "0" * 64})
    with pytest.raises(ValueError, match="DEPARTMENT_CAMPAIGN_BINDING_INVALID"):
        frozen_policy({**first_replication, "budget": "invalid"})
    with pytest.raises(ValueError, match="DEPARTMENT_CAMPAIGN_BINDING_INVALID"):
        frozen_policy(
            {
                **first_replication,
                "budget": {**first_replication["budget"], "token_limit": 5000},
            }
        )
    custom_payload = replication_policy.model_dump(mode="json", exclude={"id"})
    custom_payload["accepted_evidence_statuses"] = ["NOVELTY_SEARCH_SCOPED"]
    custom_policy = DepartmentPolicy.model_validate(
        {"id": "department-policy-" + digest(custom_payload), **custom_payload}
    )
    custom_budget = {
        **first_replication["budget"],
        "department_policy_id": custom_policy.id,
    }
    custom_budget["id"] = digest(
        {key: value for key, value in custom_budget.items() if key != "id"}
    )
    with pytest.raises(ValueError, match="DEPARTMENT_CAMPAIGN_BINDING_INVALID"):
        frozen_policy(
            {
                **first_replication,
                "department_policy_id": custom_policy.id,
                "department_policy": custom_policy.model_dump(mode="json"),
                "budget": custom_budget,
            }
        )

    recovery = campaigns.create(
        request(snapshot["id"], "replication", "Reject an unbound recovery memory snapshot"),
        "operator",
    )
    claimed = campaigns.claim("replication")
    assert claimed is not None and claimed[0]["id"] == recovery["id"]
    with store.transaction() as conn:
        store.append(
            conn,
            "autonomous-attempt",
            {
                "id": "missing-memory-snapshot",
                "campaign_id": recovery["id"],
                "generation": 0,
            },
            "missing-memory-snapshot",
        )
        state = store.state(conn, "campaign:" + recovery["id"])
        state.update(resume_attempt_id="missing-memory-snapshot", attempts=1)
        store.set_state(conn, "campaign:" + recovery["id"], state)
    rejected = campaigns.run(*claimed, search=lambda _: [item])
    assert rejected["status"] == "FAILED"
    assert rejected["reason"] == "DEPARTMENT_MEMORY_SNAPSHOT_REQUIRED"
    store.engine.dispose()


def test_department_readiness_and_compose_are_explicit(client) -> None:
    store = client.app.state.store
    with store.transaction() as conn:
        store.set_state(
            conn,
            "research-worker:replication",
            {
                "heartbeat": 1,
                "department": "replication",
                "department_policy_id": policy_for("replication").id,
                "authority": "research-only",
                "capital_eligible": False,
            },
        )
    snapshot = client.post("/api/datasets/demo").json()
    for department in ("replication", "novel"):
        response = client.post(
            "/api/campaigns",
            json=request(
                snapshot["id"], department, f"Queue the {department} research department"
            ).model_dump(mode="json"),
        )
        assert response.status_code == 202
    readiness = client.get("/api/research/readiness").json()
    assert set(readiness["workers"]) == {"replication", "novel"}
    assert readiness["workers"]["replication"]["authority"] == "research-only"
    assert readiness["workers"]["novel"] == {}
    assert readiness["queues"] == {
        "replication": {"queued": 1, "running": 0},
        "novel": {"queued": 1, "running": 0},
    }
    assert all(
        not policy["capital_eligible"] for policy in readiness["department_policies"].values()
    )
    javascript = client.get("/assets/app.js").text
    assert "Replication worker" in javascript and "Novel-hypothesis worker" in javascript
    operations = client.get("/assets/operations.js").text
    assert "readiness.workers" in operations and "readiness.worker?" not in operations

    compose = (Path(__file__).parents[1] / "compose.yaml").read_text()
    assert "  novel-worker:\n" in compose
    assert compose.count("adaptive_alpha.research.worker") == 2
    assert "ALPHA_RESEARCH_DEPARTMENT: replication" in compose
    assert "ALPHA_RESEARCH_DEPARTMENT: novel" in compose
