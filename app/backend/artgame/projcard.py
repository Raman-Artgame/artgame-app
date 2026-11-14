"""Карточка проекта (HEAD 14.11, «одна вещь — в одном месте»): кто встречает на объекте и деньги проекта.

Контакт: имя видят все, телефон — ГИП объекта, МОП и HEAD; вносят они же. Деньги — только HEAD и МОП (свои сделки):
сумма, поступило, долг, затраты (как в паспорте закрытия) и маржа сейчас, а не только при закрытии. Оплаты вносятся в сделке.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, db, deal_money
from .work import active

router = APIRouter(prefix="/api")


def can_phone(p: dict, gip_id: int | None) -> bool:
    return p["role_code"] in bx.BX_ROLES or (gip_id is not None and gip_id == p["id"])


class ContactIn(BaseModel):
    name: str = Field("", max_length=120)
    phone: str = Field("", max_length=40)


@router.post("/objects/{oid}/contact")
def set_contact(oid: int, b: ContactIn, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        o = conn.execute("SELECT id, gip_person_id FROM objects WHERE id=%s AND id<>0", (oid,)).fetchone()
        if not o:
            raise HTTPException(404, "Нет такого проекта")
        if not can_phone(p, o["gip_person_id"]):
            raise HTTPException(403, "Контакт на объекте вносят ГИП, МОП и HEAD")
        name, phone = b.name.strip() or None, b.phone.strip() or None
        conn.execute("UPDATE objects SET site_contact=%s, site_phone=%s WHERE id=%s", (name, phone, oid))
        db.audit(conn, p["id"], "site_contact", "object", oid, {"name": name, "phone": bool(phone)})
    return {"name": name, "phone": phone}


@router.get("/objects/{oid}/money")
def money(oid: int, p: dict = Depends(active)):
    if p["role_code"] not in bx.BX_ROLES:
        raise HTTPException(403, "Деньги проекта видят HEAD и МОП")
    d = bx._deal(p, oid)
    from .closing import costs
    m = deal_money.card(d)
    opp = bx._money(d.get("OPPORTUNITY"))
    vat = deal_money._vat()
    net = round(opp / (1 + vat / 100), 2) if vat else opp
    with db.pool.connection() as conn:
        c = costs(conn, oid)
    profit = round(net - c["total"], 2)
    return {"sum": opp, "net": net, "vat_pct": vat, "received": m["received"], "debt": m["debt"], "on_check": m["on_check"],
            "overpaid": m["overpaid"], "costs": [{"key": g["key"], "title": g["title"], "total": g["total"]} for g in c["groups"]],
            "costs_total": c["total"], "profit": profit, "margin": round(profit / net * 100, 1) if net > 0 else None, "warn": c["warn"]}


# ---------- материалы и расходы на объект (HEAD 14.11, п. 6) ----------
# Сбор на объект (что взяли и вернули) + купленное по чекам на объект. Командировка — своим блоком рядом.
MAT_ROLES = {"head", "mop", "mop_vip", "lead_artist", "artist_pro", "print_master"}


@router.get("/objects/{oid}/materials")
def materials(oid: int, p: dict = Depends(active)):
    from .closing import TRIP
    from .kit import KIT, usage
    with db.pool.connection() as conn:
        o = conn.execute("SELECT id, gip_person_id FROM objects WHERE id=%s AND id<>0", (oid,)).fetchone()
        if not o:
            raise HTTPException(404, "Нет такого проекта")
        if p["role_code"] not in MAT_ROLES and o["gip_person_id"] != p["id"]:
            raise HTTPException(403, "Материалы проекта видят ГИП, главные, МОП и HEAD")
        kits = []
        for k in conn.execute("SELECT zone_code, items, status, updated_at FROM kit_lists WHERE object_id=%s ORDER BY zone_code", (oid,)).fetchall():
            it, z = k["items"] or {}, KIT[k["zone_code"]]
            names = {c: (t, u) for c, t, u in z["mat"]}
            u = usage(it) if k["status"] == "closed" else None
            rows = []
            if it.get("aerosol"):
                rows.append({"title": "Аэрозоль", "taken": sum(r.get("taken") or 0 for r in it["aerosol"]), "unit": "шт",
                             "used": u["aerosol_total"] if u else None})
            if it.get("facade") and (it["facade"].get("taken") or 0) > 0:
                rows.append({"title": "Фасадная краска", "taken": it["facade"]["taken"], "unit": "л", "used": u["facade_l"] if u else None})
            for c, r in (it.get("mat") or {}).items():
                if (r.get("taken") or 0) > 0 and c in names:
                    rows.append({"title": names[c][0], "taken": r["taken"], "unit": names[c][1], "used": u["mat"].get(c) if u else None})
            for r in it.get("extra") or []:
                if (r.get("taken") or 0) > 0:
                    rows.append({"title": r["title"], "taken": r["taken"], "unit": r.get("unit") or "шт", "used": None})
            took = sum(1 for r in (it.get("obr") or {}).values() if r.get("took"))
            kits.append({"zone": k["zone_code"], "closed": k["status"] == "closed", "rows": rows, "tools": took,
                         "lost": len(u["lost"]) if u else 0})
        buys = conn.execute("""SELECT e.id, c.title, e.amount, e.status, e.created_at, pe.full_name AS person, e.note
                               FROM expenses e JOIN expense_categories c ON c.code=e.category JOIN people pe ON pe.id=e.person_id
                               WHERE (e.object_id=%s OR e.deal_id=%s) AND e.status IN ('submitted','approved') AND NOT (e.category = ANY(%s))
                               ORDER BY e.created_at DESC""", (oid, oid, list(TRIP))).fetchall()
    return {"kits": kits, "buys": [{**b, "amount": float(b["amount"])} for b in buys],
            "buys_total": round(sum(float(b["amount"]) for b in buys if b["status"] == "approved"), 2)}


# ---------- строка маркетинга (HEAD 14.11, п. 7) ----------

class PublishIn(BaseModel):
    ok: bool | None = None


@router.get("/objects/{oid}/promo")
def promo(oid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        o = conn.execute("SELECT publish_ok FROM objects WHERE id=%s AND id<>0", (oid,)).fetchone()
        if not o:
            raise HTTPException(404, "Нет такого проекта")
        n = conn.execute("""SELECT count(*) FILTER (WHERE review='approved' AND coalesce(media_type,'photo')='photo') AS photo,
                                   count(*) FILTER (WHERE review='approved' AND media_type='video') AS video,
                                   count(*) FILTER (WHERE review='approved' AND media_type='reels') AS reels,
                                   count(*) FILTER (WHERE kind='media' AND review='pending') AS wait
                            FROM files WHERE object_id=%s AND status='ready' AND kind IN ('photo','media')""", (oid,)).fetchone()
    return {**n, "publish": o["publish_ok"], "can_set": p["role_code"] in bx.BX_ROLES}


@router.post("/objects/{oid}/publish")
def set_publish(oid: int, b: PublishIn, p: dict = Depends(active)):
    if p["role_code"] not in bx.BX_ROLES:
        raise HTTPException(403, "Разрешение клиента отмечают МОП и HEAD")
    with db.pool.connection() as conn:
        if not conn.execute("UPDATE objects SET publish_ok=%s WHERE id=%s AND id<>0 RETURNING id", (b.ok, oid)).fetchone():
            raise HTTPException(404, "Нет такого проекта")
        db.audit(conn, p["id"], "publish_ok", "object", oid, {"ok": b.ok})
    return {"publish": b.ok}
