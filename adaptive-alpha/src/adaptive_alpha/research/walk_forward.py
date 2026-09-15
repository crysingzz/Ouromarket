"""Purged rolling training/test selection over a predeclared strategy matrix.

The caller must pre-register the candidate set. Applying this retrospectively to
variants already optimized against the same test periods is exploratory only.
"""

from typing import Any

import numpy as np

from adaptive_alpha.research.statistics import daily_sharpe


def rolling_selection(
    matrix: np.ndarray[Any, Any],
    train_bars: int = 120,
    test_bars: int = 30,
    embargo: int = 5,
    weights: np.ndarray[Any, Any] | None = None,
    cost_bps: float = 10,
) -> dict[str, Any]:
    if (
        matrix.ndim != 2
        or not 2 <= matrix.shape[1] <= 50
        or not np.isfinite(matrix).all()
        or np.any(matrix <= -1)
    ):
        raise ValueError("FINITE_VARIANT_MATRIX_REQUIRED")
    if not np.isfinite(cost_bps) or not 0 <= cost_bps <= 10000:
        raise ValueError("FINITE_NONNEGATIVE_COST_REQUIRED")
    if (
        train_bars < 60
        or test_bars < 10
        or embargo < 1
        or matrix.shape[0] < train_bars + embargo + test_bars
    ):
        raise ValueError("WALK_FORWARD_SAMPLE_OR_PURGE")
    if weights is not None and (
        weights.shape != matrix.shape
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
        or np.any(weights > 1)
    ):
        raise ValueError("ALIGNED_POSITION_MATRIX_REQUIRED")
    output = np.zeros(matrix.shape[0], dtype=np.float64)
    previous_weight = 0.0
    folds = []
    for test_start in range(train_bars + embargo, matrix.shape[0], test_bars):
        train_end = test_start - embargo
        train_start = train_end - train_bars
        test_end = min(test_start + test_bars, matrix.shape[0])
        training = matrix[train_start:train_end]
        scores = [daily_sharpe(training[:, i]) for i in range(matrix.shape[1])]
        winner = int(np.argmax(scores))
        output[test_start:test_end] = matrix[test_start:test_end, winner]
        if weights is not None:
            for bar in range(test_start, test_end):
                selected_weight = float(weights[bar, winner])
                within_model_change = abs(selected_weight - float(weights[bar - 1, winner]))
                actual_change = abs(selected_weight - previous_weight)
                output[bar] += (within_model_change - actual_change) * cost_bps / 10000
                previous_weight = selected_weight
        folds.append(
            {
                "train_start": train_start,
                "train_end_exclusive": train_end,
                "test_start": test_start,
                "test_end_exclusive": test_end,
                "selected_variant": winner,
                "training_score": scores[winner],
            }
        )
    evaluated = output[train_bars + embargo :]
    return {
        "method": "rolling-purged-model-selection-v1",
        "folds": folds,
        "embargo": embargo,
        "returns": evaluated.tolist(),
        "return": float(np.prod(1 + evaluated) - 1),
        "sharpe": daily_sharpe(evaluated) * float(np.sqrt(252)),
        "requires_preregistered_candidates": True,
        "switching_costs_included": weights is not None,
        "capital_eligible": False,
    }
