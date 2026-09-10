"""Reproduce a public experiment in its original runtime; never relax content-hash checks."""

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from adaptive_alpha.data import dataset_manifest, synthetic_daily
from adaptive_alpha.domain import StrategySpec
from adaptive_alpha.evaluation.engine import evaluate


def reproduce(experiment: dict[str, Any], strategy: dict[str, Any]) -> None:
    expected_system = experiment.get("operating_system")
    if expected_system and expected_system != platform.system():
        raise ValueError(
            f"Runtime mismatch: experiment requires {expected_system}; current system is "
            f"{platform.system()}. Use the recorded Docker image for exact reproduction."
        )
    spec = StrategySpec.model_validate(
        {key: value for key, value in strategy.items() if key in StrategySpec.model_fields}
    )
    frame = synthetic_daily(experiment["random_seed"])
    manifest = dataset_manifest(frame, experiment["random_seed"])
    if manifest["content_hash"] != experiment["dataset_versions"][0]["content_hash"]:
        raise ValueError(
            "Dataset content hash mismatch. Do not relax this check: NumPy/libm can differ "
            "between operating systems. Reproduce in the original pinned container."
        )
    if spec.fingerprint() != experiment["config_hash"]:
        raise ValueError("Strategy configuration hash mismatch")
    if experiment["public"] is None:
        raise ValueError("This attempt has no public evaluation to reproduce")
    actual = evaluate(frame, spec, experiment["public"]["trials"])
    if actual != experiment["public"]:
        raise ValueError("Public results differ: restore the recorded source version and runtime")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", nargs="?", type=Path)
    parser.add_argument("strategy", nargs="?", type=Path)
    parser.add_argument(
        "--stdin", action="store_true", help="Read {experiment, strategy} bundle from stdin"
    )
    args = parser.parse_args()
    try:
        if args.stdin:
            bundle = json.load(sys.stdin)
            experiment, strategy = bundle["experiment"], bundle["strategy"]
        elif args.experiment and args.strategy:
            experiment = json.loads(args.experiment.read_text())
            strategy = json.loads(args.strategy.read_text())
        else:
            parser.error("Provide two JSON files or --stdin")
        reproduce(experiment, strategy)
    except (KeyError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print("PASS: public result reproduced exactly; dataset and configuration hashes match.")


if __name__ == "__main__":
    main()
