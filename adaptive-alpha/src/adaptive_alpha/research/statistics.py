"""Diagnostic PSR/DSR and CSCV; not an investment approval certificate.

References: Bailey & Lopez de Prado (2014), deflated-sharpe.pdf equation 2;
Bailey et al. (2015), backtest-prob.pdf (both davidhbailey.com/dhbpapers).
"""

import math
from itertools import combinations
from statistics import NormalDist
from typing import Any

import numpy as np

from adaptive_alpha.evaluation.engine import Vector


def daily_sharpe(values: Vector) -> float:
    std = float(np.std(values, ddof=1))
    return float(np.mean(values) / std) if std > 1e-12 else 0.0


def deflated_sharpe(values: Vector, trial_sharpes: list[float]) -> dict[str, Any]:
    n = len(trial_sharpes)
    if n < 2 or len(values) < 60 or np.std(values) < 1e-12:
        return {"probability": None, "reason": "INSUFFICIENT_VARIANTS_OR_VARIANCE"}
    normal = NormalDist()
    dispersion = float(np.std(trial_sharpes, ddof=1))
    gamma = 0.5772156649015329
    threshold = dispersion * (
        (1 - gamma) * normal.inv_cdf(1 - 1 / n) + gamma * normal.inv_cdf(1 - 1 / (n * math.e))
    )
    centered = (values - np.mean(values)) / np.std(values)
    skew, kurtosis = float(np.mean(centered**3)), float(np.mean(centered**4))
    sr = daily_sharpe(values)
    variance = 1 - skew * sr + (kurtosis - 1) * sr * sr / 4
    probability = normal.cdf(
        (sr - threshold) * math.sqrt(len(values) - 1) / math.sqrt(max(variance, 1e-12))
    )
    return {
        "probability": probability,
        "threshold_daily_sharpe": threshold,
        "trials": n,
        "assumptions": "IID approximation; trials treated as independent; not a capital gate",
    }


def pbo(matrix: np.ndarray[Any, Any], blocks: int = 8) -> dict[str, Any]:
    if (
        matrix.ndim != 2
        or matrix.shape[1] < 2
        or matrix.shape[0] < blocks * 10
        or blocks % 2
        or not np.isfinite(matrix).all()
    ):
        return {"probability": None, "reason": "INSUFFICIENT_ALIGNED_VARIANTS"}
    chunks = np.array_split(np.arange(matrix.shape[0]), blocks)
    losses, splits = 0, 0
    for selected in combinations(range(blocks), blocks // 2):
        train = matrix[np.concatenate([chunks[i] for i in selected])]
        test = matrix[np.concatenate([chunks[i] for i in range(blocks) if i not in selected])]
        train_scores = np.array([daily_sharpe(train[:, j]) for j in range(matrix.shape[1])])
        test_scores = np.array([daily_sharpe(test[:, j]) for j in range(matrix.shape[1])])
        winner = int(np.argmax(train_scores))
        # Average rank for ties, ascending from worst=1; ties at median count as loss.
        score = test_scores[winner]
        rank = (
            1
            + np.count_nonzero(test_scores < score)
            + (np.count_nonzero(test_scores == score) - 1) / 2
        )
        omega = rank / (matrix.shape[1] + 1)
        losses += int(omega <= 0.5)
        splits += 1
    return {"probability": losses / splits, "splits": splits, "method": "CSCV", "blocks": blocks}
