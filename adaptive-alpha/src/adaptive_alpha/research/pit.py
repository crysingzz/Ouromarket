"""Immutable vendor revision ledgers and server-derived point-in-time snapshots."""

from collections import defaultdict
from typing import Any, Literal

from adaptive_alpha.domain import digest, now
from adaptive_alpha.research.contracts import Bar, DatasetImport, PITDatasetImport, PITObservation
from adaptive_alpha.research.datasets import _persist_dataset, timestamp
from adaptive_alpha.store import Store

Series = Literal["raw", "adjusted"]


def _validated_groups(request: PITDatasetImport) -> dict[str, list[PITObservation]]:
    expected_order = sorted(
        request.observations,
        key=lambda item: (timestamp(item.event_time), item.revision),
    )
    if list(request.observations) != expected_order:
        raise ValueError("PIT_LEDGER_ORDER")
    sequences: set[str] = set()
    groups: dict[str, list[PITObservation]] = defaultdict(list)
    for item in request.observations:
        event = timestamp(item.event_time)
        published = timestamp(item.published_at)
        received = timestamp(item.received_at)
        if not event <= published <= received:
            raise ValueError("PIT_TIMESTAMP_ORDER")
        if item.source_sequence in sequences:
            raise ValueError("PIT_SOURCE_SEQUENCE_DUPLICATE")
        sequences.add(item.source_sequence)
        groups[event.isoformat()].append(item)
    for revisions in groups.values():
        previous: PITObservation | None = None
        for expected_revision, item in enumerate(revisions, start=1):
            if item.revision != expected_revision:
                raise ValueError("PIT_REVISION_SEQUENCE")
            expected_predecessor = previous.source_sequence if previous is not None else None
            if item.corrects_source_sequence != expected_predecessor:
                raise ValueError("PIT_REVISION_PREDECESSOR")
            if previous is not None and timestamp(item.received_at) <= timestamp(
                previous.received_at
            ):
                raise ValueError("PIT_REVISION_RECEIPT_ORDER")
            previous = item
    return dict(groups)


def import_pit_dataset(store: Store, request: PITDatasetImport, actor: str) -> dict[str, Any]:
    groups = _validated_groups(request)
    payload = request.model_dump(mode="json")
    identity = "pit-ledger-" + digest(payload)
    report_body = {
        "ledger_id": identity,
        "ledger_content_hash": digest(payload),
        "status": "VERIFIED_REVISION_LEDGER",
        "checks": {
            "aware_timestamp_order": True,
            "deterministic_ledger_order": True,
            "unique_source_sequences": True,
            "consecutive_revision_chains": True,
            "declared_research_rights": True,
        },
        "events": len(groups),
        "observations": len(request.observations),
        "corrections": len(request.observations) - len(groups),
        "provider": request.provider,
        "provider_dataset_id": request.provider_dataset_id,
        "license_url": request.license_url,
        "usage_rights": request.usage_rights,
        "calendar": request.calendar,
        "timezone": request.timezone,
        "adjustment_policy": request.adjustment_policy.model_dump(mode="json"),
        "authority": "research-only",
        "capital_eligible": False,
    }
    report_id = "pit-report-" + digest(report_body)
    report = {"id": report_id, **report_body, "created_at": now()}
    manifest = {
        "id": identity,
        "content_hash": report_body["ledger_content_hash"],
        "name": request.name,
        "symbol": request.symbol,
        "provider": request.provider,
        "provider_dataset_id": request.provider_dataset_id,
        "events": len(groups),
        "observations": len(request.observations),
        "report_id": report_id,
        "verification": report_body["status"],
        "point_in_time_verified": True,
        "authority": "research-only",
        "capital_eligible": False,
    }
    with store.transaction() as conn:
        try:
            return dict(store.get(conn, identity, "pit-dataset")["manifest"])
        except KeyError:
            store.append(conn, "pit-verification", report, report_id)
            store.append(
                conn,
                "pit-dataset",
                {"id": identity, "manifest": manifest, "data": payload},
                identity,
            )
            store.audit(conn, "pit_dataset.imported", actor, manifest)
    return manifest


def verification_report(store: Store, ledger_id: str) -> dict[str, Any]:
    with store.transaction() as conn:
        ledger = store.get(conn, ledger_id, "pit-dataset")
        return store.get(conn, ledger["manifest"]["report_id"], "pit-verification")


def materialize_snapshot(
    store: Store,
    ledger_id: str,
    as_of: str,
    series: Series,
    actor: str,
) -> dict[str, Any]:
    cutoff = timestamp(as_of)
    with store.transaction() as conn:
        ledger = store.get(conn, ledger_id, "pit-dataset")
        report = store.get(conn, ledger["manifest"]["report_id"], "pit-verification")
    request = PITDatasetImport.model_validate(ledger["data"])
    groups = _validated_groups(request)
    if report["ledger_id"] != ledger_id or report["ledger_content_hash"] != digest(ledger["data"]):
        raise ValueError("PIT_VERIFICATION_BINDING")
    selected = [
        available[-1]
        for revisions in groups.values()
        if (available := [item for item in revisions if timestamp(item.received_at) <= cutoff])
    ]
    if len(selected) < 300:
        raise ValueError("PIT_SNAPSHOT_TOO_SHORT")
    policy = request.adjustment_policy
    adjustment = "raw" if series == "raw" else policy.adjusted_series
    snapshot = DatasetImport(
        name=f"{request.name} · {series} · {cutoff.date().isoformat()}"[:100],
        symbol=request.symbol,
        provenance=(
            f"Verified as-of snapshot from {request.provider}/{request.provider_dataset_id}; "
            f"license={request.license_url}; cutoff={cutoff.isoformat()}"
        ),
        adjustment=adjustment,
        point_in_time_verified=True,
        bars=[
            Bar(
                time=item.event_time,
                available_at=item.received_at,
                close=item.raw_close if series == "raw" else item.adjusted_close,
                volume=item.volume,
            )
            for item in selected
        ],
    )
    proof = {
        "verification_report_id": report["id"],
        "source_ledger_id": ledger_id,
        "as_of": cutoff.isoformat(),
        "series": series,
        "selected_source_sequences": [item.source_sequence for item in selected],
        "adjustment_policy": policy.model_dump(mode="json"),
        "usage_rights": request.usage_rights,
        "authority": "research-only",
    }
    return _persist_dataset(store, snapshot, actor, proof)
