"""Research owns the frozen hypothesis; Ouroboros owns its implementation."""

import re
from collections.abc import Callable
from typing import Any

from adaptive_alpha.config import Settings
from adaptive_alpha.research.contracts import Candidate
from adaptive_alpha.research.engineering import (
    RESEARCH_INSTRUCTIONS,
    EngineeringRegistry,
    ResearchSpec,
)
from adaptive_alpha.research.engineering_queue import EngineeringQueue
from adaptive_alpha.research.engineering_worker import (
    _failure_code as engineering_failure_code,
)
from adaptive_alpha.research.engineering_worker import run_once as run_engineering_once
from adaptive_alpha.research.knowledge import claim_record, mechanism_identity
from adaptive_alpha.research.ouroboros import OuroborosEngineer
from adaptive_alpha.research.provider import OpenAIProvider
from adaptive_alpha.store import Store


def _knowledge_metadata(work: Any) -> dict[str, Any]:
    mechanism = mechanism_identity(work.spec.mechanism)
    return {
        **mechanism,
        "research_claim_ids": [
            claim_record(work.id, work.spec_hash, claim)["id"]
            for claim in work.spec.evidence_claims
        ],
    }


def _failure_code(error: Exception) -> str:
    return engineering_failure_code(error)


def resume_research(
    store: Store, research_attempt_id: str
) -> tuple[Candidate, dict[str, Any], dict[str, Any]]:
    registry = EngineeringRegistry(store)
    with store.transaction() as conn:
        completed = registry.completed_result(conn, research_attempt_id)
    work = completed["work"]
    record = completed["bundle"]
    benchmark = completed["benchmark"]
    spec = work.spec
    candidate = Candidate(
        name=spec.name,
        hypothesis=spec.hypothesis,
        rationale=spec.rationale,
        evidence_ids=list(spec.evidence_ids),
        contradictions=list(spec.contradictions),
        failure_modes=list(spec.failure_modes),
        source=record["source"],
    )
    return (
        candidate,
        {
            **completed["research_usage"],
            "research_provider": "openai",
            "implementation_provider": "ouroboros",
            "tokens": "externally_accounted",
            "engineering_token_budget_requested": work.token_budget,
            "engineering_budget_enforced_by": "isolated_ouroboros_runtime",
            "recovered": True,
        },
        {
            "work_order_id": work.id,
            "spec_hash": work.spec_hash,
            "engineering_bundle_id": record["id"],
            "engineering_artifact_ids": record["artifact_ids"],
            "implementation_benchmark_id": benchmark["id"],
            "engineering_attempt_id": completed["engineering_attempt"]["id"],
            "research_department": spec.department,
            "evidence_packet_id": spec.evidence_packet_id,
            "citation_anchors": [item.model_dump(mode="json") for item in spec.citation_anchors],
            "evidence_gaps": list(spec.evidence_gaps),
            **_knowledge_metadata(work),
        },
    )


def implement_research(
    store: Store,
    settings: Settings,
    model: str,
    context: dict[str, Any],
    dataset_id: str,
    allowance: int,
    timeout: float,
    checkpoint: Callable[[], None],
) -> tuple[Candidate, dict[str, Any], dict[str, Any]]:
    # Validate engineering configuration before making a paid researcher request.
    engineer = OuroborosEngineer(
        settings.ouroboros_url,
        settings.ouroboros_workspace,
        service_token=settings.ouroboros_token.get_secret_value()
        if settings.ouroboros_token
        else "",
        provision_workspaces=settings.ouroboros_provision_workspaces,
    )
    engineer.check_ready()
    key = settings.openai_api_key
    researcher = OpenAIProvider(key.get_secret_value() if key else "")
    researcher.timeout = timeout
    with store.transaction() as conn:
        dataset = store.get(conn, dataset_id, "dataset")
        sources = {
            item["id"]: store.get(conn, item["id"], "evidence")["content_hash"]
            for item in context["evidence"]
        }
    research_context = {
        **context,
        "dataset_id": dataset_id,
        "dataset_hash": dataset["manifest"]["content_hash"],
        "source_hashes": sources,
    }
    spec, usage = researcher.structured(
        model, research_context, allowance, ResearchSpec, RESEARCH_INSTRUCTIONS
    )
    checkpoint()
    evidence_packet = context["evidence_packet"]
    if (
        spec.dataset_id != dataset_id
        or set(spec.evidence_ids) - sources.keys()
        or spec.department != context["department"]
        or spec.evidence_packet_id != evidence_packet["id"]
    ):
        raise ValueError("RESEARCH_SPEC_INPUT_MISMATCH")
    registry = EngineeringRegistry(store)
    work = registry.create_work_order(
        spec, "research", token_budget=allowance, max_seconds=max(1, int(timeout))
    )
    with store.transaction() as conn:
        store.append(
            conn,
            "engineering-link",
            {
                "work_order_id": work.id,
                "campaign_id": context["campaign_id"],
                "attempt_id": context["attempt_id"],
                "research_usage": usage,
            },
        )
    engineering_attempt = registry.create_attempt(
        work.id, context["campaign_id"], context["attempt_id"], "worker"
    )
    queue = EngineeringQueue(store)
    try:
        checkpoint()
        if settings.engineering_inline:
            run_engineering_once(store, settings, engineering_attempt["id"])
        record, benchmark = queue.wait(
            engineering_attempt["id"], timeout, checkpoint, poll_seconds=0.001
        )
    except Exception as error:
        reason = str(error)
        queue.request_cancel(
            engineering_attempt["id"],
            "research-worker",
            reason=reason
            if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", reason)
            else "RESEARCH_PIPELINE_ERROR",
        )
        raise
    candidate = Candidate(
        name=spec.name,
        hypothesis=spec.hypothesis,
        rationale=spec.rationale,
        evidence_ids=list(spec.evidence_ids),
        contradictions=list(spec.contradictions),
        failure_modes=list(spec.failure_modes),
        source=record["source"],
    )
    return (
        candidate,
        {
            **usage,
            "research_provider": "openai",
            "implementation_provider": "ouroboros",
            "tokens": "externally_accounted",
            "engineering_token_budget_requested": allowance,
            "engineering_budget_enforced_by": "isolated_ouroboros_runtime",
        },
        {
            "work_order_id": work.id,
            "spec_hash": work.spec_hash,
            "engineering_bundle_id": record["id"],
            "engineering_artifact_ids": record["artifact_ids"],
            "implementation_benchmark_id": benchmark["id"],
            "engineering_attempt_id": engineering_attempt["id"],
            "research_department": spec.department,
            "evidence_packet_id": spec.evidence_packet_id,
            "evidence_status": evidence_packet["status"],
            "citation_anchors": [item.model_dump(mode="json") for item in spec.citation_anchors],
            "evidence_gaps": list(spec.evidence_gaps),
            **_knowledge_metadata(work),
        },
    )
