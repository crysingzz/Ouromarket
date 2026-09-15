"""Host-owned execution and costs; generated code returns exposure only."""

import time
from typing import Any

import numpy as np

from adaptive_alpha.evaluation.engine import metrics
from adaptive_alpha.research.contracts import DatasetImport
from adaptive_alpha.research.datasets import timestamp
from adaptive_alpha.research.program import GRAMMAR, Program


def backtest(source: str, dataset: DatasetImport, timeout: float = 30) -> dict[str, Any]:
    program = Program(source)
    deadline = time.monotonic() + timeout
    prices = np.array([b.close for b in dataset.bars], dtype=np.float64)
    weights = np.zeros(len(prices), dtype=np.float64)
    # Strictly earlier decision-time availability. Late corrections never become
    # retroactively visible; input ordering follows the original event sequence.
    times = [timestamp(b.time) for b in dataset.bars]
    availability = [timestamp(b.available_at) for b in dataset.bars]
    for i in range(1, len(prices)):
        if time.monotonic() > deadline:
            raise ValueError("COMPUTE_BUDGET_EXHAUSTED")
        history = [float(prices[j]) for j in range(i) if availability[j] <= times[i - 1]]
        weights[i] = program.signal(history) if history else 0
    raw = np.zeros(len(prices), dtype=np.float64)
    raw[1:] = prices[1:] / prices[:-1] - 1
    turnover = np.abs(np.diff(weights, prepend=0))
    returns = weights * raw - turnover * 0.001
    # Initial 120 bars are reserved for warmup; holdout boundary is fixed before generation.
    start, split = 120, int(len(prices) * 0.75)
    oos = metrics(returns[split:], turnover[split:])
    overall = metrics(returns[start:], turnover[start:])
    stressed = metrics((weights * raw - turnover * 0.003)[split:], turnover[split:])
    folds = [
        metrics(returns[a:b], turnover[a:b])
        for a, b in zip(
            np.linspace(start, len(prices), 5, dtype=int)[:-1],
            np.linspace(start, len(prices), 5, dtype=int)[1:],
            strict=True,
        )
    ]
    gates = {
        "oos_positive": oos["return"] > 0,
        "cost_stress": stressed["return"] > 0,
        "drawdown": overall["max_drawdown"] <= 0.2,
        "sufficient_activity": overall["trades"] >= 3,
        "fold_stability": sum(f["return"] > 0 for f in folds) >= 3,
        "sizing": float(weights.max()) <= 0.2,
    }
    return {
        "protocol": "generated-research-v1",
        "grammar": GRAMMAR,
        "verdict": "PASS" if all(gates.values()) else "FAIL",
        "gates": gates,
        "metrics": overall,
        "public_oos": oos,
        "cost_stress": stressed,
        "temporal_folds": folds,
        "fold_method": "frozen program, sequential historical inference; no retraining",
        "returns": returns[start:].tolist(),
        "weights": weights[start:].tolist(),
        "equity": np.cumprod(1 + returns[start:])[::5].tolist(),
        "capital_eligible": False,
    }
