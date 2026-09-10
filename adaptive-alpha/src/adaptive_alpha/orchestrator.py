"""Bounded reference research lifecycle; attempts persist before evaluation starts."""

import platform
import time
from pathlib import Path
from typing import Any, Protocol

import httpx

from adaptive_alpha.agents.baseline import (
    TemplateEngineer,
    baseline_spec,
    mutate,
    propose_hypothesis,
)
from adaptive_alpha.config import Settings
from adaptive_alpha.data import dataset_manifest, synthetic_daily
from adaptive_alpha.domain import HiddenFeedback, JobRequest, StrategySpec, digest, new_id, now
from adaptive_alpha.evaluation.engine import evaluate
from adaptive_alpha.store import Store


class HiddenEvaluator(Protocol):
    def evaluate(self, experiment_id: str, spec: StrategySpec) -> HiddenFeedback: ...


class RemoteEvaluator:
    def __init__(self, settings: Settings):
        self.url = settings.evaluator_url
        self.token = settings.token("evaluator_token")

    def evaluate(self, experiment_id: str, spec: StrategySpec) -> HiddenFeedback:
        with httpx.Client(timeout=httpx.Timeout(10, connect=2), trust_env=False) as client:
            response = client.post(
                f"{self.url}/evaluate",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"experiment_id": experiment_id, "spec": spec.model_dump(mode="json")},
            )
            response.raise_for_status()
            return HiddenFeedback.model_validate(response.json())


class Orchestrator:
    def __init__(self, store: Store, evaluator: HiddenEvaluator, settings: Settings):
        self.store, self.evaluator, self.settings = store, evaluator, settings
        self.engineer = TemplateEngineer()
        package = Path(__file__).resolve().parent
        self.source_hash = digest(
            {
                str(path.relative_to(package)): digest(path.read_text())
                for path in sorted(package.rglob("*.py"))
            }
        )
        self.frame = synthetic_daily(42)
        self.dataset = dataset_manifest(self.frame, 42)

    def create(self, request: JobRequest, actor: str) -> dict[str, Any]:
        job = {
            "id": new_id(),
            **request.model_dump(mode="json"),
            "created_at": now(),
            "created_by": actor,
            "agent": "deterministic-reference-v1",
            "parent_job": None,
        }
        with self.store.transaction() as conn:
            self.store.append(conn, "job", job, job["id"])
            self.store.set_state(
                conn,
                f"job:{job['id']}",
                {
                    "status": "CREATED",
                    "experiments": 0,
                    "llm_tokens_used": 0,
                    "compute_seconds_used": 0,
                },
            )
            self.store.audit(conn, "research.job_created", actor, {"job_id": job["id"]})
        return job

    def get(self, job_id: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return {
                **self.store.get(conn, job_id, "job"),
                **self.store.state(conn, f"job:{job_id}"),
            }

    def cancel(self, job_id: str, actor: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            self.store.get(conn, job_id, "job")
            state = self.store.state(conn, f"job:{job_id}")
            if state["status"] in ("CREATED", "RUNNING", "PAUSED"):
                state["status"] = "CANCELLED"
                self.store.set_state(conn, f"job:{job_id}", state)
                self.store.audit(conn, "research.job_cancelled", actor, {"job_id": job_id})
            return state

    def add_strategy(self, spec: StrategySpec, actor: str) -> None:
        with self.store.transaction() as conn:
            self.store.get(conn, spec.hypothesis_id, "hypothesis")
            for parent in spec.parent_strategies:
                self.store.get(conn, parent, "strategy")
            self.store.append(conn, "strategy", spec.model_dump(mode="json"), spec.id)
            self.store.set_state(
                conn, f"strategy:{spec.id}", {"status": "RESEARCH", "capital_eligible": False}
            )
            self.store.audit(
                conn,
                "strategy.created",
                actor,
                {"strategy_id": spec.id, "parents": list(spec.parent_strategies)},
            )

    def run(self, job_id: str, actor: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            job = self.store.get(conn, job_id, "job")
            state = self.store.state(conn, f"job:{job_id}")
            if state["status"] != "CREATED":
                raise ValueError("JOB_ALREADY_STARTED")
            state["status"] = "RUNNING"
            self.store.set_state(conn, f"job:{job_id}", state)
            self.store.audit(conn, "research.job_started", actor, {"job_id": job_id})
        request = JobRequest.model_validate({key: job[key] for key in JobRequest.model_fields})
        started = time.monotonic()
        final_status = "COMPLETED"
        try:
            hypothesis = propose_hypothesis(request)
            with self.store.transaction() as conn:
                self.store.append(
                    conn, "hypothesis", hypothesis.model_dump(mode="json"), hypothesis.id
                )
                self.store.audit(
                    conn,
                    "hypothesis.created",
                    actor,
                    {"hypothesis_id": hypothesis.id, "job_id": job_id},
                )
            spec = baseline_spec(request, hypothesis)
            for generation in range(request.budget.max_experiments):
                with self.store.transaction() as conn:
                    if self.store.state(conn, f"job:{job_id}")["status"] == "CANCELLED":
                        final_status = "CANCELLED"
                        break
                if time.monotonic() - started >= request.budget.compute_seconds:
                    final_status = "BUDGET_EXHAUSTED"
                    break
                if generation:
                    spec = mutate(spec, generation)
                self.add_strategy(spec, actor)
                experiment = self.experiment(job_id, spec, generation, actor)
                if experiment["status"] == "ERROR":
                    final_status = "FAILED"
                    break
        except Exception:
            final_status = "FAILED"
            # Error details stay out of public output (providers may include credentials).
            with self.store.transaction() as conn:
                self.store.audit(
                    conn,
                    "research.job_failed",
                    "orchestrator",
                    {"job_id": job_id, "code": "PIPELINE_ERROR"},
                )
        finally:
            with self.store.transaction() as conn:
                state = self.store.state(conn, f"job:{job_id}")
                state["status"] = "CANCELLED" if state["status"] == "CANCELLED" else final_status
                state["compute_seconds_used"] = round(time.monotonic() - started, 4)
                self.store.set_state(conn, f"job:{job_id}", state)
                self.store.audit(
                    conn, "research.job_finished", "orchestrator", {"job_id": job_id, **state}
                )
        return self.get(job_id)

    def experiment(
        self, job_id: str, spec: StrategySpec, generation: int, actor: str
    ) -> dict[str, Any]:
        experiment_id = new_id()
        artifact = self.engineer.implement(spec)
        fingerprint = spec.fingerprint()
        duplicate_key = digest(
            {
                "spec": fingerprint,
                "dataset": self.dataset["content_hash"],
                "source": self.source_hash,
                "engineer": self.engineer.version,
            }
        )
        attempt = {
            "id": experiment_id,
            "research_job_id": job_id,
            "strategy_id": spec.id,
            "strategy_version": spec.version,
            "generation": generation,
            "dataset_versions": [self.dataset],
            "feature_versions": ["lagged-momentum-v1"],
            "evaluator_version": "demo-v1",
            "config_hash": fingerprint,
            "code_commit": self.settings.build_commit,
            "runtime_source_hash": self.source_hash,
            "python_version": platform.python_version(),
            "operating_system": platform.system(),
            "machine_architecture": platform.machine(),
            "container_base_image": self.settings.container_base_image,
            "dependency_lock": self.settings.build_lock_hash,
            "artifact": artifact,
            "random_seed": 42,
            "started_at": now(),
            "mode": "synthetic-demo",
        }
        with self.store.transaction() as conn:
            duplicate = bool(self.store.state(conn, f"fingerprint:{duplicate_key}"))
            self.store.set_state(
                conn, f"fingerprint:{duplicate_key}", {"experiment_id": experiment_id}
            )
            counter = self.store.state(conn, "trial-count", {"used": 0})
            counter["used"] += 1
            self.store.set_state(conn, "trial-count", counter)
            self.store.append(conn, "attempt", attempt, experiment_id)
            state = self.store.state(conn, f"job:{job_id}")
            state["experiments"] += 1
            self.store.set_state(conn, f"job:{job_id}", state)
            self.store.audit(
                conn,
                "experiment.started",
                actor,
                {"experiment_id": experiment_id, "strategy_id": spec.id},
            )
        result: dict[str, Any] = {
            "status": "DUPLICATE" if duplicate else "ERROR",
            "public": None,
            "hidden": None,
        }
        if not duplicate:
            try:
                result["public"] = evaluate(self.frame, spec, counter["used"])
                hidden = self.evaluator.evaluate(experiment_id, spec)
                result["hidden"] = hidden.model_dump()
                result["status"] = (
                    "PASS" if result["public"]["verdict"] == hidden.verdict == "PASS" else "FAIL"
                )
            except ValueError:
                result["status"] = "INVALID"
            except Exception:
                result["status"] = "ERROR"
                result["error_code"] = "EVALUATOR_UNAVAILABLE"
        with self.store.transaction() as conn:
            cancelled = self.store.state(conn, f"job:{job_id}")["status"] == "CANCELLED"
            if cancelled:
                result["status"] = "CANCELLED"
            final = {
                **attempt,
                **result,
                "completed_at": now(),
                "critic": self.engineer.analyze_failure(result),
                "capital_eligible": False,
            }
            self.store.append(conn, "experiment", final)
            self.store.set_state(
                conn,
                f"strategy:{spec.id}",
                {
                    "status": "VALIDATED" if result["status"] == "PASS" else "REJECTED",
                    "capital_eligible": False,
                    "experiment_id": experiment_id,
                    "synthetic_validation_only": True,
                },
            )
            self.store.audit(
                conn,
                "strategy.evaluated",
                "evaluator",
                {
                    "experiment_id": experiment_id,
                    "strategy_id": spec.id,
                    "status": result["status"],
                },
            )
            self.store.append(
                conn,
                "memory",
                {
                    "job_id": job_id,
                    "strategy_id": spec.id,
                    "experiment_id": experiment_id,
                    "status": result["status"],
                    "critic": final["critic"],
                },
            )
        return final
