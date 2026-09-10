"""Reproduce archived generated research against its exact public snapshot."""

import platform
from pathlib import Path
from typing import Any

import numpy as np

from adaptive_alpha.domain import digest
from adaptive_alpha.research.backtest import backtest
from adaptive_alpha.research.contracts import DatasetImport


def provenance() -> dict[str, Any]:
    package = Path(__file__).resolve().parents[1]
    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "runtime_hash": digest(
            {
                str(p.relative_to(package)): digest(p.read_text())
                for p in sorted(package.rglob("*.py"))
            }
        ),
    }


def reproduce(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    dataset = DatasetImport.model_validate(bundle["dataset"]["data"])
    if digest(dataset.model_dump(mode="json")) != bundle["dataset"]["manifest"]["content_hash"]:
        raise ValueError("DATASET_HASH_MISMATCH")
    candidates = {a["id"]: a for a in bundle["candidate"]}
    results = []
    current = provenance()
    for result in bundle["candidate-result"]:
        if "public" not in result:
            continue
        artifact = candidates[result["id"]]
        if digest(artifact["source"]) != artifact["source_hash"]:
            raise ValueError("SOURCE_HASH_MISMATCH")
        if artifact.get("provenance") != current:
            raise ValueError("PINNED_RUNTIME_REQUIRED")
        rerun = backtest(artifact["source"], dataset)
        results.append(
            {"candidate_id": artifact["id"], "exact": digest(rerun) == digest(result["public"])}
        )
    return results
