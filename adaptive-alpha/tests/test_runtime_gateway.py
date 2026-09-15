"""Real Git workspaces and ASGI scope restrictions; native task handlers use Docker acceptance."""

import importlib.util
import json
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_runtime_connection import TOKEN, work_order

from adaptive_alpha.research.engineering import runtime_task_id

module_spec = importlib.util.spec_from_file_location(
    "runtime_gateway", Path(__file__).resolve().parents[2] / "integration/runtime_gateway.py"
)
gateway = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(gateway)


def test_workspace_is_git_bound_idempotent_and_cannot_be_substituted(tmp_path):
    work = work_order().model_dump(mode="json")
    result = gateway.provision(tmp_path, work)
    assert gateway.provision(tmp_path, work) == result
    workspace = Path(result["workspace_root"])
    assert (workspace / ".git/HEAD").read_text().strip() == "ref: refs/heads/strategy"
    assert json.loads((workspace / "work-order.json").read_text()) == work
    other = gateway.provision(tmp_path, work_order().model_dump(mode="json"))
    assert other["workspace_root"] != result["workspace_root"]
    (workspace / "work-order.json").write_text("changed")
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        gateway.provision(tmp_path, work)


def test_provision_rejects_paths_size_forged_spec_and_symlinks(tmp_path):
    work = work_order().model_dump(mode="json")
    for update in (
        {"id": "../outside"},
        {"id": 1},
        {"spec_hash": "a" * 64},
        {"padding": "x" * 100001},
    ):
        with pytest.raises(ValueError):
            gateway.provision(tmp_path, {**work, **update})
    (tmp_path / work["id"]).symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="SYMLINK_FORBIDDEN"):
        gateway.provision(tmp_path, work)


@pytest.fixture
def runtime(tmp_path):
    calls = []

    async def upstream(request: Request):
        calls.append((request.method, request.url.path))
        body = await request.json() if request.method == "POST" else {}
        return JSONResponse({"upstream": True, "body": body})

    app = Starlette(routes=[Route("/{path:path}", upstream, methods=["GET", "POST"])])
    with TestClient(
        gateway.RuntimeGateway(app, TOKEN, tmp_path, {"execution_enabled": False})
    ) as client:
        yield client, calls, tmp_path


def test_gateway_auth_health_and_readiness(runtime):
    client, calls, _ = runtime
    assert client.get("/api/health").json()["upstream"]
    assert client.get("/integration/status").status_code == 401
    client.headers["Authorization"] = "Bearer " + TOKEN
    status = client.get("/integration/status").json()
    assert (
        not status["ready"] and not status["execution_enabled"] and not status["capital_eligible"]
    )
    assert client.post("/api/settings", json={}).status_code == 403
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws"):
        pass
    assert calls == [("GET", "/api/health")]
    with pytest.raises(ValueError, match="SERVICE_TOKEN_REQUIRED"):
        gateway.RuntimeGateway(None, "short", Path("/workspaces"), {})


def test_gateway_task_scope_and_provisioning(runtime):
    client, calls, root = runtime
    client.headers["Authorization"] = "Bearer " + TOKEN
    work = work_order().model_dump(mode="json")
    response = client.post("/integration/workspaces", json=work)
    assert response.status_code == 201
    body = {
        "task_id": runtime_task_id(work["id"]),
        "description": "implement frozen specification",
        "workspace_root": response.json()["workspace_root"],
        "workspace_mode": "external",
        "memory_mode": "forked",
        "attachments": [],
    }
    response = client.post("/api/tasks", json=body)
    assert response.json()["body"]["allowed_resources"] == {"network": False}
    for update in (
        {"workspace_root": str(root.parent)},
        {"type": "evolution"},
        {"memory_mode": "shared"},
        {"attachments": ["secret"]},
        {"task_id": "wrong"},
    ):
        assert client.post("/api/tasks", json={**body, **update}).status_code == 400
    assert client.get("/api/tasks/t1").json()["upstream"]
    assert client.post("/api/tasks/t1/cancel", json={}).json()["upstream"]
    assert len(calls) == 3


@pytest.mark.parametrize("content", ["[]", "invalid json", "x" * 128001])
def test_gateway_rejects_invalid_or_excess_body(runtime, content):
    client, calls, _ = runtime
    client.headers["Authorization"] = "Bearer " + TOKEN
    assert client.post("/integration/workspaces", content=content).status_code == 400
    assert calls == []
