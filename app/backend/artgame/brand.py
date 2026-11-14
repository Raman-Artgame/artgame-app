"""«Бренд» (HEAD 14.11): книга бренда и паки — прямо из приложения, без доступа к Диску.

Показываем папку «06 МАРКЕТИНГ / 01 Бренд» как есть: папки и файлы. Только чтение и скачивание. Ссылку на файл сервер
подписывает лишь для того, что сам показал в списке, поэтому чужой файл с Диска по этой дороге не достать.
"""
import hashlib
import hmac
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from . import drive
from .files import TTL, _key, _range
from .work import active

router = APIRouter(prefix="/api")
SEE = {"marketer", "head", "lead_designer", "designer"}
BRAND_ID = "1jQ0ZXK6O0GXT3XESr3XVNAvCJLcNVzYv"   # «06 МАРКЕТИНГ / 01 Бренд» на диске ARTGAME.KZ
PARENT: dict[str, tuple[str, str]] = {}          # папка → (родитель, название): только то, что показали сами


def _sign(drive_id: str, what: str) -> str:
    exp = int(time.time() + TTL)
    sig = hmac.new(_key(), f"brand:{drive_id}:{what}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"/api/mkt/brand/{what}/{drive_id}?exp={exp}&sig={sig}"


def _check(drive_id: str, what: str, exp: int, sig: str):
    good = hmac.new(_key(), f"brand:{drive_id}:{what}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    if exp < time.time() or not hmac.compare_digest(good, sig):
        raise HTTPException(403, "link expired")


def _inside(d, folder: str) -> list[dict]:
    """Путь от «Бренд» до папки; чужая папка — 404. После перезапуска сервера путь восстанавливаем по родителям на Диске."""
    path, cur = [], folder
    for _ in range(8):
        if cur == BRAND_ID:
            return path[::-1]
        if cur not in PARENT:
            m = d.meta(cur)
            if m.get("mimeType") != drive.FOLDER or not m.get("parents"):
                break
            PARENT[cur] = (m["parents"][0], m.get("name") or "Папка")
        path.append({"id": cur, "name": PARENT[cur][1]})
        cur = PARENT[cur][0]
    raise HTTPException(404, "нет такой папки в «Бренде»")


@router.get("/mkt/brand")
def brand(folder: str | None = None, p: dict = Depends(active)):
    if p["role_code"] not in SEE:
        raise HTTPException(403, "«Бренд» — у маркетинга, дизайна и HEAD")
    folder = folder or BRAND_ID
    try:
        d = drive.Drive()
        path = _inside(d, folder)
        rows = d.ls(folder)
    except HTTPException:
        raise
    except Exception as ex:
        raise drive.fail(ex)
    folders, files = [], []
    for r in sorted(rows, key=lambda x: x["name"].lower()):
        mime = r.get("mimeType") or ""
        if mime == drive.FOLDER:
            PARENT[r["id"]] = (folder, r["name"])
            folders.append({"id": r["id"], "name": r["name"]})
        elif not mime.startswith("application/vnd.google-apps."):   # документы Google файлом не отдать
            files.append({"id": r["id"], "name": r["name"], "mime": mime, "size": int(r.get("size") or 0), "url": _sign(r["id"], "file"),
                          "thumb": _sign(r["id"], "thumb") if mime.startswith(("image/", "video/")) or mime == "application/pdf" else None})
    return {"path": path, "folders": folders, "files": files}


@router.get("/mkt/brand/file/{drive_id}")
def brand_file(drive_id: str, exp: int, sig: str, request: Request, dl: int = 0):
    _check(drive_id, "file", exp, sig)
    try:
        d = drive.Drive()
        m = d.meta(drive_id)
    except Exception as ex:
        raise drive.fail(ex)
    name, size, mime = m.get("name") or "file", int(m.get("size") or 0), m.get("mimeType") or "application/octet-stream"
    ascii_name = name.encode("ascii", "ignore").decode().replace('"', "") or "file"
    hdr = {"Content-Disposition": f'{"attachment" if dl else "inline"}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}',
           "Cache-Control": "private, max-age=3600", "Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
    if mime in ("text/html", "image/svg+xml", "application/xhtml+xml"):   # не исполнять чужую разметку на нашем адресе
        mime, hdr["Content-Disposition"] = "application/octet-stream", hdr["Content-Disposition"].replace("inline", "attachment")
    rng = _range(request.headers.get("range"), size)
    if rng:
        a, b = rng
        return StreamingResponse(d.stream(drive_id, f"bytes={a}-{b}"), status_code=206, media_type=mime,
                                 headers={**hdr, "Content-Range": f"bytes {a}-{b}/{size}", "Content-Length": str(b - a + 1)})
    return StreamingResponse(d.stream(drive_id), media_type=mime, headers=hdr)


@router.get("/mkt/brand/thumb/{drive_id}")
def brand_thumb(drive_id: str, exp: int, sig: str):
    _check(drive_id, "thumb", exp, sig)
    data = drive.Drive().thumbnail(drive_id)
    if data is None:
        raise HTTPException(404, "no thumbnail")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
