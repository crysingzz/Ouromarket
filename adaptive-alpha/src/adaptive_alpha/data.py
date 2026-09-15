"""Synthetic PIT fixture and explicit availability-time checks, never a market-data claim."""

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import polars as pl

from adaptive_alpha.domain import digest

SYMBOLS = ("SPY", "QQQ", "IWM")


def synthetic_daily(seed: int, size: int = 756) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2020, 1, 1, tzinfo=UTC)
    dates = [start + timedelta(days=i) for i in range(size * 2)]
    dates = [date for date in dates if date.weekday() < 5][:size]
    rows = []
    for index, symbol in enumerate(SYMBOLS):
        returns = rng.normal(0.0003, 0.009 + index * 0.001, size)
        prices = (100 + index * 50) * np.cumprod(1 + returns)
        for date, price in zip(dates, prices, strict=True):
            rows.append(
                {
                    "symbol": symbol,
                    "event_time": date,
                    "available_time": date,
                    "ingestion_time": date + timedelta(minutes=1),
                    "close": float(price),
                }
            )
    return pl.DataFrame(rows).sort(["symbol", "event_time"])


def validate_pit(frame: pl.DataFrame) -> None:
    required = {"symbol", "event_time", "available_time", "ingestion_time", "close"}
    if not required.issubset(frame.columns) or frame.is_empty():
        raise ValueError("DATA_SCHEMA")
    if any(frame.null_count().row(0)):
        raise ValueError("MISSING_DATA")
    if frame.select(pl.struct(["symbol", "event_time"]).is_duplicated().any()).item():
        raise ValueError("DUPLICATE_BAR")
    if frame.filter((~pl.col("close").is_finite()) | (pl.col("close") <= 0)).height:
        raise ValueError("INVALID_PRICE")
    if frame.filter(
        (pl.col("available_time") < pl.col("event_time"))
        | (pl.col("ingestion_time") < pl.col("available_time"))
    ).height:
        raise ValueError("INVALID_AVAILABILITY")
    for part in frame.partition_by("symbol"):
        if not part["event_time"].is_sorted():
            raise ValueError("UNSORTED_DATA")
        # The supported close-to-close template needs today's signal available
        # by today's close. Revised/late data must use a different delayed feature.
        if part.filter(pl.col("available_time") > pl.col("event_time")).height:
            raise ValueError("LOOK_AHEAD_BIAS")


def dataset_manifest(frame: pl.DataFrame, seed: int) -> dict[str, Any]:
    rows = [
        {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in row.items()
        }
        for row in frame.to_dicts()
    ]
    return {
        "id": f"synthetic-daily-v1-{seed}",
        "version": "1",
        "source": "synthetic-demo",
        "content_hash": digest(rows),
        "schema_hash": digest({key: str(value) for key, value in frame.schema.items()}),
        "rows": frame.height,
        "point_in_time_valid": True,
        "survivorship_checked": False,
        "generator": "numpy-pcg64-v1",
        "seed": seed,
    }
