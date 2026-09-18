"""Usage: uv run python scripts/reproduce_campaign.py campaign-bundle.json."""

import argparse
import json
from pathlib import Path

from adaptive_alpha.research.reproduction import reproduce

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
args = parser.parse_args()
results = reproduce(json.loads(args.bundle.read_text()))
print(json.dumps(results, indent=2))
if not results or not all(item["exact"] for item in results):
    raise SystemExit(1)
