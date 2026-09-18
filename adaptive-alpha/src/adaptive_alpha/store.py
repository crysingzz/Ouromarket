"""Small transactional journal with DB-enforced immutable records and hash-chained audit."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, select, text
from sqlalchemy.engine import Connection

from adaptive_alpha.domain import canonical, digest, new_id, now

metadata = MetaData()
records = Table(
    "records",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("kind", String(50), nullable=False, index=True),
    Column("payload", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)
states = Table(
    "states",
    metadata,
    Column("id", String(120), primary_key=True),
    Column("payload", Text, nullable=False),
)
events = Table(
    "events",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("id", String(100), nullable=False, unique=True),
    Column("payload", Text, nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("hash", String(64), nullable=False),
)


class Store:
    def __init__(self, url: str, *, manage_schema: bool = True, artifact_dir: Path | None = None):
        self.artifact_dir = artifact_dir
        self.manage_schema = manage_schema
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30}
            if url.startswith("sqlite")
            else {},
        )

    def initialize(self) -> None:
        if not self.manage_schema:
            with self.engine.connect() as conn:
                version = self.state(conn, "schema-version")
                if version.get("version") != 2:
                    raise ValueError("DATABASE_MIGRATION_REQUIRED")
            return
        metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            if self.engine.dialect.name == "sqlite":
                for table in ("records", "events"):
                    for action in ("UPDATE", "DELETE"):
                        conn.execute(
                            text(
                                f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only'); END"
                            )
                        )  # noqa: S608
            else:
                conn.execute(
                    text(
                        "CREATE OR REPLACE FUNCTION deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only'; END $$"
                    )
                )
                for table in ("records", "events"):
                    exists = conn.execute(
                        text("SELECT 1 FROM pg_trigger WHERE tgname=:name"),
                        {"name": f"immutable_{table}"},
                    ).first()
                    if not exists:
                        conn.execute(
                            text(
                                f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE OR TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation()"
                            )
                        )  # noqa: S608
            conn.execute(
                text(
                    "INSERT INTO states (id, payload) VALUES ('__lock__', '{}') ON CONFLICT (id) DO NOTHING"
                )
            )

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.engine.connect() as conn:
            if self.engine.dialect.name == "sqlite":
                conn.execute(text("BEGIN IMMEDIATE"))
            else:
                conn.execute(select(states.c.id).where(states.c.id == "__lock__").with_for_update())
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def append(
        self, conn: Connection, kind: str, payload: dict[str, Any], record_id: str | None = None
    ) -> str:
        identity = record_id or new_id()
        conn.execute(
            records.insert().values(
                id=identity, kind=kind, payload=canonical(payload), created_at=now()
            )
        )
        return identity

    def get(self, conn: Connection, record_id: str, kind: str | None = None) -> dict[str, Any]:
        import json

        row = conn.execute(select(records).where(records.c.id == record_id)).mappings().first()
        if row is None or (kind and row["kind"] != kind):
            raise KeyError(record_id)
        return dict(json.loads(row["payload"]))

    def list_records(self, conn: Connection, kind: str, limit: int = 200) -> list[dict[str, Any]]:
        import json

        rows = conn.execute(
            select(records.c.payload)
            .where(records.c.kind == kind)
            .order_by(records.c.created_at.desc(), records.c.id)
            .limit(limit)
        )
        return [dict(json.loads(row[0])) for row in rows]

    def related(self, conn: Connection, kind: str, key: str, identity: str) -> list[dict[str, Any]]:
        import json

        needle = canonical(key) + ":" + canonical(identity)
        rows = conn.execute(
            select(records.c.payload)
            .where(records.c.kind == kind, records.c.payload.contains(needle, autoescape=True))
            .order_by(records.c.created_at, records.c.id)
        )
        return [payload for row in rows if (payload := json.loads(row[0])).get(key) == identity]

    def state(
        self, conn: Connection, identity: str, default: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        import json

        row = conn.execute(select(states.c.payload).where(states.c.id == identity)).first()
        return dict(json.loads(row[0])) if row else dict(default or {})

    def set_state(self, conn: Connection, identity: str, payload: dict[str, Any]) -> None:
        serialized = canonical(payload)
        found = conn.execute(select(states.c.id).where(states.c.id == identity)).first()
        if found:
            conn.execute(states.update().where(states.c.id == identity).values(payload=serialized))
        else:
            conn.execute(states.insert().values(id=identity, payload=serialized))

    def audit(self, conn: Connection, topic: str, actor: str, data: dict[str, Any]) -> None:
        last = conn.execute(select(events.c.hash).order_by(events.c.seq.desc()).limit(1)).first()
        previous = last[0] if last else "0" * 64
        payload = {"topic": topic, "actor": actor, "data": data, "timestamp": now()}
        event_id = new_id()
        conn.execute(
            events.insert().values(
                id=event_id,
                payload=canonical(payload),
                previous_hash=previous,
                hash=digest({"id": event_id, "previous": previous, "payload": payload}),
            )
        )

    def audit_events(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        import json

        return [
            {**json.loads(row["payload"]), "id": row["id"], "hash": row["hash"], "seq": row["seq"]}
            for row in conn.execute(
                select(events).order_by(events.c.seq.desc()).limit(limit)
            ).mappings()
        ]

    def verify_audit(self, conn: Connection) -> bool:
        import json

        previous = "0" * 64
        for row in conn.execute(select(events).order_by(events.c.seq)).mappings():
            expected = digest(
                {"id": row["id"], "previous": previous, "payload": json.loads(row["payload"])}
            )
            if row["previous_hash"] != previous or row["hash"] != expected:
                return False
            previous = row["hash"]
        return True
