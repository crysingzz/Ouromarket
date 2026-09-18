"""Thin authenticated HTTP/UI façade for research and independent paper controls."""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from adaptive_alpha.agents.baseline import mutate
from adaptive_alpha.api.operations import register_operations
from adaptive_alpha.artifacts import ArtifactStore
from adaptive_alpha.config import Settings
from adaptive_alpha.data import synthetic_daily
from adaptive_alpha.domain import (
    Hypothesis,
    JobRequest,
    KillRequest,
    MutationRequest,
    OrderIntent,
    StrategySpec,
)
from adaptive_alpha.execution import Execution
from adaptive_alpha.orchestrator import HiddenEvaluator, Orchestrator, RemoteEvaluator
from adaptive_alpha.research.benchmark import (
    AgentRevision,
    BenchmarkRequest,
    benchmark_report,
    create_benchmark,
    propose_revision,
)
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.contracts import Bar, CampaignRequest, DatasetImport, PITDatasetImport
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.research.departments import POLICIES, queue_counts
from adaptive_alpha.research.forward import ForwardPaper
from adaptive_alpha.research.lifecycle import StrategyLifecycle
from adaptive_alpha.research.pit import (
    import_pit_dataset,
    materialize_snapshot,
    verification_report,
)
from adaptive_alpha.research.portfolio import allocate, market_features, pareto_population
from adaptive_alpha.research.setup import ProviderSetup, configure_provider, load_provider
from adaptive_alpha.risk.engine import policy_dict
from adaptive_alpha.store import Store, records


def create_app(
    settings: Settings | None = None, evaluator: HiddenEvaluator | None = None
) -> FastAPI:
    config = settings or Settings()
    operator_token = config.token("operator_token")
    research_token = config.token("research_token")
    if len({operator_token, research_token, config.token("evaluator_token")}) != 3:
        raise ValueError("Operator, research and evaluator identities must use distinct tokens")
    store = Store(
        config.database_url, manage_schema=config.manage_schema, artifact_dir=config.artifact_dir
    )
    orchestrator = Orchestrator(store, evaluator or RemoteEvaluator(config), config)
    execution = Execution(store)
    campaigns = Campaigns(store, config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        store.initialize()
        execution.initialize()
        yield
        store.engine.dispose()

    app = FastAPI(
        title="Adaptive Alpha Engine",
        version="0.3.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.execution = execution
    bearer = HTTPBearer(auto_error=False)

    def identity(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> str:
        if credentials:
            if secrets.compare_digest(credentials.credentials, operator_token):
                return "operator"
            if secrets.compare_digest(credentials.credentials, research_token):
                return "research"
        raise HTTPException(
            401, "Valid bearer token required", headers={"WWW-Authenticate": "Bearer"}
        )

    def operator(actor: Annotated[str, Depends(identity)]) -> str:
        if actor != "operator":
            raise HTTPException(403, "Operator identity required")
        return actor

    @app.middleware("http")
    async def secure_headers(request: Request, call_next: Any) -> Any:
        if request.method in {"POST", "PUT", "PATCH"}:
            length = request.headers.get("content-length", "")
            body_limit = (
                2_000_000 if request.url.path in {"/api/datasets", "/api/pit-datasets"} else 65_536
            )
            if not length.isdigit() or int(length) > body_limit:
                return JSONResponse(
                    {"detail": f"Body length required; limit {body_limit} bytes"}, status_code=413
                )
        response = await call_next(request)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "detail": [
                    {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": "Record not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def conflict(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Persistence unavailable; operation not admitted"}, status_code=503
        )

    @app.get("/healthz")
    def health() -> dict[str, str]:
        with store.engine.connect() as conn:
            conn.execute(select(1))
        return {"status": "ok", "mode": config.mode}

    @app.get("/api/openapi.json", dependencies=[Depends(operator)])
    def schema() -> dict[str, Any]:
        return app.openapi()

    @app.post("/api/research/jobs", status_code=201)
    def create_job(body: JobRequest, actor: Annotated[str, Depends(identity)]) -> dict[str, Any]:
        return orchestrator.create(body, actor)

    @app.get("/api/research/jobs", dependencies=[Depends(identity)])
    def jobs() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return [
                {**job, **store.state(conn, f"job:{job['id']}")}
                for job in store.list_records(conn, "job")
            ]

    @app.get("/api/research/jobs/{job_id}", dependencies=[Depends(identity)])
    def get_job(job_id: str) -> dict[str, Any]:
        return orchestrator.get(job_id)

    @app.post("/api/research/jobs/{job_id}/run")
    def run_job(job_id: str, actor: Annotated[str, Depends(identity)]) -> dict[str, Any]:
        return orchestrator.run(job_id, actor)

    @app.post("/api/research/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, actor: Annotated[str, Depends(identity)]) -> dict[str, Any]:
        return orchestrator.cancel(job_id, actor)

    @app.post("/api/hypotheses", status_code=201)
    def hypothesis(body: Hypothesis, actor: Annotated[str, Depends(identity)]) -> dict[str, Any]:
        with store.transaction() as conn:
            store.append(conn, "hypothesis", body.model_dump(mode="json"), body.id)
            store.audit(conn, "hypothesis.created", actor, {"id": body.id})
        return body.model_dump(mode="json")

    @app.get("/api/hypotheses/{hypothesis_id}", dependencies=[Depends(identity)])
    def get_hypothesis(hypothesis_id: str) -> dict[str, Any]:
        with store.transaction() as conn:
            return store.get(conn, hypothesis_id, "hypothesis")

    @app.post("/api/strategies", status_code=201)
    def create_strategy(
        body: StrategySpec, actor: Annotated[str, Depends(identity)]
    ) -> dict[str, Any]:
        orchestrator.add_strategy(body, actor)
        return body.model_dump(mode="json")

    @app.get("/api/strategies", dependencies=[Depends(identity)])
    def strategies() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return [
                {**spec, **store.state(conn, f"strategy:{spec['id']}")}
                for spec in store.list_records(conn, "strategy")
            ]

    @app.get("/api/strategies/{strategy_id}", dependencies=[Depends(identity)])
    def strategy(strategy_id: str) -> dict[str, Any]:
        with store.transaction() as conn:
            return {
                **store.get(conn, strategy_id, "strategy"),
                **store.state(conn, f"strategy:{strategy_id}"),
            }

    @app.get("/api/strategies/{strategy_id}/lineage", dependencies=[Depends(identity)])
    def lineage(strategy_id: str) -> dict[str, Any]:
        with store.transaction() as conn:
            spec = store.get(conn, strategy_id, "strategy")
            return {
                "id": strategy_id,
                "parents": spec["parent_strategies"],
                "mutation": spec["mutation_metadata"],
            }

    @app.post("/api/strategies/{strategy_id}/paper")
    def admit_paper(strategy_id: str, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        with store.transaction() as conn:
            store.get(conn, strategy_id, "strategy")
            state = store.state(conn, f"strategy:{strategy_id}")
            if state.get("status") not in ("VALIDATED", "PAPER"):
                raise ValueError("VALIDATION_REQUIRED")
            state["status"] = "PAPER"
            store.set_state(conn, f"strategy:{strategy_id}", state)
            store.audit(
                conn,
                "capital.demo_paper_admitted",
                actor,
                {"strategy_id": strategy_id, "capital_eligible": False},
            )
            return state

    @app.get("/api/experiments", dependencies=[Depends(identity)])
    def experiments(limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return store.list_records(conn, "experiment", limit)

    @app.get("/api/attempts", dependencies=[Depends(identity)])
    def attempts() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return store.list_records(conn, "attempt")

    @app.post("/api/evolution/mutate", status_code=201)
    def mutation(body: MutationRequest, actor: Annotated[str, Depends(identity)]) -> dict[str, Any]:
        with store.transaction() as conn:
            parent = StrategySpec.model_validate(store.get(conn, body.strategy_id, "strategy"))
            second = (
                StrategySpec.model_validate(store.get(conn, body.second_parent_id, "strategy"))
                if body.second_parent_id
                else None
            )
        child = mutate(parent, 1, second)
        orchestrator.add_strategy(child, actor)
        return child.model_dump(mode="json")

    @app.get("/api/portfolio", dependencies=[Depends(operator)])
    def portfolio() -> dict[str, Any]:
        return execution.portfolio()

    @app.get("/api/risk/limits", dependencies=[Depends(identity)])
    def limits() -> dict[str, Any]:
        return policy_dict()

    @app.get("/api/risk/status", dependencies=[Depends(identity)])
    def risk_status() -> dict[str, Any]:
        with store.transaction() as conn:
            return {**store.state(conn, "kill"), "policy_version": "paper-v1", "mode": "demo-paper"}

    @app.post("/api/risk/check")
    def risk_check(body: OrderIntent, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return execution.check(body, False, actor)

    @app.post("/api/risk/halt")
    def halt(body: KillRequest, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return execution.kill(True, body.reason, actor)

    @app.post("/api/risk/resume")
    def resume(body: KillRequest, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return execution.kill(False, body.reason, actor)

    @app.post("/api/market/demo-refresh")
    def refresh_quotes(actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return execution.refresh_quotes(actor)

    @app.post("/api/orders")
    def order(body: OrderIntent, actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        return execution.check(body, True, actor)

    @app.get("/api/orders", dependencies=[Depends(operator)])
    def orders() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return store.list_records(conn, "order")

    @app.get("/api/fills", dependencies=[Depends(operator)])
    def fills() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return store.list_records(conn, "fill")

    @app.get("/api/audit", dependencies=[Depends(operator)])
    def audit() -> dict[str, Any]:
        with store.transaction() as conn:
            return {"verified": store.verify_audit(conn), "events": store.audit_events(conn)}

    @app.get("/api/dashboard", dependencies=[Depends(operator)])
    def dashboard() -> dict[str, Any]:
        with store.transaction() as conn:
            counts = {
                str(kind): int(count)
                for kind, count in conn.execute(
                    select(records.c.kind, func.count()).group_by(records.c.kind)
                )
            }
            return {
                "counts": counts,
                "dataset": orchestrator.dataset,
                "mode": config.mode,
                "agent": "deterministic-reference-v1",
                "real_capital_enabled": False,
                "capabilities": {
                    "template_research": "available",
                    "hidden_synthetic_evaluator": "available",
                    "paper_broker": "available",
                    "llm_provider": "openai_configurable",
                    "ouroboros": "task_adapter_requires_isolated_runtime",
                    "literature_connectors": "openalex",
                    "live_trading": "disabled",
                },
            }

    @app.post("/api/provider/setup")
    def setup_provider(
        body: ProviderSetup, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        result = configure_provider(config.provider_vault_dir, body)
        with store.transaction() as conn:
            store.audit(
                conn, "provider.configured", actor, {"provider": "openai", "model": result["model"]}
            )
        return result

    @app.get("/api/research/readiness", dependencies=[Depends(operator)])
    def readiness() -> dict[str, Any]:
        with store.transaction() as conn:
            workers = {
                department: store.state(conn, "research-worker:" + department)
                for department in POLICIES
            }
            queues = queue_counts(conn, store)
            engineering_worker = store.state(conn, "engineering-worker")
        return {
            "provider": "openai",
            "default_model": load_provider(config.provider_vault_dir).get(
                "model", config.openai_model
            ),
            "workers": workers,
            "queues": queues,
            "department_policies": {
                department: policy.model_dump(mode="json")
                for department, policy in POLICIES.items()
            },
            "engineering_worker": engineering_worker,
            "literature": ["openalex", "arxiv", "semantic_scholar"],
            "program_grammar": "signal-python-v1",
            "generated_capital_admission": False,
            "external_paper_broker": "not_configured",
        }

    @app.post("/api/datasets", status_code=201)
    def upload_dataset(
        body: DatasetImport, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return import_dataset(store, body, actor)

    @app.post("/api/datasets/demo", status_code=201)
    def create_demo_dataset(actor: Annotated[str, Depends(operator)]) -> dict[str, Any]:
        frame = synthetic_daily(42).filter(pl.col("symbol") == "SPY")
        dataset = DatasetImport(
            name="SPY · synthetic demonstration",
            symbol="SPY",
            provenance="Synthetic PCG64 seed 42; diagnostic fixture, not market evidence",
            adjustment="synthetic",
            bars=[
                Bar(
                    time=row["event_time"].isoformat(),
                    available_at=row["available_time"].isoformat(),
                    close=row["close"],
                    volume=0,
                )
                for row in frame.to_dicts()
            ],
        )
        return import_dataset(store, dataset, actor)

    @app.get("/api/datasets", dependencies=[Depends(identity)])
    def datasets() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return [item["manifest"] for item in store.list_records(conn, "dataset")]

    @app.post("/api/pit-datasets", status_code=201)
    def upload_pit_dataset(
        body: PITDatasetImport, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return import_pit_dataset(store, body, actor)

    @app.get("/api/pit-datasets", dependencies=[Depends(identity)])
    def pit_datasets() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return [item["manifest"] for item in store.list_records(conn, "pit-dataset")]

    @app.get("/api/pit-datasets/{ledger_id}/report", dependencies=[Depends(identity)])
    def pit_dataset_report(ledger_id: str) -> dict[str, Any]:
        return verification_report(store, ledger_id)

    @app.post("/api/pit-datasets/{ledger_id}/snapshots", status_code=201)
    def create_pit_snapshot(
        ledger_id: str,
        actor: Annotated[str, Depends(operator)],
        as_of: Annotated[str, Query(min_length=10, max_length=40)],
        series: Literal["raw", "adjusted"] = "raw",
    ) -> dict[str, Any]:
        return materialize_snapshot(store, ledger_id, as_of, series, actor)

    @app.get("/api/campaigns", dependencies=[Depends(identity)])
    def list_campaigns() -> list[dict[str, Any]]:
        return campaigns.list()

    @app.post("/api/campaigns", status_code=202)
    def create_campaign(
        body: CampaignRequest, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return campaigns.create(body, actor)

    @app.post("/api/campaigns/{campaign_id}/cancel", dependencies=[Depends(operator)])
    def cancel_campaign(campaign_id: str) -> dict[str, Any]:
        return campaigns.cancel(campaign_id)

    @app.get("/api/campaigns/{campaign_id}/artifacts", dependencies=[Depends(identity)])
    def campaign_artifacts(campaign_id: str) -> dict[str, Any]:
        with store.transaction() as conn:
            store.get(conn, campaign_id, "campaign")
            return {
                kind: store.related(conn, kind, "campaign_id", campaign_id)
                for kind in (
                    "evidence-packet",
                    "candidate",
                    "candidate-result",
                    "autonomous-attempt",
                    "campaign-diagnostics",
                    "campaign-event",
                    "agent-evolution-attempt",
                    "agent-evolution-result",
                )
            }

    @app.get("/api/knowledge", dependencies=[Depends(identity)])
    def knowledge() -> dict[str, Any]:
        with store.transaction() as conn:
            return {
                "evidence": store.list_records(conn, "evidence"),
                "packets": store.list_records(conn, "evidence-packet"),
                "claims": store.list_records(conn, "research-claim"),
                "mechanisms": store.list_records(conn, "research-mechanism"),
                "candidate_mechanisms": store.list_records(conn, "candidate-mechanism"),
                "edges": store.list_records(conn, "knowledge-edge"),
            }

    @app.get("/api/campaigns/{campaign_id}/population", dependencies=[Depends(identity)])
    def population(campaign_id: str) -> dict[str, Any]:
        with store.transaction() as conn:
            store.get(conn, campaign_id, "campaign")
            results = store.related(conn, "candidate-result", "campaign_id", campaign_id)
        return {"population": pareto_population(results), "allocation_proposal": allocate(results)}

    @app.get("/api/datasets/{dataset_id}/features", dependencies=[Depends(identity)])
    def features(dataset_id: str) -> dict[str, Any]:
        with store.transaction() as conn:
            record = store.get(conn, dataset_id, "dataset")
        return market_features(DatasetImport.model_validate(record["data"]))

    @app.post("/api/agents/revisions", status_code=201)
    def agent_revision(
        body: AgentRevision, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return propose_revision(store, body, actor)

    @app.get("/api/agents/revisions", dependencies=[Depends(identity)])
    def agent_revisions() -> list[dict[str, Any]]:
        with store.transaction() as conn:
            return store.list_records(conn, "agent-revision")

    @app.post("/api/agents/benchmarks", status_code=202)
    def agent_benchmark(
        body: BenchmarkRequest, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        return create_benchmark(store, campaigns, body, actor)

    @app.get("/api/agents/benchmarks", dependencies=[Depends(identity)])
    def list_benchmarks() -> dict[str, Any]:
        with store.transaction() as conn:
            entries = store.list_records(conn, "agent-benchmark")
            active = store.state(conn, "active-research-revision")
        return {"benchmarks": entries, "active_revision": active}

    @app.get("/api/agents/benchmarks/{benchmark_id}", dependencies=[Depends(identity)])
    def get_benchmark(benchmark_id: str) -> dict[str, Any]:
        return benchmark_report(store, benchmark_id)

    @app.post("/api/agents/benchmarks/{benchmark_id}/promote")
    def promote_agent(
        benchmark_id: str, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        report = benchmark_report(store, benchmark_id)
        if not report["promotion_evidence"]:
            raise ValueError("SUCCESSFUL_MATCHED_BENCHMARK_REQUIRED")
        with store.transaction() as conn:
            state = {"revision_id": report["revision_id"], "benchmark_id": benchmark_id}
            store.set_state(conn, "active-research-revision", state)
            store.audit(conn, "agent.revision_promoted", actor, state)
        return state

    @app.get("/api/campaigns/{campaign_id}/bundle", dependencies=[Depends(identity)])
    def campaign_bundle(campaign_id: str) -> dict[str, Any]:
        artifacts = campaign_artifacts(campaign_id)
        with store.transaction() as conn:
            campaign = store.get(conn, campaign_id, "campaign")
            dataset = store.get(conn, campaign["dataset_id"], "dataset")
        return {**artifacts, "campaign": campaign, "dataset": dataset}

    @app.post("/api/candidates/{candidate_id}/paper")
    def admit_forward(
        candidate_id: str, actor: Annotated[str, Depends(operator)]
    ) -> dict[str, Any]:
        lifecycle = StrategyLifecycle(store)
        with store.transaction() as conn:
            state = lifecycle.register_in_transaction(conn, candidate_id, actor)
            for stage, target in (
                ("RESEARCH", "LAB_VALIDATED"),
                ("LAB_VALIDATED", "SHADOW"),
                ("SHADOW", "PAPER"),
            ):
                if state["status"] == stage:
                    state = lifecycle.transition_in_transaction(
                        conn,
                        candidate_id,
                        target,
                        actor,
                        "Operator admitted internal paper observation",
                    )
            if not state["forward_eligible"]:
                raise ValueError("FORWARD_ADMISSION_REQUIRED")
            return ForwardPaper(store).create_account(conn, candidate_id, actor)

    @app.get("/api/forward", dependencies=[Depends(operator)])
    def forward_status() -> dict[str, Any]:
        with store.transaction() as conn:
            return {
                "accounts": [
                    store.state(conn, "forward:" + r["id"])
                    for r in store.list_records(conn, "forward-admission")
                ],
                "evidence": store.list_records(conn, "live-evidence"),
                "fills": store.list_records(conn, "forward-fill"),
                "worker": store.state(conn, "forward-worker"),
            }

    @app.get("/api/artifacts/{artifact_id}", dependencies=[Depends(identity)])
    def artifact_bytes(artifact_id: str) -> Response:
        if config.artifact_dir is None:
            raise HTTPException(503, "Artifact storage not configured")
        try:
            content = ArtifactStore(config.artifact_dir).get(artifact_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Artifact not found") from exc
        return Response(
            content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{artifact_id}"'},
        )

    register_operations(app, store, operator, lambda *args: campaigns.hidden(*args))

    ui = Path(__file__).resolve().parent.parent / "ui"
    app.mount("/assets", StaticFiles(directory=ui), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(ui / "index.html")

    return app
