"""CLI lifecycle, worker shutdown, migration contracts and durable storage."""

import io
import json
import os
import runpy
import signal
from unittest.mock import MagicMock, Mock

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from test_autonomous import dataset
from test_evaluation import spec

from adaptive_alpha import config
from adaptive_alpha import reproduce as legacy_reproduction
from adaptive_alpha import store as storage
from adaptive_alpha.artifacts import ArtifactStore
from adaptive_alpha.data import dataset_manifest, synthetic_daily
from adaptive_alpha.evaluation.engine import evaluate
from adaptive_alpha.research import campaigns, forward, market_connector
from adaptive_alpha.research.contracts import CampaignRequest
from adaptive_alpha.research.datasets import import_dataset
from adaptive_alpha.store import Store


def test_settings_read_service_files_and_vault_precedence(settings, tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "operator_token").write_text("o" * 48)
    (secrets / "openai_api_key").write_text("file-key")
    (secrets / "hidden_seed").write_text("123")
    settings.provider_vault_dir.mkdir()
    (settings.provider_vault_dir / "openai.json").write_text(
        json.dumps({"api_key": "vault-key", "model": "fixture-model"})
    )
    values = settings.model_dump()
    values.update(secrets_dir=secrets, operator_token=None)
    loaded = config.Settings(**values)
    assert loaded.token("operator_token") == "o" * 48
    assert loaded.hidden_seed == 123 and loaded.openai_model == "fixture-model"
    assert loaded.openai_api_key.get_secret_value() == "vault-key"
    with pytest.raises(ValueError, match="Missing secure"):
        config.Settings(**{**values, "operator_token": SecretStr("short")}).token("operator_token")


def test_artifact_bounds_racing_writer_and_symlink(tmp_path, monkeypatch):
    artifacts = ArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="ARTIFACT_TOO_LARGE"):
        artifacts.put(b"x" * 20_000_001, "text/plain")
    original = os.link

    def concurrent_write(source, target):
        original(source, target)
        raise FileExistsError("Another writer won")

    monkeypatch.setattr(os, "link", concurrent_write)
    manifest = artifacts.put(b"same-content", "text/plain")
    assert artifacts.get(manifest["id"]) == b"same-content"
    assert not list(tmp_path.glob(".pending-*"))
    (tmp_path / ("a" * 64)).symlink_to(tmp_path / manifest["id"])
    with pytest.raises(ValueError, match="ARTIFACT_SYMLINK_REJECTED"):
        artifacts.get("a" * 64)


def test_runtime_schema_gate_and_audit_tamper_detection(settings):
    owner = Store(settings.database_url)
    owner.initialize()
    runtime = Store(settings.database_url, manage_schema=False)
    with pytest.raises(ValueError, match="DATABASE_MIGRATION_REQUIRED"):
        runtime.initialize()
    with owner.transaction() as conn:
        owner.set_state(conn, "schema-version", {"version": 2})
        owner.audit(conn, "test", "operator", {})
    runtime.initialize()
    with owner.transaction() as conn:
        assert owner.verify_audit(conn)
        conn.execute(text("DROP TRIGGER immutable_events_update"))
        conn.execute(text("UPDATE events SET hash='tampered'"))
        assert not owner.verify_audit(conn)


def test_postgres_schema_installs_triggers_and_serializes_transactions(settings, monkeypatch):
    store = Store(settings.database_url)
    engine, conn = MagicMock(), MagicMock()
    engine.dialect.name = "postgresql"
    engine.begin.return_value.__enter__.return_value = conn
    engine.connect.return_value.__enter__.return_value = conn
    conn.execute.return_value.first.side_effect = [None, (1,)]
    store.engine = engine
    monkeypatch.setattr(storage.metadata, "create_all", Mock())
    store.initialize()
    sql = "\n".join(str(call.args[0]) for call in conn.execute.call_args_list)
    assert "BEFORE UPDATE OR DELETE OR TRUNCATE ON records" in sql
    assert "CREATE TRIGGER immutable_events" not in sql
    with store.transaction():
        pass
    assert "FOR UPDATE" in str(conn.execute.call_args.args[0])
    conn.commit.assert_called_once()
    with pytest.raises(RuntimeError), store.transaction():
        raise RuntimeError("atomic abort")
    conn.rollback.assert_called_once()


@pytest.mark.parametrize("exists", [False, True])
def test_migration_creates_or_rotates_restricted_runtime_role(
    settings, tmp_path, monkeypatch, capsys, exists
):
    import psycopg

    store = Store(settings.database_url)
    store.initialize()
    settings.database_url = "postgresql+psycopg://owner@migration.test/alpha"
    settings.secrets_dir.mkdir()
    (settings.secrets_dir / "runtime_password").write_text("p" * 40)
    monkeypatch.setattr(config, "Settings", lambda: settings)
    monkeypatch.setattr(storage, "Store", lambda _: store)
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = (1,) if exists else None
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(psycopg, "connect", connect)
    runpy.run_module("adaptive_alpha.migrate", run_name="__main__")
    statements = [
        call.args[0].as_string() if hasattr(call.args[0], "as_string") else call.args[0]
        for call in connection.execute.call_args_list
    ]
    assert ("ALTER ROLE" if exists else "CREATE ROLE") in statements[1]
    assert "GRANT SELECT, INSERT ON records, events TO alpha_runtime" in statements
    assert not any("GRANT UPDATE ON records" in s for s in statements)
    with store.transaction() as conn:
        assert store.state(conn, "schema-version") == {"version": 2}
    assert "p" * 40 not in capsys.readouterr().out


def test_migration_rejects_wrong_database_and_short_secret(settings, monkeypatch):
    monkeypatch.setattr(config, "Settings", lambda: settings)
    with pytest.raises(ValueError, match="POSTGRES_MIGRATION_REQUIRED"):
        runpy.run_module("adaptive_alpha.migrate", run_name="__main__")
    store = Store(settings.database_url)
    monkeypatch.setattr(storage, "Store", lambda _: store)
    settings.database_url = "postgresql+psycopg://owner@migration.test/db"
    settings.secrets_dir.mkdir()
    (settings.secrets_dir / "runtime_password").write_text("short")
    with pytest.raises(ValueError, match="RUNTIME_DATABASE_PASSWORD_REQUIRED"):
        runpy.run_module("adaptive_alpha.migrate", run_name="__main__")


def test_worker_claims_once_records_heartbeat_and_handles_shutdown(settings, monkeypatch):
    import time

    store = Store(settings.database_url)
    store.initialize()
    ds = import_dataset(store, dataset(), "test")
    manager = campaigns.Campaigns(store, settings)
    job = manager.create(
        CampaignRequest(
            objective="Test worker queue lifecycle",
            query="momentum",
            dataset_id=ds["id"],
            model="fixture",
        ),
        "test",
    )
    handlers, executed = {}, []
    monkeypatch.setattr(config, "Settings", lambda: settings)
    monkeypatch.setattr(signal, "signal", lambda kind, fn: handlers.__setitem__(kind, fn))
    monkeypatch.setattr(
        campaigns.Campaigns,
        "run",
        lambda self, request, lease: executed.append((request["id"], lease)),
    )
    monkeypatch.setattr(time, "sleep", lambda _: handlers[signal.SIGTERM](signal.SIGTERM, None))
    runpy.run_module("adaptive_alpha.research.worker", run_name="__main__")
    assert len(executed) == 1 and executed[0][0] == job["id"]
    with store.transaction() as conn:
        worker = store.state(conn, "research-worker:replication")
        assert worker["heartbeat"] > 0 and worker["department"] == "replication"
        assert worker["authority"] == "research-only" and not worker["capital_eligible"]
        assert store.state(conn, "campaign:" + job["id"])["status"] == "RUNNING"


@pytest.mark.parametrize(
    "mode", ["normal_stop", "feed_failure", "missing_key", "paused", "shared_snapshot"]
)
def test_forward_worker_shutdown_and_feed_failure_halt(settings, monkeypatch, mode):
    import time

    store = Store(settings.database_url)
    store.initialize()
    with store.transaction() as conn:
        for identity in ("first", "second"):
            store.append(conn, "forward-admission", {"id": identity})
            store.set_state(conn, "forward:" + identity, {"symbol": "SPY"})
            if mode == "paused":
                store.set_state(conn, "forward:" + identity, {"symbol": "SPY", "status": "HALTED"})
    if mode != "missing_key":
        settings.alpaca_data_key, settings.alpaca_data_secret = (
            SecretStr("key"),
            SecretStr("secret"),
        )
    handlers = {}
    monkeypatch.setattr(config, "Settings", lambda: settings)
    monkeypatch.setattr(signal, "signal", lambda kind, fn: handlers.__setitem__(kind, fn))
    monkeypatch.setattr(time, "sleep", lambda _: handlers[signal.SIGINT](signal.SIGINT, None))
    feed = Mock()
    feed.historical.return_value = dataset()
    feed.latest_quote.return_value = {"timestamp": "fixture"}
    if mode == "feed_failure":
        feed.historical.side_effect = ConnectionError("vendor credentials must not leak")
    monkeypatch.setattr(market_connector, "AlpacaMarketData", lambda *_: feed)
    executed = []

    def step(self, identity, data, quote, **kwargs):
        executed.append(identity)
        if mode != "shared_snapshot" or len(executed) == 2:
            handlers[signal.SIGINT](signal.SIGINT, None)

    monkeypatch.setattr(forward.ForwardPaper, "step", step)
    if mode == "missing_key":
        with pytest.raises(ValueError, match="ALPACA_MARKET_DATA_CONFIGURATION_REQUIRED"):
            runpy.run_module("adaptive_alpha.research.forward_worker", run_name="__main__")
        return
    runpy.run_module("adaptive_alpha.research.forward_worker", run_name="__main__")
    with store.transaction() as conn:
        assert store.state(conn, "forward-worker")["broker"] == "internal-paper"
        if mode == "feed_failure":
            assert store.state(conn, "kill")["halted"]
            assert "credentials" not in json.dumps(store.audit_events(conn))
        else:
            assert len(executed) == (
                0 if mode == "paused" else 2 if mode == "shared_snapshot" else 1
            )
            assert feed.historical.call_count == (0 if mode == "paused" else 1)


def reproduction_bundle():
    strategy = spec()
    frame = synthetic_daily(42)
    return {
        "strategy": strategy.model_dump(mode="json"),
        "experiment": {
            "random_seed": 42,
            "dataset_versions": [dataset_manifest(frame, 42)],
            "config_hash": strategy.fingerprint(),
            "public": evaluate(frame, strategy),
        },
    }


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("config", "configuration hash mismatch"),
        ("public", "no public evaluation"),
        ("result", "Public results differ"),
    ],
)
def test_legacy_reproduction_rejects_divergence(mutation, error):
    bundle = reproduction_bundle()
    if mutation == "config":
        bundle["experiment"]["config_hash"] = "bad"
    elif mutation == "public":
        bundle["experiment"]["public"] = None
    else:
        bundle["experiment"]["public"]["score"] = 999
    with pytest.raises(ValueError, match=error):
        legacy_reproduction.reproduce(bundle["experiment"], bundle["strategy"])


@pytest.mark.parametrize("mode", ["stdin", "files", "missing_args", "invalid_json"])
def test_reproduction_cli(mode, monkeypatch, tmp_path, capsys):
    bundle = reproduction_bundle()
    args = ["reproduce"]
    if mode in {"stdin", "invalid_json"}:
        args += ["--stdin"]
        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps(bundle) if mode == "stdin" else "broken")
        )
    elif mode == "files":
        for name in ("experiment", "strategy"):
            file = tmp_path / (name + ".json")
            file.write_text(json.dumps(bundle[name]))
            args.append(str(file))
    monkeypatch.setattr("sys.argv", args)
    if mode in {"missing_args", "invalid_json"}:
        with pytest.raises(SystemExit):
            runpy.run_path(legacy_reproduction.__file__, run_name="__main__")
    else:
        runpy.run_path(legacy_reproduction.__file__, run_name="__main__")
        assert "reproduced exactly" in capsys.readouterr().out
