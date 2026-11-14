"""Карточка проекта (HEAD 14.11, «одна вещь — в одном месте»): кто встречает на объекте и деньги проекта.

Контакт: имя видят все, телефон — ГИП объекта, МОП и HEAD; вносят они же. Деньги — только HEAD и МОП (свои сделки):
сумма, поступило, долг, затраты (как в паспорте закрытия) и маржа сейчас, а не только при закрытии. Оплаты вносятся в сделке.
"""
import sys
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, db, deal_money
from .marketing import MKT
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


# ---------- съёмки по проекту (HEAD 14.11): маркетолог предлагает, ГИП объекта подтверждает ----------
# Таблица mkt_shoots — общая с «Маркетинг → Съёмки». proposed — ждёт ГИП; «Подтверждаю» → planned;
# «Другая дата» — alt_date, статус остаётся proposed, маркетолог принимает дату (→ planned) или предлагает свою.

class ShootPropose(BaseModel):
    shoot_date: date
    at_time: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=2, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class ShootAnswer(BaseModel):
    ok: bool
    alt_date: date | None = None
    note: str | None = Field(default=None, max_length=500)


def _tell(conn, person_id: int | None, text: str) -> None:
    if not person_id:
        return
    r = conn.execute("SELECT tg_id FROM people WHERE id=%s AND status='active'", (person_id,)).fetchone()
    if r and r["tg_id"]:
        try:
            from .dm import SEND
            SEND(r["tg_id"], text)
        except Exception as e:  # noqa: BLE001 — бот недоступен: съёмка всё равно в карточке
            print("shoot notify:", e, file=sys.stderr)


def _shoot_obj(conn, oid: int) -> dict:
    o = conn.execute("SELECT id, title, gip_person_id FROM objects WHERE id=%s AND id<>0", (oid,)).fetchone()
    if not o:
        raise HTTPException(404, "Нет такого проекта")
    return o


@router.get("/objects/{oid}/shoots")
def obj_shoots(oid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        o = _shoot_obj(conn, oid)
        confirm = p["role_code"] == "head" or o["gip_person_id"] == p["id"]
        if not (confirm or p["role_code"] in MKT):
            raise HTTPException(403, "Съёмки видят маркетинг, ГИП и HEAD")
        rows = conn.execute("""SELECT s.id, s.title, s.shoot_date, s.at_time, s.note, s.status, s.alt_date, s.alt_note, s.confirmed_at,
                                      a.full_name AS author, c.full_name AS confirmed_name
                               FROM mkt_shoots s JOIN people a ON a.id=s.author_id LEFT JOIN people c ON c.id=s.confirmed_by
                               WHERE s.object_id=%s AND s.status<>'cancelled' ORDER BY s.shoot_date DESC, s.id DESC""", (oid,)).fetchall()
    return {"items": rows, "can_propose": p["role_code"] in MKT, "can_confirm": confirm, "gip": bool(o["gip_person_id"])}


@router.post("/objects/{oid}/shoots")
def obj_shoot_propose(oid: int, b: ShootPropose, p: dict = Depends(active)):
    if p["role_code"] not in MKT:
        raise HTTPException(403, "Съёмку предлагает маркетинг")
    with db.pool.connection() as conn, conn.transaction():
        o = _shoot_obj(conn, oid)
        st = "planned" if p["role_code"] == "head" else "proposed"   # HEAD ставит сразу
        r = conn.execute("""INSERT INTO mkt_shoots (title, shoot_date, at_time, object_id, note, status, author_id, confirmed_by, confirmed_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                         (b.title.strip(), b.shoot_date, b.at_time, oid, b.note, st, p["id"],
                          p["id"] if st == "planned" else None, datetime.now(timezone.utc) if st == "planned" else None)).fetchone()
        db.audit(conn, p["id"], "shoot_propose", "mkt_shoots", r["id"], {"object": oid, "date": str(b.shoot_date)})
        if st == "proposed":
            _tell(conn, o["gip_person_id"], f"🎥 {p['full_name']} предлагает съёмку на объекте «{o['title']}»: {b.shoot_date:%d.%m}"
                  f"{' ' + b.at_time if b.at_time else ''} — {b.title}. Подтвердите в карточке проекта.")
    return {"id": r["id"], "status": st}


def _shoot(conn, sid: int) -> dict:
    s = conn.execute("""SELECT s.*, o.gip_person_id, o.title AS object_title FROM mkt_shoots s JOIN objects o ON o.id=s.object_id
                        WHERE s.id=%s""", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Нет такой съёмки")
    return s


@router.post("/shoots/{sid}/answer")
def shoot_answer(sid: int, b: ShootAnswer, p: dict = Depends(active)):
    """ГИП объекта (или HEAD): «Подтверждаю» или «Другая дата» с датой и комментарием."""
    with db.pool.connection() as conn, conn.transaction():
        s = _shoot(conn, sid)
        if not (p["role_code"] == "head" or s["gip_person_id"] == p["id"]):
            raise HTTPException(403, "Съёмку подтверждает ГИП объекта")
        if s["status"] != "proposed":
            raise HTTPException(409, "Съёмка уже не ждёт ответа")
        if b.ok:
            conn.execute("""UPDATE mkt_shoots SET status='planned', confirmed_by=%s, confirmed_at=now(), alt_date=NULL, updated_at=now()
                            WHERE id=%s""", (p["id"], sid))
            text = f"✅ {p['full_name']} подтвердил съёмку «{s['title']}» {s['shoot_date']:%d.%m} на объекте «{s['object_title']}»."
        else:
            if not b.alt_date:
                raise HTTPException(400, "Укажите другую дату")
            conn.execute("UPDATE mkt_shoots SET alt_date=%s, alt_note=%s, updated_at=now() WHERE id=%s", (b.alt_date, b.note, sid))
            text = (f"📅 {p['full_name']} предлагает другую дату съёмки «{s['title']}»: {b.alt_date:%d.%m}"
                    f"{' — ' + b.note if b.note else ''}. Примите в карточке проекта.")
        db.audit(conn, p["id"], "shoot_answer", "mkt_shoots", sid, {"ok": b.ok, "alt": str(b.alt_date) if b.alt_date else None})
        _tell(conn, s["author_id"], text)
    return {"ok": True}


@router.post("/shoots/{sid}/accept")
def shoot_accept(sid: int, p: dict = Depends(active)):
    """Маркетинг принимает дату, которую предложил ГИП: съёмка в плане."""
    if p["role_code"] not in MKT:
        raise HTTPException(403, "Дату принимает маркетинг")
    with db.pool.connection() as conn, conn.transaction():
        s = _shoot(conn, sid)
        if s["status"] != "proposed" or not s["alt_date"]:
            raise HTTPException(409, "Другой даты нет")
        conn.execute("""UPDATE mkt_shoots SET status='planned', shoot_date=alt_date, alt_date=NULL, confirmed_by=%s, confirmed_at=now(),
                        updated_at=now() WHERE id=%s""", (s["gip_person_id"] or p["id"], sid))
        db.audit(conn, p["id"], "shoot_accept", "mkt_shoots", sid, {})
        _tell(conn, s["gip_person_id"], f"✅ Съёмка «{s['title']}» на объекте «{s['object_title']}» — {s['alt_date']:%d.%m}, как вы предложили.")
    return {"ok": True}
