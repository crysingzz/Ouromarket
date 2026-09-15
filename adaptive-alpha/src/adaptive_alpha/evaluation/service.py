"""Separate process, private data/ledger, bounded aggregate-only feedback."""

import secrets
from contextlib import asynccontextmanager
from typing import Annotated, Any

import polars as pl
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from adaptive_alpha.config import Settings
from adaptive_alpha.data import dataset_manifest, synthetic_daily
from adaptive_alpha.domain import EvaluationRequest, HiddenFeedback, digest
from adaptive_alpha.evaluation.engine import PROTOCOL, evaluate
from adaptive_alpha.research.backtest import backtest
from adaptive_alpha.research.contracts import Bar, DatasetImport, ProgramEvaluation
from adaptive_alpha.store import Store


def create_evaluator(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    token = config.token("evaluator_token")
    store = Store(config.evaluator_database_url)
    frame = synthetic_daily(config.hidden_seed)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        store.initialize()
        yield
        store.engine.dispose()

    app = FastAPI(
        title="Private hidden evaluator",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credentials is None or not secrets.compare_digest(credentials.credentials, token):
            raise HTTPException(401, "Unauthorized")

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/evaluate", response_model=HiddenFeedback, dependencies=[Depends(authenticate)])
    def submit(request: EvaluationRequest) -> HiddenFeedback:
        request_hash = digest(request.model_dump(mode="json"))
        with store.transaction() as conn:
            try:
                existing = store.get(conn, request.experiment_id, "hidden-evaluation")
            except KeyError:
                existing = None
            if existing:
                if existing["request_hash"] != request_hash:
                    raise HTTPException(409, "Experiment identity conflict")
                return HiddenFeedback.model_validate(existing["feedback"])
            counter = store.state(conn, "query-budget", {"used": 0})
            if counter["used"] >= PROTOCOL.query_limit:
                raise HTTPException(429, "Evaluation query budget exhausted")
            counter["used"] += 1
            details: dict[str, Any]
            try:
                details = evaluate(frame, request.spec, trials=counter["used"])
                feedback = HiddenFeedback(verdict=details["verdict"], score=details["score"])
            except ValueError:
                details = {"error": "INVALID_CANDIDATE"}
                feedback = HiddenFeedback(verdict="FAIL", score=-10)
            store.set_state(conn, "query-budget", counter)
            store.append(
                conn,
                "hidden-evaluation",
                {
                    "request_hash": request_hash,
                    "feedback": feedback.model_dump(),
                    "details": details,
                    "dataset": dataset_manifest(frame, config.hidden_seed),
                    "protocol": PROTOCOL.version,
                },
                request.experiment_id,
            )
            store.audit(
                conn,
                "hidden.evaluated",
                "evaluator",
                {"experiment_id": request.experiment_id, "feedback": feedback.model_dump()},
            )
            return feedback

    @app.post(
        "/evaluate-program", response_model=HiddenFeedback, dependencies=[Depends(authenticate)]
    )
    def submit_program(request: ProgramEvaluation) -> HiddenFeedback:
        request_hash = digest(request.model_dump(mode="json"))
        with store.transaction() as conn:
            try:
                existing = store.get(conn, request.experiment_id, "hidden-program")
            except KeyError:
                existing = None
            if existing:
                if existing["request_hash"] != request_hash:
                    raise HTTPException(409, "Experiment identity conflict")
                return HiddenFeedback.model_validate(existing["feedback"])
            counter = store.state(conn, "query-budget", {"used": 0})
            if counter["used"] >= PROTOCOL.query_limit:
                raise HTTPException(429, "Evaluation query budget exhausted")
            counter["used"] += 1
            details: dict[str, Any]
            dataset_hash = "unavailable"
            try:
                if config.hidden_dataset_path:
                    dataset = DatasetImport.model_validate_json(
                        config.hidden_dataset_path.read_text()
                    )
                    if dataset.symbol != request.symbol:
                        raise ValueError("HIDDEN_UNIVERSE_MISMATCH")
                else:
                    part = frame.filter(pl.col("symbol") == request.symbol)
                    dataset = DatasetImport(
                        name="private-synthetic",
                        symbol=request.symbol,
                        provenance="Private synthetic diagnostic; never real capital validation",
                        adjustment="synthetic",
                        bars=[
                            Bar(
                                time=row["event_time"].isoformat(),
                                available_at=row["available_time"].isoformat(),
                                close=row["close"],
                                volume=0,
                            )
                            for row in part.to_dicts()
                        ],
                    )
                dataset_hash = digest(dataset.model_dump(mode="json"))
                details = backtest(request.source, dataset)
                feedback = HiddenFeedback(
                    verdict=details["verdict"],
                    score=round(max(-10, min(10, details["public_oos"]["sharpe"])), 2),
                )
            except ValueError:
                details = {"error": "INVALID_CANDIDATE_OR_DATA"}
                feedback = HiddenFeedback(verdict="FAIL", score=-10)
            store.set_state(conn, "query-budget", counter)
            store.append(
                conn,
                "hidden-program",
                {
                    "request_hash": request_hash,
                    "feedback": feedback.model_dump(),
                    "details": details,
                    "dataset_hash": dataset_hash,
                    "source_hash": digest(request.source),
                    "protocol": "generated-research-v1",
                },
                request.experiment_id,
            )
            store.audit(
                conn,
                "hidden.program_evaluated",
                "evaluator",
                {"experiment_id": request.experiment_id},
            )
            return feedback

    return app
