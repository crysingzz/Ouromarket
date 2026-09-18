"""Trusted worker connecting durable harness jobs to the native-tool controller."""

from __future__ import annotations

import re
import signal
import threading
import time
from contextlib import suppress
from typing import Any, Protocol

import httpx

from adaptive_alpha.config import Settings
from adaptive_alpha.research.tool_execution import (
    Terminal,
    ToolExecutionQueue,
    schema_matches,
)
from adaptive_alpha.runner.contracts import ToolRequest
from adaptive_alpha.runner.docker import DockerRunner
from adaptive_alpha.store import Store


class NativeRunner(Protocol):
    quarantined: bool

    def recover(self) -> dict[str, Any]: ...

    def run(
        self, request: ToolRequest, cancel: threading.Event | None = None
    ) -> dict[str, Any]: ...


def _failure_code(error: Exception) -> str:
    message = str(error)
    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", message):
        return message
    return type(error).__name__.upper()[:100]


def run_once(store: Store, runner: NativeRunner, run_id: str | None = None) -> bool:
    queue = ToolExecutionQueue(store)
    recovery = runner.recover()
    if recovery.get("quarantined") or runner.quarantined:
        return False
    claimed = queue.claim(run_id=run_id)
    if claimed is None:
        return False
    run, lease = claimed
    report: dict[str, Any] | None = None
    cancel = threading.Event()
    stop = threading.Event()

    def watch() -> None:
        while not stop.wait(0.05):
            try:
                queue.checkpoint(run["id"], lease)
            except ValueError:
                cancel.set()
                return

    monitor: threading.Thread | None = None
    try:
        request, output_schema = queue.materialize(run["id"])
        queue.checkpoint(run["id"], lease)
        monitor = threading.Thread(target=watch, name="tool-run-cancellation", daemon=True)
        monitor.start()
        report = runner.run(request, cancel)
        stop.set()
        monitor.join(timeout=1)
        queue.checkpoint(run["id"], lease)
        if report.get("status") != "SUCCESS":
            raise ValueError("NATIVE_TOOL_" + str(report.get("status", "ERROR")))
        if not schema_matches(report.get("output"), output_schema):
            raise ValueError("TOOL_OUTPUT_SCHEMA_MISMATCH")
        queue.finish(run["id"], lease, "SUCCEEDED", report=report)
    except Exception as error:
        stop.set()
        if monitor is not None:
            monitor.join(timeout=1)
        code = _failure_code(error)
        if code == "TOOL_OWNERSHIP_LOST":
            return False
        terminal: Terminal = "CANCELLED" if code == "TOOL_CANCELLED" else "FAILED"
        with suppress(Exception):
            queue.finish(run["id"], lease, terminal, reason=code, report=report)
    return True


def main() -> None:
    settings = Settings()
    if settings.runner_socket is None or not settings.runner_image_id:
        raise ValueError("TOOL_RUNNER_NOT_CONFIGURED")
    store = Store(settings.database_url, manage_schema=settings.manage_schema)
    store.initialize()
    stopping = False

    def stop_worker(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    transport = httpx.HTTPTransport(uds=str(settings.runner_socket))
    try:
        with httpx.Client(transport=transport, base_url="http://docker") as client:
            runner = DockerRunner(client, settings.runner_image_id)
            while not stopping:
                with store.transaction() as conn:
                    store.set_state(
                        conn,
                        "tool-worker",
                        {
                            "heartbeat": time.time(),
                            "queue": "native-tool-v1",
                            "runtime": "runsc",
                            "ready": not runner.quarantined,
                        },
                    )
                if not run_once(store, runner):
                    time.sleep(1)
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
