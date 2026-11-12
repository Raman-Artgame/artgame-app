"""Командировка проекта (HEAD 10.11): «при галочке появлялись основные пункты расходов».

Отметка «Командировка» в карточке проекта (objects.trip: null — по городу, true/false — вручную). Ставят МОП, HEAD,
ГИП объекта и те, кто ставит людей на объект (can_crew). При смене отметки командировка всех смен объекта с 1.11
пересчитывается — питание pay.trip_food (3000 ₸/день) начисляется в ФОТ само за каждый день смены или дороги.
Проживание, дорога, транспорт на месте — суммы каждый раз разные: вносятся здесь расходом на объект (по умолчанию —
деньги компании), с чеком или без. Вносит HEAD — сразу «принято»; остальные — на проверку HEAD.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import constants as consts
from . import db, drive
from .gip import can_crew
from .work import CLOSED, TZ, active, is_trip, self_approve, with_receipt

router = APIRouter(prefix="/api")
ITEMS = [("lodging", "Проживание"), ("trip_road", "Дорога (билеты, бензин)"), ("trip_local", "Транспорт на месте"), ("trip_other", "Прочее")]
CODES = {c for c, _ in ITEMS}
TRIP_BY = {"mop", "mop_vip", "head"}


def can_trip(conn, p: dict, oid: int) -> bool:
    return not p.get("_view_as") and (p["role_code"] in TRIP_BY or can_crew(conn, p, oid))


def retrip(conn, oid: int) -> int:
    """Командировка смен объекта с 1.11 — заново по отметке/городу (питание в ФОТ считается по shifts.trip)."""
    n = 0
    for s in conn.execute("""SELECT id, person_id, trip FROM shifts WHERE object_id=%s AND status <> 'cancelled'
                             AND started_at >= '2026-11-01'""", (oid,)).fetchall():
        t = is_trip(conn, s["person_id"], oid)
        if t != s["trip"]:
            conn.execute("UPDATE shifts SET trip=%s WHERE id=%s", (t, s["id"]))
            n += 1
    return n


def summary(conn, oid: int, p: dict) -> dict:
    o = conn.execute("SELECT id, city, trip FROM objects WHERE id=%s AND id<>0", (oid,)).fetchone()
    if not o:
        raise HTTPException(404, "объекта ещё нет в приложении")
    costs = [with_receipt(e) for e in conn.execute(
        """SELECT e.id, e.category, c.title AS category_title, e.amount, e.paid_by, e.note, e.status, e.created_at,
                  e.receipt_file_id, pe.full_name AS person
           FROM expenses e JOIN expense_categories c ON c.code=e.category JOIN people pe ON pe.id=e.person_id
           WHERE e.object_id=%s AND e.category = ANY(%s) AND e.status <> 'cancelled' ORDER BY e.created_at DESC""",
        (oid, sorted(CODES))).fetchall()]
    food_rate = consts.latest(conn).get("pay.trip_food") or 0
    days = conn.execute("""SELECT pe.full_name, count(DISTINCT (s.started_at AT TIME ZONE 'Asia/Almaty')::date) AS d
                           FROM shifts s JOIN people pe ON pe.id=s.person_id
                           WHERE s.object_id=%s AND s.trip AND s.status IN ('submitted','approved') GROUP BY pe.full_name
                           ORDER BY pe.full_name""", (oid,)).fetchall()
    food_days = sum(int(x["d"]) for x in days)
    live = [c for c in costs if c["status"] != "rejected"]
    return {"id": oid, "city": o["city"], "trip": o["trip"], "on": any(True for _ in days) if o["trip"] is None else bool(o["trip"]),
            "can_edit": can_trip(conn, p, oid), "items": [{"code": c, "title": t} for c, t in ITEMS], "costs": costs,
            "food": {"rate": food_rate, "days": food_days, "amount": food_days * food_rate, "people": days},
            "total": sum(float(c["amount"]) for c in live) + food_days * food_rate}


@router.get("/objects/{oid}/trip-costs")
def trip_costs(oid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return summary(conn, oid, p)


class TripSetIn(BaseModel):
    trip: bool | None = None


@router.post("/objects/{oid}/trip-set")
def trip_set(oid: int, b: TripSetIn, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        if not can_trip(conn, p, oid):
            raise HTTPException(403, "командировку отмечают ГИП, главные, МОП и HEAD")
        if (conn.execute("SELECT closed_at FROM objects WHERE id=%s", (oid,)).fetchone() or {}).get("closed_at"):
            raise HTTPException(400, CLOSED)
        if not conn.execute("UPDATE objects SET trip=%s WHERE id=%s AND id<>0 RETURNING id", (b.trip, oid)).fetchone():
            raise HTTPException(404, "объекта ещё нет в приложении")
        n = retrip(conn, oid)
        db.audit(conn, p["id"], "object_trip", "objects", oid, {"trip": b.trip, "shifts": n})
        return {**summary(conn, oid, p), "retrip": n}


class CostIn(BaseModel):
    client_uid: UUID
    item: str
    amount: float = Field(gt=0, le=100_000_000)
    note: str | None = Field(default=None, max_length=300)
    paid_by: str = "company"
    receipt: str | None = Field(default=None, max_length=8_000_000)


@router.post("/objects/{oid}/trip-costs")
def trip_cost_add(oid: int, b: CostIn, p: dict = Depends(active)):
    if b.item not in CODES or b.paid_by not in ("own", "company"):
        raise HTTPException(400, "bad item")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT id FROM expenses WHERE client_uid=%s", (b.client_uid,)).fetchone()
        if dup:
            return summary(conn, oid, p)
        if not can_trip(conn, p, oid):
            raise HTTPException(403, "расходы командировки вносят ГИП, главные, МОП и HEAD")
        o = conn.execute("SELECT closed_at FROM objects WHERE id=%s AND id<>0", (oid,)).fetchone()
        if not o:
            raise HTTPException(404, "объекта ещё нет в приложении")
        if o["closed_at"]:
            raise HTTPException(400, CLOSED)
        fid = None
        if b.receipt:
            if not b.receipt.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
                raise HTTPException(400, "Чек — фото jpeg или png")
            name = f"Чек {datetime.now(TZ):%Y-%m-%d %H-%M} {p['full_name']} {b.amount:.0f}"
            try:
                drive_id = drive.save_receipt(conn, "mural", name, b.receipt, deal_id=oid)
            except Exception as ex:  # Диск недоступен
                raise HTTPException(502, f"drive: {ex.__class__.__name__}")
            data, mime = drive.decode_data_url(b.receipt)
            fid = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                                  VALUES (gen_random_uuid(), %s, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                               (oid, name, mime, len(data), drive_id, p["id"])).fetchone()["id"]
        row = conn.execute("""INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, note, receipt_file_id)
                              VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s) RETURNING *""",
                           (b.client_uid, p["id"], oid, b.item, b.amount, b.paid_by, b.note, fid)).fetchone()
        self_approve(conn, p, row)
        db.audit(conn, p["id"], "trip_cost_add", "expenses", row["id"], {"object": oid, "item": b.item})
        return summary(conn, oid, p)
