"""Чат проекта (HEAD «да» 13.11: «чат проекта нужен и должен создаваться в проекте»).

Создаётся сам: у каждой сделки на «Выполнении проекта» (и на «Оплата+закрывающие») есть чат, кнопка «Чат проекта» —
в карточке проекта; в «Чате» — раздел «Проекты». Участники считаются на лету: назначенные на объект (object_crew),
ГИП объекта, МОП сделки (ответственный в Битриксе → people.bitrix_user_id) и все HEAD. Сняли с объекта — выпал.
Сделка ушла дальше — чат остаётся, только для чтения. Фото из чата ложится в папку сделки (МЕДИА / Отчёты), как фото
с объекта. Бот молчит (как о личных сообщениях): новое видно в приложении — цифра на вкладке «Чат».
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .viewas import ctx
from .work import active

router = APIRouter(prefix="/api/pchat")
OPEN = ("UC_AV00QK", "UC_BMKDS4")
MAX = 4000

# участник объекта o (o — алиас objects) для человека %(me)s
MEMBER = """(EXISTS (SELECT 1 FROM object_crew c WHERE c.object_id=o.id AND c.person_id=%(me)s)
             OR o.gip_person_id=%(me)s
             OR o.mop_bx_id IS NOT NULL AND o.mop_bx_id = (SELECT bitrix_user_id FROM people WHERE id=%(me)s))"""


def _head(p: dict) -> bool:
    return p["role_code"] == "head"   # «смотрит как» — p уже человек, которого смотрят


def _visible(p: dict) -> str:
    """Какие чаты видны: открытые — участнику (HEAD — все); закрытые — если в них успели написать."""
    who = "true" if _head(p) else MEMBER
    return f"""o.id <> 0 AND {who}
               AND (o.bitrix_stage = ANY(%(open)s) OR EXISTS (SELECT 1 FROM proj_msg m WHERE m.object_id=o.id))"""


def unread(conn, p: dict) -> int:
    return conn.execute(f"""SELECT count(*) AS n FROM objects o JOIN proj_msg m ON m.object_id=o.id
                            LEFT JOIN proj_read r ON r.object_id=o.id AND r.person_id=%(me)s
                            WHERE {_visible(p)} AND m.author_id<>%(me)s AND m.id > coalesce(r.last_id, 0)""",
                        {"me": p["id"], "open": list(OPEN)}).fetchone()["n"]


def chats(conn, p: dict) -> list[dict]:
    return conn.execute(
        f"""SELECT * FROM (SELECT o.id, o.title, o.city, o.bitrix_stage = ANY(%(open)s) AS open,
                   l.text AS last_text, l.file_id IS NOT NULL AS last_photo, l.name AS last_name, l.created_at AS last_at,
                   (SELECT count(*) FROM proj_msg u WHERE u.object_id=o.id AND u.author_id<>%(me)s
                       AND u.id > coalesce((SELECT last_id FROM proj_read r WHERE r.object_id=o.id AND r.person_id=%(me)s), 0)) AS unread
            FROM objects o
            LEFT JOIN LATERAL (SELECT m.text, m.file_id, m.created_at, pe.full_name AS name FROM proj_msg m
                               JOIN people pe ON pe.id=m.author_id WHERE m.object_id=o.id
                               ORDER BY m.id DESC LIMIT 1) l ON true
            WHERE {_visible(p)}) t
            ORDER BY unread > 0 DESC, open DESC, last_at DESC NULLS LAST, id DESC""",
        {"me": p["id"], "open": list(OPEN)}).fetchall()


def _obj(conn, oid: int, p: dict) -> dict:
    o = conn.execute(f"SELECT o.id, o.title, o.city, o.bitrix_stage = ANY(%(open)s) AS open FROM objects o WHERE o.id=%(oid)s AND {_visible(p)}",
                     {"me": p["id"], "oid": oid, "open": list(OPEN)}).fetchone()
    if not o:
        raise HTTPException(404, "чат проекта недоступен")
    return o


def members(conn, oid: int) -> list[dict]:
    return conn.execute(
        """SELECT pe.id, pe.full_name, r.title AS role_title, x.why FROM (
               SELECT c.person_id AS id, 'crew' AS why FROM object_crew c WHERE c.object_id=%(o)s
               UNION SELECT o.gip_person_id, 'gip' FROM objects o WHERE o.id=%(o)s AND o.gip_person_id IS NOT NULL
               UNION SELECT pe.id, 'mop' FROM objects o JOIN people pe ON pe.bitrix_user_id=o.mop_bx_id WHERE o.id=%(o)s
               UNION SELECT id, 'head' FROM people WHERE role_code='head') x
           JOIN people pe ON pe.id=x.id LEFT JOIN roles r ON r.code=pe.role_code
           WHERE pe.status='active' AND pe.tg_id > 0
           ORDER BY x.why='head', pe.full_name""", {"o": oid}).fetchall()


@router.get("/list")
def api_list(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {"chats": chats(conn, p)}


@router.get("/{oid}")
def api_chat(oid: int, p: dict = Depends(active)):
    from .files import sign
    with db.pool.connection() as conn:
        o = _obj(conn, oid, p)
        rows = conn.execute("""SELECT m.id, m.author_id, pe.full_name AS name, pe.role_code, m.text, m.file_id, m.created_at
                               FROM proj_msg m JOIN people pe ON pe.id=m.author_id WHERE m.object_id=%s ORDER BY m.id""", (oid,)).fetchall()
        mem = {}
        for m in members(conn, oid):   # один человек может быть и ГИП, и в бригаде — роль в чате берём первую
            mem.setdefault(m["id"], m)
        if rows and not ctx():   # HEAD «смотрит как» — прочтение за сотрудника не отмечаем
            conn.execute("""INSERT INTO proj_read (object_id, person_id, last_id) VALUES (%s,%s,%s)
                            ON CONFLICT (object_id, person_id) DO UPDATE SET last_id=GREATEST(proj_read.last_id, EXCLUDED.last_id)""",
                         (oid, p["id"], rows[-1]["id"]))
    items = [{"id": r["id"], "mine": r["author_id"] == p["id"], "name": r["name"], "head": r["role_code"] == "head",
              "text": r["text"], "created_at": r["created_at"],
              "photo": {"thumb": sign(r["file_id"], "thumb"), "url": sign(r["file_id"], "content")} if r["file_id"] else None}
             for r in rows]
    return {"object": o, "members": list(mem.values()), "items": items}


class MsgIn(BaseModel):
    text: str | None = Field(default=None, max_length=MAX)
    photo: str | None = None          # data:image/jpeg;base64,… (сжато на телефоне)
    client_uid: UUID | None = None


@router.post("/{oid}")
def api_write(oid: int, b: MsgIn, p: dict = Depends(active)):
    text = (b.text or "").strip() or None
    if not text and not b.photo:
        raise HTTPException(400, "пустое сообщение")
    with db.pool.connection() as conn, conn.transaction():
        o = _obj(conn, oid, p)
        if not o["open"]:
            raise HTTPException(409, "проект ушёл с «Выполнения» — чат только для чтения")
        fid = None
        if b.photo:
            from uuid import uuid4

            from .files import get_object, store_photo
            fid = store_photo(conn, p, get_object(conn, oid), b.client_uid or uuid4(), b.photo, "чат проекта")["id"]
        row = conn.execute("INSERT INTO proj_msg (object_id, author_id, text, file_id) VALUES (%s,%s,%s,%s) RETURNING id, created_at",
                           (oid, p["id"], text, fid)).fetchone()
        conn.execute("""INSERT INTO proj_read (object_id, person_id, last_id) VALUES (%s,%s,%s)
                        ON CONFLICT (object_id, person_id) DO UPDATE SET last_id=EXCLUDED.last_id""", (oid, p["id"], row["id"]))
        db.audit(conn, p["id"], "proj_msg_add", "proj_msg", row["id"], {"object": oid, "photo": bool(fid)})
    return {"id": row["id"], "created_at": row["created_at"]}
