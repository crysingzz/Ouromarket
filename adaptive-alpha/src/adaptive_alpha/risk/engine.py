"""Immutable deterministic demo risk policy; no agent-supplied prices or health flags."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

from adaptive_alpha.domain import OrderIntent


@dataclass(frozen=True)
class RiskPolicy:
    version: str = "paper-v1"
    max_position: float = 0.20
    max_strategy: float = 0.30
    max_gross: float = 0.60
    max_volatility: float = 0.20
    max_cvar: float = 0.03
    max_drawdown: float = 0.10
    max_daily_loss: float = 0.03
    max_quote_age_seconds: int = 60
    max_order_notional: float = 10_000
    leverage: float = 1.0


POLICY = RiskPolicy()


def monitor_account(
    account: dict[str, Any], prices: dict[str, float], returns: dict[str, list[float]]
) -> dict[str, Any]:
    """Revalue held exposure even when the strategy emits no new order."""
    positions = account["positions"]
    if any(s not in prices or not np.isfinite(prices[s]) or prices[s] <= 0 for s in positions):
        return {"status": "HALT", "breaches": ["valid_prices"], "policy_version": POLICY.version}
    nav = account["cash"] + sum(q * prices[s] for s, q in positions.items())
    if not np.isfinite(nav) or nav <= 0:
        return {"status": "HALT", "breaches": ["solvency"], "policy_version": POLICY.version}
    weights = {s: q * prices[s] / nav for s, q in positions.items() if q}
    checks = {
        "cash": account["cash"] >= 0,
        "no_short": all(q >= 0 for q in positions.values()),
        "single_name": max((abs(w) for w in weights.values()), default=0) <= POLICY.max_position,
        "gross_exposure": sum(abs(w) for w in weights.values()) <= POLICY.max_gross,
        "drawdown": nav >= account["high_watermark"] * (1 - POLICY.max_drawdown),
        "daily_loss": nav >= account["day_start_nav"] * (1 - POLICY.max_daily_loss),
    }
    arrays = [np.asarray(returns.get(s, []), dtype=float) * w for s, w in weights.items()]
    checks["risk_data"] = (
        all(len(a) >= 60 and np.isfinite(a).all() for a in arrays)
        and len({len(a) for a in arrays}) <= 1
    )
    if checks["risk_data"]:
        portfolio = np.sum(arrays, axis=0) if arrays else np.zeros(252)
        checks["volatility"] = (
            float(np.std(portfolio, ddof=1) * np.sqrt(252)) <= POLICY.max_volatility
        )
        cvar = max(0.0, -float(np.mean(portfolio[portfolio <= np.quantile(portfolio, 0.05)])))
        checks["cvar"] = cvar <= POLICY.max_cvar
    breaches = [name for name, passed in checks.items() if not passed]
    return {
        "status": "HALT" if breaches else "PASS",
        "breaches": breaches,
        "nav": nav,
        "policy_version": POLICY.version,
    }


def assess(
    intent: OrderIntent,
    account: dict[str, Any],
    quotes: dict[str, Any],
    returns: dict[str, list[float]],
    strategy_positions: dict[str, int],
    *,
    halted: bool,
    reconciled: bool,
    clock: datetime | None = None,
) -> dict[str, Any]:
    clock = clock or datetime.now(UTC)
    checks: list[dict[str, Any]] = []

    def check(rule: str, okay: bool, value: Any, limit: Any) -> None:
        checks.append(
            {"rule": rule, "status": "PASS" if okay else "FAIL", "value": value, "limit": limit}
        )

    check("kill_switch", not halted, halted, False)
    check("reconciliation", reconciled, reconciled, True)
    age = (clock - datetime.fromisoformat(quotes["timestamp"])).total_seconds()
    check("stale_data", 0 <= age <= POLICY.max_quote_age_seconds, age, POLICY.max_quote_age_seconds)
    prices = quotes["prices"]
    valid_prices = all(np.isfinite(price) and price > 0 for price in prices.values())
    check("valid_prices", valid_prices, valid_prices, True)
    if not all(item["status"] == "PASS" for item in checks):
        return {
            "status": "HALT",
            "approved_quantity": 0,
            "checks": checks,
            "policy_version": POLICY.version,
        }
    positions = dict(account["positions"])
    signed = intent.quantity if intent.side == "BUY" else -intent.quantity
    positions[intent.instrument] = positions.get(intent.instrument, 0) + signed
    notional = intent.quantity * prices[intent.instrument]
    cash = account["cash"] - signed * prices[intent.instrument] - notional * 0.001
    nav = cash + sum(quantity * prices[symbol] for symbol, quantity in positions.items())
    check("solvency", nav > 0, nav, 0)
    check("no_short", all(q >= 0 for q in positions.values()), min(positions.values()), 0)
    check(
        "strategy_ownership",
        strategy_positions.get(intent.instrument, 0) + signed >= 0,
        strategy_positions.get(intent.instrument, 0) + signed,
        0,
    )
    check("cash", cash >= 0, cash, 0)
    check(
        "order_notional", notional <= POLICY.max_order_notional, notional, POLICY.max_order_notional
    )
    if nav <= 0:
        return {
            "status": "REJECT",
            "approved_quantity": 0,
            "checks": checks,
            "policy_version": POLICY.version,
        }
    weights = {symbol: q * prices[symbol] / nav for symbol, q in positions.items()}
    position = max((abs(w) for w in weights.values()), default=0.0)
    gross = sum(abs(w) for w in weights.values())
    owned = dict(strategy_positions)
    owned[intent.instrument] = owned.get(intent.instrument, 0) + signed
    strategy_weight = sum(q * prices[s] for s, q in owned.items()) / nav
    check("single_name", position <= POLICY.max_position, position, POLICY.max_position)
    check(
        "strategy_allocation",
        strategy_weight <= POLICY.max_strategy,
        strategy_weight,
        POLICY.max_strategy,
    )
    check("gross_exposure", gross <= POLICY.max_gross, gross, POLICY.max_gross)
    arrays = [
        np.array(returns.get(symbol, []), dtype=float) * weight
        for symbol, weight in weights.items()
        if weight
    ]
    valid_risk = (
        all(len(a) >= 60 and np.isfinite(a).all() for a in arrays)
        and len({len(a) for a in arrays}) <= 1
    )
    check("risk_data", valid_risk, valid_risk, True)
    if valid_risk:
        portfolio = np.sum(arrays, axis=0) if arrays else np.zeros(252)
        vol = float(np.std(portfolio, ddof=1) * np.sqrt(252))
        cvar = max(0.0, -float(np.mean(portfolio[portfolio <= np.quantile(portfolio, 0.05)])))
        check("volatility", vol <= POLICY.max_volatility, vol, POLICY.max_volatility)
        check("cvar", cvar <= POLICY.max_cvar, cvar, POLICY.max_cvar)
    drawdown = max(0.0, 1 - nav / account["high_watermark"])
    daily_loss = max(0.0, 1 - nav / account["day_start_nav"])
    check("drawdown", drawdown <= POLICY.max_drawdown, drawdown, POLICY.max_drawdown)
    check("daily_loss", daily_loss <= POLICY.max_daily_loss, daily_loss, POLICY.max_daily_loss)
    approved = all(item["status"] == "PASS" for item in checks)
    return {
        "status": "APPROVE" if approved else "REJECT",
        "approved_quantity": intent.quantity if approved else 0,
        "checks": checks,
        "policy_version": POLICY.version,
    }


def policy_dict() -> dict[str, Any]:
    return asdict(POLICY)
