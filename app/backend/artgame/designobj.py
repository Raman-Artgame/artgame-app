"""Дизайн в карточке проекта (HEAD 14.11): на любой стадии сделки основной воронки, в т. ч. ушедшей сразу на «Выполнение».

- Сложность XS–XL: Главный дизайнер или HEAD; S–XL пишется в поле сделки «Сложность дизайна», XS — только в приложении (design_sizes).
- «+ Дизайн / правка / докидка»: кто делал, размер, что сделано, ссылка → HEAD «утверждаю» → единицы design.unit.<размер>
  дизайнеру в месяце утверждения (тот же счёт, что и «УТВЕРЖДЕНО» в воронке «Дизайн РК»).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, bxw, db
from . import constants as consts
from .design import DESIGNERS, F_SIZE, SIZE_ENUM, ENUM_SIZE, SIZES, unit_of
from .work import active

router = APIRouter(prefix="/api")
EDIT = {"lead_designer", "head"}
KIND = {"design": "Дизайн проекта", "fix": "Правка / докидка"}


def _obj(conn, oid: int) -> dict:
    o = conn.execute("SELECT id, title FROM objects WHERE id=%s AND id<>0", (oid,)).fetchone()
    if not o:
        raise HTTPException(404, "Нет такого проекта")
    return o


def _rows(conn, oid: int) -> list[dict]:
    return conn.execute("""SELECT x.*, pe.full_name AS person_name, c.full_name AS by_name FROM design_extras x
                             JOIN people pe ON pe.id=x.person_id JOIN people c ON c.id=x.created_by
                            WHERE x.object_id=%s AND x.status<>'cancelled' ORDER BY x.id""", (oid,)).fetchall()


@router.get("/design/object/{oid}")
def get(oid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        _obj(conn, oid)
        local = conn.execute("SELECT size FROM design_sizes WHERE deal_id=%s", (oid,)).fetchone()
        size = (local or {}).get("size")
        if not size:
            try:
                d = bx.read("crm.deal.get", {"id": oid})
                size = ENUM_SIZE.get(str((d.get("result", d) if isinstance(d, dict) else {}).get(F_SIZE) or ""))
            except Exception:  # noqa: BLE001 — Битрикс недоступен: размер просто не показываем
                size = None
        v = consts.latest(conn)
        team = conn.execute("SELECT id, full_name FROM people WHERE status='active' AND role_code = ANY(%s) ORDER BY full_name",
                            (sorted(DESIGNERS),)).fetchall() if p["role_code"] in EDIT else []
        return {"size": size, "rows": _rows(conn, oid), "can_edit": p["role_code"] in EDIT, "can_decide": p["role_code"] == "head",
                "sizes": [{"code": s, "units": unit_of(v, s)} for s in SIZES], "team": team}


class SizeIn(BaseModel):
    size: str


@router.post("/design/object/{oid}/size")
def set_size(oid: int, b: SizeIn, p: dict = Depends(active)):
    if p["role_code"] not in EDIT:
        raise HTTPException(403, "Сложность ставят Главный дизайнер и HEAD")
    if b.size not in SIZES:
        raise HTTPException(400, "Размер: XS, S, M, L или XL")
    with db.pool.connection() as conn, conn.transaction():
        _obj(conn, oid)
        conn.execute("""INSERT INTO design_sizes (deal_id, size, set_by) VALUES (%s,%s,%s)
                        ON CONFLICT (deal_id) DO UPDATE SET size=EXCLUDED.size, set_by=EXCLUDED.set_by, set_at=now()""", (oid, b.size, p["id"]))
        db.audit(conn, p["id"], "design_size", "objects", oid, {"size": b.size})
    res = "local"
    if b.size in SIZE_ENUM and bxw.enabled():   # XS в Битриксе нет — только в приложении
        try:
            bxw.CALL("crm.deal.update", {"id": oid, "fields": {F_SIZE: SIZE_ENUM[b.size]}})
            bxw.CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": oid, "ENTITY_TYPE": "deal",
                                                             "COMMENT": f"{p['full_name']} (приложение): сложность дизайна {b.size.upper()}"}})
            bx._cache.clear()
            res = "ok"
        except Exception as ex:  # noqa: BLE001
            res = "error: " + str(ex)[:200]
    return {"ok": True, "bx": res}


class ExtraIn(BaseModel):
    kind: str
    size: str
    person_id: int
    note: str = Field(min_length=3, max_length=500)
    url: str | None = Field(default=None, max_length=500)


@router.post("/design/object/{oid}/extra")
def add(oid: int, b: ExtraIn, p: dict = Depends(active)):
    if p["role_code"] not in EDIT:
        raise HTTPException(403, "Вносят Главный дизайнер и HEAD")
    if b.kind not in KIND or b.size not in SIZES:
        raise HTTPException(400, "bad kind/size")
    with db.pool.connection() as conn, conn.transaction():
        o = _obj(conn, oid)
        if not conn.execute("SELECT 1 FROM people WHERE id=%s AND status='active' AND role_code = ANY(%s)", (b.person_id, sorted(DESIGNERS))).fetchone():
            raise HTTPException(400, "Исполнитель — дизайнер")
        row = conn.execute("""INSERT INTO design_extras (object_id, person_id, kind, size, note, url, created_by)
                              VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (oid, b.person_id, b.kind, b.size, b.note.strip(), (b.url or "").strip() or None, p["id"])).fetchone()
        if p["role_code"] == "head":   # внёс сам HEAD — сразу утверждено
            _decide(conn, row["id"], p, True, None)
        db.audit(conn, p["id"], "design_extra_add", "design_extras", row["id"], b.model_dump())
        head = conn.execute("SELECT tg_id FROM people WHERE role_code='head' AND status='active' ORDER BY id LIMIT 1").fetchone()
    if p["role_code"] != "head":
        try:
            from . import notify
            if head and head.get("tg_id"):
                notify.SEND(head["tg_id"], f"Дизайн на утверждение: {KIND[b.kind].lower()} {b.size.upper()} — №{oid} {o['title']}. "
                                           "Приложение → «Дизайн» → «Единицы».")
        except Exception as e:  # noqa: BLE001
            print("design extra notify:", e)
    return {"ok": True, "id": row["id"]}


def _decide(conn, xid: int, p: dict, ok: bool, reason: str | None) -> None:
    x = conn.execute("SELECT * FROM design_extras WHERE id=%s FOR UPDATE", (xid,)).fetchone()
    if not x or x["status"] != "sent":
        raise HTTPException(409, "Уже решено")
    units = unit_of(consts.latest(conn), x["size"]) if ok else 0
    conn.execute("UPDATE design_extras SET status=%s, units=%s, decided_by=%s, decided_at=now(), reason=%s WHERE id=%s",
                 ("approved" if ok else "returned", units, p["id"], reason, xid))


class DecideIn(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=300)


@router.post("/design/extra/{xid}/decide")
def decide(xid: int, b: DecideIn, p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "Утверждает HEAD")
    if not b.approve and not (b.reason or "").strip():
        raise HTTPException(400, "Напишите, что не так")
    with db.pool.connection() as conn, conn.transaction():
        _decide(conn, xid, p, b.approve, b.reason)
        db.audit(conn, p["id"], "design_extra_" + ("approved" if b.approve else "returned"), "design_extras", xid, b.model_dump())
    return {"ok": True}


@router.post("/design/extra/{xid}/cancel")
def cancel(xid: int, p: dict = Depends(active)):
    if p["role_code"] not in EDIT:
        raise HTTPException(403)
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("""UPDATE design_extras SET status='cancelled' WHERE id=%s AND (status IN ('sent','returned') OR %s)
                               RETURNING id""", (xid, p["role_code"] == "head")).fetchone():
            raise HTTPException(409, "Утверждённое снимает только HEAD")
        db.audit(conn, p["id"], "design_extra_cancel", "design_extras", xid)
    return {"ok": True}


def pending(conn) -> list[dict]:
    return conn.execute("""SELECT x.*, pe.full_name AS person_name, o.title AS object_title FROM design_extras x
                             JOIN people pe ON pe.id=x.person_id JOIN objects o ON o.id=x.object_id
                            WHERE x.status='sent' ORDER BY x.id""").fetchall()


def month_rows(conn, start, end, person_id: int | None = None) -> list[dict]:
    cond, args = ("", []) if person_id is None else (" AND x.person_id=%s", [person_id])
    return conn.execute(f"""SELECT x.*, pe.full_name AS person_name, o.title AS object_title FROM design_extras x
                              JOIN people pe ON pe.id=x.person_id JOIN objects o ON o.id=x.object_id
                             WHERE x.status='approved' AND x.decided_at >= %s AND x.decided_at < %s{cond} ORDER BY x.decided_at""",
                        [start, end, *args]).fetchall()
