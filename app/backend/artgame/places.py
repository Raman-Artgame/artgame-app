"""Рабочие места ролей (перенесены из артефактов 03.11): страницы, картинки, PDF.

Репозиторий публичный, а внутри — ставки, пароли, схемы МОП. Поэтому файлы лежат в places/<место>/*.enc,
зашифрованные AES-256-GCM. Ключ ARTGAME_CONTENT_KEY есть только на сервере (и в закрытой папке проекта для пересборки).
Страница открывается в приложении во фрейме по подписанной ссылке /api/p/<место>/<pid>.<exp>.<sig>/index.html;
ссылка живёт 12 ч, при каждом запросе заново проверяются статус и роль человека.
window.claude на странице заменяет place_shim.js: db → наша база, downloads → скачивание (в Telegram — downloadFile).
"""
import hashlib
import hmac
import json
import mimetypes
import secrets
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from psycopg.types.json import Jsonb

from . import constants as consts
from . import db, viewas
from .config import settings
from .deps import load_person
from .work import active

router = APIRouter(prefix="/api")

ART = {"support", "artist", "artist_pro", "lead_artist"}
PRINT = {"print_operator", "print_master"}
MOP = {"mop", "mop_vip"}
DZ = {"lead_designer", "designer_asst"}

# roles — кто открывает; aud — какие «Кто видит» из «Значений» попадают в config/values;
# editors — кто видит закрытое (vip) и правит общие документы; shared — коллекции, которые правят все, кому место открыто.
PLACES = {
    "art":   {"title": "Художники", "roles": ART | {"head"}, "aud": {"все", "производство"}},
    "print": {"title": "Печать", "roles": PRINT | {"lead_artist", "head"}, "aud": {"все", "производство"}},
    "mop":   {"title": "МОП", "roles": MOP | {"head"}, "aud": {"все", "моп"}, "editors": {"mop_vip", "head"}},
    "dz":    {"title": "Дизайн", "roles": DZ | {"head"}, "aud": {"все", "дизайн"}, "shared": {"projects"}},
}
ORDER = ["art", "print", "mop", "dz"]
BX_PLACES = {"mop"}  # на этих страницах работает подтяжка сделок Битрикса (bx.py, place_bx.js)
# Ссылки между артефактами → места приложения (переписывает place_shim.js).
ARTIFACTS = {"AUsM36vXPoSqk6J4LQUZqj": "art", "QvriqYAuWNEvypeNKAVAcE": "print", "8uecjatZFajVxKQwneyYQp": "mop",
             "BGKMEr5zCyQxr2pgWXs8oZ": "mop", "73RaYPuD5WLq43NsvkJFVm": "dz"}

TTL = 12 * 3600
ROOT = Path(__file__).resolve().parent.parent / "places"
SHIM = Path(__file__).resolve().parent / "place_shim.js"
BX_JS = Path(__file__).resolve().parent / "place_bx.js"
DL_DIR = Path(tempfile.gettempdir()) / "artgame-dl"
DL_TTL = 15 * 60
MAX_DL = 50_000_000
MAX_DOC = 1_000_000


# ---------- шифрование ----------

def _aes():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = bytes.fromhex(settings.content_key) if settings.content_key else b""
    if len(key) != 32:
        raise HTTPException(503, "content key not set")
    return AESGCM(key)


def encrypt(data: bytes, aad: str, key_hex: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(bytes.fromhex(key_hex)).encrypt(nonce, data, aad.encode())


def decrypt(blob: bytes, aad: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    try:
        return _aes().decrypt(blob[:12], blob[12:], aad.encode())
    except InvalidTag:
        raise HTTPException(503, "content key mismatch")


def key_ok() -> bool:
    chk = ROOT / "_check.enc"
    try:
        return chk.exists() and decrypt(chk.read_bytes(), "_check") == b"ok"
    except HTTPException:
        return False


# ---------- подписанные ссылки ----------

def _skey() -> bytes:
    return hashlib.sha256(b"artgame-places:" + settings.bot_token.encode()).digest()


def _sig(pid: int, code: str, exp: int, view: str = "") -> str:
    msg = f"{pid}:{code}:{exp}" + (f":{view}" if view else "")
    return hmac.new(_skey(), msg.encode(), hashlib.sha256).hexdigest()[:32]


def _view_tag() -> str:
    """Ссылка, выданная во время «смотреть как»: v<id HEAD>[-<роль>] — по ней место только для чтения."""
    d = viewas.ctx()
    if not d:
        return ""
    t = d["target"]
    return f"v{d['viewer']}" + (f"-{t['role']}" if t.get("kind") == "role" else "")


def token(pid: int, code: str, now: float | None = None) -> str:
    exp = int((now or time.time()) + TTL)
    view = _view_tag()
    return f"{pid}.{exp}.{_sig(pid, code, exp, view)}" + (f".{view}" if view else "")


def allowed(p: dict, code: str) -> bool:
    """Роль — текущая или любая из своих (две роли, HEAD 08.11): ссылка места живёт без заголовка «Я сейчас»."""
    mine = {p["role_code"], *(p.get("roles") or []), *(p.get("extra_roles") or [])}
    return p["status"] == "active" and bool(mine & PLACES[code]["roles"])


def person_by_token(code: str, tok: str) -> dict:
    if code not in PLACES:
        raise HTTPException(404)
    try:
        parts = tok.split(".")
        pid_s, exp_s, sig = parts[:3]
        view = parts[3] if len(parts) == 4 else ""
        pid, exp = int(pid_s), int(exp_s)
        if len(parts) not in (3, 4) or (view and not view.startswith("v")):
            raise ValueError
    except ValueError:
        raise HTTPException(403, "bad link")
    if exp < time.time() or not hmac.compare_digest(_sig(pid, code, exp, view), sig):
        raise HTTPException(403, "link expired")
    with db.pool.connection() as conn:
        row = conn.execute("SELECT tg_id FROM people WHERE id=%s", (pid,)).fetchone()
        p = load_person(conn, row["tg_id"]) if row else None
        if p and view:   # ссылка просмотра: HEAD должен быть действующим, место — только чтение
            vid, _, role = view[1:].partition("-")
            head = load_person(conn, int(vid), by="id")
            p = viewas.resolve(conn, head, f"role:{role}" if role else str(pid), load_person) if head else None
            if p:
                p["_ro"] = True
    if not p or not allowed(p, code):
        raise HTTPException(403, "no access")
    return p


def read_only(p: dict):
    if p.get("_ro"):
        raise HTTPException(403, viewas.RO_MSG)


def is_editor(p: dict, code: str) -> bool:
    return p["role_code"] in PLACES[code].get("editors", {"head"})


# ---------- список мест ----------

@router.get("/places")
def places(p: dict = Depends(active)):
    return [{"code": c, "title": PLACES[c]["title"], "url": f"/api/p/{c}/{token(p['id'], c)}/index.html"}
            for c in ORDER if allowed(p, c) and (ROOT / c / "index.html.enc").exists()]


@router.get("/bx/scripts")
def mop_scripts(p: dict = Depends(active)):
    """Скрипты сообщений и шаги алгоритма МОП для карточки сделки (из зашифрованного places/mop/scripts.json)."""
    if p["role_code"] not in PLACES["mop"]["roles"]:
        raise HTTPException(403, "только МОП и HEAD")
    f = ROOT / "mop" / "scripts.json.enc"
    if not f.exists():
        raise HTTPException(404, "скрипты не загружены")
    return Response(decrypt(f.read_bytes(), "mop/scripts.json"), media_type="application/json",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/p/_shim.js")
def shim():
    return FileResponse(SHIM, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/p/_bx.js")
def bx_js():
    return FileResponse(BX_JS, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


# ---------- цифры из «Значений» (контракт values_spec.md: config/values) ----------

def config_values(code: str) -> dict:
    with db.pool.connection() as conn:
        row = conn.execute("SELECT fetched_at, values FROM constants_versions ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"id": "values", "exists": False, "data": None}
    aud = PLACES[code]["aud"]
    vals = {k: consts.num(v["value"]) for k, v in row["values"].items()
            if v["status"] == "Утверждено" and consts.who_set(v.get("who") or "") & aud and str(v["value"]).strip()}
    return {"id": "values", "exists": True,
            "data": {"_updated": row["fetched_at"].isoformat(), "_source": "Значения", "values": vals}}


# ---------- общая база места ----------

def _split(path: str) -> tuple[str, str | None]:
    parts = [x for x in path.split("/") if x]
    if len(parts) == 1:
        return parts[0], None
    if len(parts) == 2:
        return parts[0], parts[1]
    raise HTTPException(400, "bad path")


def can_read(p: dict, code: str, coll: str) -> bool:
    return coll != "vip" or is_editor(p, code)


def can_write(p: dict, code: str, coll: str) -> bool:
    if coll == "config":
        return False  # config/values собирает сервер из «Значений»
    if coll in PLACES[code].get("shared", set()):
        return True
    return p["role_code"] == "head"


@router.get("/p/{code}/{tok}/_db/{path:path}")
def db_get(code: str, tok: str, path: str):
    p = person_by_token(code, tok)
    coll, doc = _split(path)
    if not can_read(p, code, coll):
        raise HTTPException(403, "closed")
    if coll == "config" and doc == "values":
        return config_values(code)
    with db.pool.connection() as conn:
        if doc is None:
            rows = conn.execute("SELECT doc_id, data, version FROM place_docs WHERE place=%s AND coll=%s ORDER BY doc_id",
                                (code, coll)).fetchall()
            return {"docs": [{"id": r["doc_id"], "data": r["data"], "version": r["version"]} for r in rows]}
        r = conn.execute("SELECT data, version FROM place_docs WHERE place=%s AND coll=%s AND doc_id=%s",
                         (code, coll, doc)).fetchone()
    return {"id": doc, "exists": bool(r), "data": r["data"] if r else None, "version": r["version"] if r else 0}


@router.put("/p/{code}/{tok}/_db/{path:path}")
async def db_set(code: str, tok: str, path: str, request: Request):
    p = person_by_token(code, tok)
    coll, doc = _split(path)
    if doc is None:
        raise HTTPException(400, "doc id required")
    read_only(p)
    if not can_write(p, code, coll):
        raise HTTPException(403, "read only")
    body = await request.body()
    if len(body) > MAX_DOC:
        raise HTTPException(413, "too big")
    try:
        data = json.loads(body)
    except ValueError:
        raise HTTPException(400, "bad json")
    if not isinstance(data, dict):
        raise HTTPException(400, "object required")
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("""INSERT INTO place_docs (place, coll, doc_id, data, updated_by) VALUES (%s,%s,%s,%s,%s)
                            ON CONFLICT (place, coll, doc_id) DO UPDATE
                            SET data=EXCLUDED.data, version=place_docs.version+1, updated_by=EXCLUDED.updated_by, updated_at=now()
                            RETURNING version""", (code, coll, doc, Jsonb(data), p["id"])).fetchone()
        db.audit(conn, p["id"], "place_doc_set", "place_docs", f"{code}/{coll}/{doc}", {"version": r["version"]})
    return {"ok": True, "version": r["version"]}


# ---------- скачивание файлов, собранных на странице (КП в PDF, договоры xlsx) ----------

def _dl_clean():
    DL_DIR.mkdir(mode=0o700, exist_ok=True)
    for f in DL_DIR.iterdir():
        if f.stat().st_mtime < time.time() - DL_TTL:
            f.unlink(missing_ok=True)


@router.post("/p/{code}/{tok}/_dl")
async def dl_put(code: str, tok: str, name: str, request: Request):
    p = person_by_token(code, tok)
    body = await request.body()
    if not body or len(body) > MAX_DL:
        raise HTTPException(413, "too big")
    _dl_clean()
    fid = secrets.token_hex(16)
    safe = "".join(c for c in name if c not in '\\/:*?"<>|\r\n').strip()[:150] or "file"
    (DL_DIR / f"{fid}.bin").write_bytes(body)
    (DL_DIR / f"{fid}.json").write_text(json.dumps({"name": safe, "mime": request.headers.get("content-type", "")}))
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "place_download", "places", code, {"name": safe, "size": len(body)})
    return {"url": f"/api/p/{code}/{tok}/_dl/{fid}"}


@router.get("/p/{code}/{tok}/_dl/{fid}")
def dl_get(code: str, tok: str, fid: str):
    person_by_token(code, tok)
    if not fid.isalnum():
        raise HTTPException(404)
    f, m = DL_DIR / f"{fid}.bin", DL_DIR / f"{fid}.json"
    if not f.exists():
        raise HTTPException(404, "expired")
    meta = json.loads(m.read_text())
    mime = meta["mime"] or mimetypes.guess_type(meta["name"])[0] or "application/octet-stream"
    return FileResponse(f, media_type=mime, filename=meta["name"])


# ---------- сами файлы места ----------

def inject(html: bytes, code: str, p: dict) -> bytes:
    cfg = {"code": code, "editor": is_editor(p, code), "artifacts": ARTIFACTS,
           "titles": {c: PLACES[c]["title"] for c in ORDER}, "bx": code in BX_PLACES}
    tag = (f'<script>window.ARTGAME_PLACE={json.dumps(cfg, ensure_ascii=False)}</script>'
           '<script src="/api/p/_shim.js"></script>'
           + ('<script src="/api/p/_bx.js" defer></script>' if code in BX_PLACES else '')).encode()
    head = html.lstrip()[:200].lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        i = html[:4000].lower().find(b"<head")
        if i >= 0:
            j = html.find(b">", i) + 1
            return html[:j] + tag + html[j:]
        return tag + html
    # артефакт хранит фрагмент страницы, остов добавляла платформа — добавляем сами
    return (b'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            b'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            + tag + b"</head><body>" + html + b"</body></html>")


@router.get("/p/{code}/{tok}/{path:path}")
def place_file(code: str, tok: str, path: str):
    p = person_by_token(code, tok)
    path = path or "index.html"
    if ".." in path.split("/") or path.startswith("_"):
        raise HTTPException(404)
    f = ROOT / code / (path + ".enc")
    if not f.is_file():
        raise HTTPException(404)
    data = decrypt(f.read_bytes(), f"{code}/{path}")
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if path == "index.html":
        return Response(inject(data, code, p), media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})
