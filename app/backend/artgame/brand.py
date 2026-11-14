"""«Бренд» (HEAD 14.11): книга бренда и паки — прямо из приложения, без доступа к Диску.

Показываем не папки Диска как есть, а полки по задачам (SHELVES). Только чтение и скачивание. Ссылку на файл сервер
подписывает лишь для того, что сам показал в списке, поэтому чужой файл с Диска по этой дороге не достать.
"""
import hashlib
import hmac
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from . import drive
from .brand_book import BOOK
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


TEAM = {"head", "lead_designer", "designer"}      # свои: видят исходники и полку «Печать»
READY = {"png", "jpg", "jpeg", "webp", "gif", "svg", "pdf", "mp4", "mov", "ttf", "otf", "woff", "woff2", "zip", "mp3", "wav", "cube", "lut"}
# Полки (HEAD 14.11: «в бренде помойка… нужны конкретные решения»): не папки Диска как есть, а паки по задачам.
# who: all — и агентство (только готовые к работе файлы, без исходников AI/PSD), team — дизайнеры и HEAD, head — только HEAD.
# Файлы на Диске не переезжают: полка — это список папок «06 МАРКЕТИНГ / 01 Бренд».
SHELVES = [
    {"key": "logo", "title": "Лого", "icon": "◆", "hint": "Знак и надпись. Берём только отсюда, не перерисовываем.", "who": "all",
     "folders": ["11nFXvEyYdRgu5PHkW-ipAA1adozukx4q"]},
    {"key": "fonts", "title": "Шрифты", "icon": "Аа", "hint": "Compacta, Onest, StudioScript. Другие в макеты не ставим.", "who": "all",
     "folders": ["1be9JlVVeRj75i06sznZi3AkaETxKoKbp"]},
    {"key": "stories", "title": "Сторис", "icon": "◐", "hint": "Рамки сторис и обложки «Актуального».", "who": "all",
     "folders": ["1pc-n7yXNwbiFjedkDXRsuDgHfq0NN3dT", "1QYXLSY6AT66oOJGhL7DgRbgFrt8Wz0vl"]},
    {"key": "reels", "title": "Рилс", "icon": "▶", "hint": "Обложки рилс. Одна серия, чтобы лента была ровной.", "who": "all",
     "folders": ["1BeHCsZ3X7txZCjXT4F7MUTkc5xb8Wf81"]},
    {"key": "headers", "title": "Шапки соцсетей", "icon": "▭", "hint": "Обложки профилей и каналов.", "who": "all",
     "folders": ["1l-Jm4JhoMz4qLQwmw2W8214yPcuZgCYT"]},
    {"key": "bg", "title": "Фоны", "icon": "▦", "hint": "Фирменные фоны под текст и плашки.", "who": "all",
     "folders": ["1I36OnGSLrnZ_5NsM7MOkvhfwYWUF7VoW"]},
    {"key": "price", "title": "Плашки цен", "icon": "₸", "hint": "Фикс-цены 129 / 199 / 279. Цифры не менять.", "who": "all",
     "folders": ["1vQQqhrjJ5BZ7SFb3YBBacPmjPMTw6zs8"]},
    {"key": "edit", "title": "Для монтажа", "icon": "✂", "hint": "Инструменты, шаблоны и примеры сборки из фул-пака.", "who": "all",
     "folders": ["1vvwIDgo3LBITVXm5O_2Q86Z5EgVoDjtW", "1vocGXbr4FAnyDJ4ajbU99G_8VUMSM5d8", "1K91vXUdVr4gc1yRoz7sAEqNSNUrIdmi8", "1UTvRxYvUWxPoP7Pfqe9NBp-0ZkYiX1nn"]},
    {"key": "portfolio", "title": "Портфолио", "icon": "★", "hint": "Лучшие объекты и фасады для постов и КП.", "who": "all",
     "folders": ["1srGGXCCcZa_GO54WjEE6C2DJNvRKnVy4", "124E_lPeM493ChSSS2CkRn-uMzXP_mdWm"]},
    {"key": "book", "title": "Книга бренда, PDF", "icon": "▤", "hint": "Полная книга одним файлом.", "who": "all",
     "folders": ["1s__lakSs6qgKVufDR2Oou81z9KBq3bbK"]},
    {"key": "print", "title": "Печать", "icon": "⎙", "hint": "Визитки, баннер, постеры, стикеры, мерч. Для типографии.", "who": "team",
     "folders": ["1efq8wtbfaLeVh1H5QnSaDVRBeRgf30Dq", "1W4HFFWWWfwdShshiRSzKquFZtaSo47FI", "1VVqrg8RV8Cu5SjTE5rJyUs0FAf9h3ySa",
                 "1EEzT5oBnjIG--OAsy7PsveqUNSzwSArc", "1Xl8YOaG1VkBJwDy52Fhrmyl3jhL0fcKf"]},
    {"key": "inner", "title": "Служебное", "icon": "⚙", "hint": "Сайт, Artgame Hub, персонаж, файлы ДТФ-печати. Видишь только ты.", "who": "head",
     "folders": ["1BUXiQm2xnjV_fCU7R3F0CPZwCXNbG6JK", "1BsOwxrD3uN75X4RaOjrNwKHeEAcRLOAH", "1B4NlkOJtQKop1wY5oJ6hQtGzDQEmnuU-",
                 "1ll8Ay-T5cKOWWqVWgzDlGgn6FSZ3gT15", "15lUVQz-UrWXAG9SUeDartxMShTvOqPDH", "1yt66R5SZ0dkGlPdtUoO96snwx_LbebN_"]},
]


ALL_ROOTS = {f for s in SHELVES for f in s["folders"]}


def _allowed(p: dict) -> list[dict]:
    role = p["role_code"]
    return [s for s in SHELVES if s["who"] == "all" or (s["who"] == "team" and role in TEAM) or role == "head"]


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _inside(d, folder: str, roots: list[str]) -> list[dict]:
    """Путь от папки полки до папки; чужая папка — 404. После перезапуска сервера путь восстанавливаем по родителям на Диске."""
    path, cur = [], folder
    for _ in range(8):
        if cur in roots:
            return path[::-1]
        if cur in ALL_ROOTS:        # дошли до чужой полки
            break
        if cur not in PARENT:
            try:
                m = d.meta(cur)
            except Exception:
                break
            if m.get("mimeType") != drive.FOLDER or not m.get("parents"):
                break
            PARENT[cur] = (m["parents"][0], m.get("name") or "Папка")
        path.append({"id": cur, "name": PARENT[cur][1]})
        cur = PARENT[cur][0]
    raise HTTPException(404, "нет такой папки на этой полке")


@router.get("/mkt/brand")
def brand(shelf: str | None = None, folder: str | None = None, p: dict = Depends(active)):
    """Без shelf — список полок для роли. С shelf — её папки и файлы; агентству — только готовые к работе, без исходников."""
    if p["role_code"] not in SEE:
        raise HTTPException(403, "«Бренд» — у маркетинга, дизайна и HEAD")
    mine = _allowed(p)
    team = p["role_code"] in TEAM
    if not shelf:
        keys = {s["key"] for s in mine}
        book = [{**c, "n": i + 1, "shelves": [k for k in c["shelves"] if k in keys]} for i, c in enumerate(BOOK)]
        return {"shelves": [{k: s[k] for k in ("key", "title", "icon", "hint", "who")} for s in mine], "sources": team, "book": book}
    sh = next((s for s in mine if s["key"] == shelf), None)
    if not sh:
        raise HTTPException(404, "нет такой полки")
    try:
        d = drive.Drive()
        path = _inside(d, folder, sh["folders"]) if folder else []
        rows = []
        for f in ([folder] if folder else sh["folders"]):
            rows += [(f, r) for r in d.ls(f)]
    except HTTPException:
        raise
    except Exception as ex:
        raise drive.fail(ex)
    folders, files, hidden = [], [], 0
    for parent, r in sorted(rows, key=lambda x: x[1]["name"].lower()):
        mime = r.get("mimeType") or ""
        if mime == drive.FOLDER:
            PARENT[r["id"]] = (parent, r["name"])
            folders.append({"id": r["id"], "name": r["name"]})
        elif not mime.startswith("application/vnd.google-apps."):   # документы Google файлом не отдать
            src = _ext(r["name"]) not in READY
            if src and not team:        # исходники (AI, PSD…) — только своим
                hidden += 1
                continue
            files.append({"id": r["id"], "name": r["name"], "mime": mime, "size": int(r.get("size") or 0), "source": src, "url": _sign(r["id"], "file"),
                          "thumb": _sign(r["id"], "thumb") if mime.startswith(("image/", "video/")) or mime == "application/pdf" else None})
    return {"shelf": {k: sh[k] for k in ("key", "title", "icon", "hint", "who")}, "path": path, "folders": folders, "files": files, "hidden": hidden}


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
