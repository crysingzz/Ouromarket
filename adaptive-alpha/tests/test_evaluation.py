from datetime import timedelta

import numpy as np
import polars as pl
import pytest

from adaptive_alpha.data import dataset_manifest, synthetic_daily, validate_pit
from adaptive_alpha.domain import StrategySpec
from adaptive_alpha.evaluation.engine import evaluate, strategy_returns


def spec(**kwargs):
    return StrategySpec(name="Test", hypothesis_id="h", thesis="Test", **kwargs)


def test_deterministic_evaluation_and_manifest():
    frame = synthetic_daily(42)
    assert evaluate(frame, spec()) == evaluate(frame, spec())
    assert dataset_manifest(frame, 42) == dataset_manifest(synthetic_daily(42), 42)
    assert (
        dataset_manifest(frame, 42)["content_hash"]
        != dataset_manifest(synthetic_daily(43), 43)["content_hash"]
    )


def test_no_lookahead_or_future_dependence():
    prices = np.array([100.0, 101.0, 105.0, 99.0, 101.0, 109.0, 95.0, 110.0])
    original, turnover = strategy_returns(prices, spec(lookback=2), 10)
    changed = prices.copy()
    changed[5:] *= 2
    revised, _ = strategy_returns(changed, spec(lookback=2), 10)
    np.testing.assert_array_equal(original[:5], revised[:5])
    assert original[2] == 0
    assert original[3] == pytest.approx(0.1 * (99 / 105 - 1) - 0.0001)
    assert turnover[3] == 0.1


def test_costs_reduce_net_returns():
    prices = np.array([100.0, 103.0, 101.0, 106.0, 102.0, 108.0, 105.0])
    gross, _ = strategy_returns(prices, spec(lookback=2), 0)
    net, _ = strategy_returns(prices, spec(lookback=2), 10)
    assert net.sum() < gross.sum()


def test_late_availability_rejected():
    frame = synthetic_daily(1).with_columns(
        (pl.col("available_time") + timedelta(days=2)).alias("available_time"),
        (pl.col("ingestion_time") + timedelta(days=3)).alias("ingestion_time"),
    )
    with pytest.raises(ValueError, match="LOOK_AHEAD"):
        validate_pit(frame)


def test_invalid_duplicate_unsorted_and_missing_data():
    frame = synthetic_daily(1)
    for broken in (
        pl.concat([frame, frame.head(1)]),
        frame.reverse(),
        frame.with_columns(pl.lit(float("nan")).alias("close")),
    ):
        with pytest.raises(ValueError):
            validate_pit(broken)


def test_missing_universe_is_not_zero_return_success():
    frame = synthetic_daily(1).filter(pl.col("symbol") != "SPY")
    with pytest.raises(ValueError, match="INSUFFICIENT_SAMPLE"):
        evaluate(frame, spec())


def test_multiplicity_counts_all_attempts():
    frame = synthetic_daily(42)
    first = evaluate(frame, spec(), 1)
    later = evaluate(frame, spec(), 50)
    assert later["score"] <= first["score"]
    assert first["dsr"] is None and first["pbo"] is None
    assert first["capital_eligible"] is False


def test_reproduction_uses_exact_dataset_and_original_runtime():
    import platform

    from adaptive_alpha.reproduce import reproduce

    strategy = spec()
    frame = synthetic_daily(42)
    experiment = {
        "random_seed": 42,
        "dataset_versions": [dataset_manifest(frame, 42)],
        "config_hash": strategy.fingerprint(),
        "public": evaluate(frame, strategy),
        "operating_system": platform.system(),
    }
    reproduce(experiment, strategy.model_dump(mode="json"))
    with pytest.raises(ValueError, match="Runtime mismatch"):
        reproduce(
            {**experiment, "operating_system": "different-system"}, strategy.model_dump(mode="json")
        )
    with pytest.raises(ValueError, match="content hash mismatch"):
        reproduce({**experiment, "random_seed": 43}, strategy.model_dump(mode="json"))
