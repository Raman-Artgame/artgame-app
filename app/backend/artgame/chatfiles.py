"""Вложения в чатах (HEAD 24.11: «в чаты нужно добавить функцию прикрепления файлов и фото»).

Файл или фото к сообщению в чате «HEAD», личном чате и чате проекта. Лежат в базе (chat_files), до 20 МБ:
личную переписку на общий Диск не кладём. Ссылки подписаны и живут 12 часов, как у файлов проекта.
Картинки, PDF, видео и звук открываются в приложении; всё остальное только скачивается (чужой html с нашего адреса
не запускаем).
"""
import base64
import hashlib
import hmac
import io
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from . import db
from .files import TTL, _key

router = APIRouter(prefix="/api/chatfiles")
MAX_FILE = 20 * 1024 * 1024
TOO_BIG = "Файл больше 20 МБ. Большое видео или макет положи в папку проекта и пришли ссылку."
INLINE = re.compile(r"^(image/(jpeg|png|webp|gif)|application/pdf|video/[\w.+-]+|audio/[\w.+-]+)$")
HEAD_RE = re.compile(r"^data:([\w.+-]+/[\w.+-]+)?(;[\w=.+-]+)*;base64$")


class FileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    data: str = Field(min_length=10, max_length=MAX_FILE * 4 // 3 + 400)   # data:<тип>;base64,…


def _sign(fid: int, what: str) -> str:
    exp = int(time.time() + TTL)
    sig = hmac.new(_key(), f"chat:{fid}:{what}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"/api/chatfiles/{fid}/{what}?exp={exp}&sig={sig}"


def _check(fid: int, what: str, exp: int, sig: str) -> None:
    good = hmac.new(_key(), f"chat:{fid}:{what}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    if exp < time.time() or not hmac.compare_digest(good, sig):
        raise HTTPException(403, "link expired")


def _thumb(data: bytes) -> bytes | None:
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(data))
        if im.width * im.height > 60_000_000:
            return None
        im = ImageOps.exif_transpose(im)
        im.thumbnail((640, 640))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=78)
        return out.getvalue()
    except Exception:   # noqa: BLE001 — не картинка или битая: будет значок файла
        return None


def save(conn, p: dict, f: FileIn, client_uid) -> tuple[int, bool]:
    """Кладёт вложение. Возвращает (id, было ли уже) — повтор с тем же client_uid второй файл не создаёт."""
    dup = conn.execute("SELECT id FROM chat_files WHERE client_uid=%s", (client_uid,)).fetchone()
    if dup:
        return dup["id"], True
    head, _, b64 = f.data.partition(",")
    m = HEAD_RE.match(head)
    if not m or not b64:
        raise HTTPException(400, "Файл не прочитался, выбери его ещё раз")
    try:
        data = base64.b64decode(b64, validate=True)
    except Exception:   # noqa: BLE001
        raise HTTPException(400, "Файл не прочитался, выбери его ещё раз")
    if not data:
        raise HTTPException(400, "Файл пустой")
    if len(data) > MAX_FILE:
        raise HTTPException(413, TOO_BIG)
    mime = (m.group(1) or "application/octet-stream").lower()
    name = re.sub(r"[\x00-\x1f/\\]", " ", f.name).strip()[:200] or "файл"
    thumb = _thumb(data) if mime.startswith("image/") else None
    fid = conn.execute("""INSERT INTO chat_files (client_uid, name, mime, size, data, thumb, uploaded_by)
                          VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (client_uid, name, mime, len(data), data, thumb, p["id"])).fetchone()["id"]
    return fid, False


# поля вложения для запросов лент: LEFT JOIN chat_files cf ON cf.id=<сообщение>.att_id
COLS = "cf.id AS att_id, cf.name AS att_name, cf.mime AS att_mime, cf.size AS att_size, cf.thumb IS NOT NULL AS att_thumb"


def pack(row: dict) -> dict:
    """Строка ленты с полями COLS → та же строка с file: {name, size, mime, url, thumb}."""
    r = dict(row)
    a = {k: r.pop("att_" + k, None) for k in ("id", "name", "mime", "size", "thumb")}
    r["file"] = {"name": a["name"], "mime": a["mime"], "size": a["size"], "url": _sign(a["id"], "content"),
                 "thumb": _sign(a["id"], "thumb") if a["thumb"] else None} if a["id"] else None
    return r


@router.get("/{fid}/content")
def content(fid: int, exp: int, sig: str, dl: int = 0):
    _check(fid, "content", exp, sig)
    with db.pool.connection() as conn:
        f = conn.execute("SELECT name, mime, data FROM chat_files WHERE id=%s", (fid,)).fetchone()
    if not f:
        raise HTTPException(404)
    inline = not dl and INLINE.match(f["mime"])
    ascii_name = f["name"].encode("ascii", "ignore").decode().replace('"', "") or "file"
    disp = f'{"inline" if inline else "attachment"}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(f["name"])}'
    return Response(bytes(f["data"]), media_type=f["mime"] if inline else "application/octet-stream",
                    headers={"Content-Disposition": disp, "Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.get("/{fid}/thumb")
def thumb(fid: int, exp: int, sig: str):
    _check(fid, "thumb", exp, sig)
    with db.pool.connection() as conn:
        f = conn.execute("SELECT thumb FROM chat_files WHERE id=%s", (fid,)).fetchone()
    if not f or not f["thumb"]:
        raise HTTPException(404)
    return Response(bytes(f["thumb"]), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
