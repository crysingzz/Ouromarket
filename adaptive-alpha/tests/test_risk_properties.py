from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from adaptive_alpha.domain import OrderIntent
from adaptive_alpha.risk.engine import assess


@given(
    quantity=st.integers(min_value=1, max_value=1000000),
    price=st.floats(min_value=1, max_value=10000, allow_nan=False, allow_infinity=False),
)
def test_approved_orders_always_respect_cash_and_exposure(quantity, price):
    clock = datetime.now(UTC)
    intent = OrderIntent(strategy_id="s", instrument="SPY", side="BUY", quantity=quantity)
    account = {
        "cash": 100000.0,
        "positions": {},
        "high_watermark": 100000.0,
        "day_start_nav": 100000.0,
    }
    decision = assess(
        intent,
        account,
        {"timestamp": clock.isoformat(), "prices": {"SPY": price}},
        {"SPY": [0.001, -0.001] * 126},
        {},
        halted=False,
        reconciled=True,
        clock=clock,
    )
    if decision["status"] == "APPROVE":
        assert all(c["status"] == "PASS" for c in decision["checks"])
        assert quantity * price <= 10000
        assert decision["approved_quantity"] == quantity
    else:
        assert decision["approved_quantity"] == 0


@given(quantity=st.integers(min_value=1, max_value=1000000))
def test_kill_switch_always_blocks(quantity):
    clock = datetime.now(UTC)
    intent = OrderIntent(strategy_id="s", instrument="SPY", side="BUY", quantity=quantity)
    decision = assess(
        intent,
        {},
        {"timestamp": clock.isoformat(), "prices": {"SPY": 100}},
        {},
        {},
        halted=True,
        reconciled=True,
        clock=clock,
    )
    assert decision["status"] == "HALT"
    assert decision["approved_quantity"] == 0
