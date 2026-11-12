"""Кабинет HEAD — «Пульт» (HEAD 08.11): одним экраном, что ждёт решения и что происходит в команде.

Только чтение и только HEAD. Деньги месяца экран берёт отдельно из /fin/summary (он медленнее: читает таблицы),
здесь — то, что лежит в базе приложения: проверка, новые люди, каталоги, смены сегодня, последние действия команды.
"""
from fastapi import APIRouter, Depends

from . import db
from .deps import require_head
from .work import READY_SQL, SHOP_SQL

router = APIRouter(prefix="/api")

FEED = ("deal_open", "place_download", "shift_add", "shift_start", "shift_finish", "media_review", "expense_add", "shift_cancel", "expense_cancel",
        "bx_write", "place_doc_set", "file_add", "register", "feedback_add")


@router.get("/head/pulse")
def pulse(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        one = lambda q, a=(): conn.execute(q, a).fetchone()  # noqa: E731
        pending = conn.execute("SELECT id, full_name, tg_username, created_at FROM people WHERE status='pending' ORDER BY created_at").fetchall()
        # HEAD 11.11: у HEAD — то, что куратор оценил, записи кураторов и то, что куратор не оценил за 24 ч; остальное ждёт куратора
        q = lambda t, extra="": f"(SELECT count(*) FROM {t} x JOIN objects o ON o.id=x.object_id WHERE x.status='submitted' {extra})"  # noqa: E731
        rv = one(f"""SELECT {q('shifts', 'AND ' + READY_SQL)} AS shifts,
                           {q('expenses', 'AND ' + READY_SQL)} AS expenses,
                           {q('appeals', 'AND ' + READY_SQL)} AS appeals,
                           {q('shifts', 'AND NOT ' + READY_SQL)} + {q('expenses', 'AND NOT ' + READY_SQL)} + {q('appeals', 'AND NOT ' + READY_SQL)} AS curating,
                           (SELECT count(*) FROM shifts WHERE status='submitted' AND cur_stars >= 4) AS rated_good,
                           (SELECT coalesce(sum(amount),0) FROM expenses WHERE status='submitted') AS expenses_sum,
                           {q('shifts', "AND coalesce(x.submitted_at, x.created_at) < now() - interval '48 hours'")} AS shifts_late,
                           {q('expenses', "AND coalesce(x.submitted_at, x.created_at) < now() - interval '48 hours'")} AS expenses_late,
                           (SELECT count(DISTINCT expense_id) FROM stock_lines l JOIN expenses e ON e.id=l.expense_id
                             WHERE e.status='submitted' AND l.flag IN ('over_cap','no_ref')) AS over_cap,
                           -- оплаты клиентов, которые внесли МОП (HEAD 10.11): сверить с чеком и выпиской
                           (SELECT count(*) FROM fin_ledger WHERE source='app' AND status='active' AND checked_at IS NULL
                             AND article_code IN ('client_payment','design_prepay')) AS payments,
                           (SELECT coalesce(sum(amount),0) FROM fin_ledger WHERE source='app' AND status='active' AND checked_at IS NULL
                             AND article_code IN ('client_payment','design_prepay')) AS payments_sum""")
        catalogs = one("SELECT count(*) AS n FROM design_catalogs WHERE status='sent'")["n"]
        feedback = conn.execute(   # «Обращения» (HEAD 08.11): новые и в работе
            """SELECT f.id, f.kind, f.text, f.place, f.status, f.created_at, pe.full_name, r.title AS role_title
               FROM feedback f JOIN people pe ON pe.id=f.person_id LEFT JOIN roles r ON r.code=f.role_code
               WHERE f.status<>'done' ORDER BY f.status='work', f.created_at DESC LIMIT 20""").fetchall()
        media = one("SELECT count(*) AS n FROM files WHERE kind='media' AND status='ready' AND review='pending'")["n"]
        from .dm import _head_unread   # «Чат» (HEAD 11.11): «Руководство» + мои личные; обращения — всем HEAD
        u = _head_unread(conn, p["id"])
        dm = {"unread": u["group"] + u["mine"], "people": u["people"]}   # «Диалог с HEAD» (09.11): непрочитанные от сотрудников
        today = conn.execute(
            f"""SELECT s.id, pe.full_name, r.title AS role_title, {SHOP_SQL.format(s="s", pe="pe")} AS object_title, s.zone_code, s.started_at, s.ended_at, s.status
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
        from .recurring import due_now   # постоянные оплаты на сегодня и просроченные (HEAD 12.11)
        bills = [{k: x[k] for k in ("id", "title", "amount", "due", "status")} for x in due_now(conn)]
        week = one("""SELECT count(*) FILTER (WHERE status='approved') AS approved, count(*) FILTER (WHERE status='rejected') AS rejected,
                             count(DISTINCT person_id) AS people
                      FROM shifts WHERE started_at > now() - interval '7 days' AND status<>'cancelled'""")
    return {"pending": pending, "review": {**rv, "expenses_sum": float(rv["expenses_sum"]), "payments_sum": float(rv["payments_sum"])},
            "catalogs": catalogs, "media": media, "feedback": feedback, "dm": dm,
            "bills": bills, "today": today, "team": team, "feed": feed, "week": week}
