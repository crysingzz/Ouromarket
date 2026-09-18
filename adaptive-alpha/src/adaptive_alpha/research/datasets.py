"""Content-addressed daily market snapshots; timestamps carry explicit availability."""

from datetime import datetime
from io import BytesIO
from typing import Any

import polars as pl

from adaptive_alpha.artifacts import ArtifactStore
from adaptive_alpha.domain import digest, now
from adaptive_alpha.research.contracts import DatasetImport
from adaptive_alpha.store import Store


def timestamp(text: str) -> datetime:
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return result


def _validate_dataset(request: DatasetImport) -> None:
    previous = None
    for bar in request.bars:
        event, available = timestamp(bar.time), timestamp(bar.available_at)
        if available < event or (previous is not None and event <= previous):
            raise ValueError("DATASET_ORDER_OR_AVAILABILITY")
        previous = event


def _persist_dataset(
    store: Store,
    request: DatasetImport,
    actor: str,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_dataset(request)
    payload = request.model_dump(mode="json")
    if verification is None and request.point_in_time_verified:
        raise ValueError("SERVER_PIT_REPORT_REQUIRED")
    if verification is not None and not request.point_in_time_verified:
        raise ValueError("VERIFIED_DATASET_FLAG_REQUIRED")
    identity = "dataset-" + digest(
        payload if verification is None else {"data": payload, "verification": verification}
    )
    manifest: dict[str, Any] = {
        "id": identity,
        "content_hash": digest(payload),
        "name": request.name,
        "symbol": request.symbol,
        "bars": len(request.bars),
        "provenance": request.provenance,
        "adjustment": request.adjustment,
        "point_in_time_verified": verification is not None,
        "verification": "server_verified_as_of" if verification is not None else "unverified",
        "created_at": now(),
        "capital_eligible": False,
    }
    if verification is not None:
        manifest["proof"] = verification
    if store.artifact_dir is not None:
        buffer = BytesIO()
        pl.DataFrame([bar.model_dump() for bar in request.bars]).write_parquet(
            buffer, compression="zstd"
        )
        manifest["parquet"] = ArtifactStore(store.artifact_dir).put(
            buffer.getvalue(), "application/vnd.apache.parquet"
        )
    with store.transaction() as conn:
        try:
            existing = store.get(conn, identity, "dataset")
            return dict(existing["manifest"])
        except KeyError:
            store.append(
                conn, "dataset", {"id": identity, "manifest": manifest, "data": payload}, identity
            )
            store.audit(conn, "dataset.imported", actor, manifest)
    return manifest


def import_dataset(store: Store, request: DatasetImport, actor: str) -> dict[str, Any]:
    return _persist_dataset(store, request, actor)
