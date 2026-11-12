"""Закупки из бюджета, не на объект (HEAD 06.11.2026).

Покупка по каталогу (POST /stock/purchase) — для ВСЕХ ролей: каждый может пополнить склад «на глаз».
Каталог (stock_items) — из «Журнала закупок»: ориентир цены за единицу задаёт HEAD, потолок = ориентир + допуск
stock.price_tolerance_pct из «Значений» (нет ключа — потолок = ориентир). Все строки в пределах потолка — принято само;
выше потолка или позиция без ориентира — ждёт HEAD. Лимитов на месяц нет. Деньги — в expenses (статья stock / canvas).
Онлайн-остатки склада — позже (поле norm — задел).

Старый вход (POST /stock/expenses по категориям с месячным лимитом) оставлен для совместимости:

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
from .work import active, with_receipt, self_approve

router = APIRouter(prefix="/api")
TZ = ZoneInfo("Asia/Almaty")
# Кто какие закупки вносит. HEAD — любые.
WHO = {"lead_artist": {"stock"}, "artist_pro": {"stock"}, "print_master": {"stock"}, "carpenter": {"canvas"},
       "head": {"stock", "canvas"}}
LIMIT = {"stock": "fin.stock.limit_month", "canvas": "fin.canvas.limit_month"}
TITLE = {"stock": "Склад", "canvas": "Мастерская холстов"}
LIVE = ("submitted", "approved")


def kinds(p: dict, strict: bool = True) -> set[str]:
    if not strict:   # просмотр своих закупок — всем ролям
        return WHO.get(p["role_code"], {"stock", "canvas"})
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
            drive_id = drive.save_receipt(conn, "stock", name, e.receipt, deal_id=e.deal_id)
        except Exception as ex:  # Диск недоступен — телефон повторит позже
            raise drive.fail(ex)
        data, mime = drive.decode_data_url(e.receipt)
        # HEAD 09.11: покупка с № сделки — это расход проекта, а не склад (такси — «Такси / доставка», прочее — «Докупка на объект»)
        oid, cat = 0, e.category
        if e.deal_id and conn.execute("SELECT 1 FROM objects WHERE id=%s", (e.deal_id,)).fetchone():
            oid, cat = e.deal_id, "purchase"
        f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                            VALUES (gen_random_uuid(), %s, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                         (oid, name, mime, len(data), drive_id, p["id"])).fetchone()
        row = conn.execute(
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, note, deal_id,
                                     receipt_file_id, over_limit, status, payout_status, checked_at, reason)
               VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (e.client_uid, p["id"], oid, cat, e.amount, e.paid_by, e.note, e.deal_id, f["id"], bool(limit) and not ok,
             "approved" if ok else "submitted", "to_pay" if ok and e.paid_by == "own" else "none",
             datetime.now(TZ) if ok else None, "в пределах лимита" if ok else None)).fetchone()
        row = self_approve(conn, p, row)
        db.audit(conn, p["id"], "stock_expense_add", "expenses", row["id"], {"article": art, "over_limit": bool(limit) and not ok})
    if not ok and settings.head_tg_id and settings.bot_token and p["role_code"] != "head":
        try:
            from . import notify
            why = f"сверх лимита {limit:,.0f} ₸ (уже {spent:,.0f} ₸)".replace(",", " ") if limit else "лимит в «Значениях» ещё не задан"
            notify.SEND(settings.head_tg_id, f"🧾 {TITLE[art]}: закупка на одобрение — {p['full_name']}, {cat['title']}, "
                                             f"{e.amount:,.0f} ₸, {why}. Вкладка «Проверка».".replace(",", " "))
        except Exception as ex:  # noqa: BLE001
            print("stock notify:", ex)
    return {**with_receipt(row), "auto": row["status"] == "approved"}


@router.get("/stock/expenses")
def month(p: dict = Depends(active)):
    """Мои закупки за месяц и остаток лимита. HEAD — все закупки склада и мастерской."""
    allowed = kinds(p, strict=False)
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
    return {"categories": cats, "limits": limits, "all": head, "me": p["id"], "items": [with_receipt(r) for r in rows],
            "total": sum(float(r["amount"]) for r in live), "waiting": sum(1 for r in rows if r["status"] == "submitted")}


@router.post("/stock/expenses/{expense_id}/cancel")
def cancel(expense_id: int, p: dict = Depends(active)):
    """Отменить свою покупку (замечание Анны 06.11: такси записали в «Склад» вместо «Трат»). Можно, пока не выплачено:
    запись не удаляется — помечается «отменено», из лимита, цен «по факту» и возмещения уходит. HEAD отменяет любую."""
    head = p["role_code"] == "head"
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("""UPDATE expenses SET status='cancelled', payout_status='none'
                              WHERE id=%s AND object_id=0 AND (%s OR person_id=%s) AND status = ANY(%s) AND payout_status <> 'paid'
                              RETURNING id, amount""", (expense_id, head, p["id"], list(LIVE))).fetchone()
        if not row:
            raise HTTPException(409, "эту покупку уже нельзя отменить (выплачено или отклонено) — напишите HEAD")
        conn.execute("UPDATE fin_accruals SET status='cancelled' WHERE kind='reimburse' AND ref=%s AND status='active'", (str(expense_id),))
        db.audit(conn, p["id"], "expense_cancel", "expenses", expense_id, {"amount": float(row["amount"]), "where": "stock"})
    return {"ok": True}


# ---------- покупка по каталогу: все роли ----------

TOL_KEY = "stock.price_tolerance_pct"
# Отдел каталога, который открывается первым у роли; остальные — переключателем.
HOME = {"support": "art", "artist": "art", "artist_pro": "art", "lead_artist": "art", "print_operator": "print",
        "print_master": "print", "carpenter": "workshop"}
FLAG = {"ok": "в норме", "above_ref": "выше ориентира", "over_cap": "выше потолка", "no_ref": "нет ориентира"}


def _tol(v: dict) -> float | None:
    t = v.get(TOL_KEY)
    return float(t) if isinstance(t, (int, float)) and t >= 0 else None


def _cap(ref, tol):
    if ref is None:
        return None
    return round(float(ref) * (1 + (tol or 0) / 100), 2)


def _flag(unit: float, ref, cap) -> str:
    if ref is None:
        return "no_ref"
    if unit > cap + 0.005:
        return "over_cap"
    return "above_ref" if unit > float(ref) + 0.005 else "ok"


def _money(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


@router.get("/stock/catalog")
def catalog(p: dict = Depends(active)):
    """Каталог по отделам + средняя фактическая цена по принятым покупкам."""
    with db.pool.connection() as conn:
        tol = _tol(consts.latest(conn))
        depts = conn.execute("""SELECT d.code, d.title, c.article FROM stock_depts d JOIN expense_categories c ON c.code=d.category
                                ORDER BY d.sort""").fetchall()
        fact = {r["item_code"]: float(r["avg"]) for r in conn.execute(
            """SELECT l.item_code, sum(l.amount) / sum(l.qty) AS avg FROM stock_lines l JOIN expenses e ON e.id=l.expense_id
               WHERE l.item_code IS NOT NULL AND e.status='approved' GROUP BY l.item_code""").fetchall()}
        items = conn.execute("SELECT * FROM stock_items WHERE active OR %s ORDER BY dept, sort, code", (p["role_code"] == "head",)).fetchall()
    for it in items:
        it["ref_price"] = float(it["ref_price"]) if it["ref_price"] is not None else None
        it["cap_price"] = _cap(it["ref_price"], tol)
        it["fact_price"] = round(fact[it["code"]], 2) if it["code"] in fact else None
        for k in ("updated_by", "updated_at"):
            it.pop(k, None)
    return {"depts": depts, "items": items, "tolerance": tol, "home": HOME.get(p["role_code"], "household"),
            "head": p["role_code"] == "head"}


class Line(BaseModel):
    item_code: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, max_length=200)   # своя позиция, которой нет в каталоге
    qty: float = Field(gt=0, le=100_000)
    amount: float = Field(gt=0, le=10_000_000)                # сумма по строке, ₸


class PurchaseIn(BaseModel):
    client_uid: UUID
    dept: str
    lines: list[Line] = Field(min_length=1, max_length=60)
    paid_by: str = "own"
    receipt: str = Field(min_length=30, max_length=8_000_000)
    note: str | None = Field(default=None, max_length=500)
    deal_id: int | None = Field(default=None, gt=0)           # под проект — по желанию


def project_category(names) -> str:
    """Статья расхода проекта для покупки «под сделку»: одно такси — transport, остальное — purchase."""
    names = [n.lower() for n in names]
    return "transport" if names and all("такси" in n or "доставк" in n for n in names) else "purchase"


@router.post("/stock/purchase")
def purchase(e: PurchaseIn, p: dict = Depends(active)):
    if e.paid_by not in ("own", "company"):
        raise HTTPException(400, "bad paid_by")
    if not e.receipt.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "Нужно фото чека")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone()
        if dup:
            return with_receipt(dup)
        d = conn.execute("""SELECT d.code, d.title, d.category, c.article FROM stock_depts d JOIN expense_categories c ON c.code=d.category
                            WHERE d.code=%s""", (e.dept,)).fetchone()
        if not d:
            raise HTTPException(400, "bad dept")
        tol = _tol(consts.latest(conn))
        lines = []
        for ln in e.lines:
            if ln.item_code:
                it = conn.execute("SELECT * FROM stock_items WHERE code=%s AND active", (ln.item_code,)).fetchone()
                if not it:
                    raise HTTPException(400, f"нет позиции {ln.item_code}")
                name, unit, ref = it["name"], it["unit"], (float(it["ref_price"]) if it["ref_price"] is not None else None)
            else:
                name = (ln.name or "").strip()
                if not name:
                    raise HTTPException(400, "Напиши, что купил")
                unit, ref = None, None
            cap = _cap(ref, tol)
            lines.append({"item_code": ln.item_code, "name": name, "unit": unit, "qty": ln.qty, "amount": ln.amount,
                          "ref": ref, "cap": cap, "flag": _flag(ln.amount / ln.qty, ref, cap)})
        total = round(sum(x["amount"] for x in lines), 2)
        bad = [x for x in lines if x["flag"] in ("over_cap", "no_ref")]
        ok = not bad
        summary = "; ".join(f"{x['name']} × {x['qty']:g} = {_money(x['amount'])}" + (f" ({FLAG[x['flag']]})" if x["flag"] != "ok" else "")
                            for x in lines)
        note = (summary + (" · " + e.note.strip() if e.note and e.note.strip() else ""))[:2000]
        name = f"Чек {datetime.now(TZ):%Y-%m-%d %H-%M} {p['full_name']} {total:.0f}"
        try:
            drive_id = drive.save_receipt(conn, "stock", name, e.receipt, deal_id=e.deal_id)
        except Exception as ex:  # Диск недоступен — телефон повторит позже
            raise drive.fail(ex)
        data, mime = drive.decode_data_url(e.receipt)
        # HEAD 09.11: покупка с № сделки — это расход проекта, а не склад (такси — «Такси / доставка», прочее — «Докупка на объект»)
        oid, cat = 0, d["category"]
        if e.deal_id and conn.execute("SELECT 1 FROM objects WHERE id=%s", (e.deal_id,)).fetchone():
            oid, cat = e.deal_id, project_category(x["name"] for x in lines)
        f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                            VALUES (gen_random_uuid(), %s, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                         (oid, name, mime, len(data), drive_id, p["id"])).fetchone()
        row = conn.execute(
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, note, deal_id,
                                     receipt_file_id, over_limit, status, payout_status, checked_at, reason)
               VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (e.client_uid, p["id"], oid, cat, total, e.paid_by, note, e.deal_id, f["id"], bool(bad),
             "approved" if ok else "submitted", "to_pay" if ok and e.paid_by == "own" else "none",
             datetime.now(TZ) if ok else None, "в пределах потолка цены" if ok else None)).fetchone()
        row = self_approve(conn, p, row)
        for x in lines:
            conn.execute("""INSERT INTO stock_lines (expense_id, item_code, name, unit, qty, amount, ref_price, cap_price, flag)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (row["id"], x["item_code"], x["name"], x["unit"], x["qty"], x["amount"], x["ref"], x["cap"], x["flag"]))
        db.audit(conn, p["id"], "stock_purchase_add", "expenses", row["id"], {"dept": d["code"], "lines": len(lines), "to_head": not ok})
    if not ok and settings.head_tg_id and settings.bot_token and p["role_code"] != "head":
        try:
            from . import notify
            why = "; ".join(f"{x['name']}: {_money(x['amount'] / x['qty'])} ₸/ед." +
                            (f" при потолке {_money(x['cap'])}" if x["cap"] is not None else " — ориентира нет") for x in bad)
            notify.SEND(settings.head_tg_id, f"🧾 Склад · {d['title']}: покупка на одобрение — {p['full_name']}, {_money(total)} ₸. "
                                             f"{why}. Вкладка «Проверка».")
        except Exception as ex:  # noqa: BLE001
            print("stock notify:", ex)
    return {**with_receipt(row), "auto": row["status"] == "approved", "lines": lines}


class ItemIn(BaseModel):
    dept: str
    name: str = Field(min_length=1, max_length=200)
    section: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=50)
    ref_price: float | None = Field(default=None, ge=0, le=100_000_000)
    where_buy: str | None = Field(default=None, max_length=100)
    norm: str | None = Field(default=None, max_length=100)
    active: bool = True


def _head(p: dict):
    if p["role_code"] != "head":
        raise HTTPException(403, "Каталог правит только HEAD")


@router.post("/stock/items/{code}")
def item_save(code: str, it: ItemIn, p: dict = Depends(active)):
    """HEAD правит позицию каталога: ориентир цены, название, где брать. Не удаляем — выключаем (active=false)."""
    _head(p)
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM stock_depts WHERE code=%s", (it.dept,)).fetchone():
            raise HTTPException(400, "bad dept")
        row = conn.execute("""UPDATE stock_items SET dept=%s, name=%s, section=%s, unit=%s, ref_price=%s, where_buy=%s, norm=%s, active=%s,
                                     updated_by=%s, updated_at=now() WHERE code=%s RETURNING *""",
                           (it.dept, it.name, it.section, it.unit, it.ref_price, it.where_buy, it.norm, it.active, p["id"], code)).fetchone()
        if not row:
            raise HTTPException(404)
        db.audit(conn, p["id"], "stock_item_save", "stock_items", None, {"code": code, **it.model_dump()})
    return row


@router.post("/stock/items")
def item_add(it: ItemIn, p: dict = Depends(active)):
    """Новая позиция: код по отделу (НОВ-001…), в конец отдела."""
    _head(p)
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM stock_depts WHERE code=%s", (it.dept,)).fetchone():
            raise HTTPException(400, "bad dept")
        conn.execute("SELECT pg_advisory_xact_lock(7316)")
        n = conn.execute("SELECT count(*) AS n FROM stock_items WHERE code LIKE 'НОВ-%%'").fetchone()["n"] + 1
        srt = conn.execute("SELECT coalesce(max(sort), 0) + 1 AS s FROM stock_items WHERE dept=%s", (it.dept,)).fetchone()["s"]
        row = conn.execute("""INSERT INTO stock_items (code, dept, section, name, unit, ref_price, where_buy, norm, sort, active, updated_by)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                           (f"НОВ-{n:03d}", it.dept, it.section, it.name, it.unit, it.ref_price, it.where_buy, it.norm, srt, it.active,
                            p["id"])).fetchone()
        db.audit(conn, p["id"], "stock_item_add", "stock_items", None, {"code": row["code"]})
    return row


@router.get("/stock/lines/{expense_id}")
def lines_of(expense_id: int, p: dict = Depends(active)):
    """Строки чека: свои — себе, любые — HEAD."""
    with db.pool.connection() as conn:
        e = conn.execute("SELECT person_id FROM expenses WHERE id=%s", (expense_id,)).fetchone()
        if not e or (e["person_id"] != p["id"] and p["role_code"] != "head"):
            raise HTTPException(404)
        return conn.execute("SELECT * FROM stock_lines WHERE expense_id=%s ORDER BY id", (expense_id,)).fetchall()
