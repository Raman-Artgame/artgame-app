"""Кабинет HEAD — «Пульт» (HEAD 08.11): одним экраном, что ждёт решения и что происходит в команде.

Только чтение и только HEAD. Деньги месяца экран берёт отдельно из /fin/summary (он медленнее: читает таблицы),
здесь — то, что лежит в базе приложения: проверка, новые люди, каталоги, смены сегодня, последние действия команды.
"""
from fastapi import APIRouter, Depends

from . import db
from .deps import require_head

router = APIRouter(prefix="/api")

FEED = ("deal_open", "place_download", "shift_add", "expense_add", "shift_cancel", "expense_cancel",
        "bx_write", "place_doc_set", "file_add", "register")


@router.get("/head/pulse")
def pulse(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        one = lambda q, a=(): conn.execute(q, a).fetchone()  # noqa: E731
        pending = conn.execute("SELECT id, full_name, tg_username, created_at FROM people WHERE status='pending' ORDER BY created_at").fetchall()
        rv = one("""SELECT (SELECT count(*) FROM shifts WHERE status='submitted') AS shifts,
                           (SELECT count(*) FROM expenses WHERE status='submitted') AS expenses,
                           (SELECT coalesce(sum(amount),0) FROM expenses WHERE status='submitted') AS expenses_sum,
                           (SELECT count(*) FROM shifts WHERE status='submitted' AND created_at < now() - interval '24 hours') AS shifts_late,
                           (SELECT count(*) FROM expenses WHERE status='submitted' AND created_at < now() - interval '24 hours') AS expenses_late,
                           (SELECT count(DISTINCT expense_id) FROM stock_lines l JOIN expenses e ON e.id=l.expense_id
                             WHERE e.status='submitted' AND l.flag IN ('over_cap','no_ref')) AS over_cap""")
        catalogs = one("SELECT count(*) AS n FROM design_catalogs WHERE status='sent'")["n"]
        today = conn.execute(
            """SELECT s.id, pe.full_name, r.title AS role_title, o.title AS object_title, s.zone_code, s.started_at, s.ended_at, s.status
               FROM shifts s JOIN people pe ON pe.id=s.person_id LEFT JOIN roles r ON r.code=pe.role_code JOIN objects o ON o.id=s.object_id
               WHERE s.status <> 'cancelled' AND (s.started_at AT TIME ZONE 'Asia/Almaty')::date = (now() AT TIME ZONE 'Asia/Almaty')::date
               ORDER BY s.started_at""").fetchall()
        team = conn.execute(
            """SELECT r.code, r.title, r.level, count(pe.id) FILTER (WHERE pe.status='active') AS active,
                      count(pe.id) FILTER (WHERE pe.status='blocked') AS blocked
               FROM roles r LEFT JOIN people pe ON pe.role_code=r.code
               WHERE r.code<>'head' GROUP BY r.code ORDER BY r.level, r.title""").fetchall()
        feed = conn.execute(
            """SELECT a.at, a.action, a.entity_id, a.data, pe.full_name, pe.role_code
               FROM audit_log a JOIN people pe ON pe.id=a.person_id
               WHERE a.person_id<>%s AND a.action = ANY(%s) ORDER BY a.at DESC LIMIT 15""", (p["id"], list(FEED))).fetchall()
        week = one("""SELECT count(*) FILTER (WHERE status='approved') AS approved, count(*) FILTER (WHERE status='rejected') AS rejected,
                             count(DISTINCT person_id) AS people
                      FROM shifts WHERE started_at > now() - interval '7 days' AND status<>'cancelled'""")
    return {"pending": pending, "review": {**rv, "expenses_sum": float(rv["expenses_sum"])}, "catalogs": catalogs,
            "today": today, "team": team, "feed": feed, "week": week}
