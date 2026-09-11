"""Durable, separately fenced delivery queue for Ouroboros WorkOrders."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from typing import Any, Literal

from adaptive_alpha.domain import new_id, now
from adaptive_alpha.research.engineering import WorkOrder
from adaptive_alpha.store import Store

Terminal = Literal["SUCCEEDED", "FAILED", "CANCELLED"]
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


class EngineeringQueue:
    """Own queue state separately from campaign and immutable attempt history."""

    def __init__(self, store: Store):
        self.store = store

    @staticmethod
    def _state_id(attempt_id: str) -> str:
        return "engineering-attempt:" + attempt_id

    @staticmethod
    def _latest(attempt: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        return {**attempt, **(events[-1] if events else {}), "id": attempt["id"]}

    def snapshot(self, attempt_id: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            attempt = self.store.get(conn, attempt_id, "engineering-attempt")
            events = self.store.related(
                conn, "engineering-attempt-event", "engineering_attempt_id", attempt_id
            )
            state = self.store.state(
                conn,
                self._state_id(attempt_id),
                {
                    "status": "QUEUED",
                    "lease": None,
                    "lease_until": 0.0,
                    "deliveries": 0,
                    "cancel_requested": False,
                },
            )
            latest = self._latest(attempt, events)
            if latest.get("status") in TERMINAL:
                state = {
                    **state,
                    "status": latest["status"],
                    "reason": latest.get("reason"),
                    "bundle_id": latest.get("bundle_id"),
                    "benchmark_id": latest.get("benchmark_id"),
                }
            return {**state, "attempt": latest}

    def claim(
        self, *, attempt_id: str | None = None, lease_seconds: float | None = None
    ) -> tuple[dict[str, Any], WorkOrder, str] | None:
        with self.store.transaction() as conn:
            attempts = (
                [self.store.get(conn, attempt_id, "engineering-attempt")]
                if attempt_id
                else list(reversed(self.store.list_records(conn, "engineering-attempt", 1000)))
            )
            current_time = time.time()
            for attempt in attempts:
                identity = attempt["id"]
                events = self.store.related(
                    conn, "engineering-attempt-event", "engineering_attempt_id", identity
                )
                latest = self._latest(attempt, events)
                state_id = self._state_id(identity)
                state = self.store.state(
                    conn,
                    state_id,
                    {
                        "status": "QUEUED",
                        "lease": None,
                        "lease_until": 0.0,
                        "deliveries": 0,
                        "cancel_requested": False,
                    },
                )
                if latest.get("status") in TERMINAL:
                    if state.get("status") not in TERMINAL:
                        state.update(
                            status=latest["status"],
                            lease=None,
                            lease_until=0.0,
                            reason=latest.get("reason"),
                            bundle_id=latest.get("bundle_id"),
                            benchmark_id=latest.get("benchmark_id"),
                        )
                        self.store.set_state(conn, state_id, state)
                    continue
                expired = (
                    state.get("status") == "RUNNING"
                    and float(state.get("lease_until", 0)) < current_time
                )
                if state.get("cancel_requested") and (state.get("status") == "QUEUED" or expired):
                    event = {
                        "id": new_id(),
                        "engineering_attempt_id": identity,
                        "status": "CANCELLED",
                        "stage": "queue",
                        "reason": state.get("cancel_reason", "ENGINEERING_CANCELLED"),
                        "bundle_id": None,
                        "benchmark_id": None,
                        "at": now(),
                    }
                    self.store.append(conn, "engineering-attempt-event", event, event["id"])
                    state.update(status="CANCELLED", lease=None, lease_until=0.0)
                    self.store.set_state(conn, state_id, state)
                    self.store.audit(
                        conn,
                        "engineering.queue_cancelled",
                        "engineering-worker",
                        {"id": identity},
                    )
                    continue
                if state.get("cancel_requested") or (
                    state.get("status") != "QUEUED" and not expired
                ):
                    continue
                work = WorkOrder.model_validate(
                    self.store.get(conn, attempt["work_order_id"], "work-order")
                )
                duration = lease_seconds if lease_seconds is not None else work.max_seconds + 30
                if not math.isfinite(duration) or duration <= 0 or duration > 1830:
                    raise ValueError("ENGINEERING_LEASE_BOUND")
                lease = new_id()
                deliveries = int(state.get("deliveries", 0)) + 1
                state.update(
                    status="RUNNING",
                    lease=lease,
                    lease_until=current_time + duration,
                    deliveries=deliveries,
                )
                self.store.set_state(conn, state_id, state)
                event = {
                    "id": new_id(),
                    "engineering_attempt_id": identity,
                    "action": "RESUMED" if expired else "CLAIMED",
                    "delivery": deliveries,
                    "at": now(),
                }
                self.store.append(conn, "engineering-queue-event", event, event["id"])
                self.store.audit(
                    conn,
                    "engineering.queue_claimed",
                    "engineering-worker",
                    {"id": identity, "delivery": deliveries},
                )
                return attempt, work, lease
        return None

    def checkpoint(self, attempt_id: str, lease: str) -> None:
        with self.store.transaction() as conn:
            state = self.store.state(conn, self._state_id(attempt_id))
            if state.get("cancel_requested"):
                raise ValueError("ENGINEERING_CANCELLED")
            if (
                state.get("status") != "RUNNING"
                or state.get("lease") != lease
                or float(state.get("lease_until", 0)) < time.time()
            ):
                raise ValueError("ENGINEERING_OWNERSHIP_LOST")

    def request_cancel(
        self, attempt_id: str, actor: str, *, reason: str = "ENGINEERING_CANCELLED"
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", reason):
            raise ValueError("ENGINEERING_CANCEL_REASON_INVALID")
        with self.store.transaction() as conn:
            attempt = self.store.get(conn, attempt_id, "engineering-attempt")
            events = self.store.related(
                conn, "engineering-attempt-event", "engineering_attempt_id", attempt_id
            )
            latest = self._latest(attempt, events)
            state_id = self._state_id(attempt_id)
            state = self.store.state(conn, state_id, {"status": "QUEUED", "deliveries": 0})
            if latest.get("status") in TERMINAL:
                return {**state, "status": latest["status"]}
            if not state.get("cancel_requested"):
                state["cancel_requested"] = True
                state["cancel_reason"] = reason
                self.store.append(
                    conn,
                    "engineering-queue-event",
                    {
                        "id": new_id(),
                        "engineering_attempt_id": attempt_id,
                        "action": "CANCEL_REQUESTED",
                        "at": now(),
                    },
                )
                self.store.audit(conn, "engineering.cancel_requested", actor, {"id": attempt_id})
            if state.get("status") == "QUEUED":
                event = {
                    "id": new_id(),
                    "engineering_attempt_id": attempt_id,
                    "status": "CANCELLED",
                    "stage": "queue",
                    "reason": reason,
                    "bundle_id": None,
                    "benchmark_id": None,
                    "at": now(),
                }
                self.store.append(conn, "engineering-attempt-event", event, event["id"])
                state.update(status="CANCELLED", lease=None, lease_until=0.0)
            self.store.set_state(conn, state_id, state)
            return state

    def cancel_campaign(self, campaign_id: str, actor: str) -> list[dict[str, Any]]:
        with self.store.transaction() as conn:
            attempt_ids = [
                item["id"]
                for item in self.store.related(
                    conn, "engineering-attempt", "campaign_id", campaign_id
                )
            ]
        return [self.request_cancel(identity, actor) for identity in attempt_ids]

    def finish(
        self,
        attempt_id: str,
        lease: str,
        status: Terminal,
        *,
        reason: str | None = None,
        bundle_id: str | None = None,
        benchmark_id: str | None = None,
        stage: str = "complete",
    ) -> dict[str, Any]:
        with self.store.transaction() as conn:
            state_id = self._state_id(attempt_id)
            state = self.store.state(conn, state_id)
            if (
                state.get("status") != "RUNNING"
                or state.get("lease") != lease
                or float(state.get("lease_until", 0)) < time.time()
            ):
                raise ValueError("ENGINEERING_OWNERSHIP_LOST")
            if state.get("cancel_requested") and status != "CANCELLED":
                raise ValueError("ENGINEERING_CANCELLED")
            attempt = self.store.get(conn, attempt_id, "engineering-attempt")
            events = self.store.related(
                conn, "engineering-attempt-event", "engineering_attempt_id", attempt_id
            )
            current = self._latest(attempt, events)["status"]
            if current not in {"QUEUED", "RUNNING", "VALIDATING"}:
                raise ValueError("ENGINEERING_ATTEMPT_TRANSITION_INVALID")
            event = {
                "id": new_id(),
                "engineering_attempt_id": attempt_id,
                "status": status,
                "stage": stage,
                "reason": reason,
                "bundle_id": bundle_id,
                "benchmark_id": benchmark_id,
                "at": now(),
            }
            self.store.append(conn, "engineering-attempt-event", event, event["id"])
            state.update(
                status=status,
                reason=reason,
                bundle_id=bundle_id,
                benchmark_id=benchmark_id,
                lease=None,
                lease_until=0.0,
                finished_at=now(),
            )
            self.store.set_state(conn, state_id, state)
            self.store.audit(
                conn,
                "engineering.attempt_transitioned",
                "engineering-worker",
                {"id": attempt_id, "status": status, "stage": stage},
            )
            return state

    def wait(
        self,
        attempt_id: str,
        timeout: float,
        checkpoint: Callable[[], None],
        *,
        poll_seconds: float = 0.1,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 1800:
            raise ValueError("ENGINEERING_WAIT_BOUND")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            checkpoint()
            snapshot = self.snapshot(attempt_id)
            status = snapshot["status"]
            attempt = snapshot["attempt"]
            if status == "SUCCEEDED":
                bundle_id = attempt.get("bundle_id") or snapshot.get("bundle_id")
                benchmark_id = attempt.get("benchmark_id") or snapshot.get("benchmark_id")
                if not bundle_id or not benchmark_id:
                    raise ValueError("ENGINEERING_RESULT_INCOMPLETE")
                with self.store.transaction() as conn:
                    return (
                        self.store.get(conn, bundle_id, "engineering-bundle"),
                        self.store.get(conn, benchmark_id, "artifact-benchmark"),
                    )
            if status in {"FAILED", "CANCELLED"}:
                reason = attempt.get("reason") or snapshot.get("reason")
                raise ValueError(reason or "ENGINEERING_FAILED")
            time.sleep(poll_seconds)
        self.request_cancel(attempt_id, "research-worker", reason="ENGINEERING_DEADLINE")
        raise ValueError("ENGINEERING_DEADLINE")
