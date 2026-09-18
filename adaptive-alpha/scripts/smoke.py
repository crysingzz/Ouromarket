"""Exercise the deployed stack using only public authenticated API contracts."""

import time
from pathlib import Path

import httpx

root = Path(__file__).resolve().parent.parent
token = (root / ".secrets/operator_token").read_text().strip()
with httpx.Client(
    base_url="http://127.0.0.1:8787", headers={"Authorization": f"Bearer {token}"}, timeout=45
) as client:
    for _attempt in range(60):
        try:
            if client.get("/healthz").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise SystemExit("Stack did not become healthy")
    job_response = client.post(
        "/api/research/jobs",
        json={
            "objective": "Smoke test: daily trend persistence after costs",
            "budget": {"max_experiments": 3, "compute_seconds": 30, "llm_tokens": 0},
        },
    )
    job_response.raise_for_status()
    job_id = job_response.json()["id"]
    run = client.post(f"/api/research/jobs/{job_id}/run", json={})
    run.raise_for_status()
    if run.json()["status"] != "COMPLETED" or run.json()["experiments"] != 3:
        raise SystemExit("Research lifecycle did not complete")
    experiments = client.get("/api/experiments").json()
    selected = [experiment for experiment in experiments if experiment["research_job_id"] == job_id]
    if len(selected) != 3 or any(e["status"] in {"ERROR", "INVALID"} for e in selected):
        raise SystemExit("Evaluation failed or lost records")
    if any(set(e["hidden"]) != {"verdict", "score"} for e in selected if e["hidden"]):
        raise SystemExit("Hidden feedback contract violated")
    if not client.get("/api/audit").json()["verified"]:
        raise SystemExit("Audit chain verification failed")
    research = (root / ".secrets/research_token").read_text().strip()
    forbidden = client.post(
        "/api/risk/halt",
        json={"reason": "Agent privilege boundary probe"},
        headers={"Authorization": f"Bearer {research}"},
    )
    if forbidden.status_code != 403:
        raise SystemExit("Research identity crossed operator boundary")
print("PASS: deployed research lifecycle, private evaluator, retained experiments, audit and RBAC.")
