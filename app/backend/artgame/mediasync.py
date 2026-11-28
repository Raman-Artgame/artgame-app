"""Подтяжка «МЕДИА» сделок с Диска в «Маркетинг → Медиа» (HEAD 26.11: «сейчас всё докладываем и раскладываем в продакшн
по 25–26 году, чтобы у них уже что-то было сгруппировано»).

«Медиа» видит только карточки файлов в базе, а то, что положено на Диск руками (Продакшн 2025–26, перенос с Яндекса), карточек
не имеет. Здесь приложение само читает папки сделки и заводит карточки:
  МЕДИА / Продакшн / Фото, Видео → утверждено (review='approved', как одобренное HEAD);
  МЕДИА / Рилс                    → рилс, утверждено;
  МЕДИА / Отчёты                  → без решения (review пусто: в «Медиа» видно, в очередь HEAD не попадает).
На Диске ничего не создаётся и не двигается: папок, которых нет, просто нет. Уже известные файлы (drive_id или копия
в «Продакшн» — prod_drive_id) второй раз не заводятся. Дата — съёмки из EXIF, иначе более ранняя из «создан/изменён» на Диске.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

from . import db, drive
from .promo import _system_person
from .work import active

router = APIRouter(prefix="/api")
FRESH = timedelta(hours=12)
MAX_PER_OBJECT = 3000
# (путь внутри «МЕДИА», тип по умолчанию, отметка HEAD)
PLACES = (("Продакшн/Фото", "photo", "approved"), ("Продакшн/Видео", "video", "approved"),
          ("Рилс", "reels", "approved"), ("Отчёты", None, None))
FIELDS = "nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime,imageMediaMetadata/time)"


def _ls(d: drive.Drive, parent: str) -> list[dict]:
    out, token = [], None
    while True:
        r = drive._retry(httpx.get, drive.API, headers=d.h, timeout=30,
                         params={**drive.ALL, "corpora": "allDrives", "pageSize": 1000, "fields": FIELDS,
                                 "q": f"'{parent}' in parents and trashed = false", **({"pageToken": token} if token else {})})
        r.raise_for_status()
        j = r.json()
        out += j.get("files", [])
        token = j.get("nextPageToken")
        if not token:
            return out


def _sub(items: list[dict], name: str) -> str | None:
    for f in items:
        if f.get("mimeType") == drive.FOLDER and f["name"].strip().casefold() == name.casefold():
            return f["id"]
    return None


def _when(f: dict) -> datetime | None:
    t = (f.get("imageMediaMetadata") or {}).get("time")
    if t and re.match(r"\d{4}:\d\d:\d\d \d\d:\d\d:\d\d", t):
        try:
            return datetime.strptime(t[:19], "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=5)))
        except ValueError:
            pass
    ts = [datetime.fromisoformat(f[k].replace("Z", "+00:00")) for k in ("createdTime", "modifiedTime") if f.get(k)]
    return min(ts) if ts else None


def media_type(mime: str, default: str | None) -> str | None:
    if mime.startswith("image/"):
        return "photo"
    if mime.startswith("video/"):
        return "reels" if default == "reels" else "video"
    return None


def walk(d: drive.Drive, root: str) -> list[tuple[dict, str, str, str | None]]:
    """Файлы «МЕДИА» сделки: (файл Диска, путь, тип, отметка). Внутри места — до двух уровней подпапок."""
    media = _sub(_ls(d, root), "МЕДИА")
    if not media:
        return []
    top = _ls(d, media)
    out = []
    for path, default, review in PLACES:
        parts, fid, items = path.split("/"), media, top
        for part in parts:
            fid = _sub(items, part)
            if not fid:
                break
            items = _ls(d, fid)
        if not fid:
            continue
        queue, depth = [(items, path)], 0
        while queue and depth < 3 and len(out) < MAX_PER_OBJECT:
            nxt = []
            for its, pth in queue:
                for f in its:
                    if f.get("mimeType") == drive.FOLDER:
                        if depth < 2:
                            nxt.append((_ls(d, f["id"]), f"{pth}/{f['name']}"))
                        continue
                    t = media_type(f.get("mimeType") or "", default)
                    if t:
                        out.append((f, pth, t, review))
            queue, depth = nxt, depth + 1
    return out


def sync_object(conn, obj: dict, found: list) -> int:
    """Завести карточки на найденные файлы «МЕДИА» сделки (found — из walk, Диск читается без соединения с базой),
    которых в базе ещё нет. Возвращает, сколько добавлено."""
    who = _system_person(conn)
    if not who or obj["id"] == 0:
        return 0
    known = set()
    for r in conn.execute("SELECT drive_id, prod_drive_id FROM files WHERE object_id=%s", (obj["id"],)):
        known.update(x for x in (r["drive_id"], r["prod_drive_id"]) if x)
    added = 0
    for f, path, t, review in found:
        if f["id"] in known:
            continue
        known.add(f["id"])
        conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, note, status, uploaded_by,
                                           media_type, review, created_at)
                        VALUES (%s, %s, 'media', %s, %s, %s, %s, %s, 'ready', %s, %s, %s, coalesce(%s, now()))
                        ON CONFLICT (client_uid) DO NOTHING""",
                     (uuid.uuid5(uuid.NAMESPACE_URL, "drive:" + f["id"]), obj["id"], f["name"], f.get("mimeType"),
                      int(f["size"]) if f.get("size") else None, f["id"], "Диск: МЕДИА/" + path, who, t, review, _when(f)))
        added += 1
    conn.execute("UPDATE objects SET media_synced_at=now() WHERE id=%s", (obj["id"],))
    return added


@router.post("/mkt/library/sync")
def sync_batch(limit: int = 15, p: dict = Depends(active)):
    """HEAD: подтянуть «МЕДИА» сделок с Диска частями — давно не сверенные сделки, по `limit` за вызов. Экран зовёт, пока left > 0."""
    if p["role_code"] != "head":
        raise HTTPException(403, "только HEAD")
    limit = max(1, min(limit, 40))
    with db.pool.connection() as conn:
        objs = conn.execute("""SELECT * FROM objects WHERE id <> 0 AND drive_folder IS NOT NULL
                                 AND (media_synced_at IS NULL OR media_synced_at < now() - %s)
                               ORDER BY media_synced_at NULLS FIRST, id DESC LIMIT %s""", (FRESH, limit)).fetchall()
    d, added, errors = drive.Drive(), 0, []
    for o in objs:
        try:
            found = walk(d, o["drive_folder"])
            with db.pool.connection() as conn, conn.transaction():
                added += sync_object(conn, o, found)
        except Exception as ex:  # noqa: BLE001 — одна сделка с ошибкой Диска не останавливает остальные
            errors.append({"object_id": o["id"], "error": ex.__class__.__name__})
            with db.pool.connection() as conn:
                conn.execute("UPDATE objects SET media_synced_at=now() WHERE id=%s", (o["id"],))
    with db.pool.connection() as conn:
        left = conn.execute("""SELECT count(*) AS n FROM objects WHERE id <> 0 AND drive_folder IS NOT NULL
                                 AND (media_synced_at IS NULL OR media_synced_at < now() - %s)""", (FRESH,)).fetchone()["n"]
    return {"done": len(objs), "added": added, "left": left, "errors": errors}
