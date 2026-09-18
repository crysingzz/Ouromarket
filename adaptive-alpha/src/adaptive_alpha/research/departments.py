"""Server-owned research department policies, memory and queue diagnostics."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.engine import Connection

from adaptive_alpha.domain import Contract, digest, now
from adaptive_alpha.research.evidence import Department, ResearchEvidencePacket
from adaptive_alpha.store import Store, states

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PolicyId = Annotated[str, Field(pattern=r"^department-policy-[a-f0-9]{64}$")]
ResultCriterion = Literal["source_bound_replication", "scoped_distinct_mechanism"]


class DepartmentPolicy(Contract):
    id: PolicyId
    department: Department
    queue: Literal["replication", "novel"]
    memory_namespace: Literal["replication", "novel"]
    budget_scope: Literal["campaign"] = "campaign"
    result_criterion: ResultCriterion
    accepted_evidence_statuses: tuple[str, ...] = Field(min_length=1, max_length=3)
    version: Literal["research-department-v1"] = "research-department-v1"
    authority: Literal["research-only"] = "research-only"
    capital_eligible: Literal[False] = False

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"id"})

    @model_validator(mode="after")
    def identity_and_namespaces_match(self) -> DepartmentPolicy:
        if self.queue != self.department or self.memory_namespace != self.department:
            raise ValueError("DEPARTMENT_POLICY_NAMESPACE_MISMATCH")
        if self.id != "department-policy-" + digest(self.identity_payload()):
            raise ValueError("DEPARTMENT_POLICY_IDENTITY_INVALID")
        return self


def _policy(
    department: Department,
    result_criterion: ResultCriterion,
    accepted_evidence_statuses: tuple[str, ...],
) -> DepartmentPolicy:
    payload = {
        "department": department,
        "queue": department,
        "memory_namespace": department,
        "budget_scope": "campaign",
        "result_criterion": result_criterion,
        "accepted_evidence_statuses": accepted_evidence_statuses,
        "version": "research-department-v1",
        "authority": "research-only",
        "capital_eligible": False,
    }
    return DepartmentPolicy.model_validate(
        {"id": "department-policy-" + digest(payload), **payload}
    )


POLICIES: dict[Department, DepartmentPolicy] = {
    "replication": _policy(
        "replication",
        "source_bound_replication",
        ("REPLICATION_EVIDENCE_INCOMPLETE", "REPLICATION_EVIDENCE_AVAILABLE"),
    ),
    "novel": _policy("novel", "scoped_distinct_mechanism", ("NOVELTY_SEARCH_SCOPED",)),
}


def policy_for(department: Department) -> DepartmentPolicy:
    return POLICIES[department]


def frozen_policy(campaign: dict[str, Any]) -> DepartmentPolicy:
    try:
        policy = DepartmentPolicy.model_validate(campaign["department_policy"])
    except (KeyError, ValueError) as error:
        raise ValueError("DEPARTMENT_POLICY_REQUIRED") from error
    budget = campaign.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("DEPARTMENT_CAMPAIGN_BINDING_INVALID")
    expected_policy = POLICIES.get(policy.department)
    if (
        expected_policy is None
        or policy != expected_policy
        or campaign.get("department") != policy.department
        or campaign.get("department_policy_id") != policy.id
        or budget.get("scope") != "campaign"
        or budget.get("token_limit") != campaign.get("token_budget")
        or budget.get("id")
        != digest(
            {
                "campaign_id": campaign.get("id"),
                "department_policy_id": policy.id,
                "scope": "campaign",
                "token_limit": campaign.get("token_budget"),
            }
        )
    ):
        raise ValueError("DEPARTMENT_CAMPAIGN_BINDING_INVALID")
    return policy


def validate_department_packet(
    policy: DepartmentPolicy, packet: ResearchEvidencePacket
) -> ResultCriterion:
    if (
        packet.department != policy.department
        or packet.status not in policy.accepted_evidence_statuses
    ):
        raise ValueError("DEPARTMENT_EVIDENCE_POLICY_MISMATCH")
    return policy.result_criterion


def append_memory(
    conn: Connection,
    store: Store,
    campaign: dict[str, Any],
    candidate: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    policy = frozen_policy(campaign)
    public_value = result.get("public")
    public: dict[str, Any] = public_value if isinstance(public_value, dict) else {}
    payload = {
        "campaign_id": campaign["id"],
        "candidate_id": candidate["id"],
        "attempt_id": candidate["attempt_id"],
        "department": policy.department,
        "department_policy_id": policy.id,
        "result_criterion": policy.result_criterion,
        "outcome": result["status"],
        "reason": result.get("reason"),
        "evidence_status": candidate["evidence_status"],
        "evidence_gaps": candidate.get("evidence_gaps", []),
        "mechanism_fingerprint": candidate.get("mechanism_fingerprint"),
        "mechanism_family": candidate.get("mechanism_family"),
        "public_verdict": public.get("verdict"),
        "public_gates": public.get("gates", {}),
        "authority": "research-only",
        "capital_eligible": False,
    }
    record = {"id": "research-memory-" + digest(payload), **payload, "created_at": now()}
    try:
        retained = store.get(conn, record["id"], "research-memory")
    except KeyError:
        store.append(conn, "research-memory", record, record["id"])
    else:
        if {key: value for key, value in retained.items() if key != "created_at"} != {
            key: value for key, value in record.items() if key != "created_at"
        }:
            raise ValueError("DEPARTMENT_MEMORY_IDENTITY_CONFLICT")
        record = retained
    return record


def memory_context(
    conn: Connection,
    store: Store,
    department: Department,
    *,
    identities: list[str] | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    if identities is None:
        records = store.related(conn, "research-memory", "department", department)[-limit:]
    else:
        records = [store.get(conn, identity, "research-memory") for identity in identities]
    if any(record.get("department") != department for record in records):
        raise ValueError("DEPARTMENT_MEMORY_NAMESPACE_MISMATCH")
    return [
        {
            "id": record["id"],
            "candidate_id": record["candidate_id"],
            "outcome": record["outcome"],
            "reason": record.get("reason"),
            "evidence_status": record["evidence_status"],
            "evidence_gaps": record.get("evidence_gaps", []),
            "mechanism_fingerprint": record.get("mechanism_fingerprint"),
            "mechanism_family": record.get("mechanism_family"),
            "public_verdict": record.get("public_verdict"),
            "public_gates": record.get("public_gates", {}),
            "authority": "research-only",
            "capital_eligible": False,
        }
        for record in records
    ]


def queue_counts(conn: Connection, store: Store) -> dict[Department, dict[str, int]]:
    counts: dict[Department, dict[str, int]] = {
        "replication": {"queued": 0, "running": 0},
        "novel": {"queued": 0, "running": 0},
    }
    entries = conn.execute(
        select(states.c.id, states.c.payload).where(states.c.id.like("campaign:%"))
    ).all()
    import json

    for identity, payload in entries:
        state = json.loads(payload)
        if state.get("status") not in {"QUEUED", "RUNNING"}:
            continue
        try:
            campaign = store.get(conn, identity.removeprefix("campaign:"), "campaign")
            policy = frozen_policy(campaign)
        except (KeyError, ValueError):
            continue
        counts[policy.department][state["status"].casefold()] += 1
    return counts
