"""«Выдано и допуски» (HEAD 08.11): что у человека на руках — ключи, одежда, инструмент, доступы — и допуски ТБ.

Выдаёт HEAD; допуски к оборудованию — ещё Главный художник, Художник-Про и Мастер печати (кто допускает — «База знаний», ТБ).
Человек видит своё в кабинете и нажимает «Получил». Возврат и «утеряно» отмечает выдавший или HEAD. Ничего не удаляется.
Пароли и коды сюда не пишем — только факт: «доступ к … выдан».
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .work import active

router = APIRouter(prefix="/api")
KINDS = {"key": "Ключи", "clothes": "Одежда", "tool": "Инструмент", "access": "Доступы", "permit": "Допуски", "other": "Другое"}
PERMIT_BY = {"lead_artist", "artist_pro", "print_master"}


def _can_issue(p: dict, kind: str) -> bool:
    return p["role_code"] == "head" or (kind == "permit" and p["role_code"] in PERMIT_BY)


SQL = """SELECT i.*, ib.full_name AS issued_by_name FROM person_items i JOIN people ib ON ib.id=i.issued_by
         WHERE i.person_id=%s ORDER BY i.status='issued' DESC, i.kind, i.issued_at DESC"""


@router.get("/items/my")
def my_items(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {"items": conn.execute(SQL, (p["id"],)).fetchall(), "kinds": KINDS}


@router.get("/people/{person_id}/items")
def person_items(person_id: int, p: dict = Depends(active)):
    if p["role_code"] != "head" and p["role_code"] not in PERMIT_BY:
        raise HTTPException(403)
    with db.pool.connection() as conn:
        return {"items": conn.execute(SQL, (person_id,)).fetchall(), "kinds": KINDS}


class ItemIn(BaseModel):
    kind: str
    title: str = Field(min_length=2, max_length=200)
    qty: int = Field(default=1, ge=1, le=1000)
    note: str | None = Field(default=None, max_length=500)


@router.post("/people/{person_id}/items")
def issue(person_id: int, b: ItemIn, p: dict = Depends(active)):
    if b.kind not in KINDS:
        raise HTTPException(400, "bad kind")
    if not _can_issue(p, b.kind):
        raise HTTPException(403, "выдаёт HEAD; допуски — Главный, Про, Мастер печати")
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM people WHERE id=%s", (person_id,)).fetchone():
            raise HTTPException(404)
        row = conn.execute("""INSERT INTO person_items (person_id, kind, title, qty, note, issued_by) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                           (person_id, b.kind, b.title.strip(), b.qty, b.note, p["id"])).fetchone()
        db.audit(conn, p["id"], "item_issue", "person_items", row["id"], {"for": person_id, "kind": b.kind, "title": row["title"]})
        return row


@router.post("/items/{item_id}/ack")
def ack(item_id: int, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("UPDATE person_items SET ack_at=coalesce(ack_at, now()) WHERE id=%s AND person_id=%s RETURNING *",
                           (item_id, p["id"])).fetchone()
        if not row:
            raise HTTPException(404)
        db.audit(conn, p["id"], "item_ack", "person_items", item_id)
        return row


class CloseIn(BaseModel):
    status: str   # returned | lost


@router.post("/items/{item_id}/close")
def close(item_id: int, b: CloseIn, p: dict = Depends(active)):
    if b.status not in ("returned", "lost"):
        raise HTTPException(400)
    with db.pool.connection() as conn, conn.transaction():
        it = conn.execute("SELECT * FROM person_items WHERE id=%s FOR UPDATE", (item_id,)).fetchone()
        if not it:
            raise HTTPException(404)
        if p["role_code"] != "head" and it["issued_by"] != p["id"]:
            raise HTTPException(403, "закрывает выдавший или HEAD")
        if it["status"] != "issued":
            raise HTTPException(409, "уже закрыто")
        row = conn.execute("UPDATE person_items SET status=%s, closed_by=%s, closed_at=now() WHERE id=%s RETURNING *",
                           (b.status, p["id"], item_id)).fetchone()
        db.audit(conn, p["id"], "item_" + b.status, "person_items", item_id, {"for": it["person_id"], "title": it["title"]})
        return row
