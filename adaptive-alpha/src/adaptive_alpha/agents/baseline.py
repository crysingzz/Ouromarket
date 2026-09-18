"""Explicit deterministic reference agents, not an LLM or Ouroboros integration."""

from typing import Any

from adaptive_alpha.domain import Hypothesis, JobRequest, StrategySpec, digest, new_id


class TemplateEngineer:
    version = "template-engineer-v1"

    def propose_implementation(self, spec: StrategySpec) -> dict[str, Any]:
        return {"kind": "trusted-template", "family": spec.family, "lookback": spec.lookback}

    def implement(self, spec: StrategySpec) -> dict[str, Any]:
        # Code is an inspectable artifact, never eval/exec/imported from agent output.
        code = f"# Trusted template {self.version}\nLOOKBACK = {spec.lookback}\nPOSITION_FRACTION = {spec.position_fraction!r}\nFAMILY = {spec.family!r}\n"
        return {
            "id": new_id(),
            "kind": "trusted-template",
            "engineer_version": self.version,
            "spec_hash": digest(spec.model_dump(mode="json")),
            "code": code,
            "code_hash": digest(code),
            "runtime": "adaptive_alpha.evaluation.engine.strategy_returns",
            "arbitrary_code_execution": False,
        }

    def fix_tests(self, artifact_id: str) -> dict[str, Any]:
        return {"status": "unsupported", "artifact_id": artifact_id}

    def create_tool(self, description: str) -> dict[str, Any]:
        return {"status": "unsupported", "reason": "Requires reviewed sandbox integration"}

    def analyze_failure(self, evidence: dict[str, Any]) -> str:
        return "Check public time stability and costs; hidden feedback cannot support causal explanations."


def propose_hypothesis(job: JobRequest) -> Hypothesis:
    return Hypothesis(
        statement=job.objective,
        economic_rationale="Reference hypothesis: delayed trend persistence may compensate slow information diffusion.",
        supporting_evidence=("synthetic-fixture: engineering evidence only",),
        contradictory_evidence=(
            "No retrieved papers or empirical market evidence in this baseline",
        ),
        expected_regime="Persistent trends",
        expected_failure_modes=("Whipsaw", "Costs exceed signal", "Regime reversal"),
        proposed_test="Predefined momentum and reversion templates; daily public and separate hidden synthetic samples.",
    )


def baseline_spec(job: JobRequest, hypothesis: Hypothesis) -> StrategySpec:
    return StrategySpec(
        name="Trend persistence · baseline",
        hypothesis_id=hypothesis.id,
        thesis=hypothesis.economic_rationale,
        universe=job.universe,
    )


def mutate(
    parent: StrategySpec, generation: int, second: StrategySpec | None = None
) -> StrategySpec:
    lookback = min(120, parent.lookback + 5)
    return StrategySpec(
        name=f"Generation {generation} · {'crossover' if second else 'lookback mutation'}",
        family=parent.family
        if second
        else ("mean_reversion" if parent.family == "momentum" else "momentum"),
        hypothesis_id=parent.hypothesis_id,
        thesis=parent.thesis,
        universe=parent.universe,
        lookback=lookback,
        position_fraction=second.position_fraction if second else parent.position_fraction,
        parent_strategies=(parent.id, second.id) if second else (parent.id,),
        mutation_metadata=f"Lookback {parent.lookback} → {lookback}; "
        + (
            "inherit second parent's sizing"
            if second
            else "switch signal direction to test mechanism"
        ),
    )
