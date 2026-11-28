"""Подключение к PostgreSQL и применение миграций по порядку."""
import sys
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

pool: ConnectionPool | None = None


def open_pool(url: str | None = None) -> ConnectionPool:
    global pool
    # HEAD 16.11 «приложение зависает»: по умолчанию в пуле всего 4 соединения на воркер — пока одни запросы ждут Диск/Битрикс
    # с открытым соединением, остальные стоят в очереди. Фото и чеки больше не держат соединение, пока идут в Google
    # (files.preupload, drive._own_conn), поэтому хватает 15 на воркер: 2 воркера × (test + prod) = 60 из 100 у Postgres.
    pool = ConnectionPool(url or settings.database_url, kwargs={"row_factory": dict_row}, open=True,
                          min_size=4, max_size=15, timeout=15, max_idle=300)
    return pool


def migrate(p: ConnectionPool) -> list[str]:
    applied = []
    with p.connection() as conn:
        # RAISE NOTICE миграций данных (что пропущено и почему) — в журнал службы: journalctl -u artgame-api@test | grep MIGRATION
        cur = {"f": ""}
        def notice(d):
            if cur["f"]:
                print(f"MIGRATION {cur['f']}: {d.severity} {d.message_primary}", file=sys.stderr, flush=True)
        conn.add_notice_handler(notice)
        try:
            return _apply(conn, applied, cur)
        finally:
            conn.remove_notice_handler(notice)


def _apply(conn, applied: list[str], cur: dict) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name in done:
            continue
        cur["f"] = f.name
        with conn.transaction():
            conn.execute(f.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
        applied.append(f.name)
    return applied


def is_gip(conn, oid: int, person_id: int) -> bool:
    """Куратор ГИП объекта — первый или второй (HEAD 28.11: кураторов может быть двое, права одинаковые)."""
    o = conn.execute("SELECT gip_person_id, gip2_person_id FROM objects WHERE id=%s", (oid,)).fetchone()
    return bool(o and person_id in (o["gip_person_id"], o["gip2_person_id"]))


def audit(conn, person_id, action, entity=None, entity_id=None, data=None):
    from psycopg.types.json import Jsonb

    from .viewas import audit_owner
    person_id, data = audit_owner(person_id, data)   # просмотр «как сотрудник» пишется на HEAD
    conn.execute(
        "INSERT INTO audit_log (person_id, action, entity, entity_id, data) VALUES (%s,%s,%s,%s,%s)",
        (person_id, action, entity, None if entity_id is None else str(entity_id), Jsonb(data) if data is not None else None),
    )
