"""ТЗ дизайнеру (HEAD 26.11 «все окей, давай начинаем работу»): вопрос дизайнера к МОП и бриф клиента по ссылке.

- «Вопрос МОП»: дизайнер пишет вопрос в задаче — она уходит в «Сбор информации», у МОП строка в «Сегодня».
  МОП отвечает в карточке сделки — задача возвращается в работу. Бот молчит.
- «Бриф клиенту ссылкой»: ссылку делает МОП (своей сделки) или дизайнер. Клиент открывает её без входа, отвечает кнопками
  (RU/ҚАЗ) и может приложить фото стены. Ответы ложатся в ту же задачу, фото — в «ДИЗАЙН / Фото объекта» сделки.
  По ссылке видно только название задачи; данных сделки, цен и условий оплаты там нет.
"""
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import bx, db, drive
from .config import settings
from .design import ALL, need
from .designtasks import ASK, SQL, _bitrix, _out, ensure_object
from .work import active

router = APIRouter(prefix="/api")

# Вопросы брифа клиента: ключ → сколько вариантов можно выбрать. Тексты и варианты — на странице (RU/ҚАЗ).
CLIENT_Q = {"place": 1, "where": 1, "who": 3, "mood": 3, "style": 3, "colors": 3}
CLIENT_TEXT = ("size", "idea", "must", "avoid", "name", "phone")
MAX_CLIENT_PHOTOS = 10
MAX_PHOTO = 8_000_000


class Text(BaseModel):
    text: str = Field(min_length=2, max_length=1000)


def _task(conn, tid: int, lock: bool = True) -> dict:
    t = conn.execute("SELECT * FROM design_tasks WHERE id=%s AND status='active'" + (" FOR UPDATE" if lock else ""), (tid,)).fetchone()
    if not t:
        raise HTTPException(404, "Нет такой задачи")
    return t


def _row(conn, tid: int, bitrix: bool = False) -> dict:
    r = conn.execute(SQL + " WHERE t.id=%s", (tid,)).fetchone()
    return {**_out(r), **({"bitrix": _bitrix(r["deal_id"])} if bitrix else {})}


@router.post("/design/tasks/{tid}/ask")
def ask(tid: int, b: Text, p: dict = Depends(active)):
    """Дизайнер спрашивает МОП: вопрос остаётся в задаче, задача — в «Сбор информации»."""
    need(p)
    with db.pool.connection() as conn, conn.transaction():
        t = _task(conn, tid)
        if p["role_code"] not in ALL and t["designer_id"] not in (None, p["id"]):
            raise HTTPException(403, "Это задача другого дизайнера")
        if t["stage"] == "done":
            raise HTTPException(400, "Задача уже утверждена")
        conn.execute("INSERT INTO design_task_msgs (task_id, person_id, kind, text) VALUES (%s,%s,'ask',%s)", (tid, p["id"], b.text.strip()))
        conn.execute("""UPDATE design_tasks SET stage='info', designer_id=coalesce(designer_id, %s), updated_at=now() WHERE id=%s""",
                     (p["id"] if p["role_code"] not in ALL else None, tid))
        db.audit(conn, p["id"], "design_task_ask", "design_tasks", tid, {"deal": t["deal_id"]})
        return _row(conn, tid, True)


@router.post("/bx/deals/{deal_id}/design-tasks/{tid}/answer")
def answer(deal_id: int, tid: int, b: Text, p: dict = Depends(active)):
    """МОП (или HEAD) отвечает дизайнеру из карточки сделки: задача возвращается в работу."""
    if p["role_code"] not in ASK:
        raise HTTPException(403, "Отвечают МОП и HEAD из карточки сделки")
    bx._deal(p, deal_id)
    with db.pool.connection() as conn, conn.transaction():
        t = _task(conn, tid)
        if t["deal_id"] != deal_id:
            raise HTTPException(404, "Нет такой задачи")
        conn.execute("INSERT INTO design_task_msgs (task_id, person_id, kind, text) VALUES (%s,%s,'answer',%s)", (tid, p["id"], b.text.strip()))
        if t["stage"] == "info":
            conn.execute("UPDATE design_tasks SET stage=%s, updated_at=now() WHERE id=%s", ("work" if t["designer_id"] else "new", tid))
        db.audit(conn, p["id"], "design_task_answer", "design_tasks", tid, {"deal": deal_id})
        return _row(conn, tid)


@router.post("/design/tasks/{tid}/brief-link")
def brief_link(tid: int, request: Request, p: dict = Depends(active)):
    """Ссылка на бриф для клиента: одна на задачу, повторный вызов отдаёт ту же. МОП — своей сделки, дизайнеры и HEAD — любой."""
    with db.pool.connection() as conn, conn.transaction():
        t = _task(conn, tid)
        if p["role_code"] in ASK:
            bx._deal(p, t["deal_id"])
        else:
            need(p)
        token = t["brief_token"]
        if not token:
            token = secrets.token_urlsafe(18)
            conn.execute("UPDATE design_tasks SET brief_token=%s, updated_at=now() WHERE id=%s", (token, tid))
            db.audit(conn, p["id"], "design_brief_link", "design_tasks", tid, {"deal": t["deal_id"]})
    origin = (request.headers.get("origin") or settings.public_origin).rstrip("/")
    return {"url": f"{origin}/?brief={token}"}


# ---------- страница клиента: без входа, по токену ----------

def _by_token(conn, token: str, lock: bool = False) -> dict:
    if not (16 <= len(token) <= 64):
        raise HTTPException(404, "Ссылка не найдена")
    t = conn.execute("SELECT * FROM design_tasks WHERE brief_token=%s AND status='active'" + (" FOR UPDATE" if lock else ""), (token,)).fetchone()
    if not t:
        raise HTTPException(404, "Ссылка не найдена")
    return t


@router.get("/brief/{token}")
def brief_get(token: str):
    with db.pool.connection() as conn:
        t = _by_token(conn, token)
    return {"title": t["title"], "answers": t["client_brief"] or {}, "done": bool(t["client_brief_at"])}


class BriefIn(BaseModel):
    answers: dict
    lang: str = "ru"


def clean_client(a: dict) -> dict:
    """Только известные вопросы; варианты и текст обрезаются — страница открыта без входа."""
    out: dict = {}
    for k, n in CLIENT_Q.items():
        v = a.get(k)
        v = [v] if isinstance(v, str) else v if isinstance(v, list) else []
        v = [str(x).strip()[:60] for x in v if isinstance(x, str) and x.strip()][:n]
        if v:
            out[k] = v
    for k in CLIENT_TEXT:
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:600]
    return out


@router.post("/brief/{token}")
def brief_post(token: str, b: BriefIn):
    ans = clean_client(b.answers)
    if not ans:
        raise HTTPException(400, "Ответьте хотя бы на один вопрос")
    ans["lang"] = "kk" if b.lang == "kk" else "ru"
    with db.pool.connection() as conn, conn.transaction():
        t = _by_token(conn, token, lock=True)
        if t["stage"] == "done":
            raise HTTPException(409, "Эскиз уже утверждён — напишите менеджеру")
        conn.execute("UPDATE design_tasks SET client_brief=%s, client_brief_at=now(), updated_at=now() WHERE id=%s", (Jsonb(ans), t["id"]))
        db.audit(conn, None, "design_brief_client", "design_tasks", t["id"], {"deal": t["deal_id"], "keys": sorted(ans)})
    return {"ok": True}


class PhotoIn(BaseModel):
    data: str = Field(max_length=MAX_PHOTO)


@router.post("/brief/{token}/photo")
def brief_photo(token: str, b: PhotoIn):
    """Фото стены от клиента: сжато на телефоне, ложится в «ДИЗАЙН / Фото объекта» сделки. Не больше десяти на задачу."""
    if not b.data.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "Нужно фото (JPEG или PNG)")
    with db.pool.connection() as conn, conn.transaction():
        t = _by_token(conn, token, lock=True)
        n = conn.execute("SELECT count(*) AS n FROM files WHERE object_id=%s AND kind='brief' AND note='от клиента'", (t["deal_id"],)).fetchone()["n"]
        if n >= MAX_CLIENT_PHOTOS:
            raise HTTPException(400, f"Достаточно {MAX_CLIENT_PHOTOS} фото — остальные отправьте менеджеру")
        ensure_object(conn, t["deal_id"])
        obj = conn.execute("SELECT * FROM objects WHERE id=%s", (t["deal_id"],)).fetchone()
        data, mime = drive.decode_data_url(b.data)
        name = f"{t['deal_id']} Фото от клиента {n + 1}"
        try:
            drive_id = drive.save_photo(conn, obj, name, b.data, kind="brief")
        except Exception as ex:
            raise drive.fail(ex)
        conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, note, uploaded_by)
                        VALUES (%s,%s,'brief',%s,%s,%s,%s,'от клиента',%s)""",
                     (uuid4(), t["deal_id"], name, mime, len(data), drive_id, t["created_by"]))
        db.audit(conn, None, "design_brief_photo", "design_tasks", t["id"], {"deal": t["deal_id"]})
    return {"ok": True, "n": n + 1}
