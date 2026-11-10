"""Файлы объектов: фото, дизайн, документы, чеки. Хранятся на Диске, работа — только через приложение.

Кто видит: фото и дизайн — все активные; документы — HEAD, МОП, главные; чеки — HEAD и проверяющие (в расходах).
Кто грузит: фото — все; дизайн — зона «Дизайн» или HEAD; документы — HEAD, МОП, главные.
Ссылки на просмотр подписаны и живут 12 часов (картинке в <img> заголовок не передать).
"""
import hashlib
import hmac
import re
import time
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from . import db, drive
from .config import settings
from .work import active

router = APIRouter(prefix="/api")

DOC_ROLES = {"head", "mop", "mop_vip", "artist_pro", "lead_artist", "print_master", "lead_designer"}   # Про — выше Главного (HEAD 09.11)
KINDS = ("photo", "design", "doc", "media")
PROD = {"lead_artist", "artist_pro", "print_master", "lead_designer", "head"}   # «Продакшн» (HEAD 08.11; Главный дизайнер — 10.11)
TTL = 12 * 3600
MAX_PHOTO = 8_000_000
MAX_BIG = 2_000_000_000  # 2 ГБ на файл дизайна


def can_see(p: dict, kind: str) -> bool:
    if kind in ("photo", "design", "media"):
        return True
    if kind == "doc":
        return p["role_code"] in DOC_ROLES
    return p["role_code"] == "head"


def can_prod(p: dict) -> bool:
    """«Продакшн»: роль из PROD или переключатель «Оплачиваемые рилс» у человека (HEAD 09.11: Глеб)."""
    return p["role_code"] in PROD or bool(p.get("reels"))


def can_upload(p: dict, kind: str) -> bool:
    if kind == "photo":
        return True
    if kind == "design":
        return p["role_code"] == "head" or "design" in p["zones"]
    if kind == "media":
        return can_prod(p)
    return p["role_code"] in DOC_ROLES


def _key() -> bytes:
    return hashlib.sha256(b"artgame-files:" + settings.bot_token.encode()).digest()


def sign(file_id: int, what: str, now: float | None = None) -> str:
    exp = int((now or time.time()) + TTL)
    sig = hmac.new(_key(), f"{file_id}:{what}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"/api/files/{file_id}/{what}?exp={exp}&sig={sig}"


def check_sig(file_id: int, what: str, exp: int, sig: str):
    good = hmac.new(_key(), f"{file_id}:{what}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    if exp < time.time() or not hmac.compare_digest(good, sig):
        raise HTTPException(403, "link expired")


def links(f: dict) -> dict:
    out = {k: f.get(k) for k in ("id", "object_id", "kind", "name", "mime", "size", "note", "status", "created_at",
                                 "media_type", "review", "review_note")}
    out["by"] = f.get("by")
    if f["status"] == "ready":
        out["url"] = sign(f["id"], "content")
        out["thumb"] = sign(f["id"], "thumb") if (f["mime"] or "").startswith("image/") else None
    return out


def get_object(conn, object_id: int) -> dict:
    o = conn.execute("SELECT * FROM objects WHERE id=%s", (object_id,)).fetchone()
    if not o:
        raise HTTPException(404, "no object")
    if o["id"] == 0:  # «Офис / без объекта» — только для трат, своей папки на Диске нет (HEAD 08.11)
        raise HTTPException(400, "files need a deal")
    return o


@router.get("/objects")
def objects(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return conn.execute(
            """SELECT o.id, o.title, o.city, o.status,
                      count(f.id) FILTER (WHERE f.kind='photo')  AS photos,
                      count(f.id) FILTER (WHERE f.kind='design') AS designs
               FROM objects o LEFT JOIN files f ON f.object_id=o.id AND f.status='ready'
               WHERE o.status='active' AND o.id<>0 GROUP BY o.id ORDER BY o.id DESC""").fetchall()


@router.get("/objects/{object_id}/files")
def object_files(object_id: int, kind: str = "photo", p: dict = Depends(active)):
    if kind not in KINDS or not can_see(p, kind):
        raise HTTPException(403, "no access")
    with db.pool.connection() as conn:
        get_object(conn, object_id)
        rows = conn.execute("""SELECT f.*, pe.full_name AS by FROM files f JOIN people pe ON pe.id=f.uploaded_by
                               WHERE f.object_id=%s AND f.kind=%s AND f.status='ready' ORDER BY f.created_at DESC""",
                            (object_id, kind)).fetchall()
    return [links(f) for f in rows]


class PhotoIn(BaseModel):
    client_uid: UUID
    data: str = Field(max_length=MAX_PHOTO)
    note: str | None = None


def store_photo(conn, p: dict, obj: dict, client_uid, data_url: str, note: str | None = None) -> dict:
    """Фото с объекта → МЕДИА / Отчёты сделки + карточка файла. Повтор с тем же client_uid не создаёт дубль."""
    if not data_url.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "bad photo")
    dup = conn.execute("SELECT * FROM files WHERE client_uid=%s", (client_uid,)).fetchone()
    if dup:
        return dup
    data, mime = drive.decode_data_url(data_url)
    name = f"{obj['id']} {p['full_name']} {time.strftime('%Y-%m-%d %H-%M-%S')}" + (f" {note}" if note else "")
    try:
        drive_id = drive.save_photo(conn, obj, name, data_url, kind="photo")
    except Exception as ex:
        raise HTTPException(502, f"drive: {ex.__class__.__name__}")
    f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, note, uploaded_by)
                        VALUES (%s,%s,'photo',%s,%s,%s,%s,%s,%s) ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
                     (client_uid, obj["id"], name, mime, len(data), drive_id, note, p["id"])).fetchone()
    if not f:
        return conn.execute("SELECT * FROM files WHERE client_uid=%s", (client_uid,)).fetchone()
    db.audit(conn, p["id"], "file_add", "files", f["id"], {"kind": "photo", "object": obj["id"]})
    return f


@router.post("/objects/{object_id}/photos")
def add_photo(object_id: int, body: PhotoIn, p: dict = Depends(active)):
    """Фото с объекта: сжато на телефоне, может прийти из офлайн-очереди."""
    with db.pool.connection() as conn, conn.transaction():
        f = store_photo(conn, p, get_object(conn, object_id), body.client_uid, body.data, body.note)
        return links({**f, "by": p["full_name"]})


class UploadIn(BaseModel):
    client_uid: UUID
    kind: str
    media_type: str | None = None   # «Продакшн»: photo | video | reels
    name: str = Field(min_length=1, max_length=200)
    mime: str = "application/octet-stream"
    size: int = Field(gt=0, le=MAX_BIG)
    note: str | None = None


@router.post("/objects/{object_id}/uploads")
def start_upload(object_id: int, body: UploadIn, request: Request, p: dict = Depends(active)):
    """Большой файл (дизайн, документ, видео): сервер выдаёт ссылку, телефон грузит прямо в Google."""
    if body.kind not in KINDS or not can_upload(p, body.kind):
        raise HTTPException(403, "no access")
    media = body.kind == "media"
    if media and body.media_type not in ("photo", "video", "reels"):
        raise HTTPException(400, "bad media_type")
    origin = request.headers.get("origin") or settings.public_origin
    with db.pool.connection() as conn, conn.transaction():
        obj = get_object(conn, object_id)
        f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, note, status, uploaded_by, media_type, review)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,'uploading',%s,%s,%s) ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
                         (body.client_uid, object_id, body.kind, body.name, body.mime, body.size, body.note, p["id"],
                          body.media_type if media else None, "pending" if media else None)).fetchone()
        if not f:
            f = conn.execute("SELECT * FROM files WHERE client_uid=%s", (body.client_uid,)).fetchone()
            if f["status"] == "ready":
                return {"file_id": f["id"], "done": True}
        try:
            d = drive.Drive()
            url = d.resumable(drive.folder_of(conn, obj, body.kind, d, body.media_type), body.name, body.mime, body.size, origin)
        except Exception as ex:
            raise HTTPException(502, f"drive: {ex.__class__.__name__}")
        return {"file_id": f["id"], "upload_url": url}


class DoneIn(BaseModel):
    drive_id: str = Field(min_length=10, max_length=100)


@router.post("/files/{file_id}/done")
def finish_upload(file_id: int, body: DoneIn, p: dict = Depends(active)):
    """Телефон закончил загрузку. Сервер сверяет, что файл лёг в нужную папку и размер совпал."""
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT * FROM files WHERE id=%s AND uploaded_by=%s", (file_id, p["id"])).fetchone()
        if not f:
            raise HTTPException(404)
        if f["status"] == "ready":
            return links({**f, "by": p["full_name"]})
        obj = get_object(conn, f["object_id"])
        try:
            d = drive.Drive()
            m = d.meta(body.drive_id)
            folder = drive.folder_of(conn, obj, f["kind"], d, f.get("media_type"))
        except Exception as ex:
            raise HTTPException(502, f"drive: {ex.__class__.__name__}")
        if folder not in m.get("parents", []) or int(m.get("size", -1)) != f["size"]:
            raise HTTPException(400, "file mismatch")
        f = conn.execute("UPDATE files SET drive_id=%s, status='ready', mime=%s WHERE id=%s RETURNING *",
                         (body.drive_id, m.get("mimeType") or f["mime"], file_id)).fetchone()
        db.audit(conn, p["id"], "file_add", "files", file_id, {"kind": f["kind"], "object": f["object_id"]})
        return links({**f, "by": p["full_name"]})


@router.post("/files/{file_id}/archive")
def archive(file_id: int, p: dict = Depends(active)):
    """Убрать из ленты: автор или HEAD. На Диске файл остаётся."""
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("""UPDATE files SET status='archived' WHERE id=%s AND (uploaded_by=%s OR %s)
                              RETURNING id""", (file_id, p["id"], p["role_code"] == "head")).fetchone()
        if not row:
            raise HTTPException(403)
        db.audit(conn, p["id"], "file_archive", "files", file_id)
    return {"ok": True}


def _ready(file_id: int) -> dict:
    with db.pool.connection() as conn:
        f = conn.execute("SELECT * FROM files WHERE id=%s AND drive_id IS NOT NULL", (file_id,)).fetchone()
    if not f:
        raise HTTPException(404)
    return f


def _range(h: str | None, size: int) -> tuple[int, int] | None:
    """«bytes=a-b» / «bytes=a-» / «bytes=-n» → (a, b) включительно; чужое или кривое — None (отдаём целиком)."""
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", (h or "").strip())
    if not m or size <= 0 or (not m[1] and not m[2]):
        return None
    a, b = (int(m[1]), int(m[2]) if m[2] else size - 1) if m[1] else (max(0, size - int(m[2])), size - 1)
    return (a, min(b, size - 1)) if a <= b and a < size else None


@router.get("/files/{file_id}/content")
def content(file_id: int, exp: int, sig: str, request: Request, dl: int = 0):
    """Файл с Диска через сервер. dl=1 — скачать (attachment), иначе открыть в приложении; Range — для видео."""
    check_sig(file_id, "content", exp, sig)
    f = _ready(file_id)
    name = f["name"] or "file"
    ascii_name = name.encode("ascii", "ignore").decode().replace('"', "") or "file"
    disp = f'{"attachment" if dl else "inline"}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}'
    hdr = {"Content-Disposition": disp, "Cache-Control": "private, max-age=3600", "Accept-Ranges": "bytes"}
    size = int(f["size"] or 0)
    rng = _range(request.headers.get("range"), size)
    if rng:
        a, b = rng
        return StreamingResponse(drive.Drive().stream(f["drive_id"], f"bytes={a}-{b}"), status_code=206, media_type=f["mime"] or "application/octet-stream",
                                 headers={**hdr, "Content-Range": f"bytes {a}-{b}/{size}", "Content-Length": str(b - a + 1)})
    return StreamingResponse(drive.Drive().stream(f["drive_id"]), media_type=f["mime"] or "application/octet-stream", headers=hdr)


@router.get("/files/{file_id}/thumb")
def thumb(file_id: int, exp: int, sig: str):
    check_sig(file_id, "thumb", exp, sig)
    f = _ready(file_id)
    data = drive.Drive().thumbnail(f["drive_id"])
    if data is None:
        raise HTTPException(404, "no thumbnail")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
