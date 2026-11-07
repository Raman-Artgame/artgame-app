"""Раздел «Смены и расходы». Отправка идемпотентна по client_uid (офлайн-очередь на телефоне)."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import math

from . import constants as consts
from . import db, drive
from .deps import current_person

router = APIRouter(prefix="/api")

# Кто проверяет какую зону (ARCHITECTURE.md «Роли и зоны»). HEAD — всё, ГИП — свой объект.
CHECKS = {"lead_artist": {"mural"}, "artist_pro": {"mural"}, "print_master": {"print"}, "lead_designer": {"design"}}
# Лестница (константы, HEAD 06.11): Саппорт → Художник → Главный → Про. По зоне проверяют только тех, кто ниже по уровню:
# Главный не проверяет Главного и Про; Про проверяет Главного. ГИП своего объекта и HEAD — всех.
RANK_SQL = "(SELECT r.level FROM people pp JOIN roles r ON r.code=pp.role_code WHERE pp.id=x.person_id)"


def active(p: dict = Depends(current_person)) -> dict:
    if p["status"] != "active":
        raise HTTPException(403, "pending")
    return p


def check_zone(conn, p: dict, zone: str, object_id: int):
    if zone not in p["zones"]:
        raise HTTPException(400, "zone not assigned")
    o = conn.execute("SELECT status FROM objects WHERE id=%s", (object_id,)).fetchone()
    if not o or o["status"] != "active":
        raise HTTPException(400, "object closed or missing")


@router.get("/work/dict")
def work_dict(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {
            "objects": conn.execute("SELECT id, title, city FROM objects WHERE status='active' ORDER BY id DESC").fetchall(),
            "categories": conn.execute("SELECT code, title FROM expense_categories WHERE active AND article='project' ORDER BY sort").fetchall(),
            "zones": p["zones"],
            "printer": consts.latest(conn).get("print.tech.printer"),
        }


class ShiftIn(BaseModel):
    client_uid: UUID
    object_id: int
    zone_code: str
    started_at: datetime
    ended_at: datetime | None = None
    area_m2: float | None = Field(default=None, ge=0)
    complexity: str | None = None
    note: str | None = None
    geo_lat: float | None = None
    geo_lon: float | None = None
    printer: str | None = Field(default=None, max_length=100)
    at_height: bool = False
    outdoor: bool = False
    hard_surface: bool = False


COMPLEXITY = ("easy", "medium", "hard", "author")
ROLE_NORM = {"support": "norm.role.support", "artist_pro": "norm.role.pro"}
PRINT_BONUS = {"print_operator": "pay.print.bonus_operator", "print_master": "pay.print.bonus_master"}


def _n(v: dict, key: str, default=None):
    x = v.get(key, default)
    return x if isinstance(x, (int, float)) else default


def shift_norm(v: dict, s: ShiftIn, role: str | None) -> dict:
    """Норма/план, КПД и бонус смены по «Значениям». Чего нет в «Значениях» — не считаем."""
    full = _n(v, "shift.hours", 10)
    hours = (s.ended_at - s.started_at).total_seconds() / 3600 if s.ended_at else full
    out = {"plan_m2": None, "kpd": None, "bonus": None}
    if s.zone_code == "mural" and s.complexity in COMPLEXITY:
        base = _n(v, f"norm.mural.{s.complexity}")
        if base:
            k = 1.0
            for flag, key in ((s.at_height, "norm.k.height"), (s.outdoor, "norm.k.outdoor"), (s.hard_surface, "norm.k.surface")):
                if flag:
                    k *= _n(v, key, 1)
            k *= _n(v, ROLE_NORM.get(role, ""), 1)
            out["plan_m2"] = round(base * k * min(hours, full * 1.5) / full, 2)
    elif s.zone_code == "print":
        out["plan_m2"] = _n(v, "print.plan_per_shift")
        step, rate = _n(v, "pay.print.bonus_step_m2"), _n(v, PRINT_BONUS.get(role, ""))
        if out["plan_m2"] and step and rate and s.area_m2:
            out["bonus"] = max(0, math.floor((s.area_m2 - out["plan_m2"]) / step)) * rate
    if out["plan_m2"] and s.area_m2 is not None:
        out["kpd"] = round(s.area_m2 / out["plan_m2"], 3)
    return out


@router.post("/shifts")
def add_shift(s: ShiftIn, p: dict = Depends(active)):
    if s.ended_at and s.ended_at <= s.started_at:
        raise HTTPException(400, "end before start")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (s.client_uid,)).fetchone()
        if dup:
            return dup
        check_zone(conn, p, s.zone_code, s.object_id)
        if s.complexity and s.complexity not in COMPLEXITY:
            raise HTTPException(400, "bad complexity")
        n = shift_norm(consts.latest(conn), s, p["role_code"])
        row = conn.execute(
            """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, area_m2,
                                   complexity, note, geo_lat, geo_lon, printer, at_height, outdoor, hard_surface,
                                   plan_m2, kpd, bonus)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (s.client_uid, p["id"], s.object_id, s.zone_code, s.started_at, s.ended_at, s.area_m2,
             s.complexity, s.note, s.geo_lat, s.geo_lon, s.printer, s.at_height, s.outdoor, s.hard_surface,
             n["plan_m2"], n["kpd"], n["bonus"])).fetchone()
        if not row:  # параллельный повтор успел раньше
            return conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (s.client_uid,)).fetchone()
        db.audit(conn, p["id"], "shift_add", "shifts", row["id"])
        return row


class ExpenseIn(BaseModel):
    client_uid: UUID
    object_id: int
    zone_code: str
    category: str
    amount: float = Field(ge=0)
    paid_by: str = "own"
    receipt: str | None = Field(default=None, max_length=8_000_000)  # data:image/jpeg;base64,… (сжато на телефоне)
    note: str | None = None


@router.post("/expenses")
def add_expense(e: ExpenseIn, p: dict = Depends(active)):
    if e.paid_by not in ("own", "company"):
        raise HTTPException(400, "bad paid_by")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone()
        if dup:
            return dup
        check_zone(conn, p, e.zone_code, e.object_id)
        if not conn.execute("SELECT 1 FROM expense_categories WHERE code=%s AND active AND article='project'", (e.category,)).fetchone():
            raise HTTPException(400, "bad category")
        drive_id = None
        if e.receipt:
            if not e.receipt.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
                raise HTTPException(400, "bad receipt")
            obj = conn.execute("SELECT * FROM objects WHERE id=%s", (e.object_id,)).fetchone()
            name = f"Чек {datetime.now():%Y-%m-%d %H-%M} {p['full_name']} {e.amount:.0f}"
            try:
                drive_id = drive.save_photo(conn, obj, name, e.receipt, kind="receipt")
            except Exception as ex:  # Диск недоступен — телефон повторит позже
                raise HTTPException(502, f"drive: {ex.__class__.__name__}")
        row = conn.execute(
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, receipt_url, note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (e.client_uid, p["id"], e.object_id, e.zone_code, e.category, e.amount, e.paid_by, None, e.note)).fetchone()
        if not row:
            return with_receipt(conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone())
        if drive_id:
            data, mime = drive.decode_data_url(e.receipt)
            f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                                VALUES (gen_random_uuid(), %s, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                             (e.object_id, name, mime, len(data), drive_id, p["id"])).fetchone()
            row = conn.execute("UPDATE expenses SET receipt_file_id=%s WHERE id=%s RETURNING *", (f["id"], row["id"])).fetchone()
        db.audit(conn, p["id"], "expense_add", "expenses", row["id"])
        return with_receipt(row)


def with_receipt(e: dict) -> dict:
    """Подписанная ссылка на чек (живёт 12 ч)."""
    from .files import sign
    e["receipt_url"] = sign(e["receipt_file_id"], "content") if e.get("receipt_file_id") else None
    return e


@router.get("/my")
def my(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {
            "shifts": conn.execute("""SELECT s.*, o.title AS object_title FROM shifts s JOIN objects o ON o.id=s.object_id
                                      WHERE person_id=%s ORDER BY started_at DESC LIMIT 100""", (p["id"],)).fetchall(),
            "expenses": [with_receipt(e) for e in conn.execute("""SELECT e.*, o.title AS object_title FROM expenses e JOIN objects o ON o.id=e.object_id
                                        WHERE person_id=%s ORDER BY created_at DESC LIMIT 100""", (p["id"],)).fetchall()],
        }


TABLE = {"shift": "shifts", "expense": "expenses"}


@router.post("/{kind}/{item_id}/cancel")
def cancel(kind: str, item_id: int, p: dict = Depends(active)):
    """Сам отменяет свою запись, пока её не проверили. Не удаляем — помечаем."""
    t = TABLE.get(kind)
    if not t:
        raise HTTPException(404)
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute(f"UPDATE {t} SET status='cancelled' WHERE id=%s AND person_id=%s AND status='submitted' RETURNING id",
                           (item_id, p["id"])).fetchone()
        if not row:
            raise HTTPException(409, "not cancellable")
        db.audit(conn, p["id"], f"{kind}_cancel", t, item_id)
    return {"ok": True}


def review_filter(p: dict) -> tuple[str, list]:
    """SQL-условие: какие записи человек может проверять (не свои)."""
    if p["role_code"] == "head":
        return "TRUE", []
    zones = sorted(CHECKS.get(p["role_code"], set()))
    own = f"(SELECT level FROM roles WHERE code=%s)"
    return (f"((x.zone_code = ANY(%s) AND COALESCE({RANK_SQL}, 0) < {own}) OR o.gip_person_id = %s) AND x.person_id <> %s",
            [zones, p["role_code"], p["id"], p["id"]])


@router.get("/review")
def review_list(p: dict = Depends(active)):
    cond, args = review_filter(p)
    with db.pool.connection() as conn:
        out = {}
        for kind, t in TABLE.items():
            out[t] = conn.execute(
                f"""SELECT x.*, o.title AS object_title, pe.full_name AS person_name
                    FROM {t} x JOIN objects o ON o.id=x.object_id JOIN people pe ON pe.id=x.person_id
                    WHERE x.status='submitted' AND {cond} ORDER BY x.created_at""", args).fetchall()
        cats = {c["code"]: c for c in conn.execute("SELECT code, title, article FROM expense_categories").fetchall()}
        flags = {}   # покупки по каталогу: почему ждёт HEAD (выше потолка / нет ориентира)
        for r in conn.execute("""SELECT expense_id, array_agg(DISTINCT flag) AS f FROM stock_lines
                                 WHERE expense_id = ANY(%s) AND flag IN ('over_cap','no_ref') GROUP BY expense_id""",
                              ([e["id"] for e in out["expenses"]],)).fetchall():
            flags[r["expense_id"]] = [{"over_cap": "выше потолка цены", "no_ref": "нет ориентира цены"}[f] for f in sorted(r["f"], reverse=True)]
        for e in out["expenses"]:   # трата отдела продаж: вместо «Офис / без объекта» — статья и сделка
            c = cats.get(e["category"]) or {}
            e["category_title"] = c.get("title", e["category"])
            if c.get("article") in ("stock", "canvas"):
                fl = flags.get(e["id"])
                tail = (" · " + ", ".join(fl)) if fl else (" · сверх лимита" if e.get("over_limit") else "")
                e["object_title"] = ("Склад" if c["article"] == "stock" else "Мастерская холстов") + " · " + e["category_title"] + tail
            if c.get("article") == "sales":
                e["object_title"] = "Отдел продаж · " + e["category_title"] + (f" · сделка № {e['deal_id']}" if e.get("deal_id") else "") + (" · сверх лимита" if e.get("over_limit") else "")
        out["expenses"] = [with_receipt(e) for e in out["expenses"]]
        if p["role_code"] != "head":
            for x in out["shifts"]:
                x.pop("bonus", None)
        return out


class Decision(BaseModel):
    approve: bool
    reason: str | None = None


@router.post("/{kind}/{item_id}/review")
def review(kind: str, item_id: int, d: Decision, p: dict = Depends(active)):
    t = TABLE.get(kind)
    if not t:
        raise HTTPException(404)
    if not d.approve and not (d.reason or "").strip():
        raise HTTPException(400, "reason required")
    cond, args = review_filter(p)
    with db.pool.connection() as conn, conn.transaction():
        ok = conn.execute(f"SELECT x.id FROM {t} x JOIN objects o ON o.id=x.object_id WHERE x.id=%s AND x.status='submitted' AND {cond}",
                          [item_id, *args]).fetchone()
        if not ok:
            raise HTTPException(403, "cannot review")
        status = "approved" if d.approve else "rejected"
        extra = ", payout_status = CASE WHEN paid_by='own' THEN 'to_pay' ELSE payout_status END" if t == "expenses" and d.approve else ""
        conn.execute(f"UPDATE {t} SET status=%s, reason=%s, checked_by=%s, checked_at=now(){extra} WHERE id=%s",
                     (status, d.reason, p["id"], item_id))
        db.audit(conn, p["id"], f"{kind}_{status}", t, item_id, {"reason": d.reason})
    return {"ok": True, "status": status}
