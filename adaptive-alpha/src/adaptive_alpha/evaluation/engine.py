"""Deterministic template evaluation. demo-v1 is NOT a capital admission protocol."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

from adaptive_alpha.data import validate_pit
from adaptive_alpha.domain import StrategySpec

Vector = npt.NDArray[np.float64]


@dataclass(frozen=True)
class EvaluationProtocol:
    version: str = "demo-v1"
    cost_bps: float = 10.0
    minimum_bars: int = 252
    minimum_trades: int = 3
    minimum_sharpe: float = 0.0
    max_drawdown: float = 0.20
    query_limit: int = 50


PROTOCOL = EvaluationProtocol()


def strategy_returns(prices: Vector, spec: StrategySpec, cost_bps: float) -> tuple[Vector, Vector]:
    """Signal at close t-1 determines exposure over t-1 → t; initial exposure is zero."""
    size = len(prices)
    signal = np.zeros(size, dtype=np.float64)
    momentum = prices[spec.lookback :] / prices[: -spec.lookback] - 1
    signal[spec.lookback :] = (
        momentum > 0 if spec.family == "momentum" else momentum < 0
    ) * spec.position_fraction
    weights = np.roll(signal, 1)
    weights[0] = 0
    raw_returns = np.zeros(size, dtype=np.float64)
    raw_returns[1:] = prices[1:] / prices[:-1] - 1
    turnover = np.abs(np.diff(weights, prepend=0))
    return weights * raw_returns - turnover * cost_bps / 10_000, turnover


def metrics(returns: Vector, turnover: Vector) -> dict[str, Any]:
    if not len(returns) or not np.isfinite(returns).all() or np.any(returns <= -1):
        raise ValueError("INVALID_RETURNS")
    equity = np.cumprod(1 + returns)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    vol = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    tail = returns[returns <= np.quantile(returns, 0.05)]
    return {
        "return": float(equity[-1] - 1),
        "cagr": float(equity[-1] ** (252 / len(returns)) - 1),
        "volatility": vol * np.sqrt(252),
        "sharpe": float(np.mean(returns) / vol * np.sqrt(252)) if vol > 1e-12 else 0.0,
        "max_drawdown": float(np.max(1 - equity / peaks)),
        "cvar": max(0.0, -float(np.mean(tail))),
        "turnover": float(turnover.sum()),
        "trades": int(np.count_nonzero(turnover)),
        "bars": len(returns),
    }


def evaluate(frame: pl.DataFrame, spec: StrategySpec, trials: int = 1) -> dict[str, Any]:
    validate_pit(frame)
    if not spec.universe or len(set(spec.universe)) != len(spec.universe):
        raise ValueError("INVALID_UNIVERSE")
    vectors, changes = [], []
    common_dates: list[Any] | None = None
    for symbol in spec.universe:
        part = frame.filter(pl.col("symbol") == symbol)
        dates = part["event_time"].to_list()
        if common_dates is not None and common_dates != dates:
            raise ValueError("UNALIGNED_UNIVERSE")
        common_dates = dates
        prices = np.asarray(part["close"].to_numpy(), dtype=np.float64)
        if len(prices) < PROTOCOL.minimum_bars:
            raise ValueError("INSUFFICIENT_SAMPLE")
        returns, turnover = strategy_returns(prices, spec, PROTOCOL.cost_bps)
        vectors.append(returns)
        changes.append(turnover)
    combined = np.mean(vectors, axis=0)
    turnover = np.mean(changes, axis=0)
    start = max(121, spec.lookback + 1)
    combined, turnover = combined[start:], turnover[start:]
    split_a, split_b = int(len(combined) * 0.5), int(len(combined) * 0.75)
    full = metrics(combined, turnover)
    oos = metrics(combined[split_b:], turnover[split_b:])
    folds = [
        metrics(chunk, changed)
        for chunk, changed in zip(
            np.array_split(combined[split_a:], 3),
            np.array_split(turnover[split_a:], 3),
            strict=True,
        )
    ]
    # Conservative, explicitly non-DSR multiplicity penalty. Full DSR/PBO are a later protocol.
    penalty = float(np.sqrt(2 * np.log(max(1, trials)) / max(1, len(combined))) * np.sqrt(252))
    score = float(np.clip(oos["sharpe"] - penalty, -10, 10))
    gates = {
        "sample": oos["bars"] >= 60,
        "trades": full["trades"] >= PROTOCOL.minimum_trades,
        "after_costs": oos["return"] > 0,
        "drawdown": full["max_drawdown"] <= PROTOCOL.max_drawdown,
        "walk_forward": sum(fold["return"] > 0 for fold in folds) >= 2,
        "multiplicity": score > PROTOCOL.minimum_sharpe,
    }
    return {
        "protocol": PROTOCOL.version,
        "verdict": "PASS" if all(gates.values()) else "FAIL",
        "score": round(score, 2),
        "metrics": full,
        "public_oos": oos,
        "walk_forward": folds,
        "gates": gates,
        "cost_bps": PROTOCOL.cost_bps,
        "trials": trials,
        "multiple_testing_method": "conservative-sharpe-penalty-demo",
        "dsr": None,
        "pbo": None,
        "capital_eligible": False,
        "equity": [round(float(value), 6) for value in np.cumprod(1 + combined)[::5]],
    }
