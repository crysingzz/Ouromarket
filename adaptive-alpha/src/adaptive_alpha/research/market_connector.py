"""Alpaca daily data adapter. Revised historical bars are never asserted PIT-safe."""

from datetime import timedelta
from typing import Literal
from urllib.parse import quote

import httpx

from adaptive_alpha.research.contracts import Bar, DatasetImport
from adaptive_alpha.research.datasets import timestamp
from adaptive_alpha.research.literature import bounded_json


class AlpacaMarketData:
    def __init__(self, key: str, secret: str, client: httpx.Client):
        if not key or not secret:
            raise ValueError("ALPACA_DATA_CREDENTIALS_REQUIRED")
        self.client = client
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    def historical(
        self, symbol: str, start: str, end: str, feed: Literal["iex", "sip"] = "iex"
    ) -> DatasetImport:
        start_at, end_at = timestamp(start), timestamp(end)
        if start_at >= end_at:
            raise ValueError("INVALID_DATE_RANGE")
        bars = []
        page_token = None
        seen = set()
        for _ in range(10):
            params = {
                "start": start,
                "end": end,
                "timeframe": "1Day",
                "limit": "1000",
                "adjustment": "raw",
                "feed": feed,
                "sort": "asc",
            }
            if page_token:
                params["page_token"] = page_token
            payload = bounded_json(
                self.client,
                "GET",
                "https://data.alpaca.markets/v2/stocks/" + quote(symbol, safe="") + "/bars",
                params=params,
                headers=self.headers,
            )
            for b in payload.get("bars", []):
                # Daily bars are labelled at start of day. Only make a completed
                # bar visible the following day; vendor revisions remain unverified.
                event = timestamp(b["t"]) + timedelta(days=1)
                bars.append(
                    Bar(
                        time=event.isoformat(),
                        available_at=event.isoformat(),
                        close=b["c"],
                        volume=b["v"],
                    )
                )
            if len(bars) > 5000:
                raise ValueError("DATASET_ROW_LIMIT")
            page_token = payload.get("next_page_token")
            if not page_token:
                break
            if page_token in seen:
                raise ValueError("UPSTREAM_PAGINATION_CYCLE")
            seen.add(page_token)
        else:
            raise ValueError("UPSTREAM_PAGINATION_LIMIT")
        return DatasetImport(
            name=f"Alpaca {symbol} {start[:10]}–{end[:10]}",
            symbol=symbol,
            provenance=f"Alpaca historical bars; feed={feed}; raw; end-of-day availability approximation; vendor revisions and survivorship NOT verified",
            adjustment="raw",
            point_in_time_verified=False,
            bars=bars,
        )

    def latest_quote(self, symbol: str) -> dict[str, object]:
        payload = bounded_json(
            self.client,
            "GET",
            "https://data.alpaca.markets/v2/stocks/" + quote(symbol, safe="") + "/quotes/latest",
            params={"feed": "iex"},
            headers=self.headers,
        )
        current = payload["quote"]
        bid, ask = float(current["bp"]), float(current["ap"])
        if not 0 < bid <= ask:
            raise ValueError("INVALID_MARKET_QUOTE")
        return {
            "timestamp": timestamp(current["t"]).isoformat(),
            "prices": {symbol: (bid + ask) / 2},
            "source": "alpaca-iex",
        }
