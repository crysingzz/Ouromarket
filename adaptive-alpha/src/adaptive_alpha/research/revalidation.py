"""Operator-requested diagnostic revalidation with idempotent evaluator identity.

Evaluation runs outside the journal transaction. A bounded lease fences late
results; recovery retries the same hidden attempt after process loss. This does
not create new independent data or any capital permission.
"""

import time
from collections.abc import Callable
from typing import Any

from adaptive_alpha.domain import HiddenFeedback, digest, new_id, now
from adaptive_alpha.research.backtest import backtest
from adaptive_alpha.research.contracts import DatasetImport
from adaptive_alpha.research.lifecycle import StrategyLifecycle
from adaptive_alpha.store import Store


class Revalidation:
    def __init__(self, store: Store, hidden: Callable[[str, str, str], dict[str, Any]]):
        self.store, self.hidden = store, hidden

    def run(
        self, candidate_id: str, actor: str, request_id: str, expected_version: int, reason: str
    ) -> dict[str, Any]:
        if actor != "operator":
            raise ValueError("OPERATOR_REQUIRED")
        fingerprint = digest([candidate_id, expected_version, reason])
        key = "revalidation:" + digest(request_id)
        lifecycle = StrategyLifecycle(self.store)
        with self.store.transaction() as conn:
            receipt = self.store.state(conn, key)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                if receipt["status"] == "COMPLETED":
                    return dict(receipt["result"])
                if receipt["lease_until"] > time.time():
                    raise ValueError("REVALIDATION_IN_PROGRESS")
            state = lifecycle.get_in_transaction(conn, candidate_id)
            if state["version"] != expected_version:
                raise ValueError("LIFECYCLE_VERSION_CONFLICT")
            if state["status"] != "RESEARCH" or not state.get("validation_after"):
                raise ValueError("REVALIDATION_STAGE_REQUIRED")
            candidate = self.store.get(conn, candidate_id, "candidate")
            dataset = self.store.get(conn, candidate["dataset_id"], "dataset")
            if (
                digest(candidate["source"]) != state["source_hash"]
                or digest(dataset["data"]) != dataset["manifest"]["content_hash"]
            ):
                raise ValueError("REVALIDATION_INPUT_INTEGRITY")
            data = DatasetImport.model_validate(dataset["data"])
            attempt = receipt["attempt_id"] if receipt else new_id()
            lease = new_id()
            if not receipt:
                self.store.append(
                    conn,
                    "revalidation-request",
                    {
                        "id": attempt,
                        "candidate_id": candidate_id,
                        "source_hash": state["source_hash"],
                        "dataset_hash": dataset["manifest"]["content_hash"],
                        "validation_after": state["validation_after"],
                        "expected_version": expected_version,
                        "reason": reason,
                        "actor": actor,
                        "at": now(),
                    },
                    attempt,
                )
            self.store.set_state(
                conn,
                key,
                {
                    "status": "RUNNING",
                    "attempt_id": attempt,
                    "fingerprint": fingerprint,
                    "lease": lease,
                    "lease_until": time.time() + 90,
                },
            )
            self.store.audit(
                conn, "revalidation.started", actor, {"id": attempt, "candidate_id": candidate_id}
            )
        public: dict[str, Any] = {}
        feedback: dict[str, Any] = {}
        try:
            public = backtest(candidate["source"], data, timeout=30)
            feedback = HiddenFeedback.model_validate(
                self.hidden(attempt, candidate["source"], data.symbol)
            ).model_dump()
            status = "PASS" if public["verdict"] == feedback["verdict"] == "PASS" else "FAIL"
        except Exception:
            # Provider error bodies and secrets never enter the public journal.
            status = "ERROR"
        with self.store.transaction() as conn:
            receipt = self.store.state(conn, key)
            if receipt["lease"] != lease or receipt["lease_until"] < time.time():
                raise ValueError("REVALIDATION_OWNERSHIP_LOST")
            current = lifecycle.get_in_transaction(conn, candidate_id)
            if current["version"] != expected_version or current["status"] != "RESEARCH":
                status = "STALE"
            result = {
                "id": candidate_id,
                "revalidation_id": attempt,
                "validation_after": state["validation_after"],
                "source_hash": state["source_hash"],
                "dataset_id": state["dataset_id"],
                "public": public,
                "hidden": feedback,
                "status": status,
                "at": now(),
                "scope": "internal-paper",
                "capital_eligible": False,
            }
            result_id = self.store.append(conn, "candidate-result", result)
            response = {**result, "result_id": result_id}
            self.store.set_state(conn, key, {**receipt, "status": "COMPLETED", "result": response})
            self.store.audit(
                conn,
                "revalidation.completed",
                actor,
                {
                    "id": attempt,
                    "candidate_id": candidate_id,
                    "result_id": result_id,
                    "status": status,
                },
            )
            return response
