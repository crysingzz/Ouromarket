"""Worker for the durable Ouroboros engineering queue."""

from __future__ import annotations

import re
import signal
import time
from contextlib import suppress

from adaptive_alpha.config import Settings
from adaptive_alpha.research.engineering import EngineeringRegistry
from adaptive_alpha.research.engineering_queue import EngineeringQueue, Terminal
from adaptive_alpha.research.ouroboros import OuroborosEngineer
from adaptive_alpha.research.tool_catalog import ToolCatalog
from adaptive_alpha.store import Store


def _failure_code(error: Exception) -> str:
    message = str(error)
    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", message):
        return message
    return type(error).__name__.upper()[:100]


def run_once(store: Store, settings: Settings, attempt_id: str | None = None) -> bool:
    queue = EngineeringQueue(store)
    claimed = queue.claim(attempt_id=attempt_id)
    if claimed is None:
        return False
    attempt, work, lease = claimed
    registry = EngineeringRegistry(store)
    stage = "ouroboros"

    def checkpoint() -> None:
        queue.checkpoint(attempt["id"], lease)

    try:
        current = queue.snapshot(attempt["id"])["attempt"]["status"]
        if current == "QUEUED":
            registry.transition_attempt(attempt["id"], "RUNNING", stage, "engineering-worker")
        checkpoint()
        with store.transaction() as conn:
            existing = store.related(conn, "engineering-bundle", "work_order_id", work.id)
        if existing:
            record = existing[0]
        else:
            ToolCatalog(store).verify_work_order(work)
            engineer = OuroborosEngineer(
                settings.ouroboros_url,
                settings.ouroboros_workspace,
                service_token=settings.ouroboros_token.get_secret_value()
                if settings.ouroboros_token
                else "",
                provision_workspaces=settings.ouroboros_provision_workspaces,
            )
            bundle = engineer.implement(work, work.max_seconds, checkpoint=checkpoint)
            checkpoint()
            record = registry.accept(bundle, "ouroboros")
        current = queue.snapshot(attempt["id"])["attempt"]["status"]
        if current == "RUNNING":
            stage = "contract-validation"
            registry.transition_attempt(attempt["id"], "VALIDATING", stage, "engineering-worker")
        checkpoint()
        with store.transaction() as conn:
            prior = store.related(conn, "artifact-benchmark", "bundle_id", record["id"])
        benchmark = prior[0] if prior else registry.benchmark(record["id"], "engineering-worker")
        if not benchmark["passed"]:
            raise ValueError("IMPLEMENTATION_CONTRACT_FAILED")
        queue.finish(
            attempt["id"],
            lease,
            "SUCCEEDED",
            bundle_id=record["id"],
            benchmark_id=benchmark["id"],
        )
    except Exception as error:
        code = _failure_code(error)
        if code == "ENGINEERING_OWNERSHIP_LOST":
            return False
        terminal: Terminal = "CANCELLED" if code == "ENGINEERING_CANCELLED" else "FAILED"
        with suppress(Exception):
            queue.finish(attempt["id"], lease, terminal, reason=code, stage=stage)
    return True


def main() -> None:
    settings = Settings()
    store = Store(settings.database_url, manage_schema=settings.manage_schema)
    store.initialize()
    stopping = False

    def stop(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            settings = Settings()
            with store.transaction() as conn:
                store.set_state(
                    conn,
                    "engineering-worker",
                    {"heartbeat": time.time(), "queue": "durable-v1"},
                )
            if not run_once(store, settings):
                time.sleep(1)
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
