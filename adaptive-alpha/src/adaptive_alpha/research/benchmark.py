"""Pre-registered, matched-budget comparison of static and adaptive campaigns."""

from typing import Any, Literal

from pydantic import Field

from adaptive_alpha.domain import Contract, new_id, now
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import CampaignRequest
from adaptive_alpha.store import Store


class AgentRevision(Contract):
    name: str = Field(min_length=3, max_length=100)
    parent_id: str | None = None
    research_instructions: str = Field(min_length=10, max_length=2000)
    workflow: Literal["static", "adaptive"] = "adaptive"
    openspec_rationale: str = Field(min_length=20, max_length=4000)


class BenchmarkRequest(Contract):
    objective: str = Field(min_length=8, max_length=2000)
    query: str = Field(min_length=3, max_length=300)
    dataset_id: str
    model: str
    challenger_revision_id: str
    generations: int = Field(default=3, ge=3, le=5)
    tokens_per_arm: int = Field(default=90_000, ge=15_000, le=100_000)
    seconds_per_arm: int = Field(default=600, ge=60, le=1800)


def propose_revision(store: Store, revision: AgentRevision, actor: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": new_id(),
        **revision.model_dump(mode="json"),
        "status": "PROPOSED",
        "created_at": now(),
        "actor": actor,
        "allowed_scope": ["research prompts", "research workflow"],
        "forbidden_scope": ["evaluation", "risk", "broker", "permissions"],
    }
    with store.transaction() as conn:
        if revision.parent_id:
            store.get(conn, revision.parent_id, "agent-revision")
        store.append(conn, "agent-revision", payload, payload["id"])
        store.audit(conn, "agent.revision_proposed", actor, {"id": payload["id"]})
    return payload


def create_benchmark(
    store: Store, campaigns: Campaigns, request: BenchmarkRequest, actor: str
) -> dict[str, Any]:
    with store.transaction() as conn:
        revision = store.get(conn, request.challenger_revision_id, "agent-revision")
        store.get(conn, request.dataset_id, "dataset")
    common = {
        "objective": request.objective,
        "query": request.query,
        "dataset_id": request.dataset_id,
        "model": request.model,
        "generations": request.generations,
        "token_budget": request.tokens_per_arm,
        "max_seconds": request.seconds_per_arm,
    }
    # Queue both arms under a shared start gate so no worker can observe a half-created pair.
    baseline = campaigns.create(CampaignRequest(**common, workflow="static"), actor, defer=True)
    challenger = campaigns.create(
        CampaignRequest(**common, workflow=revision["workflow"], agent_revision_id=revision["id"]),
        actor,
        defer=True,
    )
    record = {
        "id": new_id(),
        "baseline_id": baseline["id"],
        "challenger_id": challenger["id"],
        "revision_id": revision["id"],
        "registered_at": now(),
        "controls": common,
        "acceptance": {"minimum_hidden_pass_gain": 1, "maximum_token_ratio": 1.0},
        "interpretation": "Paired exploratory benchmark; replicate across datasets and seeds before generalizing",
    }
    with store.transaction() as conn:
        store.append(conn, "agent-benchmark", record, record["id"])
        for campaign in (baseline, challenger):
            state = store.state(conn, "campaign:" + campaign["id"])
            state["status"] = "QUEUED"
            store.set_state(conn, "campaign:" + campaign["id"], state)
        store.audit(conn, "agent.benchmark_registered", actor, {"id": record["id"]})
    return record


def benchmark_report(store: Store, identity: str) -> dict[str, Any]:
    with store.transaction() as conn:
        benchmark = store.get(conn, identity, "agent-benchmark")
        arms: dict[str, dict[str, Any]] = {}
        for name, key in (("static", "baseline_id"), ("adaptive", "challenger_id")):
            campaign_id = benchmark[key]
            state = store.state(conn, "campaign:" + campaign_id)
            results = store.related(conn, "candidate-result", "campaign_id", campaign_id)
            passed = sum(r.get("status") == "PASS" for r in results)
            public_pass = [r for r in results if r.get("public", {}).get("verdict") == "PASS"]
            hidden_fail = sum(r.get("hidden", {}).get("verdict") == "FAIL" for r in public_pass)
            arms[name] = {
                "campaign_id": campaign_id,
                "status": state["status"],
                "attempts": state["attempts"],
                "validated_strategies": passed,
                "tokens_reserved": state["tokens_charged"],
                "tokens_per_validated": state["tokens_charged"] / passed if passed else None,
                "public_to_hidden_failure_fraction": hidden_fail / len(public_pass)
                if public_pass
                else None,
                "hidden_mean_score": sum(r["hidden"]["score"] for r in results if "hidden" in r)
                / max(1, sum("hidden" in r for r in results)),
            }
    completed = all(a["status"] == "COMPLETED" for a in arms.values())
    better = (
        completed
        and arms["adaptive"]["validated_strategies"] > arms["static"]["validated_strategies"]
        and arms["adaptive"]["tokens_reserved"] <= arms["static"]["tokens_reserved"]
    )
    return {
        **benchmark,
        "arms": arms,
        "complete": completed,
        "promotion_evidence": better,
        "promotion": "requires operator review of OpenSpec proposal and benchmark",
        "capital_eligible": False,
    }
