"""Actual pinned upstream API acceptance, with zero LLM calls and no generated code."""
# ruff: noqa: S101 — assertions belong to this acceptance test, not a production gate

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

from adaptive_alpha.domain import digest
from adaptive_alpha.research.engineering import ResearchSpec, WorkOrder
from adaptive_alpha.research.ouroboros import OuroborosEngineer

root = Path(__file__).resolve().parent
pin = json.loads((root / "upstream.json").read_text())
token = (root / ".secrets/ouroboros_token").read_text().strip()
url = "http://127.0.0.1:8765"
with httpx.Client(base_url=url, timeout=30, trust_env=False) as client:
    for _attempt in range(30):
        try:
            response = client.get("/api/health")
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise SystemExit("Ouroboros health deadline")
    assert response.json()["version"] == pin["release"]
    assert client.get("/integration/status").status_code == 401
    client.headers["Authorization"] = "Bearer " + token
    state = client.get("/integration/status").raise_for_status().json()
    assert state["commit"] == pin["commit"] and not state["execution_enabled"]
    adapter = OuroborosEngineer(
        url, "/workspaces", client, service_token=token, provision_workspaces=True
    )
    try:
        adapter.check_ready()
    except ValueError as exc:
        assert str(exc) == "OUROBOROS_EXECUTION_NOT_READY"
    else:
        raise AssertionError("Bootstrap unexpectedly allows model execution")
    research = ResearchSpec(
        name="Protocol acceptance fixture",
        hypothesis="A fixed historical trend implies continuation",
        rationale="Controlled fixture for API compatibility only",
        evidence_ids=("fixture-paper",),
        source_hashes=("a" * 64,),
        contradictions=(),
        failure_modes=("A reversal refutes continuation",),
        decision_rules=("Hold when the last close exceeds the first close",),
        dataset_id="fixture-data",
        dataset_hash="b" * 64,
        acceptance_cases=(
            {"history": [100, 101], "expected": 1},
            {"history": [101, 100], "expected": 0},
        ),
    )
    work = WorkOrder(
        id="work-" + str(uuid4()),
        spec=research,
        spec_hash=digest(research.model_dump(mode="json")),
        input_digest="c" * 64,
        runtime_digest="d" * 64,
        max_seconds=10,
    )
    workspace = (
        client.post("/integration/workspaces", json=work.model_dump(mode="json"))
        .raise_for_status()
        .json()
    )
    assert (
        client.post("/integration/workspaces", json=work.model_dump(mode="json")).json()
        == workspace
    )
    assert client.post("/api/settings", json={"OPENAI_API_KEY": "forbidden"}).status_code == 403
    assert (
        client.post(
            "/api/tasks", json={"description": "outside", "workspace_root": "/opt/ouroboros"}
        ).status_code
        == 400
    )
    admitted = client.post(
        "/api/tasks",
        json={
            "description": "Protocol fixture only: retain this frozen WorkOrder. No model execution is enabled.\n"
            + work.model_dump_json(),
            "workspace_root": workspace["workspace_root"],
            "workspace_mode": "external",
            "memory_mode": "forked",
            "attachments": [],
            "actor_id": "alpha-research",
            "source": "adaptive-alpha",
            "timeout_sec": 10,
            "metadata": {"source": "adaptive-alpha"},
        },
    )
    assert admitted.status_code == 503
    assert admitted.json()["reason_code"] == "worker_pool_unavailable"
    absent = "protocol-absent-" + uuid4().hex
    assert client.get("/api/tasks/" + absent).status_code == 404
    assert client.post("/api/tasks/" + absent + "/cancel", json={}).status_code == 404
report = {
    "upstream": pin,
    "work_order_id": work.id,
    "admission": "refused_worker_pool_unavailable",
    "http_status": admitted.status_code,
    "model_calls": 0,
    "execution_ready": False,
    "capital_eligible": False,
}
(root / ".state").mkdir(exist_ok=True)
(root / ".state/protocol-acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    "PASS: actual Ouroboros health, auth, Git workspace and explicit unready-pool refusal; no model execution"
)
