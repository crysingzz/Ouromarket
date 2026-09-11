"""Narrow authenticated gateway around the actual upstream ASGI application.

Bootstrap exposes task handlers but cannot start model execution. Workspace roots
are server-owned. No finance source, broker keys or Docker authority are present.
"""

import hashlib
import hmac
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def provision(root: Path, work: dict[str, Any]) -> dict[str, str]:
    identity = work.get("id", "")
    if not isinstance(identity, str) or not re.fullmatch(r"work-[a-f0-9-]{36}", identity):
        raise ValueError("WORK_ORDER_ID_REQUIRED")
    encoded = canonical(work)
    if len(encoded.encode()) > 100000:
        raise ValueError("WORK_ORDER_TOO_LARGE")
    spec_hash = hashlib.sha256(canonical(work.get("spec")).encode()).hexdigest()
    if spec_hash != work.get("spec_hash"):
        raise ValueError("WORK_ORDER_SPEC_INTEGRITY")
    path = root / identity
    if path.is_symlink():
        raise ValueError("WORKSPACE_SYMLINK_FORBIDDEN")
    if path.exists():
        manifest = path / "work-order.json"
        gitdir = path / ".git"
        if (
            manifest.is_symlink()
            or gitdir.is_symlink()
            or not gitdir.is_dir()
            or manifest.read_text() != encoded
        ):
            raise ValueError("WORKSPACE_IDENTITY_CONFLICT")
    else:
        path.mkdir(mode=0o700)
        (path / "work-order.json").write_text(encoded)
        env = {
            "PATH": os.environ["PATH"],
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        for arguments in (
            ["init", "-b", "strategy"],
            ["add", "work-order.json"],
            [
                "-c",
                "user.name=Ouromarket",
                "-c",
                "user.email=engineering@localhost",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-m",
                "Frozen research specification",
            ],
        ):
            subprocess.run(  # noqa: S603 — fixed git operations; request data is never an argument
                ["/usr/bin/git", *arguments],
                cwd=path,
                env=env,
                check=True,
                capture_output=True,
                timeout=10,
            )
    return {"workspace_root": str(path), "work_order_id": identity, "spec_hash": spec_hash}


class RuntimeGateway:
    def __init__(self, app: ASGIApp, token: str, root: Path, pin: dict[str, Any]) -> None:
        if len(token) < 32:
            raise ValueError("SERVICE_TOKEN_REQUIRED")
        self.app, self.token, self.root, self.pin = app, token, root.resolve(), pin

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            return await send({"type": "websocket.close", "code": 4403})
        request = Request(scope, receive)
        path, method = request.url.path, request.method
        if path == "/api/health" and method == "GET":
            return await self.app(scope, receive, send)
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(supplied.encode(), self.token.encode()):
            return await JSONResponse({"error": "SERVICE_AUTH_REQUIRED"}, status_code=401)(
                scope, receive, send
            )
        if path == "/integration/status" and method == "GET":
            return await JSONResponse(
                {
                    **self.pin,
                    "ready": False,
                    "reason": "MODEL_EXECUTION_NOT_ADMITTED",
                    "workspace_root": str(self.root),
                    "capital_eligible": False,
                }
            )(scope, receive, send)
        task_read = method == "GET" and re.fullmatch(r"/api/tasks/[a-zA-Z0-9_-]+", path)
        task_cancel = method == "POST" and re.fullmatch(r"/api/tasks/[a-zA-Z0-9_-]+/cancel", path)
        if task_read or task_cancel:
            return await self.app(scope, receive, send)
        if method != "POST" or path not in {"/integration/workspaces", "/api/tasks"}:
            return await JSONResponse({"error": "ROUTE_NOT_ADMITTED"}, status_code=403)(
                scope, receive, send
            )
        raw = bytearray()
        try:
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 128000:
                    raise ValueError("REQUEST_TOO_LARGE")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("OBJECT_REQUIRED")
            if path == "/integration/workspaces":
                result = provision(self.root, body)
                return await JSONResponse(result, status_code=201)(scope, receive, send)
            allowed = {
                "description",
                "workspace_root",
                "workspace_mode",
                "memory_mode",
                "attachments",
                "actor_id",
                "source",
                "metadata",
                "timeout_sec",
                "task_id",
            }
            workspace = Path(body.get("workspace_root", ""))
            if set(body) - allowed or workspace.parent != self.root or workspace.is_symlink():
                raise ValueError("TASK_SCOPE_FORBIDDEN")
            if (
                body.get("workspace_mode") != "external"
                or body.get("memory_mode") != "forked"
                or body.get("attachments")
            ):
                raise ValueError("EXTERNAL_FORKED_TASK_REQUIRED")
            work = json.loads((workspace / "work-order.json").read_text())
            if provision(self.root, work)["workspace_root"] != str(workspace):
                raise ValueError("WORKSPACE_IDENTITY_CONFLICT")
            expected_task_id = "alpha-" + hashlib.sha256(work["id"].encode()).hexdigest()[:32]
            if body.get("task_id") != expected_task_id:
                raise ValueError("TASK_IDENTITY_CONFLICT")
            body["allowed_resources"] = {"network": False}
            payload = canonical(body).encode()
        except (ValueError, OSError, TypeError, subprocess.SubprocessError):
            return await JSONResponse({"error": "INVALID_ENGINEERING_REQUEST"}, status_code=400)(
                scope, receive, send
            )
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}

        forwarded = dict(scope)
        forwarded["headers"] = [
            (k, v) for k, v in scope["headers"] if k.lower() != b"content-length"
        ]
        return await self.app(forwarded, replay, send)
