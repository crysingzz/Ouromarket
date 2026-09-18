"""Optional live-feed/internal-paper loop. No external broker order authority."""

import signal
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from adaptive_alpha.config import Settings
from adaptive_alpha.domain import now
from adaptive_alpha.research.contracts import DatasetImport
from adaptive_alpha.research.forward import ForwardPaper
from adaptive_alpha.research.market_connector import AlpacaMarketData
from adaptive_alpha.store import Store


def main() -> None:
    settings = Settings()
    key = settings.alpaca_data_key
    secret = settings.alpaca_data_secret
    if not key or not secret or not key.get_secret_value() or not secret.get_secret_value():
        raise ValueError("ALPACA_MARKET_DATA_CONFIGURATION_REQUIRED")
    store = Store(settings.database_url, manage_schema=settings.manage_schema)
    store.initialize()
    paper = ForwardPaper(store)
    stopping = False

    def stop(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        feed = AlpacaMarketData(key.get_secret_value(), secret.get_secret_value(), client)
        while not stopping:
            with store.transaction() as conn:
                subscriptions = store.list_records(conn, "forward-admission")
                store.set_state(
                    conn,
                    "forward-worker",
                    {"heartbeat": time.time(), "feed": "alpaca-iex", "broker": "internal-paper"},
                )
            snapshots: dict[str, tuple[DatasetImport, dict[str, Any]]] = {}
            for subscription in subscriptions:
                if stopping:
                    break
                try:
                    with store.transaction() as conn:
                        state = store.state(conn, "forward:" + subscription["id"])
                    if state.get("status", "PAPER") != "PAPER":
                        continue
                    symbol = state["symbol"]
                    if symbol not in snapshots:
                        clock = datetime.now(UTC)
                        snapshots[symbol] = (
                            feed.historical(
                                symbol,
                                (clock - timedelta(days=730)).isoformat(),
                                clock.isoformat(),
                            ),
                            feed.latest_quote(symbol),
                        )
                    dataset, quote = snapshots[symbol]
                    paper.step(subscription["id"], dataset, quote, clock=datetime.now(UTC))
                except Exception:
                    with store.transaction() as conn:
                        store.set_state(
                            conn,
                            "kill",
                            {
                                "halted": True,
                                "reason": "Forward feed or execution failure",
                                "timestamp": now(),
                            },
                        )
                        store.audit(
                            conn,
                            "forward.feed_failure",
                            "forward-worker",
                            {"candidate_id": subscription["id"]},
                        )
            for _ in range(60):
                if stopping:
                    break
                time.sleep(1)
    store.engine.dispose()


if __name__ == "__main__":
    main()
