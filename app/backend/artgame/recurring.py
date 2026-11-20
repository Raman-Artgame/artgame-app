"""График постоянных оплат (HEAD 10–12.11.2026): «в этот день приходило полноценное напоминание … сразу оплачивал и прикреплял».

Список — аренда, связь, подписки, сервер, Битрикс, госзакуп (fin_recurring, миграция 060). Сумма — из «Значений»
по ключу статьи (fin_articles.plan_key, fin.fixed.*), в коде цифр нет.
- Обычный платёж: в день оплаты горит на Пульте HEAD и приходит в бот (notify.head_recurring), пока не отмечен.
  «Оплачено» — переводом с чеком (обязателен) или наличными, как «К выплате в понедельник».
- Автосписание (подписки, HEAD 12.11): в день списания расход пишется сам по сумме из «Значений», в бот — «Списано».
  Не та сумма — HEAD отменяет строку в «Деньгах», платёж снова ждёт и вносится руками с верной суммой.
Оба пишут строку журнала денег по статье платежа (тот же журнал, что «+ Операция»), source_ref 'recurring:<id>:<цикл>'.
Цикл: месяц «2026-11» или год «2027». Долги считаются только с даты start_date (раньше — оплачено до приложения).
"""
import calendar
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .deps import require_head
from .finance import TZ, _receipt, add_ledger, vals
from .work import with_receipt

router = APIRouter(prefix="/api")
SOON = 3   # «скоро» — за столько дней платёж выделен в списке


def _on(y: int, m: int, day: int) -> date:
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def cycles(r: dict, today: date) -> list[tuple[str, date]]:
    """Прошлый, текущий и следующий цикл платежа: (ключ, дата оплаты)."""
    if r["every"] == "year":
        return [(str(y), _on(y, r["month"], r["day"])) for y in (today.year - 1, today.year, today.year + 1)]
    res = []
    for k in (-1, 0, 1):
        y, m = divmod(today.year * 12 + today.month - 1 + k, 12)
        res.append((f"{y}-{m + 1:02d}", _on(y, m + 1, r["day"])))
    return res


def _ref(rid: int, cycle: str) -> str:
    return f"recurring:{rid}:{cycle}"


def _today() -> date:
    return datetime.now(TZ).date()


def _rows(conn, all_rows: bool = False) -> list[dict]:
    return conn.execute("""SELECT r.*, a.plan_key FROM fin_recurring r JOIN fin_articles a ON a.code=r.article_code
                           WHERE %s OR r.active ORDER BY r.active DESC, r.every, r.day, r.sort, r.id""", (all_rows,)).fetchall()


def items(conn, today: date | None = None, all_rows: bool = False) -> list[dict]:
    """Каждый платёж с ближайшим неоплаченным циклом: status overdue | today | soon | later | paid | off."""
    today = today or _today()
    v = vals(conn)
    paid = {x["source_ref"]: x for x in conn.execute(
        """SELECT source_ref, op_date, amount, account_code FROM fin_ledger
           WHERE source='app' AND status='active' AND source_ref LIKE 'recurring:%%'""").fetchall()}
    out = []
    for r in _rows(conn, all_rows):
        cyc = [(c, d) for c, d in cycles(r, today) if d >= r["start_date"]]
        unpaid = [(c, d) for c, d in cyc if _ref(r["id"], c) not in paid]
        last = next((paid[_ref(r["id"], c)] for c, _ in reversed(cyc) if _ref(r["id"], c) in paid), None)
        if unpaid:
            c, d = unpaid[0]
            left = (d - today).days
            st = "overdue" if left < 0 else "today" if left == 0 else "soon" if left <= SOON else "paid" if last else "later"
        else:
            c, d = cyc[-1] if cyc else ("", None)
            st = "paid"
        out.append({"id": r["id"], "title": r["title"], "article": r["article_code"], "every": r["every"], "day": r["day"],
                    "month": r["month"], "active": r["active"], "auto": r["auto"], "account": r["account_code"],
                    "amount": v.get(r["plan_key"]) if r["plan_key"] else None,
                    "amount_key": r["plan_key"], "cycle": c, "due": d.isoformat() if d else None,
                    "status": st if r["active"] else "off",
                    "last_paid": {"date": last["op_date"].isoformat(), "amount": float(last["amount"]), "account": last["account_code"]} if last else None})
    return out


def due_now(conn, today: date | None = None) -> list[dict]:
    """Что оплатить сейчас: сегодня и просроченное (Пульт и бот). Автосписание сначала записывается само,
    сюда попадает, только если HEAD отменил строку (не та сумма) или в «Значениях» нет суммы."""
    auto_book(conn, today)
    return [x for x in items(conn, today) if x["status"] in ("today", "overdue")]


def auto_book(conn, today: date | None = None) -> list[dict]:
    """Автосписания: на дату списания — строка расхода по сумме из «Значений». Отменённую строку не повторяем."""
    today = today or _today()
    head = conn.execute("SELECT id FROM people WHERE role_code='head' AND status='active' ORDER BY id LIMIT 1").fetchone()
    if not head:
        return []
    v = vals(conn)
    done = []
    for r in _rows(conn):
        if not r["auto"]:
            continue
        amount = v.get(r["plan_key"]) if r["plan_key"] else None
        for c, d in cycles(r, today):
            if d < r["start_date"] or d > today or not amount:
                continue
            ref = _ref(r["id"], c)
            if conn.execute("SELECT 1 FROM fin_ledger WHERE source='app' AND source_ref=%s", (ref,)).fetchone():
                continue   # уже записано (или HEAD отменил — тогда вносит руками)
            period = c if r["every"] == "month" else f"{d:%Y-%m}"
            with conn.transaction():
                row = add_ledger(conn, {"id": head["id"]}, client_uid=uuid.uuid4(), op_date=d, account=r["account_code"], direction="out",
                                 amount=amount, article=r["article_code"], period=period,
                                 note=f"Автосписание: {r['title']} за {c}", source="app", source_ref=ref)
                db.audit(conn, head["id"], "fin_recurring_auto", "fin_recurring", r["id"], {"cycle": c, "amount": amount, "ledger": row["id"]})
            done.append({"id": r["id"], "title": r["title"], "amount": amount, "cycle": c})
    return done


@router.get("/fin/recurring")
def recurring_list(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        auto_book(conn)   # если таймер ещё не прошёл — запишем сейчас
        rows = items(conn, all_rows=True)
        arts = conn.execute("SELECT code, title, plan_key FROM fin_articles WHERE active AND kind IN ('fixed','variable','tax') ORDER BY sort").fetchall()
        hist = [with_receipt(x) for x in conn.execute(
            """SELECT l.id, l.op_date, l.amount, l.account_code, l.receipt_file_id, l.source_ref, a.title AS account, r.title, r.auto
               FROM fin_ledger l JOIN fin_accounts a ON a.code=l.account_code
               JOIN fin_recurring r ON split_part(l.source_ref, ':', 2) = r.id::text
               WHERE l.source='app' AND l.status='active' AND l.source_ref LIKE 'recurring:%%' AND l.op_date >= current_date - 60
               ORDER BY l.op_date DESC, l.id DESC LIMIT 60""").fetchall()]
    now = [x for x in rows if x["status"] in ("today", "overdue")]
    return {"items": rows, "due": now, "due_total": round(sum(x["amount"] or 0 for x in now)),
            "month_total": round(sum(x["amount"] or 0 for x in rows if x["active"] and x["every"] == "month")),
            "articles": arts, "paid": hist}


class RecPayIn(BaseModel):
    client_uid: uuid.UUID
    cycle: str = Field(pattern=r"^\d{4}(-\d{2})?$")
    account: str
    op_date: date
    amount: float = Field(gt=0, le=1_000_000_000)   # в этот раз сумма может отличаться (телефон) — HEAD правит при оплате
    receipt: str | None = Field(default=None, max_length=8_000_000)
    note: str | None = Field(default=None, max_length=300)


@router.post("/fin/recurring/{rid}/pay")
def recurring_pay(rid: int, b: RecPayIn, p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM fin_ledger WHERE client_uid=%s", (b.client_uid,)).fetchone():
            return {"ok": True, "repeat": True}
        r = conn.execute("SELECT * FROM fin_recurring WHERE id=%s", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "нет такого платежа")
        if (r["every"] == "year") != (len(b.cycle) == 4):
            raise HTTPException(400, "не тот период платежа")
        if not conn.execute("SELECT 1 FROM fin_accounts WHERE code=%s AND active", (b.account,)).fetchone():
            raise HTTPException(400, "нет такого счёта")
        if b.account != "cash" and not b.receipt and not r["auto"]:
            raise HTTPException(400, "Переводом — приложите чек")   # HEAD 12.11
        ref = _ref(rid, b.cycle)
        if conn.execute("SELECT 1 FROM fin_ledger WHERE source='app' AND source_ref=%s AND status='active'", (ref,)).fetchone():
            raise HTTPException(409, "уже оплачено за этот период")
        period = b.cycle if r["every"] == "month" else f"{b.op_date:%Y-%m}"
        with conn.transaction():
            fid = _receipt(conn, p, f"{b.op_date} {r['title']} {b.amount:.0f}", b.receipt) if b.receipt else None
            row = add_ledger(conn, p, client_uid=b.client_uid, op_date=b.op_date, account=b.account, direction="out", amount=b.amount,
                             article=r["article_code"], period=period,
                             note=f"Постоянная оплата: {r['title']} за {b.cycle}" + (f" · {b.note}" if b.note else ""),
                             receipt_file_id=fid, source="app", source_ref=ref)
            db.audit(conn, p["id"], "fin_recurring_pay", "fin_recurring", rid, {"cycle": b.cycle, "amount": b.amount, "ledger": row["id"]})
    return {"ok": True, "ledger": row["id"]}


class RecIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    article: str
    every: str = Field(pattern="^(month|year)$")
    day: int = Field(ge=1, le=31)
    month: int | None = Field(default=None, ge=1, le=12)
    auto: bool = False
    account: str = "kaspi"
    active: bool = True


def _check(conn, b: RecIn):
    if b.every == "year" and not b.month:
        raise HTTPException(400, "раз в год: укажите месяц")
    if not conn.execute("SELECT 1 FROM fin_articles WHERE code=%s AND active AND kind IN ('fixed','variable','tax')", (b.article,)).fetchone():
        raise HTTPException(400, "нет такой статьи")
    if not conn.execute("SELECT 1 FROM fin_accounts WHERE code=%s AND active", (b.account,)).fetchone():
        raise HTTPException(400, "нет такого счёта")


@router.post("/fin/recurring")
def recurring_add(b: RecIn, p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        _check(conn, b)
        row = conn.execute("""INSERT INTO fin_recurring (title, article_code, every, day, month, auto, account_code, active, start_date, sort)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,(now() AT TIME ZONE 'Asia/Almaty')::date, 100) RETURNING id""",
                           (b.title.strip(), b.article, b.every, b.day, b.month if b.every == "year" else None, b.auto, b.account,
                            b.active)).fetchone()
        db.audit(conn, p["id"], "fin_recurring_add", "fin_recurring", row["id"], b.model_dump())
    return {"ok": True, "id": row["id"]}


@router.post("/fin/recurring/{rid}")
def recurring_edit(rid: int, b: RecIn, p: dict = Depends(require_head)):
    """Поменять число, название, статью, автосписание или убрать в архив (не удаляем)."""
    with db.pool.connection() as conn, conn.transaction():
        _check(conn, b)
        old = conn.execute("SELECT * FROM fin_recurring WHERE id=%s", (rid,)).fetchone()
        if not old:
            raise HTTPException(404, "нет такого платежа")
        conn.execute("""UPDATE fin_recurring SET title=%s, article_code=%s, every=%s, day=%s, month=%s, auto=%s, account_code=%s, active=%s
                        WHERE id=%s""", (b.title.strip(), b.article, b.every, b.day, b.month if b.every == "year" else None, b.auto,
                                         b.account, b.active, rid))
        db.audit(conn, p["id"], "fin_recurring_edit", "fin_recurring", rid,
                 {"was": {k: old[k] for k in ("title", "article_code", "every", "day", "month", "auto", "account_code", "active")},
                  "now": b.model_dump()})
    return {"ok": True}
