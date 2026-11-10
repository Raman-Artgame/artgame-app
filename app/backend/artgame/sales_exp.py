"""Траты отдела продаж (HEAD 05.11.2026).

Статья «Коммерческие расходы — отдел продаж»: канцелярия и материалы, выезды и транспорт, встречи и представительские,
образцы и презентации. В себестоимость проектов не идут, считаются в стоимости привлечения клиента.
- Без фото чека трата не сохраняется.
- Месячный лимит МОП — ключ mop.expense.limit_month в «Значениях». В пределах лимита трата одобряется сама,
  сверх лимита (или пока лимит не задан) — ждёт HEAD во вкладке «Проверка».
- Привязка к сделке Битрикса — по желанию МОП (deal_id).
"""
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, drive
from .config import settings
from .work import active, with_receipt, self_approve

router = APIRouter(prefix="/api")
TZ = ZoneInfo("Asia/Almaty")
ROLES = {"mop", "mop_vip", "head"}
LIMIT_KEY = "mop.expense.limit_month"
LIVE = ("submitted", "approved")


def _limit() -> float:
    from .bx import _vals
    return float(_vals().get(LIMIT_KEY) or 0)


def _month(ym: str | None) -> tuple[datetime, datetime, str]:
    now = datetime.now(TZ)
    y, m = (int(x) for x in ym.split("-")) if ym else (now.year, now.month)
    start = datetime(y, m, 1, tzinfo=TZ)
    return start, datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=TZ), f"{y}-{m:02d}"


def _spent(conn, person_id: int, start, end) -> float:
    r = conn.execute("""SELECT coalesce(sum(e.amount), 0) AS s FROM expenses e JOIN expense_categories c ON c.code=e.category
                        WHERE e.person_id=%s AND c.article='sales' AND e.status = ANY(%s) AND e.created_at >= %s AND e.created_at < %s""",
                     (person_id, list(LIVE), start, end)).fetchone()
    return float(r["s"])


def need(p: dict) -> dict:
    if p["role_code"] not in ROLES:
        raise HTTPException(403, "Траты отдела продаж — для МОП и HEAD")
    return p


class SalesExpenseIn(BaseModel):
    client_uid: UUID
    category: str
    amount: float = Field(gt=0, le=10_000_000)
    paid_by: str = "own"
    receipt: str = Field(min_length=30, max_length=8_000_000)   # data:image/jpeg;base64,… — обязательно
    note: str | None = Field(default=None, max_length=500)
    deal_id: int | None = Field(default=None, gt=0)


@router.post("/sales/expenses")
def add(e: SalesExpenseIn, p: dict = Depends(active)):
    need(p)
    if e.paid_by not in ("own", "company"):
        raise HTTPException(400, "bad paid_by")
    if not e.receipt.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "Нужно фото чека")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone()
        if dup:
            return with_receipt(dup)
        cat = conn.execute("SELECT title FROM expense_categories WHERE code=%s AND active AND article='sales'", (e.category,)).fetchone()
        if not cat:
            raise HTTPException(400, "bad category")
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (p["id"],))   # две траты одновременно не обойдут лимит
        start, end, _ = _month(None)
        limit = _limit()
        spent = _spent(conn, p["id"], start, end)
        ok = limit > 0 and spent + e.amount <= limit
        name = f"Чек {datetime.now(TZ):%Y-%m-%d %H-%M} {p['full_name']} {e.amount:.0f}" + (f" сделка {e.deal_id}" if e.deal_id else "")
        try:
            drive_id = drive.save_receipt(conn, drive.dept_for(p, "sales"), name, e.receipt, deal_id=e.deal_id)
        except Exception as ex:  # Диск недоступен — телефон повторит позже
            raise HTTPException(502, f"drive: {ex.__class__.__name__}")
        data, mime = drive.decode_data_url(e.receipt)
        f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                            VALUES (gen_random_uuid(), 0, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                         (name, mime, len(data), drive_id, p["id"])).fetchone()
        row = conn.execute(
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, note, deal_id,
                                     receipt_file_id, over_limit, status, payout_status, checked_at, reason)
               VALUES (%s,%s,0,'sales',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (e.client_uid, p["id"], e.category, e.amount, e.paid_by, e.note, e.deal_id, f["id"], not ok,
             "approved" if ok else "submitted", "to_pay" if ok and e.paid_by == "own" else "none",
             datetime.now(TZ) if ok else None, "в пределах лимита" if ok else None)).fetchone()
        row = self_approve(conn, p, row)
        db.audit(conn, p["id"], "sales_expense_add", "expenses", row["id"], {"over_limit": not ok, "deal": e.deal_id})
    if not ok and settings.head_tg_id and settings.bot_token and p["role_code"] != "head":
        try:
            from . import notify
            why = f"сверх лимита {limit:,.0f} ₸ (уже {spent:,.0f} ₸)".replace(",", " ") if limit else "лимит в «Значениях» ещё не задан"
            notify.SEND(settings.head_tg_id, f"💳 Трата отдела продаж на одобрение: {p['full_name']}, {cat['title']}, "
                                             f"{e.amount:,.0f} ₸ — {why}. Вкладка «Проверка».".replace(",", " "))
        except Exception as ex:  # noqa: BLE001
            print("sales expense notify:", ex)
    return {**with_receipt(row), "auto": row["status"] == "approved"}


@router.get("/sales/expenses")
def month(ym: str | None = None, p: dict = Depends(active)):
    """Мои траты за месяц и лимит. HEAD — траты всего отдела, по людям и статьям."""
    need(p)
    start, end, ym = _month(ym)
    head = p["role_code"] == "head"
    with db.pool.connection() as conn:
        cats = conn.execute("SELECT code, title FROM expense_categories WHERE active AND article='sales' ORDER BY sort").fetchall()
        rows = conn.execute(
            """SELECT e.id, e.person_id, pe.full_name AS person, e.category, c.title AS category_title, e.amount, e.paid_by, e.note,
                      e.deal_id, e.status, e.payout_status, e.over_limit, e.reason, e.receipt_file_id, e.created_at
               FROM expenses e JOIN expense_categories c ON c.code=e.category JOIN people pe ON pe.id=e.person_id
               WHERE c.article='sales' AND e.created_at >= %s AND e.created_at < %s AND e.status <> 'cancelled'
                 AND (%s OR e.person_id=%s)
               ORDER BY e.created_at DESC""", (start, end, head, p["id"])).fetchall()
        spent = _spent(conn, p["id"], start, end)
    live = [r for r in rows if r["status"] in LIVE]
    limit = _limit()
    out = {"month": ym, "limit": limit, "spent": spent, "left": max(0.0, limit - spent) if limit else None,
           "categories": cats, "items": [with_receipt(r) for r in rows], "all": head,
           "total": sum(float(r["amount"]) for r in live),
           "by_category": {c["code"]: sum(float(r["amount"]) for r in live if r["category"] == c["code"]) for c in cats},
           "waiting": sum(1 for r in rows if r["status"] == "submitted")}
    if head:
        by: dict = {}
        for r in live:
            by.setdefault(r["person_id"], {"id": r["person_id"], "name": r["person"], "total": 0.0})["total"] += float(r["amount"])
        out["people"] = sorted(by.values(), key=lambda x: -x["total"])
    return out


def for_deal(deal_id: int) -> dict:
    """Траты на привлечение по сделке (в карточку): сумма и число живых трат с привязкой."""
    with db.pool.connection() as conn:
        r = conn.execute("""SELECT coalesce(sum(e.amount), 0) AS s, count(*) AS n FROM expenses e JOIN expense_categories c ON c.code=e.category
                            WHERE e.deal_id=%s AND c.article='sales' AND e.status = ANY(%s)""", (deal_id, list(LIVE))).fetchone()
    return {"sum": float(r["s"]), "count": r["n"]}
