"""Engineering authority, immutable research binding and server benchmark contracts."""

import json
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from adaptive_alpha.domain import digest
from adaptive_alpha.research import engineering
from adaptive_alpha.research.engineering import (
    ArtifactProposal,
    EngineeringRegistry,
    ImplementationBundle,
    ResearchSpec,
    SignalCase,
    runtime_task_id,
)
from adaptive_alpha.research.ouroboros import OuroborosEngineer
from adaptive_alpha.store import Store

SOURCE = "def signal(history):\n    return 1.0 if history[-1] > history[0] else 0.0\n"


@pytest.fixture
def registry(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/engineering.db")
    store.initialize()
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        store.append(conn, "evidence", {"content_hash": "b" * 64}, "paper")
    yield EngineeringRegistry(store)
    store.engine.dispose()


def spec(**updates):
    return ResearchSpec.model_validate(
        {
            "name": "Momentum",
            "hypothesis": "Persistent trends predict the next return",
            "rationale": "Slow information diffusion can explain continuation",
            "evidence_ids": ["paper"],
            "source_hashes": ["b" * 64],
            "contradictions": [],
            "failure_modes": ["Mean reverting regime"],
            "decision_rules": ["Hold one if last close exceeds first, otherwise hold zero"],
            "dataset_id": "dataset",
            "dataset_hash": "a" * 64,
            "acceptance_cases": [
                {"history": [100, 102], "expected": 1},
                {"history": [102, 100], "expected": 0},
            ],
            **updates,
        }
    )


def proposal(**updates):
    return ArtifactProposal.model_validate(
        {
            "name": "reproduction",
            "kind": "skill",
            "path": "skills/reproduction.md",
            "source": "Reproduce the immutable research specification examples.",
            "capabilities": ["describe_research_tool"],
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            **updates,
        }
    )


def register(registry, source=SOURCE, artifacts=(), **work_options):
    work = registry.create_work_order(spec(), "research", **work_options)
    bundle = ImplementationBundle(
        work_order_id=work.id, spec_hash=work.spec_hash, source=source, artifacts=artifacts
    )
    return work, bundle, registry.accept(bundle, "ouroboros")


def test_spec_is_deeply_frozen_and_input_bound(registry):
    research = spec()
    with pytest.raises(ValidationError):
        research.name = "Modified"
    assert isinstance(research.acceptance_cases, tuple)
    work = registry.create_work_order(research, "research")
    assert work.spec_hash == digest(research.model_dump(mode="json"))
    assert work == registry.get_work_order(work.id)
    assert registry.list_work_orders()[0]["input_digest"] == work.input_digest
    with registry.store.transaction() as conn:
        assert registry.store.verify_audit(conn)


@pytest.mark.parametrize(
    "update,error",
    [
        ({"evidence_ids": ["paper", "paper"], "source_hashes": ["b" * 64] * 2}, "SOURCE_BINDING"),
        ({"source_hashes": ["b" * 64] * 2}, "SOURCE_BINDING"),
        ({"acceptance_cases": [{"history": [1], "expected": 0}] * 2}, "DISTINCT_ACCEPTANCE"),
        ({"decision_rules": ["x" * 3001]}, "String should have at most"),
    ],
)
def test_spec_rejects_ambiguous_unbounded_contract(update, error):
    with pytest.raises(ValidationError, match=error):
        spec(**update)


@pytest.mark.parametrize(
    "update,error",
    [
        ({"dataset_hash": "c" * 64}, "DATASET_HASH_MISMATCH"),
        ({"source_hashes": ["c" * 64]}, "EVIDENCE_HASH_MISMATCH"),
    ],
)
def test_registry_verifies_actual_research_inputs(registry, update, error):
    with pytest.raises(ValueError, match=error):
        registry.create_work_order(spec(**update), "research")
    assert registry.list_work_orders() == []


@pytest.mark.parametrize(
    "path",
    [
        "../risk/engine.py",
        "skills/../../risk.py",
        "skills/.secrets/key",
        "/skills/a.md",
        "skills\\a.md",
        "skills//a.md",
        "skills/а.md",
        "risk/engine.py",
        "skills/a b.md",
    ],
)
def test_generated_paths_cannot_target_protected_or_ambiguous_locations(path):
    with pytest.raises(ValidationError, match="TARGET_FORBIDDEN"):
        proposal(path=path)


@pytest.mark.parametrize(
    "update,error",
    [
        ({"capabilities": ["broker.submit"]}, "Input should be"),
        ({"input_schema": {"type": "array"}}, "BOUNDED_OBJECT"),
        ({"input_schema": {"type": "object", "description": "x" * 5000}}, "BOUNDED_OBJECT"),
        (
            {"output_schema": {"type": "object", "$ref": "https://attacker.test"}},
            "REFERENCES_FORBIDDEN",
        ),
    ],
)
def test_generated_capabilities_and_schemas_are_bounded(update, error):
    with pytest.raises(ValidationError, match=error):
        proposal(**update)


def test_bundle_registration_benchmark_review_is_not_capital_or_tool_activation(registry):
    artifacts = (
        proposal(),
        proposal(kind="subagent", name="replicator", path="subagents/replicator.json"),
        proposal(kind="harness", name="replay", path="harnesses/replay.py"),
    )
    work, bundle, registered = register(registry, artifacts=artifacts)
    assert registry.accept(bundle, "ouroboros") == registered
    assert len(registry.list_artifacts()) == 4
    report = registry.benchmark(registered["id"], "operator")
    assert report["passed"] and report["producer"] == "server"
    assert len(report["proposal_only_artifacts"]) == 3
    assert registry.list_benchmarks() == [report]
    for artifact_id in registered["artifact_ids"]:
        artifact = registry.get_artifact(artifact_id)
        review = registry.promote(artifact_id, report["id"], "operator")
        assert review == registry.promote(artifact_id, report["id"], "operator")
        assert not review["capital_eligible"]
        assert artifact["spec_hash"] == work.spec_hash
        assert registry.get_artifact(artifact_id)["reviews"] == [review]
        if artifact["kind"] != "strategy":
            assert review["status"] == "REVIEWED_PROPOSAL"
            assert review["execution"] == "inert_proposal"


def test_result_identity_and_version_conflicts_are_rejected(registry):
    work, bundle, _ = register(registry)
    with pytest.raises(ValueError, match="SPEC_HASH_MISMATCH"):
        registry.accept(bundle.model_copy(update={"spec_hash": "c" * 64}), "ouroboros")
    with pytest.raises(ValueError, match="ALREADY_IMPLEMENTED"):
        registry.accept(bundle.model_copy(update={"source": SOURCE + "\n"}), "ouroboros")
    second = registry.create_work_order(spec(), "research")
    with pytest.raises(ValueError, match="DUPLICATE_ARTIFACT_TARGET"):
        registry.accept(
            ImplementationBundle(
                work_order_id=second.id,
                spec_hash=second.spec_hash,
                source=SOURCE,
                artifacts=(proposal(), proposal()),
            ),
            "ouroboros",
        )
    with pytest.raises(ValueError, match="PROGRAM_GRAMMAR"):
        registry.accept(
            ImplementationBundle(
                work_order_id=second.id,
                spec_hash=second.spec_hash,
                source="import os\ndef signal(history):\n    return 0.0\n",
            ),
            "ouroboros",
        )


def test_registered_interpreter_change_requires_new_work_order(registry):
    _, bundle, registered = register(registry)
    with patch.object(engineering, "runtime_digest", return_value="c" * 64):
        with pytest.raises(ValueError, match="RUNTIME_CHANGED"):
            registry.accept(bundle, "ouroboros")
        with pytest.raises(ValueError, match="RUNTIME_CHANGED"):
            registry.benchmark(registered["id"], "operator")


@pytest.mark.parametrize(
    "source",
    [
        "def signal(history):\n    return 0.0\n",
        "def signal(history):\n    return history[99]\n",
    ],
)
def test_failed_server_replay_cannot_be_promoted(registry, source):
    _, _, registered = register(registry, source=source)
    report = registry.benchmark(registered["id"], "operator")
    assert not report["passed"]
    with pytest.raises(ValueError, match="SERVER_BENCHMARK_REQUIRED"):
        registry.promote(registered["artifact_ids"][0], report["id"], "operator")
    with pytest.raises(ValueError, match="OPERATOR_REVIEW_REQUIRED"):
        registry.promote(registered["artifact_ids"][0], report["id"], "ouroboros")


def test_artifact_lineage_and_dependency_capabilities(registry):
    _, _, parent = register(registry, artifacts=(proposal(),))
    strategy_id, skill_id = parent["artifact_ids"]
    child = proposal(parent_id=skill_id, source="Improved reproduction description.")
    with pytest.raises(ValueError, match="PARENT_NOT_AUTHORIZED"):
        register(registry, artifacts=(child,))
    with pytest.raises(ValueError, match="PARENT_MISMATCH"):
        register(
            registry,
            artifacts=(proposal(parent_id=strategy_id),),
            parent_artifact_ids=(strategy_id,),
        )
    with pytest.raises(ValueError, match="DEPENDENCY_CAPABILITY_ESCALATION"):
        register(registry, artifacts=(proposal(dependencies=(strategy_id,)),))
    _, _, descendant = register(
        registry,
        artifacts=(child,),
        parent_artifact_ids=(strategy_id, skill_id),
    )
    report = registry.benchmark(descendant["id"], "operator")
    assert report["comparisons"] == [{"parent_id": strategy_id, "passed_cases": 2}]
    assert registry.get_artifact(descendant["artifact_ids"][1])["parent_ids"] == [skill_id]


def test_dependency_requires_review_before_dependent_review(registry):
    _, _, parent = register(registry, artifacts=(proposal(),))
    _, _, child = register(
        registry, artifacts=(proposal(dependencies=(parent["artifact_ids"][1],)),)
    )
    benchmark = registry.benchmark(child["id"], "operator")
    child_id = child["artifact_ids"][1]
    with pytest.raises(ValueError, match="DEPENDENCY_REVIEW_REQUIRED"):
        registry.promote(child_id, benchmark["id"], "operator")
    parent_benchmark = registry.benchmark(parent["id"], "operator")
    registry.promote(parent["artifact_ids"][1], parent_benchmark["id"], "operator")
    assert registry.promote(child_id, benchmark["id"], "operator")["status"] == "REVIEWED_PROPOSAL"


def test_undeclared_work_capabilities_are_rejected(registry):
    work = registry.create_work_order(spec(), "research")
    constrained = work.model_copy(update={"capabilities": ("compute_signal",)})
    with (
        patch.object(registry, "get_work_order", return_value=constrained),
        pytest.raises(ValueError, match="UNDECLARED_ARTIFACT_CAPABILITY"),
    ):
        registry.accept(
            ImplementationBundle(
                work_order_id=work.id,
                spec_hash=work.spec_hash,
                source=SOURCE,
            ),
            "ouroboros",
        )


def test_ouroboros_engineer_receives_frozen_spec_and_cannot_substitute_result(registry):
    work = registry.create_work_order(spec(), "research", token_budget=1000, max_seconds=2)
    calls = []
    result = ImplementationBundle(work_order_id=work.id, spec_hash=work.spec_hash, source=SOURCE)

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"task_id": runtime_task_id(work.id)}
            if request.method == "POST"
            else {
                "status": "completed",
                "result": result.model_dump_json(),
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = OuroborosEngineer("https://isolated.test", "/research-workspace", client)
        assert adapter.implement(work, 10) == result
        sent = json.loads(calls[0].content)
        assert sent["timeout_sec"] == 2
        assert sent["task_id"] == runtime_task_id(work.id)
        assert sent["workspace_mode"] == "external" and sent["memory_mode"] == "forked"
        assert "Do not invent" in sent["description"]
        assert (
            work.spec_hash in sent["description"] and '"token_budget":1000' in sent["description"]
        )
        assert calls[-1].url.path == f"/api/tasks/{runtime_task_id(work.id)}/cancel"
        result = result.model_copy(update={"work_order_id": "other"})
        with pytest.raises(ValueError, match="WORK_ORDER_MISMATCH"):
            adapter.implement(work, 1)
        with pytest.raises(ValueError, match="WORK_ORDER_SPEC_INTEGRITY"):
            adapter.implement(work.model_copy(update={"spec_hash": "c" * 64}), 1)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), 1801])
def test_ouroboros_time_budget_is_finite_and_bounded(timeout):
    with pytest.raises(ValueError, match="TIMEOUT_BOUND"):
        OuroborosEngineer("https://isolated.test", "/workspace").generate({}, timeout)


def test_acceptance_case_forbids_nonfinite_and_unknown_fields():
    with pytest.raises(ValidationError):
        SignalCase(history=[float("nan")], expected=0)
    with pytest.raises(ValidationError):
        ImplementationBundle(work_order_id="w", spec_hash="a" * 64, source=SOURCE, passed=True)


def test_engineering_attempts_are_append_only_and_transition_once(registry):
    work = registry.create_work_order(spec(), "research", token_budget=1234, max_seconds=45)
    attempt = registry.create_attempt(work.id, "campaign", "research-attempt", "worker")
    assert attempt["status"] == "QUEUED" and attempt["budget"] == {
        "tokens": 1234,
        "seconds": 45,
    }
    assert attempt["runtime_task_id"] == runtime_task_id(work.id)
    registry.transition_attempt(attempt["id"], "RUNNING", "ouroboros", "worker")
    registry.transition_attempt(attempt["id"], "VALIDATING", "contract", "worker")
    completed = registry.transition_attempt(
        attempt["id"],
        "SUCCEEDED",
        "complete",
        "worker",
        bundle_id="bundle",
        benchmark_id="benchmark",
    )
    retained = registry.list_attempts()[0]
    assert completed["bundle_id"] == "bundle"
    assert retained["status"] == "SUCCEEDED" and len(retained["events"]) == 3
    with pytest.raises(ValueError, match="TRANSITION_INVALID"):
        registry.transition_attempt(attempt["id"], "FAILED", "late", "worker")
    with pytest.raises(ValueError, match="STAGE_INVALID"):
        registry.transition_attempt(attempt["id"], "FAILED", "", "worker")
