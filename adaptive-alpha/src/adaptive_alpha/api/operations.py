"""Operator surface for evidence-bound strategy and engineering operations."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from pydantic import Field

from adaptive_alpha.domain import Contract
from adaptive_alpha.research.engineering import EngineeringRegistry
from adaptive_alpha.research.forward import ForwardPaper
from adaptive_alpha.research.lifecycle import StrategyLifecycle
from adaptive_alpha.research.performance import PerformanceMonitor
from adaptive_alpha.research.revalidation import Revalidation
from adaptive_alpha.research.tool_execution import ToolExecutionQueue, ToolValidationRequest
from adaptive_alpha.store import Store


class TransitionRequest(Contract):
    target: str = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=8, max_length=1000)
    expected_version: int = Field(ge=0)
    request_id: str = Field(min_length=1, max_length=80)
    comparison_id: str | None = Field(default=None, max_length=100)


class ComparisonRequest(Contract):
    active_id: str | None = Field(default=None, max_length=100)
    challenger_id: str = Field(min_length=1, max_length=100)


class ArtifactPromotion(Contract):
    benchmark_id: str = Field(min_length=1, max_length=100)


class RevalidationRequest(Contract):
    reason: str = Field(min_length=8, max_length=1000)
    expected_version: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=80)


def register_operations(
    app: FastAPI,
    store: Store,
    operator: Callable[..., str],
    hidden: Callable[[str, str, str], dict[str, Any]],
) -> None:
    lifecycle = StrategyLifecycle(store)
    engineering = EngineeringRegistry(store)
    tools = ToolExecutionQueue(store)

    @app.post("/api/lifecycle/{candidate_id}/revalidate")
    def revalidate(
        candidate_id: str, body: RevalidationRequest, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return Revalidation(store, hidden).run(
            candidate_id, actor, body.request_id, body.expected_version, body.reason
        )

    @app.get("/api/lifecycle", dependencies=[Depends(operator)])
    def overview() -> dict[str, Any]:
        entries = lifecycle.list()
        registered = {item["candidate_id"] for item in entries}
        with store.transaction() as conn:
            candidates = store.list_records(conn, "candidate")
            transitions = store.list_records(conn, "lifecycle-transition")
        return {
            "strategies": entries,
            "unregistered": [
                {"candidate_id": c["id"], "name": c.get("name", c["id"])}
                for c in candidates
                if c["id"] not in registered
            ],
            "comparisons": lifecycle.list_comparisons(),
            "transitions": transitions,
            "mode": "internal-paper",
            "capital_eligible": False,
        }

    @app.post("/api/lifecycle/{candidate_id}/register")
    def register(candidate_id: str, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return lifecycle.register(candidate_id, actor)

    @app.get("/api/lifecycle/{candidate_id}", dependencies=[Depends(operator)])
    def detail(candidate_id: str) -> dict[str, Any]:
        return lifecycle.get(candidate_id)

    @app.post("/api/lifecycle/{candidate_id}/transitions")
    def transition(
        candidate_id: str, body: TransitionRequest, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        with store.transaction() as conn:
            result = lifecycle.transition_in_transaction(
                conn,
                candidate_id,
                body.target,
                actor,
                body.reason,
                expected_version=body.expected_version,
                request_id=body.request_id,
                comparison_id=body.comparison_id,
            )
            if body.target in {"SHADOW", "PAPER"}:
                ForwardPaper(store).create_account(conn, candidate_id, actor)
            return result

    @app.post("/api/strategy-comparisons", status_code=201)
    def compare(
        body: ComparisonRequest, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return lifecycle.register_comparison(body.active_id, body.challenger_id, actor)

    @app.get("/api/strategy-comparisons/{comparison_id}", dependencies=[Depends(operator)])
    def comparison(comparison_id: str) -> dict[str, Any]:
        return lifecycle.comparison(comparison_id)

    @app.post("/api/lifecycle/{candidate_id}/monitor")
    def monitor(candidate_id: str, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return lifecycle.monitor(candidate_id, actor=actor)

    @app.get("/api/lifecycle/{candidate_id}/performance", dependencies=[Depends(operator)])
    def performance(candidate_id: str) -> dict[str, Any]:
        return PerformanceMonitor(store).report(candidate_id)

    @app.get("/api/rollback/{symbol}", dependencies=[Depends(operator)])
    def rollback(symbol: str) -> dict[str, Any]:
        return lifecycle.select_rollback(symbol, "operator")

    @app.get("/api/engineering", dependencies=[Depends(operator)])
    def artifacts() -> dict[str, Any]:
        with store.transaction() as conn:
            tool_worker = store.state(conn, "tool-worker")
        return {
            "artifacts": [
                engineering.get_artifact(item["id"]) for item in engineering.list_artifacts()
            ],
            "work_orders": engineering.list_work_orders(),
            "benchmarks": engineering.list_benchmarks(),
            "attempts": engineering.list_attempts(),
            "tool_runs": tools.list(),
            "tool_worker": tool_worker,
            "arbitrary_execution_enabled": False,
            "reviewed_harness_execution": "isolated-runner-only",
        }

    @app.get("/api/engineering/artifacts/{artifact_id}", dependencies=[Depends(operator)])
    def artifact(artifact_id: str) -> dict[str, Any]:
        return engineering.get_artifact(artifact_id)

    @app.get("/api/engineering/work-orders/{order_id}", dependencies=[Depends(operator)])
    def work_order(order_id: str) -> dict[str, Any]:
        return engineering.get_work_order(order_id).model_dump(mode="json")

    @app.post("/api/engineering/bundles/{bundle_id}/benchmark")
    def benchmark(bundle_id: str, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return engineering.benchmark(bundle_id, actor)

    @app.post("/api/engineering/artifacts/{artifact_id}/promote")
    def promote(
        artifact_id: str, body: ArtifactPromotion, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return engineering.promote(artifact_id, body.benchmark_id, actor)

    @app.post("/api/engineering/artifacts/{artifact_id}/tool-runs", status_code=202)
    def run_tool(
        artifact_id: str,
        body: ToolValidationRequest,
        actor: Annotated[str, Depends(operator)],
    ) -> dict[str, Any]:
        return tools.submit(artifact_id, body, actor)

    @app.get("/api/engineering/tool-runs", dependencies=[Depends(operator)])
    def tool_runs() -> list[dict[str, Any]]:
        return tools.list()

    @app.post("/api/engineering/tool-runs/{run_id}/cancel")
    def cancel_tool(run_id: str, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return tools.cancel(run_id, actor)
