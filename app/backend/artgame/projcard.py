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
