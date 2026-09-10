"""Deterministic research population, diversification and market diagnostics.

These outputs are proposals. The execution risk engine independently authorizes
orders; a portfolio recommendation never creates broker authority.
"""

from typing import Any

import numpy as np

from adaptive_alpha.domain import digest, now
from adaptive_alpha.research.contracts import DatasetImport


def market_features(dataset: DatasetImport) -> dict[str, Any]:
    close = np.array([b.close for b in dataset.bars], dtype=np.float64)
    returns = np.diff(close) / close[:-1]
    vol = float(np.std(returns[-60:], ddof=1) * np.sqrt(252))
    trend = float(close[-1] / close[-61] - 1)
    volume = float(np.mean([b.volume for b in dataset.bars[-20:]]))
    return {
        "version": "world-daily-v1",
        "dataset_hash": digest(dataset.model_dump(mode="json")),
        "as_of": dataset.bars[-1].available_at,
        "trend_60d": trend,
        "volatility_60d": vol,
        "average_daily_volume": volume,
        "regime": (
            "high_volatility"
            if vol > 0.3
            else "trend_up"
            if trend > 0.05
            else "trend_down"
            if trend < -0.05
            else "range"
        ),
        "point_in_time_verified": dataset.point_in_time_verified,
    }


def allocate(
    results: list[dict[str, Any]], max_gross: float = 0.6, max_weight: float = 0.2
) -> dict[str, Any]:
    eligible = [
        r for r in results if r.get("status") == "PASS" and r.get("public", {}).get("returns")
    ]
    eligible = sorted(eligible, key=lambda r: r["id"])[:50]
    if not eligible:
        return {
            "weights": {},
            "cash": 1.0,
            "clusters": [],
            "reason": "NO_PASSED_RESEARCH_CANDIDATES",
            "capital_eligible": False,
        }
    lengths = {len(r["public"]["returns"]) for r in eligible}
    if len(lengths) != 1:
        raise ValueError("ALIGNED_DATASET_REQUIRED")
    matrix = np.column_stack([r["public"]["returns"] for r in eligible])
    std = np.std(matrix, axis=0, ddof=1)
    valid = std > 1e-12
    eligible = [r for i, r in enumerate(eligible) if valid[i]]
    matrix = matrix[:, valid]
    std = std[valid]
    if not eligible:
        return {
            "weights": {},
            "cash": 1.0,
            "clusters": [],
            "reason": "ZERO_VARIANCE",
            "capital_eligible": False,
        }
    corr = (
        np.atleast_2d(np.corrcoef(matrix, rowvar=False)) if len(eligible) > 1 else np.ones((1, 1))
    )
    # Connected components of |correlation| >= .8, deterministic transitive clustering.
    unseen = set(range(len(eligible)))
    clusters = []
    while unseen:
        component = {min(unseen)}
        frontier = list(component)
        while frontier:
            node = frontier.pop()
            neighbors = {i for i in unseen if abs(corr[node, i]) >= 0.8} - component
            component.update(neighbors)
            frontier.extend(sorted(neighbors))
        unseen -= component
        clusters.append(sorted(component))
    weights = np.zeros(len(eligible))
    for cluster in clusters:
        inverse = 1 / std[cluster]
        weights[cluster] = np.minimum(
            max_weight, max_gross / len(clusters) * inverse / inverse.sum()
        )
    combined = matrix @ weights
    equity = np.cumprod(1 + combined)
    tail = combined[combined <= np.quantile(combined, 0.05)]
    cvar = max(0.0, -float(np.mean(tail)))
    vol = float(np.std(combined, ddof=1) * np.sqrt(252))
    # Only reduce exposure when aggregate stress exceeds frozen proposal thresholds.
    scale = min(1.0, 0.03 / max(cvar, 1e-12), 0.2 / max(vol, 1e-12))
    weights *= scale
    return {
        "version": "cluster-inverse-vol-v1",
        "weights": {r["id"]: float(weights[i]) for i, r in enumerate(eligible)},
        "cash": float(1 - weights.sum()),
        "clusters": [[eligible[i]["id"] for i in group] for group in clusters],
        "correlation": corr.tolist(),
        "volatility": vol * scale,
        "cvar": cvar * scale,
        "unscaled_drawdown": float(
            np.max(1 - equity / np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:])
        ),
        "stress": {
            "equity_crash_20pct": float(weights.sum() * -0.2),
            "correlation_one_volatility": float(np.dot(weights, std) * np.sqrt(252)),
        },
        "capital_eligible": False,
        "created_at": now(),
    }


def pareto_population(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [r for r in results if "public" in r]
    frontier = []
    for item in candidates:
        metrics = item["public"]["metrics"]
        objectives = (metrics["return"], -metrics["max_drawdown"], -metrics["turnover"])
        dominated = False
        for other in candidates:
            if other["id"] == item["id"]:
                continue
            m = other["public"]["metrics"]
            other_objectives = (m["return"], -m["max_drawdown"], -m["turnover"])
            if all(a >= b for a, b in zip(other_objectives, objectives, strict=True)) and any(
                a > b for a, b in zip(other_objectives, objectives, strict=True)
            ):
                dominated = True
                break
        frontier.append(
            {
                "id": item["id"],
                "pareto_front": not dominated,
                "status": item["status"],
                "objectives": list(objectives),
            }
        )
    return sorted(frontier, key=lambda x: (not x["pareto_front"], x["id"]))
