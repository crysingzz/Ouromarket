"""Download daily bars using separate market-data credentials, then operator-import."""

import argparse
import json
from pathlib import Path

import httpx

from adaptive_alpha.research.market_connector import AlpacaMarketData


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--secrets", type=Path, default=Path(".secrets"))
    args = parser.parse_args()
    key = (args.secrets / "alpaca_data_key").read_text().strip()
    secret = (args.secrets / "alpaca_data_secret").read_text().strip()
    with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
        dataset = AlpacaMarketData(key, secret, client).historical(
            args.symbol, args.start, args.end
        )
    with args.output.open("x") as handle:
        json.dump(dataset.model_dump(mode="json"), handle)
    print(f"Wrote {len(dataset.bars)} bars. Import this JSON through Autonomous R&D.")


if __name__ == "__main__":
    main()
