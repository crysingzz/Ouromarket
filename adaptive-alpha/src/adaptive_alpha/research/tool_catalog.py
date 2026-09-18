"""Matched qualification and operator lifecycle for reusable Ouroboros tools."""

from __future__ import annotations

import hashlib
import uuid
from typing import Annotated, Any

from pydantic import Field
from sqlalchemy.engine import Connection

from adaptive_alpha.domain import Contract, digest, new_id, now
from adaptive_alpha.research.engineering import ToolAttachment, WorkOrder, runtime_digest
from adaptive_alpha.store import Store

Short = Annotated[str, Field(min_length=1, max_length=100)]


class ToolBenchmarkPlanRequest(Contract):
    request_id: str = Field(min_length=1, max_length=80)
    source_work_order_id: Short
    artifact_id: Short


class ToolQualificationRequest(Contract):
    plan_ids: tuple[Short, ...] = Field(min_length=3, max_length=10)


class ToolAdoptionRequest(Contract):
    qualification_id: Short


class ToolRevocationRequest(Contract):
    reason: str = Field(min_length=8, max_length=500)


class ToolCatalog:
    """Keep reusable tools evidence-bound and separate from capital authority."""

    state_id = "engineering-tool-catalog"
    protocol = "engineering-tool-comparison-v1"

    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _slot(artifact: dict[str, Any]) -> str:
        return f"{artifact['kind']}:{artifact['name']}"

    @staticmethod
    def _stable_uuid(payload: dict[str, Any]) -> str:
        return str(uuid.UUID(digest(payload)[:32]))

    def _reviewed(self, conn: Connection, artifact_id: str) -> dict[str, Any]:
        artifact = self.store.get(conn, artifact_id, "engineering-artifact")
        if artifact.get("kind") not in {"skill", "subagent", "harness"}:
            raise ValueError("REUSABLE_TOOL_REQUIRED")
        source = artifact.get("source")
        reviews = self.store.related(conn, "artifact-review", "artifact_id", artifact_id)
        if (
            not isinstance(source, str)
            or artifact.get("source_digest") != hashlib.sha256(source.encode()).hexdigest()
            or artifact.get("runtime_digest") != runtime_digest()
            or len(reviews) != 1
            or reviews[0].get("actor") != "operator"
            or reviews[0].get("status") != "REVIEWED_PROPOSAL"
        ):
            raise ValueError("REVIEWED_TOOL_REQUIRED")
        benchmark = self.store.get(conn, reviews[0]["benchmark_id"], "artifact-benchmark")
        if (
            benchmark.get("producer") != "server"
            or benchmark.get("passed") is not True
            or benchmark.get("runtime_digest") != runtime_digest()
            or artifact_id not in benchmark.get("artifact_ids", [])
        ):
            raise ValueError("REVIEWED_TOOL_REQUIRED")
        return artifact

    def _attachment(self, artifact: dict[str, Any]) -> ToolAttachment:
        return ToolAttachment(
            artifact_id=artifact["id"],
            kind=artifact["kind"],
            name=artifact["name"],
            source=artifact["source"],
            source_digest=artifact["source_digest"],
            runtime_digest=artifact["runtime_digest"],
            capabilities=tuple(artifact["capabilities"]),
        )

    def attachments(
        self,
        conn: Connection,
        artifact_ids: tuple[str, ...] | None,
        *,
        require_active: bool,
    ) -> tuple[ToolAttachment, ...]:
        catalog = self.store.state(conn, self.state_id, {"active": {}})["active"]
        selected = (
            tuple(catalog[key] for key in sorted(catalog)) if artifact_ids is None else artifact_ids
        )
        if len(set(selected)) != len(selected):
            raise ValueError("TOOL_SELECTION_DUPLICATE")
        attachments = []
        for artifact_id in selected:
            artifact = self._reviewed(conn, artifact_id)
            if require_active and catalog.get(self._slot(artifact)) != artifact_id:
                raise ValueError("TOOL_NOT_ACTIVE")
            attachments.append(self._attachment(artifact))
        return tuple(attachments)

    def active(self) -> list[dict[str, Any]]:
        with self.store.transaction() as conn:
            catalog = self.store.state(conn, self.state_id, {"active": {}})["active"]
            return [
                self._attachment(self._reviewed(conn, catalog[key])).model_dump(mode="json")
                for key in sorted(catalog)
            ]

    def prepare(self, request: ToolBenchmarkPlanRequest, actor: str) -> dict[str, Any]:
        if actor != "operator":
            raise ValueError("OPERATOR_TOOL_BENCHMARK_REQUIRED")
        request = ToolBenchmarkPlanRequest.model_validate(request.model_dump(mode="json"))
        retained_plan = None
        with self.store.transaction() as conn:
            previous = self.store.related(
                conn, "engineering-tool-benchmark-plan", "request_id", request.request_id
            )
            if previous:
                if len(previous) != 1 or any(
                    previous[0].get(key) != value
                    for key, value in {
                        "source_work_order_id": request.source_work_order_id,
                        "artifact_id": request.artifact_id,
                    }.items()
                ):
                    raise ValueError("TOOL_BENCHMARK_REQUEST_CONFLICT")
                retained_plan = previous[0]
            source = WorkOrder.model_validate(
                self.store.get(conn, request.source_work_order_id, "work-order")
            )
            artifact = self._reviewed(conn, request.artifact_id)
            if (
                source.purpose != "strategy-implementation"
                or source.spec_hash == artifact["spec_hash"]
            ):
                raise ValueError("INDEPENDENT_TOOL_BENCHMARK_REQUIRED")
            catalog = self.store.state(conn, self.state_id, {"active": {}})["active"]
            slot = self._slot(artifact)
            if catalog.get(slot) == artifact["id"] and retained_plan is None:
                raise ValueError("TOOL_ALREADY_ACTIVE")
            for dependency in artifact["dependencies"]:
                dependency_artifact = self._reviewed(conn, dependency)
                if catalog.get(self._slot(dependency_artifact)) != dependency:
                    raise ValueError("ACTIVE_TOOL_DEPENDENCY_REQUIRED")
            baseline_map = dict(catalog)
            trial_map = {**baseline_map, slot: artifact["id"]}
            identity = "tool-plan-" + digest(request.model_dump(mode="json"))
            baseline_work_id = "work-" + self._stable_uuid({"plan": identity, "arm": "baseline"})
            trial_work_id = "work-" + self._stable_uuid({"plan": identity, "arm": "trial"})
            baseline_attempt_id = "engineering-run-" + self._stable_uuid(
                {"plan": identity, "arm": "baseline"}
            )
            trial_attempt_id = "engineering-run-" + self._stable_uuid(
                {"plan": identity, "arm": "trial"}
            )
            baseline_ids = tuple(baseline_map[key] for key in sorted(baseline_map))
            trial_ids = tuple(trial_map[key] for key in sorted(trial_map))

        from adaptive_alpha.research.engineering import EngineeringRegistry

        registry = EngineeringRegistry(self.store)
        baseline = registry.create_work_order(
            source.spec,
            actor,
            token_budget=source.token_budget,
            max_seconds=source.max_seconds,
            parent_artifact_ids=source.parent_artifact_ids,
            tool_artifact_ids=baseline_ids,
            purpose="tool-benchmark",
            work_id=baseline_work_id,
        )
        trial = registry.create_work_order(
            source.spec,
            actor,
            token_budget=source.token_budget,
            max_seconds=source.max_seconds,
            parent_artifact_ids=source.parent_artifact_ids,
            tool_artifact_ids=trial_ids,
            purpose="tool-benchmark",
            work_id=trial_work_id,
        )
        plan = {
            "id": identity,
            **request.model_dump(mode="json"),
            "source_spec_hash": source.spec_hash,
            "baseline_work_order_id": baseline.id,
            "trial_work_order_id": trial.id,
            "baseline_attempt_id": baseline_attempt_id,
            "trial_attempt_id": trial_attempt_id,
            "baseline_tool_ids": list(baseline_ids),
            "trial_tool_ids": list(trial_ids),
            "protocol": self.protocol,
            "status": "QUEUED",
            "created_at": retained_plan["created_at"] if retained_plan else now(),
            "capital_eligible": False,
        }
        with self.store.transaction() as conn:
            try:
                retained = self.store.get(conn, identity, "engineering-tool-benchmark-plan")
            except KeyError:
                retained = None
            if retained is not None:
                if retained != plan:
                    raise ValueError("TOOL_BENCHMARK_PLAN_CONFLICT")
            else:
                self.store.append(conn, "engineering-tool-benchmark-plan", plan, identity)
                self.store.audit(
                    conn,
                    "engineering.tool_benchmark_prepared",
                    actor,
                    {"id": identity, "artifact_id": artifact["id"]},
                )
        # Attempts become visible only after their immutable comparison plan exists.
        # Deterministic identities repair a partial enqueue safely on retry.
        campaign_id = "tool-benchmark:" + identity
        registry.create_attempt(
            baseline.id,
            campaign_id,
            identity + ":baseline",
            actor,
            attempt_id=baseline_attempt_id,
        )
        registry.create_attempt(
            trial.id,
            campaign_id,
            identity + ":trial",
            actor,
            attempt_id=trial_attempt_id,
        )
        return plan

    def _benchmark(self, conn: Connection, work_order_id: str) -> dict[str, Any]:
        reports = self.store.related(conn, "artifact-benchmark", "work_order_id", work_order_id)
        if len(reports) != 1:
            raise ValueError("TOOL_BENCHMARK_RESULT_REQUIRED")
        report = reports[0]
        if (
            report.get("producer") != "server"
            or report.get("protocol") != "engineering-contract-v1"
            or report.get("runtime_digest") != runtime_digest()
        ):
            raise ValueError("TOOL_BENCHMARK_RESULT_INVALID")
        return report

    def qualify(
        self, artifact_id: str, request: ToolQualificationRequest, actor: str
    ) -> dict[str, Any]:
        if actor != "operator":
            raise ValueError("OPERATOR_TOOL_BENCHMARK_REQUIRED")
        request = ToolQualificationRequest.model_validate(request.model_dump(mode="json"))
        if len(set(request.plan_ids)) != len(request.plan_ids):
            raise ValueError("DISTINCT_TOOL_BENCHMARKS_REQUIRED")
        with self.store.transaction() as conn:
            artifact = self._reviewed(conn, artifact_id)
            outcomes = []
            source_specs = set()
            for plan_id in request.plan_ids:
                plan = self.store.get(conn, plan_id, "engineering-tool-benchmark-plan")
                if plan.get("artifact_id") != artifact_id or plan.get("protocol") != self.protocol:
                    raise ValueError("TOOL_BENCHMARK_PLAN_MISMATCH")
                source_specs.add(plan["source_spec_hash"])
                baseline = self._benchmark(conn, plan["baseline_work_order_id"])
                trial = self._benchmark(conn, plan["trial_work_order_id"])
                baseline_passed = baseline.get("passed") is True
                trial_passed = trial.get("passed") is True
                outcome = (
                    "WIN"
                    if trial_passed and not baseline_passed
                    else "REGRESSION"
                    if baseline_passed and not trial_passed
                    else "TIE"
                )
                outcomes.append(
                    {
                        "plan_id": plan_id,
                        "source_spec_hash": plan["source_spec_hash"],
                        "baseline_benchmark_id": baseline["id"],
                        "trial_benchmark_id": trial["id"],
                        "outcome": outcome,
                    }
                )
            if len(source_specs) != len(request.plan_ids) or artifact["spec_hash"] in source_specs:
                raise ValueError("INDEPENDENT_TOOL_BENCHMARK_REQUIRED")
            wins = sum(item["outcome"] == "WIN" for item in outcomes)
            regressions = sum(item["outcome"] == "REGRESSION" for item in outcomes)
            policy = {
                "protocol": self.protocol,
                "minimum_distinct_tasks": 3,
                "minimum_win_fraction": "2/3",
                "maximum_regressions": 0,
            }
            record = {
                "artifact_id": artifact_id,
                "plan_ids": list(request.plan_ids),
                "outcomes": outcomes,
                "wins": wins,
                "regressions": regressions,
                "ties": len(outcomes) - wins - regressions,
                "passed": regressions == 0 and wins * 3 >= len(outcomes) * 2,
                "policy": policy,
                "producer": "server",
                "runtime_digest": runtime_digest(),
                "created_at": now(),
                "capital_eligible": False,
            }
            record["id"] = "tool-qualification-" + digest(
                {key: value for key, value in record.items() if key != "created_at"}
            )
            try:
                retained = self.store.get(conn, record["id"], "engineering-tool-qualification")
            except KeyError:
                retained = None
            if retained is not None:
                return retained
            self.store.append(conn, "engineering-tool-qualification", record, record["id"])
            self.store.audit(
                conn,
                "engineering.tool_qualified",
                "server",
                {"id": record["id"], "artifact_id": artifact_id, "passed": record["passed"]},
            )
            return record

    def adopt(self, artifact_id: str, qualification_id: str, actor: str) -> dict[str, Any]:
        if actor != "operator":
            raise ValueError("OPERATOR_TOOL_ADOPTION_REQUIRED")
        with self.store.transaction() as conn:
            artifact = self._reviewed(conn, artifact_id)
            qualification = self.store.get(conn, qualification_id, "engineering-tool-qualification")
            if (
                qualification.get("artifact_id") != artifact_id
                or qualification.get("producer") != "server"
                or qualification.get("passed") is not True
                or qualification.get("runtime_digest") != runtime_digest()
            ):
                raise ValueError("PASSING_TOOL_QUALIFICATION_REQUIRED")
            if artifact["kind"] == "harness":
                runs = self.store.related(conn, "tool-run", "artifact_id", artifact_id)
                if not any(
                    self.store.state(conn, "tool-run:" + run["id"]).get("status") == "SUCCEEDED"
                    and bool(self.store.related(conn, "tool-run-result", "tool_run_id", run["id"]))
                    for run in runs
                ):
                    raise ValueError("SUCCESSFUL_ISOLATED_HARNESS_RUN_REQUIRED")
            catalog = self.store.state(conn, self.state_id, {"active": {}})
            active = catalog["active"]
            for dependency in artifact["dependencies"]:
                dependency_artifact = self._reviewed(conn, dependency)
                if active.get(self._slot(dependency_artifact)) != dependency:
                    raise ValueError("ACTIVE_TOOL_DEPENDENCY_REQUIRED")
            slot = self._slot(artifact)
            previous = active.get(slot)
            if previous == artifact_id:
                events = self.store.related(
                    conn, "engineering-tool-event", "artifact_id", artifact_id
                )
                return events[-1]
            if previous:
                for active_id in active.values():
                    dependent = self.store.get(conn, active_id, "engineering-artifact")
                    if previous in dependent.get("dependencies", []):
                        raise ValueError("TOOL_HAS_ACTIVE_DEPENDENTS")
                superseded = {
                    "id": new_id(),
                    "artifact_id": previous,
                    "slot": slot,
                    "action": "SUPERSEDED",
                    "replacement_artifact_id": artifact_id,
                    "at": now(),
                    "actor": actor,
                }
                self.store.append(conn, "engineering-tool-event", superseded, superseded["id"])
            active[slot] = artifact_id
            catalog["active"] = active
            self.store.set_state(conn, self.state_id, catalog)
            event = {
                "id": new_id(),
                "artifact_id": artifact_id,
                "qualification_id": qualification_id,
                "slot": slot,
                "action": "ADOPTED",
                "supersedes_artifact_id": previous,
                "at": now(),
                "actor": actor,
                "capital_eligible": False,
            }
            self.store.append(conn, "engineering-tool-event", event, event["id"])
            self.store.audit(
                conn,
                "engineering.tool_adopted",
                actor,
                {"artifact_id": artifact_id, "qualification_id": qualification_id},
            )
            return event

    def revoke(self, artifact_id: str, reason: str, actor: str) -> dict[str, Any]:
        if actor != "operator":
            raise ValueError("OPERATOR_TOOL_ADOPTION_REQUIRED")
        if len(reason.strip()) < 8 or len(reason) > 500:
            raise ValueError("TOOL_REVOCATION_REASON_INVALID")
        with self.store.transaction() as conn:
            artifact = self._reviewed(conn, artifact_id)
            catalog = self.store.state(conn, self.state_id, {"active": {}})
            active = catalog["active"]
            slot = self._slot(artifact)
            if active.get(slot) != artifact_id:
                raise ValueError("TOOL_NOT_ACTIVE")
            for active_id in active.values():
                dependent = self.store.get(conn, active_id, "engineering-artifact")
                if artifact_id in dependent.get("dependencies", []):
                    raise ValueError("TOOL_HAS_ACTIVE_DEPENDENTS")
            del active[slot]
            catalog["active"] = active
            self.store.set_state(conn, self.state_id, catalog)
            event = {
                "id": new_id(),
                "artifact_id": artifact_id,
                "slot": slot,
                "action": "REVOKED",
                "reason": reason,
                "at": now(),
                "actor": actor,
            }
            self.store.append(conn, "engineering-tool-event", event, event["id"])
            self.store.audit(conn, "engineering.tool_revoked", actor, {"artifact_id": artifact_id})
            return event

    def verify_work_order(self, work: WorkOrder) -> None:
        work = WorkOrder.model_validate(work.model_dump(mode="json"))
        if work.toolset_digest is None:
            if work.tools:
                raise ValueError("WORK_ORDER_TOOLSET_MISMATCH")
            return
        tool_payload = [tool.model_dump(mode="json") for tool in work.tools]
        expected_input = digest(
            {
                "dataset": work.spec.dataset_hash,
                "sources": work.spec.source_hashes,
                "toolset": digest(tool_payload),
            }
        )
        if expected_input != work.input_digest:
            raise ValueError("WORK_ORDER_TOOL_BINDING_INVALID")
        with self.store.transaction() as conn:
            for tool in work.tools:
                artifact = self._reviewed(conn, tool.artifact_id)
                if self._attachment(artifact) != tool:
                    raise ValueError("WORK_ORDER_TOOL_BINDING_INVALID")
            if work.purpose == "strategy-implementation":
                catalog = self.store.state(conn, self.state_id, {"active": {}})["active"]
                if any(
                    catalog.get(f"{tool.kind}:{tool.name}") != tool.artifact_id
                    for tool in work.tools
                ):
                    raise ValueError("WORK_ORDER_TOOL_REVOKED")
            else:
                plans = [
                    *self.store.related(
                        conn,
                        "engineering-tool-benchmark-plan",
                        "baseline_work_order_id",
                        work.id,
                    ),
                    *self.store.related(
                        conn,
                        "engineering-tool-benchmark-plan",
                        "trial_work_order_id",
                        work.id,
                    ),
                ]
                if len(plans) != 1:
                    raise ValueError("TOOL_BENCHMARK_PLAN_REQUIRED")
                plan = plans[0]
                is_baseline = plan.get("baseline_work_order_id") == work.id
                expected_ids = plan.get("baseline_tool_ids" if is_baseline else "trial_tool_ids")
                if (
                    plan.get("protocol") != self.protocol
                    or plan.get("source_spec_hash") != work.spec_hash
                    or expected_ids != [tool.artifact_id for tool in work.tools]
                ):
                    raise ValueError("TOOL_BENCHMARK_PLAN_MISMATCH")

    def overview(self) -> dict[str, Any]:
        with self.store.transaction() as conn:
            catalog = self.store.state(conn, self.state_id, {"active": {}})["active"]
            return {
                "active": [
                    self._attachment(self._reviewed(conn, catalog[key])).model_dump(mode="json")
                    for key in sorted(catalog)
                ],
                "plans": self.store.list_records(conn, "engineering-tool-benchmark-plan"),
                "qualifications": self.store.list_records(conn, "engineering-tool-qualification"),
                "events": self.store.list_records(conn, "engineering-tool-event"),
                "protocol": self.protocol,
                "capital_eligible": False,
            }
