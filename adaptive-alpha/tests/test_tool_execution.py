"""Durable reviewed-harness execution without runner authority in the API."""

import json
import runpy
import signal
import time
from pathlib import Path

import pytest
from conftest import RESEARCH
from test_engineering import proposal, register

from adaptive_alpha import config as config_module
from adaptive_alpha import store as store_module
from adaptive_alpha.domain import digest
from adaptive_alpha.research import tool_execution as execution_module
from adaptive_alpha.research import tool_worker
from adaptive_alpha.research.engineering import EngineeringRegistry
from adaptive_alpha.research.tool_execution import (
    ToolExecutionQueue,
    ToolValidationRequest,
    schema_matches,
)
from adaptive_alpha.research.tool_worker import run_once
from adaptive_alpha.runner import docker as docker_module
from adaptive_alpha.runner.contracts import PROTOCOL, ToolRequest
from adaptive_alpha.store import Store

IMAGE = "sha256:" + "d" * 64
HARNESS = "def run(payload):\n    return {'doubled': payload['value'] * 2}\n"
INPUT_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"doubled": {"type": "integer"}},
    "required": ["doubled"],
    "additionalProperties": False,
}


@pytest.fixture
def registry(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/tools.db")
    store.initialize()
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        store.append(conn, "evidence", {"content_hash": "b" * 64}, "paper")
    yield EngineeringRegistry(store)
    store.engine.dispose()


def reviewed(registry, *, kind="harness", source=HARNESS):
    path = "harnesses/reproduction.py" if kind == "harness" else "skills/reproduction.md"
    item = proposal(
        kind=kind,
        path=path,
        source=source,
        capabilities=("run_contract_tests",),
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
    )
    _, _, bundle = register(registry, artifacts=(item,))
    benchmark = registry.benchmark(bundle["id"], "operator")
    artifact_id = bundle["artifact_ids"][1]
    review = registry.promote(artifact_id, benchmark["id"], "operator")
    return artifact_id, review, benchmark


class Runner:
    quarantined = False

    def __init__(self, output=None, status="SUCCESS"):
        self.output = {"doubled": 6} if output is None else output
        self.status = status
        self.requests = []
        self.recoveries = 0

    def recover(self):
        self.recoveries += 1
        return {"removed": [], "quarantined": False}

    def run(self, request, cancel=None):
        self.requests.append(request)
        return report(request, self.status, self.output)


def report(request: ToolRequest, status="SUCCESS", output=None):
    return {
        "id": "alpha-tool-00000000-0000-0000-0000-000000000001",
        "status": status,
        "output": output,
        "request_hash": request.fingerprint,
        "source_hash": digest(request.source),
        "input_hash": digest(request.payload),
        "image_id": IMAGE,
        "policy_hash": "a" * 64,
        "runtime": "runsc",
        "cleanup_confirmed": True,
        "fixture_only": False,
        "capital_eligible": False,
        "protocol": PROTOCOL,
    }


def request(request_id="request-1", value=3):
    return ToolValidationRequest(request_id=request_id, payload={"value": value})


def test_executes_reviewed_harness_with_retained_result(registry):
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    created = queue.submit(artifact_id, request(), "operator")
    runner = Runner()
    assert run_once(registry.store, runner, created["id"])
    result = queue.snapshot(created["id"])
    assert result["status"] == "SUCCEEDED" and result["result"]["report"]["output"] == {
        "doubled": 6
    }
    assert result["deliveries"] == 1 and runner.recoveries == 1
    assert len(runner.requests) == 1 and runner.requests[0].payload == {"value": 3}
    with registry.store.transaction() as conn:
        assert len(registry.store.list_records(conn, "tool-run-result")) == 1
        assert registry.store.state(conn, queue.active_state_id)["ids"] == []
        assert registry.store.verify_audit(conn)


def test_resumes_expired_tool_lease_without_duplicate_result(registry):
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    created = queue.submit(artifact_id, request(), "operator")
    first = queue.claim(lease_seconds=1)
    assert first is not None
    with registry.store.transaction() as conn:
        state = registry.store.state(conn, "tool-run:" + created["id"])
        state["lease_until"] = time.time() - 1
        registry.store.set_state(conn, "tool-run:" + created["id"], state)
    runner = Runner()
    assert run_once(registry.store, runner, created["id"])
    result = queue.snapshot(created["id"])
    assert result["status"] == "SUCCEEDED" and result["deliveries"] == 2
    with registry.store.transaction() as conn:
        events = registry.store.related(conn, "tool-run-event", "tool_run_id", created["id"])
        assert [event["action"] for event in events].count("RESUMED") == 1
        assert len(registry.store.list_records(conn, "tool-run-result")) == 1


def test_rejects_unreviewed_or_wrong_artifact(registry):
    _, _, unreviewed = register(
        registry,
        artifacts=(
            proposal(
                kind="harness",
                path="harnesses/unreviewed.py",
                source=HARNESS,
                capabilities=("run_contract_tests",),
                input_schema=INPUT_SCHEMA,
                output_schema=OUTPUT_SCHEMA,
            ),
        ),
    )
    queue = ToolExecutionQueue(registry.store)
    with pytest.raises(ValueError, match="REVIEWED_HARNESS_REQUIRED"):
        queue.submit(unreviewed["artifact_ids"][1], request(), "operator")
    skill_id, _, _ = reviewed(registry, kind="skill", source="Describe the test harness only.")
    with pytest.raises(ValueError, match="REVIEWED_HARNESS_REQUIRED"):
        queue.submit(skill_id, request("request-2"), "operator")
    harness_id, _, _ = reviewed(registry)
    with pytest.raises(ValueError, match="OPERATOR_TOOL_EXECUTION_REQUIRED"):
        queue.submit(harness_id, request("request-3"), "research")
    with pytest.raises(ValueError, match="TOOL_INPUT_SCHEMA_MISMATCH"):
        queue.submit(harness_id, ToolValidationRequest(request_id="request-4"), "operator")


def test_cancellation_fences_stale_owner(registry):
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    first_run = queue.submit(artifact_id, request(), "operator")
    first_claim = queue.claim(run_id=first_run["id"])
    assert first_claim is not None
    run, lease = first_claim
    queue.cancel(run["id"], "operator")
    native_request, _ = queue.materialize(run["id"])
    with pytest.raises(ValueError, match="TOOL_CANCELLED"):
        queue.finish(run["id"], lease, "SUCCEEDED", report=report(native_request))
    cancelled = queue.finish(
        run["id"], lease, "CANCELLED", report=report(native_request, "CANCELLED")
    )
    assert cancelled["status"] == "CANCELLED"

    second = queue.submit(artifact_id, request("request-2"), "operator")
    old = queue.claim(run_id=second["id"], lease_seconds=1)
    assert old is not None
    with registry.store.transaction() as conn:
        state = registry.store.state(conn, "tool-run:" + second["id"])
        state["lease_until"] = time.time() - 1
        registry.store.set_state(conn, "tool-run:" + second["id"], state)
    current = queue.claim(run_id=second["id"])
    assert current is not None and current[1] != old[1]
    with pytest.raises(ValueError, match="TOOL_OWNERSHIP_LOST"):
        queue.finish(second["id"], old[1], "FAILED", reason="STALE")
    finished = queue.finish(second["id"], current[1], "FAILED", reason="CONTROLLED")
    assert finished["status"] == "FAILED"


def test_operator_api_and_ui_visibility(client):
    registry = EngineeringRegistry(client.app.state.store)
    with registry.store.transaction() as conn:
        registry.store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        registry.store.append(conn, "evidence", {"content_hash": "b" * 64}, "paper")
        registry.store.set_state(
            conn,
            "tool-worker",
            {"heartbeat": time.time(), "queue": PROTOCOL, "runtime": "runsc", "ready": True},
        )
    artifact_id, _, _ = reviewed(registry)
    response = client.post(
        f"/api/engineering/artifacts/{artifact_id}/tool-runs",
        json=request().model_dump(mode="json"),
    )
    assert response.status_code == 202 and response.json()["status"] == "QUEUED"
    client.headers["Authorization"] = "Bearer " + RESEARCH
    assert client.get("/api/engineering/tool-runs").status_code == 403
    assert (
        client.post(
            f"/api/engineering/artifacts/{artifact_id}/tool-runs",
            json=request("research-request").model_dump(mode="json"),
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/engineering/tool-runs/{response.json()['id']}/cancel").status_code == 403
    )
    client.headers["Authorization"] = "Bearer " + "o" * 48
    runs = client.get("/api/engineering/tool-runs")
    assert runs.status_code == 200 and len(runs.json()) == 1
    cancelled = client.post(f"/api/engineering/tool-runs/{response.json()['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    view = client.get("/api/engineering").json()
    assert view["tool_worker"]["ready"] and len(view["tool_runs"]) == 1
    assert view["reviewed_harness_execution"] == "isolated-runner-only"
    root = Path(__file__).parents[1] / "src/adaptive_alpha/ui"
    assert 'id="engineering-tool-runs"' in (root / "index.html").read_text()
    assert "Tool worker не допущен" in (root / "operations.js").read_text()


def test_compose_isolates_tool_worker_from_api_and_secrets():
    root = Path(__file__).parents[1]
    compose = (root / "compose.yaml").read_text()
    api = compose.split("  api:\n", 1)[1].split("  worker:\n", 1)[0]
    tool = compose.split("  tool-worker:\n", 1)[1].split("  evaluator:\n", 1)[0]
    assert "docker.sock" not in api and "ALPHA_RUNNER" not in api
    assert "profiles: [native-tools]" in tool and "adaptive_alpha.research.tool_worker" in tool
    assert "docker.sock:ro" in tool and "networks: [database]" in tool
    assert "secrets:" not in tool and "public" not in tool and "evaluation" not in tool
    operations = (root / "src/adaptive_alpha/api/operations.py").read_text()
    assert "runner.docker" not in operations and "DockerRunner" not in operations


def test_schema_subset_and_idempotent_requests(registry):
    assert schema_matches([], {"type": "array", "items": {"type": "string"}})
    assert schema_matches("x", {"type": "string"})
    assert schema_matches(1, {"type": "integer"}) and schema_matches(1.2, {"type": "number"})
    assert schema_matches(True, {"type": "boolean"}) and schema_matches(None, {"type": "null"})
    assert not schema_matches(True, {"type": "integer"})
    assert not schema_matches([], {"type": "object"})
    assert not schema_matches({}, {"type": "object", "title": "unsupported"})
    assert not schema_matches({}, {"type": "array", "items": {"type": "string"}})
    assert not schema_matches([], {"type": "array", "items": {}, "title": "unsupported"})
    assert not schema_matches(float("inf"), {"type": "number"})
    assert not schema_matches("x", {"type": "string", "minLength": 2})
    assert not schema_matches({}, {"type": "unknown"})
    assert not schema_matches({}, {"type": "object", "required": [1]})
    assert not schema_matches({}, {"type": "object"}, depth=7)
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    first = queue.submit(artifact_id, request(), "operator")
    assert queue.submit(artifact_id, request(), "operator")["id"] == first["id"]
    with pytest.raises(ValueError, match="TOOL_REQUEST_ID_CONFLICT"):
        queue.submit(artifact_id, request(value=4), "operator")
    assert queue.list()[0]["id"] == first["id"] and "payload" not in queue.list()[0]
    with registry.store.transaction() as conn:
        duplicate = registry.store.get(conn, first["id"], "tool-run")
        duplicate = {**duplicate, "id": "duplicate-request-record"}
        registry.store.append(conn, "tool-run", duplicate, duplicate["id"])
    with pytest.raises(ValueError, match="TOOL_REQUEST_ID_CONFLICT"):
        queue.submit(artifact_id, request(), "operator")


def test_worker_records_output_and_runner_failures(registry):
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    quarantined = queue.submit(artifact_id, request("request-quarantined"), "operator")
    quarantined_runner = Runner()
    quarantined_runner.quarantined = True
    assert not run_once(registry.store, quarantined_runner, quarantined["id"])
    assert queue.snapshot(quarantined["id"])["status"] == "QUEUED"
    invalid = queue.submit(artifact_id, request(), "operator")
    assert run_once(registry.store, Runner(output={"wrong": 1}), invalid["id"])
    assert queue.snapshot(invalid["id"])["reason"] == "TOOL_OUTPUT_SCHEMA_MISMATCH"
    failed = queue.submit(artifact_id, request("request-failed"), "operator")
    assert run_once(registry.store, Runner(output=None, status="TOOL_FAILED"), failed["id"])
    assert queue.snapshot(failed["id"])["reason"] == "NATIVE_TOOL_TOOL_FAILED"


def test_tool_request_and_result_bindings_fail_closed(registry):
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    created = queue.submit(artifact_id, request(), "operator")
    claim = queue.claim(run_id=created["id"])
    assert claim is not None
    native_request, _ = queue.materialize(created["id"])
    forged = report(native_request)
    forged["image_id"] = "latest"
    with pytest.raises(ValueError, match="TOOL_RESULT_IDENTITY_INVALID"):
        queue.finish(created["id"], claim[1], "SUCCEEDED", report=forged)
    bounded = queue.submit(artifact_id, request("lease-bound"), "operator")
    with pytest.raises(ValueError, match="TOOL_LEASE_BOUND"):
        queue.claim(run_id=bounded["id"], lease_seconds=float("nan"))
    queued = queue.submit(artifact_id, request("queued-cancel"), "operator")
    assert queue.cancel(queued["id"], "operator")["status"] == "CANCELLED"
    assert queue.cancel(queued["id"], "operator")["status"] == "CANCELLED"
    assert queue.claim(run_id=queued["id"]) is None
    with pytest.raises(ValueError, match="OPERATOR_TOOL_EXECUTION_REQUIRED"):
        queue.cancel(created["id"], "research")
    with pytest.raises(ValueError, match="TOOL_RESULT_IDENTITY_INVALID"):
        queue.finish(created["id"], claim[1], "SUCCEEDED")


def test_artifact_and_materialized_request_bindings(registry, monkeypatch):
    queue = ToolExecutionQueue(registry.store)
    with registry.store.transaction() as conn:
        registry.store.append(
            conn,
            "engineering-artifact",
            {
                "id": "damaged-harness",
                "kind": "harness",
                "source": HARNESS,
                "source_digest": "0" * 64,
            },
            "damaged-harness",
        )
    with pytest.raises(ValueError, match="TOOL_SOURCE_IDENTITY_INVALID"):
        queue.submit("damaged-harness", request(), "operator")

    artifact_id, review, _ = reviewed(registry)
    monkeypatch.setattr(execution_module, "runtime_digest", lambda: "changed")
    with pytest.raises(ValueError, match="SERVER_REVIEW_BINDING_INVALID"):
        queue.submit(artifact_id, request("changed-runtime"), "operator")
    monkeypatch.undo()
    with registry.store.transaction() as conn:
        registry.store.append(
            conn,
            "tool-run",
            {
                "id": "forged-tool-run",
                "artifact_id": artifact_id,
                "review_id": review["id"],
                "payload": {"value": 3},
                "seconds": 5,
                "output_bytes": 16_384,
                "request_hash": "0" * 64,
                "source_hash": digest(HARNESS),
                "input_hash": digest({"value": 3}),
                "output_schema_hash": digest(OUTPUT_SCHEMA),
            },
            "forged-tool-run",
        )
    with pytest.raises(ValueError, match="TOOL_RUN_BINDING_INVALID"):
        queue.materialize("forged-tool-run")


def test_running_cancellation_is_sealed_after_lease_expiry(registry):
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    created = queue.submit(artifact_id, request(), "operator")
    claim = queue.claim(run_id=created["id"])
    assert claim is not None and queue.claim(run_id=created["id"]) is None
    queue.cancel(created["id"], "operator")
    with pytest.raises(ValueError, match="TOOL_CANCELLED"):
        queue.checkpoint(created["id"], claim[1])
    with registry.store.transaction() as conn:
        state = registry.store.state(conn, "tool-run:" + created["id"])
        state["lease_until"] = time.time() - 1
        registry.store.set_state(conn, "tool-run:" + created["id"], state)
    assert queue.claim(run_id=created["id"]) is None
    assert queue.snapshot(created["id"])["status"] == "CANCELLED"
    with pytest.raises(ValueError, match="TOOL_CANCELLED"):
        queue.checkpoint(created["id"], claim[1])


def test_worker_monitor_propagates_cancel_and_ownership_loss(registry):
    artifact_id, _, _ = reviewed(registry)
    queue = ToolExecutionQueue(registry.store)
    cancelled = queue.submit(artifact_id, request(), "operator")

    class CancellingRunner(Runner):
        def run(self, native_request, cancel=None):
            queue.cancel(cancelled["id"], "operator")
            assert cancel is not None and cancel.wait(1)
            return report(native_request, "CANCELLED")

    assert run_once(registry.store, CancellingRunner(), cancelled["id"])
    assert queue.snapshot(cancelled["id"])["status"] == "CANCELLED"

    lost = queue.submit(artifact_id, request("lost-owner"), "operator")

    class OwnershipRunner(Runner):
        def run(self, native_request, cancel=None):
            with registry.store.transaction() as conn:
                state = registry.store.state(conn, "tool-run:" + lost["id"])
                state["lease"] = "new-owner"
                registry.store.set_state(conn, "tool-run:" + lost["id"], state)
            assert cancel is not None and cancel.wait(1)
            return report(native_request, "CANCELLED")

    assert not run_once(registry.store, OwnershipRunner(), lost["id"])
    assert queue.snapshot(lost["id"])["result"] is None


def test_tool_worker_configuration_and_module_entrypoint(settings, monkeypatch):
    monkeypatch.setattr(tool_worker, "Settings", lambda: settings)
    with pytest.raises(ValueError, match="TOOL_RUNNER_NOT_CONFIGURED"):
        tool_worker.main()
    monkeypatch.undo()

    settings.runner_socket = Path("/var/run/docker.sock")
    settings.runner_image_id = IMAGE
    store = Store(settings.database_url)
    store.initialize()
    handlers = {}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    runner = Runner()
    monkeypatch.setattr(config_module, "Settings", lambda: settings)
    monkeypatch.setattr(store_module, "Store", lambda *args, **kwargs: store)
    monkeypatch.setattr(tool_worker.httpx, "HTTPTransport", lambda **kwargs: object())
    monkeypatch.setattr(tool_worker.httpx, "Client", lambda **kwargs: Client())
    monkeypatch.setattr(docker_module, "DockerRunner", lambda *args, **kwargs: runner)
    monkeypatch.setattr(signal, "signal", lambda kind, fn: handlers.__setitem__(kind, fn))
    monkeypatch.setattr(time, "sleep", lambda _: handlers[signal.SIGTERM](signal.SIGTERM, None))
    runpy.run_module("adaptive_alpha.research.tool_worker", run_name="__main__")
    assert runner.recoveries == 1
    with store.transaction() as conn:
        assert store.state(conn, "tool-worker")["runtime"] == "runsc"


def test_failure_code_redacts_unbounded_errors():
    assert tool_worker._failure_code(ValueError("BOUNDED_CODE")) == "BOUNDED_CODE"
    assert tool_worker._failure_code(RuntimeError("provider detail")) == "RUNTIMEERROR"


def test_contract_payload_is_json_serializable():
    assert json.loads(request().model_dump_json())["payload"] == {"value": 3}
