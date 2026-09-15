"""Matched qualification and controlled reuse of Ouroboros engineering tools."""

import hashlib
from pathlib import Path

import pytest
from conftest import OPERATOR, RESEARCH
from pydantic import ValidationError
from test_engineering import SOURCE, proposal, register, spec

from adaptive_alpha.domain import digest
from adaptive_alpha.research.engineering import (
    EngineeringRegistry,
    ImplementationBundle,
    ToolAttachment,
    WorkOrder,
)
from adaptive_alpha.research.ouroboros import OuroborosEngineer
from adaptive_alpha.research.tool_catalog import (
    ToolAdoptionRequest,
    ToolBenchmarkPlanRequest,
    ToolCatalog,
    ToolQualificationRequest,
)

FAILING_SOURCE = "def signal(history):\n    return 0.5\n"


@pytest.fixture
def registry(tmp_path):
    from adaptive_alpha.store import Store

    store = Store(f"sqlite:///{tmp_path}/catalog.db")
    store.initialize()
    with store.transaction() as conn:
        store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        store.append(conn, "evidence", {"content_hash": "b" * 64}, "paper")
    yield EngineeringRegistry(store)
    store.engine.dispose()


def reviewed_tool(registry, **updates):
    item = proposal(**updates)
    work, _, bundle = register(registry, artifacts=(item,))
    benchmark = registry.benchmark(bundle["id"], "operator")
    artifact_id = bundle["artifact_ids"][1]
    registry.promote(artifact_id, benchmark["id"], "operator")
    return work, artifact_id


def independent_work(registry, number):
    return registry.create_work_order(
        spec(
            name=f"Independent task {number}",
            hypothesis=f"Independent market premise {number} predicts the next return",
        ),
        "research",
    )


def plans_for(registry, artifact_id, count=3):
    catalog = ToolCatalog(registry.store)
    return [
        catalog.prepare(
            ToolBenchmarkPlanRequest(
                request_id=f"comparison-{artifact_id[-8:]}-{number}",
                source_work_order_id=independent_work(registry, number).id,
                artifact_id=artifact_id,
            ),
            "operator",
        )
        for number in range(count)
    ]


def complete(registry, plan, *, baseline=False, trial=True):
    reports = []
    for arm, passed in (("baseline", baseline), ("trial", trial)):
        work = registry.get_work_order(plan[f"{arm}_work_order_id"])
        bundle = registry.accept(
            ImplementationBundle(
                work_order_id=work.id,
                spec_hash=work.spec_hash,
                source=SOURCE if passed else FAILING_SOURCE,
            ),
            "ouroboros",
        )
        reports.append(registry.benchmark(bundle["id"], "server"))
    return reports


def qualify_and_adopt(registry, **updates):
    _, artifact_id = reviewed_tool(registry, **updates)
    plans = plans_for(registry, artifact_id)
    for plan in plans:
        complete(registry, plan)
    catalog = ToolCatalog(registry.store)
    qualification = catalog.qualify(
        artifact_id,
        ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in plans)),
        "operator",
    )
    event = catalog.adopt(artifact_id, qualification["id"], "operator")
    return artifact_id, plans, qualification, event


def test_prepares_idempotent_paired_benchmark_plans(registry):
    _, artifact_id = reviewed_tool(registry)
    source = independent_work(registry, 1)
    catalog = ToolCatalog(registry.store)
    request = ToolBenchmarkPlanRequest(
        request_id="matched-comparison", source_work_order_id=source.id, artifact_id=artifact_id
    )
    plan = catalog.prepare(request, "operator")
    assert catalog.prepare(request, "operator") == plan
    baseline = registry.get_work_order(plan["baseline_work_order_id"])
    trial = registry.get_work_order(plan["trial_work_order_id"])
    assert baseline.purpose == trial.purpose == "tool-benchmark"
    assert baseline.tools == () and [tool.artifact_id for tool in trial.tools] == [artifact_id]
    assert plan["baseline_attempt_id"] != plan["trial_attempt_id"]
    attempts = {item["id"] for item in registry.list_attempts()}
    assert {plan["baseline_attempt_id"], plan["trial_attempt_id"]} <= attempts
    with registry.store.transaction() as conn:
        assert registry.store.verify_audit(conn)


def test_rejects_unreviewed_or_nonindependent_benchmark_inputs(registry):
    origin, _, bundle = register(registry, artifacts=(proposal(),))
    artifact_id = bundle["artifact_ids"][1]
    catalog = ToolCatalog(registry.store)
    request = ToolBenchmarkPlanRequest(
        request_id="unreviewed",
        source_work_order_id=independent_work(registry, 1).id,
        artifact_id=artifact_id,
    )
    with pytest.raises(ValueError, match="REVIEWED_TOOL_REQUIRED"):
        catalog.prepare(request, "operator")
    benchmark = registry.benchmark(bundle["id"], "operator")
    registry.promote(artifact_id, benchmark["id"], "operator")
    with pytest.raises(ValueError, match="INDEPENDENT_TOOL_BENCHMARK_REQUIRED"):
        catalog.prepare(
            ToolBenchmarkPlanRequest(
                request_id="same-spec", source_work_order_id=origin.id, artifact_id=artifact_id
            ),
            "operator",
        )
    with pytest.raises(ValueError, match="OPERATOR_TOOL_BENCHMARK_REQUIRED"):
        catalog.prepare(request, "research")


def test_qualifies_and_adopts_reusable_tool(registry):
    artifact_id, plans, qualification, event = qualify_and_adopt(registry)
    assert qualification["passed"] is True
    assert qualification["wins"] == len(plans) == 3
    assert qualification["regressions"] == 0
    assert event["action"] == "ADOPTED" and event["capital_eligible"] is False
    catalog = ToolCatalog(registry.store)
    assert (
        catalog.qualify(
            artifact_id,
            ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in plans)),
            "operator",
        )
        == qualification
    )
    assert catalog.adopt(artifact_id, qualification["id"], "operator") == event
    assert [item["artifact_id"] for item in catalog.active()] == [artifact_id]


def test_active_tool_is_snapshotted_for_ouroboros(registry, monkeypatch):
    artifact_id, _, _, _ = qualify_and_adopt(registry)
    work = independent_work(registry, 20)
    assert [tool.artifact_id for tool in work.tools] == [artifact_id]
    assert work.toolset_digest and artifact_id in work.model_dump_json()
    ToolCatalog(registry.store).verify_work_order(work)
    captured = {}

    def produce(self, prompt, timeout, *, work, checkpoint):
        assert timeout == 3
        captured["prompt"] = prompt
        return ImplementationBundle(
            work_order_id=work.id, spec_hash=work.spec_hash, source=SOURCE
        ).model_dump_json()

    monkeypatch.setattr(OuroborosEngineer, "_run", produce)
    bundle = OuroborosEngineer("https://ouroboros.test", "/workspace").implement(work, 3)
    assert bundle.work_order_id == work.id
    assert artifact_id in captured["prompt"]
    assert "untrusted reference data" in captured["prompt"]


def test_regression_and_revocation_fail_closed(registry):
    _, artifact_id = reviewed_tool(registry)
    plans = plans_for(registry, artifact_id)
    complete(registry, plans[0], baseline=True, trial=False)
    complete(registry, plans[1])
    complete(registry, plans[2])
    catalog = ToolCatalog(registry.store)
    qualification = catalog.qualify(
        artifact_id,
        ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in plans)),
        "operator",
    )
    assert qualification["passed"] is False and qualification["regressions"] == 1
    with pytest.raises(ValueError, match="PASSING_TOOL_QUALIFICATION_REQUIRED"):
        catalog.adopt(artifact_id, qualification["id"], "operator")

    active_id, _, _, _ = qualify_and_adopt(
        registry, name="audited-tool", path="skills/audited-tool.md"
    )
    pending = independent_work(registry, 40)
    event = catalog.revoke(active_id, "Regression detected during monitored use", "operator")
    assert event["action"] == "REVOKED"
    with pytest.raises(ValueError, match="WORK_ORDER_TOOL_REVOKED"):
        catalog.verify_work_order(pending)
    assert all(item["artifact_id"] != active_id for item in catalog.active())


def test_operator_api_and_ui_show_tool_lifecycle(client):
    registry = EngineeringRegistry(client.app.state.store)
    with registry.store.transaction() as conn:
        registry.store.append(conn, "dataset", {"manifest": {"content_hash": "a" * 64}}, "dataset")
        registry.store.append(conn, "evidence", {"content_hash": "b" * 64}, "paper")
    _, artifact_id = reviewed_tool(registry)
    plans = plans_for(registry, artifact_id)
    for plan in plans:
        complete(registry, plan)
    qualified = client.post(
        f"/api/engineering/artifacts/{artifact_id}/qualify",
        json={"plan_ids": [plan["id"] for plan in plans]},
    )
    assert qualified.status_code == 200 and qualified.json()["passed"] is True
    adopted = client.post(
        f"/api/engineering/artifacts/{artifact_id}/adopt",
        json=ToolAdoptionRequest(qualification_id=qualified.json()["id"]).model_dump(mode="json"),
    )
    assert adopted.status_code == 200 and adopted.json()["action"] == "ADOPTED"
    overview = client.get("/api/engineering").json()["tool_catalog"]
    assert overview["active"][0]["artifact_id"] == artifact_id
    assert overview["capital_eligible"] is False
    extra = independent_work(registry, 90)
    prepared = client.post(
        "/api/engineering/tool-benchmark-plans",
        json={
            "request_id": "operator-api-comparison",
            "source_work_order_id": extra.id,
            "artifact_id": artifact_id,
        },
    )
    assert prepared.status_code == 409  # An active version cannot benchmark itself.

    client.headers["Authorization"] = "Bearer " + RESEARCH
    assert (
        client.post(
            "/api/engineering/tool-benchmark-plans",
            json={"request_id": "forbidden", "source_work_order_id": "x", "artifact_id": "x"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/engineering/artifacts/{artifact_id}/adopt",
            json={"qualification_id": qualified.json()["id"]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/engineering/artifacts/{artifact_id}/revoke",
            json={"reason": "Operator access is required"},
        ).status_code
        == 403
    )
    client.headers["Authorization"] = "Bearer " + OPERATOR
    revoked = client.post(
        f"/api/engineering/artifacts/{artifact_id}/revoke",
        json={"reason": "Operator observed a verified regression"},
    )
    assert revoked.status_code == 200 and revoked.json()["action"] == "REVOKED"
    ui = Path(__file__).parents[1] / "src/adaptive_alpha/ui"
    assert 'id="engineering-tool-catalog"' in (ui / "index.html").read_text()
    script = (ui / "operations.js").read_text()
    assert "tool_catalog" in script and "catalog.protocol" in script


def test_tool_contracts_reject_tampering_and_unauthorized_selection(registry):
    with pytest.raises(ValidationError, match="TOOL_ATTACHMENT_SOURCE_MISMATCH"):
        ToolAttachment(
            artifact_id="artifact-one",
            kind="skill",
            name="one",
            source="A sufficiently long source",
            source_digest="0" * 64,
            runtime_digest="1" * 64,
            capabilities=("describe_research_tool",),
        )
    with pytest.raises(ValueError, match="OPERATOR_TOOL_SELECTION_REQUIRED"):
        registry.create_work_order(spec(), "research", tool_artifact_ids=())
    with pytest.raises(ValueError, match="OPERATOR_TOOL_BENCHMARK_REQUIRED"):
        registry.create_work_order(spec(), "research", purpose="tool-benchmark")

    _, artifact_id = reviewed_tool(registry)
    with registry.store.transaction() as conn:
        with pytest.raises(ValueError, match="TOOL_SELECTION_DUPLICATE"):
            ToolCatalog(registry.store).attachments(
                conn, (artifact_id, artifact_id), require_active=False
            )
        with pytest.raises(ValueError, match="TOOL_NOT_ACTIVE"):
            ToolCatalog(registry.store).attachments(conn, (artifact_id,), require_active=True)
    work = independent_work(registry, 70)
    attachment = ToolCatalog(registry.store)._attachment(registry.get_artifact(artifact_id))
    with pytest.raises(ValidationError, match="WORK_ORDER_TOOLSET_MISMATCH"):
        WorkOrder.model_validate(
            {**work.model_dump(mode="json"), "tools": [attachment], "toolset_digest": "f" * 64}
        )
    with pytest.raises(ValidationError, match="WORK_ORDER_TOOL_DUPLICATE"):
        WorkOrder.model_validate(
            {
                **work.model_dump(mode="json"),
                "tools": [attachment, attachment],
                "toolset_digest": digest(
                    [attachment.model_dump(mode="json"), attachment.model_dump(mode="json")]
                ),
            }
        )
    large = []
    for number in range(4):
        source = str(number) + "x" * 16_383
        large.append(
            ToolAttachment(
                artifact_id=f"large-{number}",
                kind="skill",
                name=f"large-{number}",
                source=source,
                source_digest=hashlib.sha256(source.encode()).hexdigest(),
                runtime_digest="1" * 64,
                capabilities=("describe_research_tool",),
            )
        )
    with pytest.raises(ValidationError, match="WORK_ORDER_TOOLSET_TOO_LARGE"):
        WorkOrder.model_validate(
            {
                **work.model_dump(mode="json"),
                "tools": large,
                "toolset_digest": digest([item.model_dump(mode="json") for item in large]),
            }
        )


def test_work_order_identity_and_benchmark_binding_fail_closed(registry):
    _, artifact_id = reviewed_tool(registry)
    plan = plans_for(registry, artifact_id, 1)[0]
    work = registry.get_work_order(plan["trial_work_order_id"])
    with pytest.raises(ValueError, match="WORK_ORDER_ID_CONFLICT"):
        registry.create_work_order(
            spec(name="Changed identity"),
            "operator",
            purpose="tool-benchmark",
            work_id=work.id,
        )
    with pytest.raises(ValueError, match="ENGINEERING_ATTEMPT_ID_CONFLICT"):
        registry.create_attempt(
            work.id,
            "other-campaign",
            "other-attempt",
            "operator",
            attempt_id=plan["trial_attempt_id"],
        )
    forged = WorkOrder.model_validate(
        {
            **work.model_dump(mode="json"),
            "input_digest": "f" * 64,
        }
    )
    with pytest.raises(ValueError, match="WORK_ORDER_TOOL_BINDING_INVALID"):
        ToolCatalog(registry.store).verify_work_order(forged)
    catalog = ToolCatalog(registry.store)
    catalog.verify_work_order(registry.get_work_order(plan["baseline_work_order_id"]))
    catalog.verify_work_order(work)
    legacy = WorkOrder.model_validate(
        {**independent_work(registry, 71).model_dump(mode="json"), "toolset_digest": None}
    )
    catalog.verify_work_order(legacy)
    attached_legacy = WorkOrder.model_validate(
        {**work.model_dump(mode="json"), "toolset_digest": None}
    )
    with pytest.raises(ValueError, match="WORK_ORDER_TOOLSET_MISMATCH"):
        catalog.verify_work_order(attached_legacy)
    modified_tool = work.tools[0].model_copy(update={"name": "forged-name"})
    modified_payload = [modified_tool.model_dump(mode="json")]
    modified = WorkOrder.model_validate(
        {
            **work.model_dump(mode="json"),
            "tools": modified_payload,
            "toolset_digest": digest(modified_payload),
            "input_digest": digest(
                {
                    "dataset": work.spec.dataset_hash,
                    "sources": work.spec.source_hashes,
                    "toolset": digest(modified_payload),
                }
            ),
        }
    )
    with pytest.raises(ValueError, match="WORK_ORDER_TOOL_BINDING_INVALID"):
        catalog.verify_work_order(modified)
    baseline = registry.get_work_order(plan["baseline_work_order_id"])
    trial_payload = [item.model_dump(mode="json") for item in work.tools]
    wrong_arm = WorkOrder.model_validate(
        {
            **baseline.model_dump(mode="json"),
            "tools": trial_payload,
            "toolset_digest": digest(trial_payload),
            "input_digest": digest(
                {
                    "dataset": baseline.spec.dataset_hash,
                    "sources": baseline.spec.source_hashes,
                    "toolset": digest(trial_payload),
                }
            ),
        }
    )
    with pytest.raises(ValueError, match="TOOL_BENCHMARK_PLAN_MISMATCH"):
        catalog.verify_work_order(wrong_arm)
    orphan = registry.create_work_order(
        spec(name="Orphan benchmark"),
        "operator",
        purpose="tool-benchmark",
        tool_artifact_ids=(),
    )
    with pytest.raises(ValueError, match="TOOL_BENCHMARK_PLAN_REQUIRED"):
        catalog.verify_work_order(orphan)


def test_qualification_requires_distinct_complete_matching_plans(registry):
    _, artifact_id = reviewed_tool(registry)
    plans = plans_for(registry, artifact_id)
    catalog = ToolCatalog(registry.store)
    with pytest.raises(ValueError, match="DISTINCT_TOOL_BENCHMARKS_REQUIRED"):
        catalog.qualify(
            artifact_id,
            ToolQualificationRequest(plan_ids=(plans[0]["id"],) * 3),
            "operator",
        )
    with pytest.raises(ValueError, match="TOOL_BENCHMARK_RESULT_REQUIRED"):
        catalog.qualify(
            artifact_id,
            ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in plans)),
            "operator",
        )
    with pytest.raises(ValueError, match="OPERATOR_TOOL_BENCHMARK_REQUIRED"):
        catalog.qualify(
            artifact_id,
            ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in plans)),
            "research",
        )


def test_catalog_rejects_forged_evidence_and_conflicting_plans(registry):
    _, artifact_id = reviewed_tool(registry)
    catalog = ToolCatalog(registry.store)
    with registry.store.transaction() as conn:
        strategy_id = next(
            item["id"]
            for item in registry.store.list_records(conn, "engineering-artifact")
            if item["kind"] == "strategy"
        )
        with pytest.raises(ValueError, match="REUSABLE_TOOL_REQUIRED"):
            catalog._reviewed(conn, strategy_id)
        artifact = registry.store.get(conn, artifact_id, "engineering-artifact")
        review = registry.store.related(conn, "artifact-review", "artifact_id", artifact_id)[0]
        benchmark = registry.store.get(conn, review["benchmark_id"], "artifact-benchmark")
        forged_id = "artifact-forged-review"
        forged_benchmark_id = "benchmark-forged-review"
        registry.store.append(
            conn,
            "engineering-artifact",
            {**artifact, "id": forged_id},
            forged_id,
        )
        registry.store.append(
            conn,
            "artifact-benchmark",
            {
                **benchmark,
                "id": forged_benchmark_id,
                "artifact_ids": [forged_id],
                "producer": "ouroboros",
            },
            forged_benchmark_id,
        )
        registry.store.append(
            conn,
            "artifact-review",
            {
                **review,
                "id": "review-forged",
                "artifact_id": forged_id,
                "benchmark_id": forged_benchmark_id,
            },
            "review-forged",
        )
        with pytest.raises(ValueError, match="REVIEWED_TOOL_REQUIRED"):
            catalog._reviewed(conn, forged_id)

    source = independent_work(registry, 80)
    request = ToolBenchmarkPlanRequest(
        request_id="conflict-request", source_work_order_id=source.id, artifact_id=artifact_id
    )
    catalog.prepare(request, "operator")
    with pytest.raises(ValueError, match="TOOL_BENCHMARK_REQUEST_CONFLICT"):
        catalog.prepare(
            request.model_copy(update={"source_work_order_id": independent_work(registry, 81).id}),
            "operator",
        )

    collision = ToolBenchmarkPlanRequest(
        request_id="identity-collision",
        source_work_order_id=independent_work(registry, 82).id,
        artifact_id=artifact_id,
    )
    collision_id = "tool-plan-" + digest(collision.model_dump(mode="json"))
    with registry.store.transaction() as conn:
        registry.store.append(
            conn,
            "engineering-tool-benchmark-plan",
            {"id": collision_id, "request_id": "unrelated"},
            collision_id,
        )
    with pytest.raises(ValueError, match="TOOL_BENCHMARK_PLAN_CONFLICT"):
        catalog.prepare(collision, "operator")


def test_qualification_rejects_invalid_reports_mismatch_and_reused_tasks(registry):
    _, artifact_id = reviewed_tool(registry)
    plans = plans_for(registry, artifact_id)
    catalog = ToolCatalog(registry.store)
    runtime = registry.get_work_order(plans[0]["baseline_work_order_id"]).runtime_digest
    with registry.store.transaction() as conn:
        registry.store.append(
            conn,
            "artifact-benchmark",
            {
                "id": "invalid-tool-report",
                "work_order_id": plans[0]["baseline_work_order_id"],
                "producer": "ouroboros",
                "protocol": "engineering-contract-v1",
                "runtime_digest": runtime,
            },
            "invalid-tool-report",
        )
    with pytest.raises(ValueError, match="TOOL_BENCHMARK_RESULT_INVALID"):
        catalog.qualify(
            artifact_id,
            ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in plans)),
            "operator",
        )

    _, other_id = reviewed_tool(registry, name="other", path="skills/other.md")
    with pytest.raises(ValueError, match="TOOL_BENCHMARK_PLAN_MISMATCH"):
        catalog.qualify(
            other_id,
            ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in plans)),
            "operator",
        )

    fresh = [
        catalog.prepare(
            ToolBenchmarkPlanRequest(
                request_id=f"fresh-comparison-{number}",
                source_work_order_id=independent_work(registry, 100 + number).id,
                artifact_id=artifact_id,
            ),
            "operator",
        )
        for number in range(3)
    ]
    for plan in fresh:
        complete(registry, plan)
    duplicate_ids = []
    with registry.store.transaction() as conn:
        for number, plan in enumerate(fresh):
            clone = {
                **plan,
                "id": f"reused-task-{number}",
                "source_spec_hash": fresh[0]["source_spec_hash"],
            }
            registry.store.append(conn, "engineering-tool-benchmark-plan", clone, clone["id"])
            duplicate_ids.append(clone["id"])
    with pytest.raises(ValueError, match="INDEPENDENT_TOOL_BENCHMARK_REQUIRED"):
        catalog.qualify(
            artifact_id,
            ToolQualificationRequest(plan_ids=tuple(duplicate_ids)),
            "operator",
        )


def test_harness_dependencies_supersession_and_revocation_guards(registry):
    catalog = ToolCatalog(registry.store)
    _, harness_id = reviewed_tool(
        registry,
        kind="harness",
        path="harnesses/check.py",
        source="def run(payload):\n    return payload\n",
        capabilities=("run_contract_tests",),
    )
    harness_plans = plans_for(registry, harness_id)
    for plan in harness_plans:
        complete(registry, plan)
    harness_q = catalog.qualify(
        harness_id,
        ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in harness_plans)),
        "operator",
    )
    with pytest.raises(ValueError, match="SUCCESSFUL_ISOLATED_HARNESS_RUN_REQUIRED"):
        catalog.adopt(harness_id, harness_q["id"], "operator")
    with registry.store.transaction() as conn:
        registry.store.append(
            conn, "tool-run", {"id": "harness-run", "artifact_id": harness_id}, "harness-run"
        )
        registry.store.set_state(conn, "tool-run:harness-run", {"status": "SUCCEEDED"})
        registry.store.append(
            conn,
            "tool-run-result",
            {"id": "harness-result", "tool_run_id": "harness-run"},
            "harness-result",
        )
    assert catalog.adopt(harness_id, harness_q["id"], "operator")["action"] == "ADOPTED"

    parent_id, _, _, _ = qualify_and_adopt(registry, name="dependency", path="skills/dependency.md")
    _, child_id = reviewed_tool(
        registry,
        name="dependent",
        path="skills/dependent.md",
        dependencies=(parent_id,),
    )
    with registry.store.transaction() as conn:
        state = registry.store.state(conn, catalog.state_id, {"active": {}})
        del state["active"]["skill:dependency"]
        registry.store.set_state(conn, catalog.state_id, state)
    with pytest.raises(ValueError, match="ACTIVE_TOOL_DEPENDENCY_REQUIRED"):
        catalog.prepare(
            ToolBenchmarkPlanRequest(
                request_id="missing-dependency",
                source_work_order_id=independent_work(registry, 91).id,
                artifact_id=child_id,
            ),
            "operator",
        )
    with registry.store.transaction() as conn:
        state = registry.store.state(conn, catalog.state_id, {"active": {}})
        state["active"]["skill:dependency"] = parent_id
        registry.store.set_state(conn, catalog.state_id, state)
    child_plans = plans_for(registry, child_id)
    for plan in child_plans:
        complete(registry, plan)
    child_q = catalog.qualify(
        child_id,
        ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in child_plans)),
        "operator",
    )
    with registry.store.transaction() as conn:
        state = registry.store.state(conn, catalog.state_id, {"active": {}})
        del state["active"]["skill:dependency"]
        registry.store.set_state(conn, catalog.state_id, state)
    with pytest.raises(ValueError, match="ACTIVE_TOOL_DEPENDENCY_REQUIRED"):
        catalog.adopt(child_id, child_q["id"], "operator")
    with registry.store.transaction() as conn:
        state = registry.store.state(conn, catalog.state_id, {"active": {}})
        state["active"]["skill:dependency"] = parent_id
        registry.store.set_state(conn, catalog.state_id, state)
    catalog.adopt(child_id, child_q["id"], "operator")
    with pytest.raises(ValueError, match="TOOL_HAS_ACTIVE_DEPENDENTS"):
        catalog.revoke(parent_id, "Dependency is still used by the child", "operator")
    _, parent_replacement_id = reviewed_tool(
        registry,
        name="dependency",
        path="skills/dependency-v2.md",
        source="Updated dependency implementation proposal.",
    )
    parent_replacement_plans = plans_for(registry, parent_replacement_id)
    for plan in parent_replacement_plans:
        complete(registry, plan)
    parent_replacement_q = catalog.qualify(
        parent_replacement_id,
        ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in parent_replacement_plans)),
        "operator",
    )
    with pytest.raises(ValueError, match="TOOL_HAS_ACTIVE_DEPENDENTS"):
        catalog.adopt(parent_replacement_id, parent_replacement_q["id"], "operator")

    original_id, _, _, _ = qualify_and_adopt(registry)
    _, replacement_id = reviewed_tool(registry)
    replacement_plans = plans_for(registry, replacement_id)
    for plan in replacement_plans:
        complete(registry, plan)
    replacement_q = catalog.qualify(
        replacement_id,
        ToolQualificationRequest(plan_ids=tuple(plan["id"] for plan in replacement_plans)),
        "operator",
    )
    replaced = catalog.adopt(replacement_id, replacement_q["id"], "operator")
    assert replaced["supersedes_artifact_id"] is not None
    assert any(event["action"] == "SUPERSEDED" for event in catalog.overview()["events"])
    with pytest.raises(ValueError, match="OPERATOR_TOOL_ADOPTION_REQUIRED"):
        catalog.adopt(replacement_id, replacement_q["id"], "research")
    with pytest.raises(ValueError, match="OPERATOR_TOOL_ADOPTION_REQUIRED"):
        catalog.revoke(replacement_id, "A sufficiently detailed reason", "research")
    with pytest.raises(ValueError, match="TOOL_REVOCATION_REASON_INVALID"):
        catalog.revoke(replacement_id, "short", "operator")
    with pytest.raises(ValueError, match="TOOL_NOT_ACTIVE"):
        catalog.revoke(original_id, "Superseded version is no longer active", "operator")
