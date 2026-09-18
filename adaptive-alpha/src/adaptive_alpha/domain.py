"""Versioned transport contracts; no provider, persistence or execution dependencies."""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class JobStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class Verdict(StrEnum):
    PASS = "PASS"  # noqa: S105 — evaluation verdict, not a password
    FAIL = "FAIL"
    INVALID = "INVALID"
    OVERFIT = "OVERFIT"
    DUPLICATE = "DUPLICATE"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class Budget(Contract):
    llm_tokens: int = Field(default=0, ge=0, le=100_000)
    compute_seconds: int = Field(default=30, ge=1, le=120)
    max_experiments: int = Field(default=3, ge=1, le=12)


class JobRequest(Contract):
    objective: str = Field(min_length=8, max_length=2000)
    budget: Budget = Field(default_factory=Budget)
    universe: tuple[Literal["SPY", "QQQ", "IWM"], ...] = ("SPY",)
    timeframe: Literal["1d"] = "1d"


class Hypothesis(Contract):
    id: str = Field(default_factory=new_id)
    statement: str
    economic_rationale: str
    supporting_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    expected_regime: str
    expected_failure_modes: tuple[str, ...]
    proposed_test: str
    novelty_score: Fraction = 0
    confidence: Fraction = 0


class StrategySpec(Contract):
    schema_version: Literal["1"] = "1"
    id: str = Field(default_factory=new_id)
    version: int = Field(default=1, ge=1)
    name: str = Field(min_length=1, max_length=100)
    family: Literal["momentum", "mean_reversion"] = "momentum"
    hypothesis_id: str
    thesis: str = Field(max_length=4000)
    universe: tuple[Literal["SPY", "QQQ", "IWM"], ...] = ("SPY",)
    timeframe: Literal["1d"] = "1d"
    lookback: int = Field(default=20, ge=2, le=120)
    position_fraction: Fraction = 0.1
    evaluation_protocol: Literal["demo-v1"] = "demo-v1"
    parent_strategies: tuple[str, ...] = ()
    mutation_metadata: str = Field(default="Baseline", max_length=1000)

    def fingerprint(self) -> str:
        """Deduplicate executable semantics, not names or host-generated identities."""
        return digest(
            self.model_dump(
                include={
                    "family",
                    "universe",
                    "lookback",
                    "position_fraction",
                    "timeframe",
                    "evaluation_protocol",
                },
                mode="json",
            )
        )


class EvaluationRequest(Contract):
    experiment_id: str = Field(min_length=1, max_length=100)
    spec: StrategySpec


class HiddenFeedback(Contract):
    verdict: Literal["PASS", "FAIL"]
    score: float = Field(ge=-10, le=10)


class OrderIntent(Contract):
    order_intent_id: str = Field(default_factory=new_id, max_length=100)
    strategy_id: str = Field(min_length=1, max_length=100)
    instrument: Literal["SPY", "QQQ", "IWM"]
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, le=1_000_000)


class KillRequest(Contract):
    reason: str = Field(min_length=3, max_length=500)


class MutationRequest(Contract):
    strategy_id: str
    second_parent_id: str | None = None


class ConnectionHealth(Contract):
    market_data: bool
    reconciliation: bool
    permissions: bool
    risk: bool
