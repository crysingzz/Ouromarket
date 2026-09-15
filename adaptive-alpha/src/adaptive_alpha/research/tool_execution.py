"""Durable operator-controlled queue for reviewed native harness validation."""

from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Any, Literal

from pydantic import Field
from sqlalchemy.engine import Connection

from adaptive_alpha.domain import Contract, digest, new_id, now
from adaptive_alpha.research.engineering import runtime_digest
from adaptive_alpha.runner.contracts import PROTOCOL, ToolRequest
from adaptive_alpha.store import Store

Terminal = Literal["SUCCEEDED", "FAILED", "CANCELLED"]
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


class ToolValidationRequest(Contract):
    request_id: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    seconds: int = Field(default=5, ge=1, le=30)
    output_bytes: int = Field(default=16_384, ge=1024, le=65_536)


def schema_matches(value: Any, schema: dict[str, Any], depth: int = 0) -> bool:
    """Evaluate the bounded JSON-schema subset accepted for tool contracts."""

    if depth > 6 or not isinstance(schema, dict):
        return False
    expected = schema.get("type")
    if expected == "object":
        if set(schema) - {"type", "properties", "required", "additionalProperties"}:
            return False
        if not isinstance(value, dict):
            return False
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional = schema.get("additionalProperties", True)
        if (
            not isinstance(properties, dict)
            or not isinstance(required, list)
            or any(not isinstance(item, str) for item in required)
            or not isinstance(additional, bool)
            or any(item not in value for item in required)
            or (not additional and any(item not in properties for item in value))
        ):
            return False
        return all(
            key not in value or schema_matches(value[key], child, depth + 1)
            for key, child in properties.items()
        )
    if expected == "array":
        if set(schema) - {"type", "items"}:
            return False
        items = schema.get("items", {})
        return isinstance(value, list) and all(
            schema_matches(item, items, depth + 1) for item in value
        )
    if expected == "string":
        return set(schema) == {"type"} and isinstance(value, str)
    if expected == "integer":
        return set(schema) == {"type"} and isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            set(schema) == {"type"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if expected == "boolean":
        return set(schema) == {"type"} and isinstance(value, bool)
    if expected == "null":
        return set(schema) == {"type"} and value is None
    return False


class ToolExecutionQueue:
    """Keep runner authority out of API while retaining every request and outcome."""

    active_state_id = "tool-run-active"

    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _state_id(run_id: str) -> str:
        return "tool-run:" + run_id

    def _activate(self, conn: Connection, run_id: str) -> None:
        active = self.store.state(conn, self.active_state_id, {"ids": []})
        active["ids"].append(run_id)
        self.store.set_state(conn, self.active_state_id, active)

    def _deactivate(self, conn: Connection, run_id: str) -> None:
        active = self.store.state(conn, self.active_state_id, {"ids": []})
        active["ids"] = [identity for identity in active["ids"] if identity != run_id]
        self.store.set_state(conn, self.active_state_id, active)

    def _validated_artifact(
        self, conn: Connection, artifact_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        artifact = self.store.get(conn, artifact_id, "engineering-artifact")
        if artifact.get("kind") != "harness":
            raise ValueError("REVIEWED_HARNESS_REQUIRED")
        source = artifact.get("source")
        if (
            not isinstance(source, str)
            or artifact.get("source_digest") != hashlib.sha256(source.encode()).hexdigest()
        ):
            raise ValueError("TOOL_SOURCE_IDENTITY_INVALID")
        reviews = self.store.related(conn, "artifact-review", "artifact_id", artifact_id)
        if len(reviews) != 1 or reviews[0].get("actor") != "operator":
            raise ValueError("REVIEWED_HARNESS_REQUIRED")
        review = reviews[0]
        benchmark = self.store.get(conn, review["benchmark_id"], "artifact-benchmark")
        if (
            review.get("status") != "REVIEWED_PROPOSAL"
            or benchmark.get("producer") != "server"
            or benchmark.get("passed") is not True
            or artifact_id not in benchmark.get("artifact_ids", [])
            or benchmark.get("runtime_digest") != runtime_digest()
        ):
            raise ValueError("SERVER_REVIEW_BINDING_INVALID")
        return artifact, review

    def submit(
        self, artifact_id: str, request: ToolValidationRequest, actor: str
    ) -> dict[str, Any]:
        if actor != "operator":
            raise ValueError("OPERATOR_TOOL_EXECUTION_REQUIRED")
        request = ToolValidationRequest.model_validate(request.model_dump(mode="json"))
        with self.store.transaction() as conn:
            artifact, review = self._validated_artifact(conn, artifact_id)
            tool_request = ToolRequest(
                source=artifact["source"],
                payload=request.payload,
                seconds=request.seconds,
                output_bytes=request.output_bytes,
            )
            if not schema_matches(request.payload, artifact["input_schema"]):
                raise ValueError("TOOL_INPUT_SCHEMA_MISMATCH")
            immutable = {
                "artifact_id": artifact_id,
                "review_id": review["id"],
                "request_id": request.request_id,
                "payload": request.payload,
                "seconds": request.seconds,
                "output_bytes": request.output_bytes,
                "request_hash": tool_request.fingerprint,
                "source_hash": digest(artifact["source"]),
                "input_hash": digest(request.payload),
                "output_schema_hash": digest(artifact["output_schema"]),
                "protocol": PROTOCOL,
                "purpose": "operator_validation",
                "capital_eligible": False,
            }
            previous = self.store.related(conn, "tool-run", "request_id", request.request_id)
            if previous:
                if len(previous) != 1:
                    raise ValueError("TOOL_REQUEST_ID_CONFLICT")
                retained = previous[0]
                if any(retained.get(key) != value for key, value in immutable.items()):
                    raise ValueError("TOOL_REQUEST_ID_CONFLICT")
                return self._snapshot(conn, retained)
            record = {
                "id": "tool-run-" + new_id(),
                **immutable,
                "created_at": now(),
                "actor": actor,
            }
            self.store.append(conn, "tool-run", record, record["id"])
            self.store.set_state(
                conn,
                self._state_id(record["id"]),
                {
                    "status": "QUEUED",
                    "lease": None,
                    "lease_until": 0.0,
                    "deliveries": 0,
                    "cancel_requested": False,
                },
            )
            self._activate(conn, record["id"])
            self.store.append(
                conn,
                "tool-run-event",
                {
                    "id": new_id(),
                    "tool_run_id": record["id"],
                    "action": "QUEUED",
                    "at": now(),
                },
            )
            self.store.audit(
                conn,
                "engineering.tool_queued",
                actor,
                {"id": record["id"], "artifact_id": artifact_id},
            )
            return self._snapshot(conn, record)

    def _snapshot(self, conn: Connection, run: dict[str, Any]) -> dict[str, Any]:
        state = self.store.state(conn, self._state_id(run["id"]))
        results = self.store.related(conn, "tool-run-result", "tool_run_id", run["id"])
        public = {key: value for key, value in run.items() if key != "payload"}
        return {**public, **state, "result": results[-1] if results else None}

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self._snapshot(conn, self.store.get(conn, run_id, "tool-run"))

    def list(self) -> list[dict[str, Any]]:
        with self.store.transaction() as conn:
            return [
                self._snapshot(conn, run)
                for run in reversed(self.store.list_records(conn, "tool-run", 1000))
            ]

    def claim(
        self, *, run_id: str | None = None, lease_seconds: float | None = None
    ) -> tuple[dict[str, Any], str] | None:
        with self.store.transaction() as conn:
            runs = (
                [self.store.get(conn, run_id, "tool-run")]
                if run_id
                else [
                    self.store.get(conn, identity, "tool-run")
                    for identity in self.store.state(conn, self.active_state_id, {"ids": []})["ids"]
                ]
            )
            current_time = time.time()
            for run in runs:
                state_id = self._state_id(run["id"])
                state = self.store.state(conn, state_id)
                if state.get("status") in TERMINAL:
                    continue
                expired = (
                    state.get("status") == "RUNNING"
                    and float(state.get("lease_until", 0)) < current_time
                )
                if state.get("cancel_requested") and (state.get("status") == "QUEUED" or expired):
                    state.update(status="CANCELLED", lease=None, lease_until=0.0, finished_at=now())
                    self.store.set_state(conn, state_id, state)
                    self._deactivate(conn, run["id"])
                    self.store.append(
                        conn,
                        "tool-run-event",
                        {
                            "id": new_id(),
                            "tool_run_id": run["id"],
                            "action": "CANCELLED",
                            "reason": state.get("cancel_reason", "TOOL_CANCELLED"),
                            "at": now(),
                        },
                    )
                    self.store.audit(
                        conn, "engineering.tool_cancelled", "tool-worker", {"id": run["id"]}
                    )
                    continue
                if state.get("cancel_requested") or (
                    state.get("status") != "QUEUED" and not expired
                ):
                    continue
                duration = lease_seconds if lease_seconds is not None else run["seconds"] + 75
                if not math.isfinite(duration) or duration <= 0 or duration > 105:
                    raise ValueError("TOOL_LEASE_BOUND")
                lease = new_id()
                delivery = int(state.get("deliveries", 0)) + 1
                state.update(
                    status="RUNNING",
                    lease=lease,
                    lease_until=current_time + duration,
                    deliveries=delivery,
                )
                self.store.set_state(conn, state_id, state)
                self.store.append(
                    conn,
                    "tool-run-event",
                    {
                        "id": new_id(),
                        "tool_run_id": run["id"],
                        "action": "RESUMED" if expired else "CLAIMED",
                        "delivery": delivery,
                        "at": now(),
                    },
                )
                self.store.audit(
                    conn,
                    "engineering.tool_claimed",
                    "tool-worker",
                    {"id": run["id"], "delivery": delivery},
                )
                return run, lease
        return None

    def materialize(self, run_id: str) -> tuple[ToolRequest, dict[str, Any]]:
        with self.store.transaction() as conn:
            run = self.store.get(conn, run_id, "tool-run")
            artifact, review = self._validated_artifact(conn, run["artifact_id"])
            request = ToolRequest(
                source=artifact["source"],
                payload=run["payload"],
                seconds=run["seconds"],
                output_bytes=run["output_bytes"],
            )
            if (
                review["id"] != run.get("review_id")
                or request.fingerprint != run.get("request_hash")
                or digest(artifact["source"]) != run.get("source_hash")
                or digest(run["payload"]) != run.get("input_hash")
                or digest(artifact["output_schema"]) != run.get("output_schema_hash")
                or not schema_matches(run["payload"], artifact["input_schema"])
            ):
                raise ValueError("TOOL_RUN_BINDING_INVALID")
            return request, artifact["output_schema"]

    def checkpoint(self, run_id: str, lease: str) -> None:
        with self.store.transaction() as conn:
            state = self.store.state(conn, self._state_id(run_id))
            if state.get("cancel_requested"):
                raise ValueError("TOOL_CANCELLED")
            if (
                state.get("status") != "RUNNING"
                or state.get("lease") != lease
                or float(state.get("lease_until", 0)) < time.time()
            ):
                raise ValueError("TOOL_OWNERSHIP_LOST")

    def cancel(self, run_id: str, actor: str) -> dict[str, Any]:
        if actor != "operator":
            raise ValueError("OPERATOR_TOOL_EXECUTION_REQUIRED")
        with self.store.transaction() as conn:
            self.store.get(conn, run_id, "tool-run")
            state_id = self._state_id(run_id)
            state = self.store.state(conn, state_id)
            if state.get("status") in TERMINAL:
                return state
            if not state.get("cancel_requested"):
                state["cancel_requested"] = True
                state["cancel_reason"] = "OPERATOR_CANCELLED"
                self.store.append(
                    conn,
                    "tool-run-event",
                    {
                        "id": new_id(),
                        "tool_run_id": run_id,
                        "action": "CANCEL_REQUESTED",
                        "at": now(),
                    },
                )
                self.store.audit(conn, "engineering.tool_cancel_requested", actor, {"id": run_id})
            if state.get("status") == "QUEUED":
                state.update(status="CANCELLED", lease=None, lease_until=0.0, finished_at=now())
                self._deactivate(conn, run_id)
                self.store.append(
                    conn,
                    "tool-run-event",
                    {
                        "id": new_id(),
                        "tool_run_id": run_id,
                        "action": "CANCELLED",
                        "reason": "OPERATOR_CANCELLED",
                        "at": now(),
                    },
                )
                self.store.audit(conn, "engineering.tool_cancelled", actor, {"id": run_id})
            self.store.set_state(conn, state_id, state)
            return state

    def finish(
        self,
        run_id: str,
        lease: str,
        status: Terminal,
        *,
        reason: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.store.transaction() as conn:
            state_id = self._state_id(run_id)
            state = self.store.state(conn, state_id)
            if (
                state.get("status") != "RUNNING"
                or state.get("lease") != lease
                or float(state.get("lease_until", 0)) < time.time()
            ):
                raise ValueError("TOOL_OWNERSHIP_LOST")
            if state.get("cancel_requested") and status != "CANCELLED":
                raise ValueError("TOOL_CANCELLED")
            run = self.store.get(conn, run_id, "tool-run")
            if status == "SUCCEEDED" and report is None:
                raise ValueError("TOOL_RESULT_IDENTITY_INVALID")
            if report is not None and (
                report.get("request_hash") != run["request_hash"]
                or report.get("source_hash") != run["source_hash"]
                or report.get("input_hash") != run["input_hash"]
                or report.get("protocol") != PROTOCOL
                or report.get("capital_eligible") is not False
                or report.get("runtime") != "runsc"
                or report.get("cleanup_confirmed") is not True
                or report.get("fixture_only") is not False
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", str(report.get("image_id", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(report.get("policy_hash", "")))
                or not re.fullmatch(
                    r"alpha-tool-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
                    str(report.get("id", "")),
                )
                or (status == "SUCCEEDED" and report.get("status") != "SUCCESS")
                or (status == "CANCELLED" and report.get("status") != "CANCELLED")
            ):
                raise ValueError("TOOL_RESULT_IDENTITY_INVALID")
            result_id = "tool-result-" + new_id()
            result = {
                "id": result_id,
                "tool_run_id": run_id,
                "status": status,
                "reason": reason,
                "report": report,
                "at": now(),
            }
            self.store.append(conn, "tool-run-result", result, result_id)
            state.update(
                status=status,
                reason=reason,
                lease=None,
                lease_until=0.0,
                finished_at=now(),
            )
            self.store.set_state(conn, state_id, state)
            self._deactivate(conn, run_id)
            self.store.append(
                conn,
                "tool-run-event",
                {
                    "id": new_id(),
                    "tool_run_id": run_id,
                    "action": status,
                    "reason": reason,
                    "at": now(),
                },
            )
            self.store.audit(
                conn, "engineering.tool_finished", "tool-worker", {"id": run_id, "status": status}
            )
            return self._snapshot(conn, run)
