"""Подключение к PostgreSQL и применение миграций по порядку."""
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

pool: ConnectionPool | None = None


def open_pool(url: str | None = None) -> ConnectionPool:
    global pool
    pool = ConnectionPool(url or settings.database_url, kwargs={"row_factory": dict_row}, open=True)
    return pool


def migrate(p: ConnectionPool) -> list[str]:
    applied = []
    with p.connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            with conn.transaction():
                conn.execute(f.read_text())
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
            applied.append(f.name)
    return applied


def audit(conn, person_id, action, entity=None, entity_id=None, data=None):
    from psycopg.types.json import Jsonb

    from .viewas import audit_owner
    person_id, data = audit_owner(person_id, data)   # просмотр «как сотрудник» пишется на HEAD
    conn.execute(
        "INSERT INTO audit_log (person_id, action, entity, entity_id, data) VALUES (%s,%s,%s,%s,%s)",
        (person_id, action, entity, None if entity_id is None else str(entity_id), Jsonb(data) if data is not None else None),
    )
