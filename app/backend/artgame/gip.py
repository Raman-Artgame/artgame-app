"""ГИП (куратор) проекта (HEAD 09.11): назначают HEAD и МОП в карточке проекта; ГИП видит по проекту всё — кто когда работал,
м², что сделал, фото, расходы с чеками — и принимает смены своего объекта («Проверка», work.review_filter по gip_person_id).
Объект без записи в objects (сделка ещё не синхронизирована) — назначить нельзя."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db
from .feedback import _send
from .work import active, more_photos, photos, with_receipt

router = APIRouter(prefix="/api")
GIP_ROLES = {"lead_artist", "artist_pro", "print_master"}
ASSIGN = {"head", "mop", "mop_vip"}
SEE_ALL = {"head", "artist_pro"}   # Про проверяет Главных — видит историю любого проекта


def can_see(conn, p: dict, oid: int) -> bool:
    if p["role_code"] in SEE_ALL:
        return True
    o = conn.execute("SELECT gip_person_id FROM objects WHERE id=%s", (oid,)).fetchone()
    return bool(o and o["gip_person_id"] == p["id"])


@router.get("/gip/candidates")
def candidates(p: dict = Depends(active)):
    if p["role_code"] not in ASSIGN:
        raise HTTPException(403, "назначают HEAD и МОП")
    with db.pool.connection() as conn:
        return conn.execute("""SELECT pe.id, pe.full_name, coalesce(pe.acting_role, pe.role_code) AS role_code, r.title AS role_title,
                                      pe.acting_role IS NOT NULL AS acting
                               FROM people pe JOIN roles r ON r.code = coalesce(pe.acting_role, pe.role_code)
                               WHERE pe.status='active' AND (pe.role_code = ANY(%s) OR pe.acting_role = ANY(%s)) ORDER BY pe.full_name""",
                            (list(GIP_ROLES), list(GIP_ROLES))).fetchall()


class GipIn(BaseModel):
    person_id: int = 0   # 0 — снять


@router.post("/objects/{oid}/gip")
def set_gip(oid: int, b: GipIn, p: dict = Depends(active)):
    if p["role_code"] not in ASSIGN or p.get("_view_as"):
        raise HTTPException(403, "назначают HEAD и МОП")
    with db.pool.connection() as conn, conn.transaction():
        o = conn.execute("SELECT id, title FROM objects WHERE id=%s", (oid,)).fetchone()
        if not o or not oid:
            raise HTTPException(404, "объекта ещё нет в приложении — он появится после синхронизации со сделкой")
        pe = None
        if b.person_id:
            pe = conn.execute("""SELECT id, tg_id, full_name FROM people WHERE id=%s AND status='active'
                                 AND (role_code = ANY(%s) OR acting_role = ANY(%s))""", (b.person_id, list(GIP_ROLES), list(GIP_ROLES))).fetchone()
            if not pe:
                raise HTTPException(400, "ГИП — Главный художник, Художник-Про или Мастер печати")
        conn.execute("UPDATE objects SET gip_person_id=%s WHERE id=%s", (pe["id"] if pe else None, oid))
        db.audit(conn, p["id"], "gip_set", "objects", oid, {"person": pe["id"] if pe else None})
    if pe:
        _send(pe["tg_id"], f"Ты ГИП проекта № {oid} «{o['title']}». В «Проектах» — вся история объекта, смены по нему принимаешь ты.")
    return {"ok": True, "gip_id": pe["id"] if pe else None, "gip_name": pe["full_name"] if pe else None}


@router.get("/objects/{oid}/history")
def history(oid: int, p: dict = Depends(active)):
    """Всё по проекту для ГИП: смены по людям (часы, м², что сделал, фото до/после, статус), расходы с чеками, итоги по людям."""
    with db.pool.connection() as conn:
        if not can_see(conn, p, oid):
            raise HTTPException(403, "историю проекта видят ГИП проекта, Художник-Про и HEAD")
        shifts = more_photos(conn, [photos(s) for s in conn.execute(
            """SELECT s.id, s.person_id, pe.full_name, s.role_code, s.zone_code, s.kind, s.started_at, s.ended_at, s.area_m2, s.work_done,
                      s.status, s.reason, s.backfill, s.photo_before, s.photo_after
               FROM shifts s JOIN people pe ON pe.id=s.person_id
               WHERE s.object_id=%s AND s.status <> 'cancelled' ORDER BY s.started_at DESC""", (oid,)).fetchall()])
        exps = [with_receipt(e) for e in conn.execute(
            """SELECT e.id, pe.full_name, c.title AS category, e.amount, e.paid_by, e.note, e.status, e.created_at, e.backfill, e.receipt_file_id
               FROM expenses e JOIN people pe ON pe.id=e.person_id LEFT JOIN expense_categories c ON c.code=e.category
               WHERE e.object_id=%s AND e.status <> 'cancelled' ORDER BY e.created_at DESC""", (oid,)).fetchall()]
    people = {}
    for s in shifts:
        if s["status"] == "rejected":
            continue
        x = people.setdefault(s["person_id"], {"name": s["full_name"], "shifts": 0, "m2": 0.0, "hours": 0.0})
        x["shifts"] += 1
        x["m2"] += float(s["area_m2"] or 0)
        if s["ended_at"]:
            x["hours"] += round((s["ended_at"] - s["started_at"]).total_seconds() / 3600, 1)
    return {"shifts": shifts, "expenses": exps, "people": sorted(people.values(), key=lambda x: -x["m2"]),
            "spent": sum(float(e["amount"]) for e in exps if e["status"] != "rejected")}
