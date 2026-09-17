from datetime import UTC, datetime, timedelta

import pytest
from conftest import OPERATOR, RESEARCH
from fastapi.testclient import TestClient

from adaptive_alpha.research.contracts import (
    AdjustmentPolicy,
    DatasetImport,
    PITDatasetImport,
    PITObservation,
)
from adaptive_alpha.research.datasets import _persist_dataset, import_dataset
from adaptive_alpha.research.pit import (
    import_pit_dataset,
    materialize_snapshot,
    verification_report,
)
from adaptive_alpha.store import Store


def pit_dataset() -> PITDatasetImport:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    observations: list[PITObservation] = []
    for index in range(300):
        event = start + timedelta(days=index)
        first = PITObservation(
            event_time=event.isoformat(),
            published_at=(event + timedelta(minutes=1)).isoformat(),
            received_at=(event + timedelta(minutes=2)).isoformat(),
            source_sequence=f"bar-{index}-r1",
            revision=1,
            raw_close=100 + index,
            adjusted_close=50 + index,
            volume=1_000_000 + index,
        )
        observations.append(first)
        if index == 10:
            observations.append(
                first.model_copy(
                    update={
                        "published_at": (start + timedelta(days=310)).isoformat(),
                        "received_at": (start + timedelta(days=311)).isoformat(),
                        "source_sequence": "bar-10-r2",
                        "revision": 2,
                        "corrects_source_sequence": first.source_sequence,
                        "raw_close": 999.0,
                        "adjusted_close": 499.5,
                    }
                )
            )
    return PITDatasetImport(
        name="Licensed XNYS daily fixture",
        symbol="SPY",
        provider="fixture-vendor",
        provider_dataset_id="daily-spy-v1",
        license_url="https://example.test/license",
        usage_rights="research",
        calendar="XNYS",
        timezone="America/New_York",
        adjustment_policy=AdjustmentPolicy(
            name="Fixture split adjustment",
            version="1.0.0",
            adjusted_series="split",
            description="Deterministic split factors retained by the fixture vendor",
        ),
        observations=observations,
    )


def record(store: Store, identity: str, kind: str = "dataset") -> dict:
    with store.transaction() as conn:
        return store.get(conn, identity, kind)


def test_as_of_snapshots_hide_future_revisions(settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    source = pit_dataset()
    ledger = import_pit_dataset(store, source, "operator")
    assert import_pit_dataset(store, source, "operator") == ledger
    before = materialize_snapshot(
        store, ledger["id"], "2020-11-01T00:00:00+00:00", "raw", "operator"
    )
    again = materialize_snapshot(
        store, ledger["id"], "2020-11-01T00:00:00+00:00", "raw", "operator"
    )
    after = materialize_snapshot(
        store, ledger["id"], "2020-12-01T00:00:00+00:00", "adjusted", "operator"
    )
    assert before == again
    assert before["id"] != after["id"]
    assert before["proof"]["selected_source_sequences"][10] == "bar-10-r1"
    assert after["proof"]["selected_source_sequences"][10] == "bar-10-r2"
    assert record(store, before["id"])["data"]["bars"][10]["close"] == 110
    assert record(store, after["id"])["data"]["bars"][10]["close"] == 499.5
    assert record(store, before["id"])["data"]["bars"][10]["close"] == 110
    report = verification_report(store, ledger["id"])
    assert report["corrections"] == 1 and report["capital_eligible"] is False


def test_invalid_ledgers_fail_closed(settings) -> None:
    store = Store(settings.database_url)
    store.initialize()
    ordinary = DatasetImport.model_validate(
        {
            "name": "forged",
            "symbol": "SPY",
            "provenance": "Caller assertion",
            "adjustment": "raw",
            "point_in_time_verified": True,
            "bars": [
                {
                    "time": item.event_time,
                    "available_at": item.received_at,
                    "close": item.raw_close,
                    "volume": item.volume,
                }
                for item in pit_dataset().observations
                if item.revision == 1
            ],
        }
    )
    with pytest.raises(ValueError, match="SERVER_PIT_REPORT_REQUIRED"):
        import_dataset(store, ordinary, "operator")
    with pytest.raises(ValueError, match="VERIFIED_DATASET_FLAG_REQUIRED"):
        _persist_dataset(
            store,
            ordinary.model_copy(update={"point_in_time_verified": False}),
            "operator",
            {"proof": "forged"},
        )

    source = pit_dataset()
    second = source.observations[1]
    correction_index = next(
        index
        for index, item in enumerate(source.observations)
        if item.source_sequence == "bar-10-r2"
    )
    correction = source.observations[correction_index]
    cases = [
        (list(reversed(source.observations)), "PIT_LEDGER_ORDER"),
        (
            [
                source.observations[0].model_copy(
                    update={"published_at": "2019-01-01T00:00:00+00:00"}
                ),
                *source.observations[1:],
            ],
            "PIT_TIMESTAMP_ORDER",
        ),
        (
            [source.observations[0], second.model_copy(update={"source_sequence": "bar-0-r1"})]
            + source.observations[2:],
            "PIT_SOURCE_SEQUENCE_DUPLICATE",
        ),
        (
            [
                source.observations[0],
                second.model_copy(update={"revision": 2, "corrects_source_sequence": "bar-0-r1"}),
                *source.observations[2:],
            ],
            "PIT_REVISION_SEQUENCE",
        ),
        (
            source.observations[:correction_index]
            + [correction.model_copy(update={"corrects_source_sequence": None})]
            + source.observations[correction_index + 1 :],
            "PIT_REVISION_PREDECESSOR",
        ),
        (
            source.observations[:correction_index]
            + [
                correction.model_copy(
                    update={
                        "published_at": source.observations[correction_index - 1].published_at,
                        "received_at": source.observations[correction_index - 1].received_at,
                    }
                )
            ]
            + source.observations[correction_index + 1 :],
            "PIT_REVISION_RECEIPT_ORDER",
        ),
    ]
    for observations, message in cases:
        with pytest.raises(ValueError, match=message):
            import_pit_dataset(store, source.model_copy(update={"observations": observations}), "x")

    ledger = import_pit_dataset(store, source, "operator")
    with pytest.raises(ValueError, match="PIT_SNAPSHOT_TOO_SHORT"):
        materialize_snapshot(store, ledger["id"], "2020-01-02T00:00:00+00:00", "raw", "x")
    valid_report = verification_report(store, ledger["id"])
    valid_ledger = record(store, ledger["id"], "pit-dataset")
    with store.transaction() as conn:
        forged_report = {**valid_report, "id": "forged-report"}
        forged_report["ledger_content_hash"] = "0" * 64
        store.append(conn, "pit-verification", forged_report, forged_report["id"])
        forged_ledger = {**valid_ledger, "id": "forged-ledger"}
        forged_ledger["manifest"] = {
            **forged_ledger["manifest"],
            "id": "forged-ledger",
            "report_id": forged_report["id"],
        }
        store.append(conn, "pit-dataset", forged_ledger, forged_ledger["id"])
    with pytest.raises(ValueError, match="PIT_VERIFICATION_BINDING"):
        materialize_snapshot(store, "forged-ledger", "2020-12-01T00:00:00+00:00", "raw", "x")


def test_pit_api_requires_operator_and_exposes_proof(client: TestClient) -> None:
    body = pit_dataset().model_dump(mode="json")
    client.headers["Authorization"] = f"Bearer {RESEARCH}"
    assert client.post("/api/pit-datasets", json=body).status_code == 403
    client.headers["Authorization"] = f"Bearer {OPERATOR}"
    created = client.post("/api/pit-datasets", json=body)
    assert created.status_code == 201
    ledger = created.json()
    assert client.get("/api/pit-datasets").json() == [ledger]
    report = client.get(f"/api/pit-datasets/{ledger['id']}/report")
    assert report.status_code == 200
    assert report.json()["status"] == "VERIFIED_REVISION_LEDGER"
    snapshot = client.post(
        f"/api/pit-datasets/{ledger['id']}/snapshots",
        params={"as_of": "2020-11-01T00:00:00+00:00", "series": "raw"},
    )
    assert snapshot.status_code == 201
    assert snapshot.json()["proof"]["verification_report_id"] == ledger["report_id"]
