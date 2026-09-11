"""Research owns the frozen hypothesis; Ouroboros owns its implementation."""

import re
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from adaptive_alpha.config import Settings
from adaptive_alpha.research.contracts import Candidate
from adaptive_alpha.research.engineering import (
    RESEARCH_INSTRUCTIONS,
    EngineeringRegistry,
    EngineeringStatus,
    ResearchSpec,
)
from adaptive_alpha.research.ouroboros import OuroborosEngineer
from adaptive_alpha.research.provider import OpenAIProvider
from adaptive_alpha.store import Store


def _failure_code(error: Exception) -> str:
    message = str(error)
    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", message):
        return message
    return type(error).__name__.upper()[:100]


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
    if spec.dataset_id != dataset_id or set(spec.evidence_ids) - sources.keys():
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
    stage = "dispatch"
    try:
        checkpoint()
        registry.transition_attempt(engineering_attempt["id"], "RUNNING", "ouroboros", "worker")
        bundle = engineer.implement(work, timeout, checkpoint=checkpoint)
        checkpoint()
        stage = "contract-validation"
        registry.transition_attempt(engineering_attempt["id"], "VALIDATING", stage, "worker")
        record = registry.accept(bundle, "ouroboros")
        benchmark = registry.benchmark(record["id"], "worker")
        if not benchmark["passed"]:
            raise ValueError("IMPLEMENTATION_CONTRACT_FAILED")
        registry.transition_attempt(
            engineering_attempt["id"],
            "SUCCEEDED",
            "complete",
            "worker",
            bundle_id=record["id"],
            benchmark_id=benchmark["id"],
        )
    except Exception as error:
        status: EngineeringStatus = (
            "CANCELLED" if str(error) == "CAMPAIGN_OWNERSHIP_LOST" else "FAILED"
        )
        with suppress(Exception):
            registry.transition_attempt(
                engineering_attempt["id"],
                status,
                stage,
                "worker",
                reason=_failure_code(error),
            )
        raise
    candidate = Candidate(
        name=spec.name,
        hypothesis=spec.hypothesis,
        rationale=spec.rationale,
        evidence_ids=list(spec.evidence_ids),
        contradictions=list(spec.contradictions),
        failure_modes=list(spec.failure_modes),
        source=bundle.source,
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
        },
    )
