"""Закупки из бюджета, не на объект (HEAD 06.11.2026).

- Склад расходников (stock): главные художники, художники Про, мастер печати закупают краску, валики, скотч, чернила впрок.
- Мастерская холстов (canvas): мастер-плотник закупает брус, холст, грунт, крепёж для подрамников.
Фото чека обязательно. Месячный лимит на человека — fin.stock.limit_month / fin.canvas.limit_month в «Значениях»:
в пределах — одобрено само («к выплате», если свои деньги), сверх или пока лимита нет — ждёт HEAD во «Проверке».
"""
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import constants as consts
from . import db, drive
from .config import settings
from .work import active, with_receipt

router = APIRouter(prefix="/api")
TZ = ZoneInfo("Asia/Almaty")
# Кто какие закупки вносит. HEAD — любые.
WHO = {"lead_artist": {"stock"}, "artist_pro": {"stock"}, "print_master": {"stock"}, "carpenter": {"canvas"},
       "head": {"stock", "canvas"}}
LIMIT = {"stock": "fin.stock.limit_month", "canvas": "fin.canvas.limit_month"}
TITLE = {"stock": "Склад", "canvas": "Мастерская холстов"}
LIVE = ("submitted", "approved")


def kinds(p: dict) -> set[str]:
    k = WHO.get(p["role_code"])
    if not k:
        raise HTTPException(403, "Закупки на склад — для главных художников, Про, мастера печати и мастера-плотника")
    return k


def _month(now=None):
    now = now or datetime.now(TZ)
    start = datetime(now.year, now.month, 1, tzinfo=TZ)
    return start, datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=TZ)


def _spent(conn, person_id: int, article: str, start, end) -> float:
    return float(conn.execute("""SELECT coalesce(sum(e.amount), 0) AS s FROM expenses e JOIN expense_categories c ON c.code=e.category
                                 WHERE e.person_id=%s AND c.article=%s AND e.status = ANY(%s) AND e.created_at >= %s AND e.created_at < %s""",
                              (person_id, article, list(LIVE), start, end)).fetchone()["s"])


class StockIn(BaseModel):
    client_uid: UUID
    category: str
    amount: float = Field(gt=0, le=10_000_000)
    paid_by: str = "own"
    receipt: str = Field(min_length=30, max_length=8_000_000)
    note: str | None = Field(default=None, max_length=500)
    deal_id: int | None = Field(default=None, gt=0)   # холсты под конкретный заказ картин — по желанию


@router.post("/stock/expenses")
def add(e: StockIn, p: dict = Depends(active)):
    allowed = kinds(p)
    if e.paid_by not in ("own", "company"):
        raise HTTPException(400, "bad paid_by")
    if not e.receipt.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "Нужно фото чека")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone()
        if dup:
            return with_receipt(dup)
        cat = conn.execute("SELECT title, article FROM expense_categories WHERE code=%s AND active", (e.category,)).fetchone()
        if not cat or cat["article"] not in allowed:
            raise HTTPException(400, "bad category")
        art = cat["article"]
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (p["id"],))
        start, end = _month()
        lim = consts.latest(conn).get(LIMIT[art])
        limit = float(lim) if isinstance(lim, (int, float)) else 0.0
        spent = _spent(conn, p["id"], art, start, end)
        ok = limit > 0 and spent + e.amount <= limit
        name = f"Чек {datetime.now(TZ):%Y-%m-%d %H-%M} {p['full_name']} {e.amount:.0f}"
        try:
            drive_id = drive.save_office_receipt(f"{TITLE[art]} — чеки", name, e.receipt)
        except Exception as ex:  # Диск недоступен — телефон повторит позже
            raise HTTPException(502, f"drive: {ex.__class__.__name__}")
        data, mime = drive.decode_data_url(e.receipt)
        f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                            VALUES (gen_random_uuid(), 0, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                         (name, mime, len(data), drive_id, p["id"])).fetchone()
        row = conn.execute(
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, note, deal_id,
                                     receipt_file_id, over_limit, status, payout_status, checked_at, reason)
               VALUES (%s,%s,0,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (e.client_uid, p["id"], e.category, e.amount, e.paid_by, e.note, e.deal_id, f["id"], bool(limit) and not ok,
             "approved" if ok else "submitted", "to_pay" if ok and e.paid_by == "own" else "none",
             datetime.now(TZ) if ok else None, "в пределах лимита" if ok else None)).fetchone()
        db.audit(conn, p["id"], "stock_expense_add", "expenses", row["id"], {"article": art, "over_limit": bool(limit) and not ok})
    if not ok and settings.head_tg_id and settings.bot_token and p["role_code"] != "head":
        try:
            from . import notify
            why = f"сверх лимита {limit:,.0f} ₸ (уже {spent:,.0f} ₸)".replace(",", " ") if limit else "лимит в «Значениях» ещё не задан"
            notify.SEND(settings.head_tg_id, f"🧾 {TITLE[art]}: закупка на одобрение — {p['full_name']}, {cat['title']}, "
                                             f"{e.amount:,.0f} ₸, {why}. Вкладка «Проверка».".replace(",", " "))
        except Exception as ex:  # noqa: BLE001
            print("stock notify:", ex)
    return {**with_receipt(row), "auto": ok}


@router.get("/stock/expenses")
def month(p: dict = Depends(active)):
    """Мои закупки за месяц и остаток лимита. HEAD — все закупки склада и мастерской."""
    allowed = kinds(p)
    head = p["role_code"] == "head"
    start, end = _month()
    with db.pool.connection() as conn:
        v = consts.latest(conn)
        cats = conn.execute("SELECT code, title, article FROM expense_categories WHERE active AND article = ANY(%s) ORDER BY sort",
                            (sorted(allowed),)).fetchall()
        rows = conn.execute(
            """SELECT e.id, e.person_id, pe.full_name AS person, e.category, c.title AS category_title, c.article, e.amount, e.paid_by,
                      e.note, e.deal_id, e.status, e.payout_status, e.over_limit, e.reason, e.receipt_file_id, e.created_at
               FROM expenses e JOIN expense_categories c ON c.code=e.category JOIN people pe ON pe.id=e.person_id
               WHERE c.article = ANY(%s) AND e.created_at >= %s AND e.created_at < %s AND e.status <> 'cancelled' AND (%s OR e.person_id=%s)
               ORDER BY e.created_at DESC""", (sorted(allowed), start, end, head, p["id"])).fetchall()
        limits = {}
        for a in sorted(allowed):
            lim = v.get(LIMIT[a]) if isinstance(v.get(LIMIT[a]), (int, float)) else 0
            spent = _spent(conn, p["id"], a, start, end)
            limits[a] = {"title": TITLE[a], "limit": lim, "spent": spent, "left": max(0.0, lim - spent) if lim else None}
    live = [r for r in rows if r["status"] in LIVE]
    return {"categories": cats, "limits": limits, "all": head, "items": [with_receipt(r) for r in rows],
            "total": sum(float(r["amount"]) for r in live), "waiting": sum(1 for r in rows if r["status"] == "submitted")}
