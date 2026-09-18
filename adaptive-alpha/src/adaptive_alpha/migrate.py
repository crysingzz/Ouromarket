"""One-shot PostgreSQL schema owner. Runtime services cannot alter journals or triggers."""

from pathlib import Path

import psycopg
from psycopg import sql

from adaptive_alpha.config import Settings
from adaptive_alpha.store import Store


def main() -> None:
    settings = Settings()
    if not settings.database_url.startswith("postgresql+psycopg://"):
        raise ValueError("POSTGRES_MIGRATION_REQUIRED")
    store = Store(settings.database_url)
    store.initialize()
    password = (Path(settings.secrets_dir) / "runtime_password").read_text().strip()
    if len(password) < 32:
        raise ValueError("RUNTIME_DATABASE_PASSWORD_REQUIRED")
    with psycopg.connect(
        settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1), autocommit=True
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='alpha_runtime'"
        ).fetchone()
        command = (
            "ALTER ROLE alpha_runtime LOGIN PASSWORD {}"
            if exists
            else "CREATE ROLE alpha_runtime LOGIN PASSWORD {}"
        )
        connection.execute(sql.SQL(command).format(sql.Literal(password)))
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("GRANT USAGE ON SCHEMA public TO alpha_runtime")
        connection.execute("GRANT SELECT, INSERT ON records, events TO alpha_runtime")
        connection.execute("GRANT SELECT, INSERT, UPDATE ON states TO alpha_runtime")
        connection.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO alpha_runtime")
    with store.transaction() as conn:
        store.set_state(conn, "schema-version", {"version": 2})
    store.engine.dispose()
    print("Schema ready; runtime journal permissions restricted.")


if __name__ == "__main__":
    main()
