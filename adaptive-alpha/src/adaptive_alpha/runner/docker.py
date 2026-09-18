"""Trusted Docker controller, deployed outside research/API/broker processes.

Production native source requires runsc. runc mode exposes only fixed acceptance
fixtures. No request can select an image, mount, environment, network or command.
"""

import json
import math
import re
import threading
import time
from typing import Any

import httpx

from adaptive_alpha.domain import canonical, digest, new_id
from adaptive_alpha.runner.contracts import PROTOCOL, ToolRequest
from adaptive_alpha.runner.fixtures import FIXTURES

OWNER = "ouromarket-native-tool-v1"
LABEL = "org.ouromarket.runner.owner"
DEADLINE = "org.ouromarket.runner.deadline"


class DockerRunner:
    def __init__(self, client: httpx.Client, image_id: str, *, development_fixtures: bool = False):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise ValueError("PINNED_RUNNER_IMAGE_REQUIRED")
        self.client, self.image_id = client, image_id
        self.development_fixtures = development_fixtures
        self.quarantined = False
        self._lock = threading.Lock()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self.client.request(method, "/v1.47" + path, timeout=10, **kwargs)
        response.raise_for_status()
        return response

    def _verify(self) -> None:
        info = self._request("GET", "/info").json()
        if not self.development_fixtures and "runsc" not in info.get("Runtimes", {}):
            raise ValueError("GVISOR_REQUIRED")
        image = self._request("GET", "/images/" + self.image_id + "/json").json()
        if (
            image["Id"] != self.image_id
            or image["Config"].get("Labels", {}).get("org.ouromarket.runner.protocol") != PROTOCOL
        ):
            raise ValueError("RUNNER_IMAGE_MISMATCH")

    def run(self, request: ToolRequest, cancel: threading.Event | None = None) -> dict[str, Any]:
        if self.development_fixtures:
            raise ValueError("DEVELOPMENT_FIXTURES_ONLY")
        with self._lock:
            return self._run(request, cancel or threading.Event())

    def run_fixture(
        self, name: str, *, seconds: int = 2, cancel: threading.Event | None = None
    ) -> dict[str, Any]:
        with self._lock:
            return self._run(
                ToolRequest(source=FIXTURES[name], payload={"fixture": name}, seconds=seconds),
                cancel or threading.Event(),
            )

    def _config(self, name: str, request: ToolRequest) -> dict[str, Any]:
        job = {**request.model_dump(mode="json"), "request_hash": request.fingerprint}
        return {
            "Image": self.image_id,
            "Entrypoint": ["/usr/local/bin/python", "-I", "-S", "-B", "/runner/supervisor.py"],
            "Cmd": [canonical(job)],
            "User": "0:0",
            "WorkingDir": "/tmp",  # noqa: S108 — private bounded container tmpfs
            "Env": ["PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", "PYTHONUNBUFFERED=1"],
            "AttachStdout": False,
            "AttachStderr": False,
            "NetworkDisabled": True,
            "Labels": {
                LABEL: OWNER,
                DEADLINE: str(time.time() + request.seconds + 60),
                "org.ouromarket.runner.name": name,
            },
            "HostConfig": {
                "Runtime": "runc" if self.development_fixtures else "runsc",
                "NetworkMode": "none",
                "ReadonlyRootfs": True,
                "CapDrop": ["ALL"],
                "CapAdd": ["SETUID", "SETGID", "KILL"],
                "SecurityOpt": ["no-new-privileges:true"],
                "Memory": 192 * 1024 * 1024,
                "MemorySwap": 192 * 1024 * 1024,
                "NanoCpus": 1_000_000_000,
                "PidsLimit": 32,
                "Ulimits": [
                    {"Name": "nofile", "Soft": 64, "Hard": 64},
                    {"Name": "fsize", "Soft": 1048576, "Hard": 1048576},
                ],
                "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=32m,mode=1777"},  # noqa: S108
                "ShmSize": 1048576,
                "LogConfig": {"Type": "json-file", "Config": {"max-size": "128k", "max-file": "1"}},
                "RestartPolicy": {"Name": "no"},
            },
        }

    def _remove(self, name: str) -> bool:
        try:
            response = self.client.delete(
                "/v1.47/containers/" + name, params={"force": "true", "v": "true"}, timeout=10
            )
            return response.status_code in {204, 404}
        except httpx.HTTPError:
            return False

    def _logs(self, name: str, request: ToolRequest) -> dict[str, Any]:
        raw = bytearray()
        with self.client.stream(
            "GET",
            "/v1.47/containers/" + name + "/logs",
            params={"stdout": "true", "stderr": "false"},
            timeout=10,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 131072:
                    raise ValueError("RUNNER_LOG_LIMIT")
        output = bytearray()
        while raw:
            if len(raw) < 8 or raw[0] != 1 or raw[1:4] != b"\0\0\0":
                raise ValueError("RUNNER_LOG_PROTOCOL")
            size = int.from_bytes(raw[4:8], "big")
            if size > len(raw) - 8:
                raise ValueError("RUNNER_LOG_PROTOCOL")
            output.extend(raw[8 : 8 + size])
            del raw[: 8 + size]
        result = json.loads(output)
        if (
            not isinstance(result, dict)
            or result.get("request_hash") != request.fingerprint
            or result.get("protocol") != PROTOCOL
            or result.get("status")
            not in {"SUCCESS", "TIMEOUT", "OUTPUT_LIMIT", "INVALID_OUTPUT", "TOOL_FAILED"}
        ):
            raise ValueError("RUNNER_RESULT_IDENTITY")
        if len(canonical(result.get("output")).encode()) > request.output_bytes:
            raise ValueError("RUNNER_OUTPUT_LIMIT")
        return {
            "status": result["status"],
            "output": result.get("output"),
            "python": result.get("python"),
        }

    def _run(self, request: ToolRequest, cancel: threading.Event) -> dict[str, Any]:
        request = ToolRequest.model_validate(json.loads(canonical(request.model_dump())))
        if self.quarantined:
            raise ValueError("RUNNER_QUARANTINED")
        self._verify()
        name = "alpha-tool-" + new_id()
        config = self._config(name, request)
        result: dict[str, Any] = {"status": "CANCELLED", "output": None}
        created = False
        create_confirmed = False
        clean = True
        try:
            if not cancel.is_set():
                # Set before the call: a lost create response may still have made
                # the container, so cleanup must address the known unique name.
                created = True
                self._request("POST", "/containers/create", params={"name": name}, json=config)
                create_confirmed = True
                if not cancel.is_set():
                    self._request("POST", "/containers/" + name + "/start")
                deadline = time.monotonic() + request.seconds + 5
                while True:
                    if cancel.is_set():
                        break
                    if time.monotonic() >= deadline:
                        result = {"status": "TIMEOUT", "output": None}
                        break
                    state = self._request("GET", "/containers/" + name + "/json").json()["State"]
                    if not state["Running"]:
                        result = {
                            "status": "RESOURCE_LIMIT" if state.get("OOMKilled") else "TOOL_FAILED",
                            "output": None,
                        }
                        if state["ExitCode"] == 0:
                            result = self._logs(name, request)
                        break
                    cancel.wait(0.05)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, RecursionError):
            result = {"status": "RUNNER_ERROR", "output": None}
        finally:
            if created:
                removed = self._remove(name)
                # An ambiguous create can finish after DELETE returned 404.
                # Keep this controller quarantined even if removal succeeded.
                clean = removed and create_confirmed
                self.quarantined = not clean
        if not clean:
            result = {"status": "CLEANUP_UNCONFIRMED", "output": None}
        return {
            **result,
            "id": name,
            "request_hash": request.fingerprint,
            "source_hash": digest(request.source),
            "input_hash": digest(request.payload),
            "image_id": self.image_id,
            "policy_hash": digest(config["HostConfig"]),
            "runtime": config["HostConfig"]["Runtime"],
            "cleanup_confirmed": clean,
            "fixture_only": self.development_fixtures,
            "capital_eligible": False,
            "protocol": PROTOCOL,
        }

    def recover(self) -> dict[str, Any]:
        """Reap expired containers owned by this protocol, never other workloads."""
        with self._lock:
            return self._recover()

    def _recover(self) -> dict[str, Any]:
        items = self._request(
            "GET",
            "/containers/json",
            params={"all": "true", "filters": canonical({"label": [LABEL + "=" + OWNER]})},
        ).json()
        removed = []
        for item in items:
            labels = item.get("Labels", {})
            name = labels.get("org.ouromarket.runner.name", "")
            if labels.get(LABEL) != OWNER or not re.fullmatch(r"alpha-tool-[a-f0-9-]{36}", name):
                continue
            try:
                deadline = float(labels[DEADLINE])
                if not math.isfinite(deadline):
                    raise ValueError("NONFINITE_LEASE")
            except (ValueError, KeyError, TypeError) as exc:
                self.quarantined = True
                raise ValueError("RUNNER_INVALID_LEASE") from exc
            if deadline >= time.time():
                continue
            if not self._remove(name):
                self.quarantined = True
                raise ValueError("RUNNER_CLEANUP_REQUIRED")
            removed.append(name)
        # Clearing quarantine requires a fresh controller after operator review:
        # a lost create response could refer to a container not yet listed.
        return {"removed": removed, "quarantined": self.quarantined}
