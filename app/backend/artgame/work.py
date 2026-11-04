"""Раздел «Смены и расходы». Отправка идемпотентна по client_uid (офлайн-очередь на телефоне)."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .deps import current_person

router = APIRouter(prefix="/api")

# Кто проверяет какую зону (ARCHITECTURE.md «Роли и зоны»). HEAD — всё, ГИП — свой объект.
CHECKS = {"lead_artist": {"mural"}, "print_master": {"print"}, "lead_designer": {"design"}}


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
            "categories": conn.execute("SELECT code, title FROM expense_categories WHERE active ORDER BY sort").fetchall(),
            "zones": p["zones"],
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


@router.post("/shifts")
def add_shift(s: ShiftIn, p: dict = Depends(active)):
    if s.ended_at and s.ended_at <= s.started_at:
        raise HTTPException(400, "end before start")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (s.client_uid,)).fetchone()
        if dup:
            return dup
        check_zone(conn, p, s.zone_code, s.object_id)
        row = conn.execute(
            """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, area_m2,
                                   complexity, note, geo_lat, geo_lon)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (s.client_uid, p["id"], s.object_id, s.zone_code, s.started_at, s.ended_at, s.area_m2,
             s.complexity, s.note, s.geo_lat, s.geo_lon)).fetchone()
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
    receipt_url: str | None = None
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
        if not conn.execute("SELECT 1 FROM expense_categories WHERE code=%s AND active", (e.category,)).fetchone():
            raise HTTPException(400, "bad category")
        row = conn.execute(
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, receipt_url, note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (e.client_uid, p["id"], e.object_id, e.zone_code, e.category, e.amount, e.paid_by, e.receipt_url, e.note)).fetchone()
        if not row:
            return conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone()
        db.audit(conn, p["id"], "expense_add", "expenses", row["id"])
        return row


@router.get("/my")
def my(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {
            "shifts": conn.execute("""SELECT s.*, o.title AS object_title FROM shifts s JOIN objects o ON o.id=s.object_id
                                      WHERE person_id=%s ORDER BY started_at DESC LIMIT 100""", (p["id"],)).fetchall(),
            "expenses": conn.execute("""SELECT e.*, o.title AS object_title FROM expenses e JOIN objects o ON o.id=e.object_id
                                        WHERE person_id=%s ORDER BY created_at DESC LIMIT 100""", (p["id"],)).fetchall(),
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
    return "(x.zone_code = ANY(%s) OR o.gip_person_id = %s) AND x.person_id <> %s", [zones, p["id"], p["id"]]


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
