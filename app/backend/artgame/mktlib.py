"""Маркетинг: рубрики и поиск в «Медиа», исходники в рубрику, сценарий → утверждение HEAD → «Съёмка» с папкой (HEAD 24.11).

Рубрики — те же папки Диска «06 МАРКЕТИНГ / 02 КОНТЕНТ»; у материала с объектов — метки («До/после», «Отзывы», «Готовые работы»).
Исходники агентство грузит из приложения: «02 КОНТЕНТ / <рубрика> / Исходники / ГГГГ-ММ-ДД Название» — доступ к Диску им не нужен.
Сценарий живёт только в приложении; при «В съёмку» в папку съёмки кладётся его копия файлом.
"""
import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import bx, db, drive
from .config import settings
from .files import MAX_BIG, links
from .marketing import IDEA_JOBS, SHOOT_JOBS, _job, _mkt
from .work import active

router = APIRouter(prefix="/api")
CONTENT_ID = "1EZ0NkwjOkQbb7fDzshqnZPNxHVubDF75"       # Диск: 06 МАРКЕТИНГ / 02 КОНТЕНТ
TYPES = ("photo", "video", "reels")


def _n(s: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", (s or "").lower().replace("ё", "е")).strip()


def _safe(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|]+', " ", s)).strip()[:80] or "Без названия"


def rubric_folder(d, title: str) -> str:
    """Папка рубрики в «02 КОНТЕНТ»: у папок на Диске бывают номера впереди («01 Процесс росписи») — ищем по названию."""
    want = _n(title)
    for f in d.ls(CONTENT_ID):
        if f.get("mimeType") == drive.FOLDER and want and want in _n(f["name"]):
            return f["id"]
    return d.child(CONTENT_ID, title)


def src_folder(d, rubric: str, name: str) -> str:
    return d.child(d.child(rubric_folder(d, rubric), "Исходники"), name)


def rubrics(conn) -> list[dict]:
    return conn.execute("SELECT id, title, project FROM mkt_rubrics ORDER BY sort, id").fetchall()


@router.get("/mkt/rubrics")
def rubrics_get(p: dict = Depends(active)):
    _mkt(p)
    with db.pool.connection() as conn:
        return rubrics(conn)


# ---------- «Медиа»: поиск, фильтры, метки ----------
CAT, SUB = "UF_CRM_ARTGAME_PROJECT_CATEGORY", "UF_CRM_ARTGAME_PROJECT_SUBCATEGORY"


def categories() -> list[dict]:
    """Утверждённые категории проекта (поле сделки, по ним делаются каталоги; HEAD 25.11) с подкатегориями.
    Подкатегория «4.2. Школы и вузы» относится к 4-й категории по порядку списка Битрикса."""
    try:
        cats = list(bx.enum_map(CAT).items())
        subs = list(bx.enum_map(SUB).items())
    except Exception:
        return []
    out = [{"id": k, "name": v, "subs": []} for k, v in cats]
    for k, v in subs:
        m = re.match(r"\s*(\d+)\.", v)
        if m and 0 < int(m.group(1)) <= len(out):
            out[int(m.group(1)) - 1]["subs"].append({"id": k, "name": v})
    return out


def deals_in(field: str, value: str) -> list[int]:
    """ID сделок с этой категорией/подкатегорией (папка сделки = objects.id). Кэш как у остальных чтений Битрикса."""
    rows = bx.read_all("crm.deal.list", {"filter": {field: value}, "select": ["ID"], "order": {"ID": "ASC"}})
    return [int(r["ID"]) for r in rows if str(r.get("ID", "")).isdigit()]


@router.get("/mkt/library")
def library(type: str | None = None, best: bool = False, q: str | None = None, year: int | None = None, city: str | None = None,
            tag: int | None = None, object_id: int | None = None, cat: str | None = None, sub: str | None = None,
            p: dict = Depends(active)):
    """Весь материал: с объектов (кроме возвращённого HEAD) и исходники рубрик. Поиск — по названию файла, проекту, городу, папке."""
    if p["role_code"] not in ("marketer", "head", "lead_designer"):
        raise HTTPException(403, "медиатека — у Главного дизайнера, маркетинга и HEAD")
    cond, args = ["f.status='ready'", "(f.kind='src' OR (f.kind='media' AND f.review IS DISTINCT FROM 'rejected'))"], []
    if best:
        cond.append("f.review='approved'")
    if type in TYPES:
        cond.append("coalesce(f.media_type, 'photo')=%s"); args.append(type)
    if year:
        cond.append("extract(year FROM f.created_at AT TIME ZONE 'Asia/Almaty')=%s"); args.append(year)
    if city:
        cond.append("o.city=%s"); args.append(city)
    if object_id:
        cond.append("f.object_id=%s"); args.append(object_id)
    if sub or cat:   # категория проекта из сделки — только материал с объектов, исходники рубрик сюда не попадают
        ids = deals_in(SUB, sub) if sub else deals_in(CAT, cat)
        cond.append("f.kind='media' AND f.object_id = ANY(%s)"); args.append(ids)
    if tag:
        cond.append("EXISTS (SELECT 1 FROM file_tags t WHERE t.file_id=f.id AND t.rubric_id=%s)"); args.append(tag)
    for w in _n(q or "").split()[:5]:
        cond.append("lower(f.name || ' ' || coalesce(o.title,'') || ' ' || coalesce(o.city,'') || ' ' || coalesce(f.src_folder,'') || ' ' || f.object_id::text) LIKE %s")
        args.append(f"%{w}%")
    with db.pool.connection() as conn:
        rows = conn.execute(f"""SELECT f.*, pe.full_name AS by, o.title AS object_title, o.city AS object_city,
                                       (SELECT coalesce(array_agg(t.rubric_id), '{{}}') FROM file_tags t WHERE t.file_id=f.id) AS tags
                                FROM files f JOIN people pe ON pe.id=f.uploaded_by JOIN objects o ON o.id=f.object_id
                                WHERE {' AND '.join(cond)} ORDER BY f.created_at DESC LIMIT 300""", args).fetchall()
        fac = conn.execute("""SELECT array_agg(DISTINCT extract(year FROM f.created_at AT TIME ZONE 'Asia/Almaty')::int) AS years,
                                     array_agg(DISTINCT o.city) FILTER (WHERE o.city IS NOT NULL AND o.city <> '' AND f.kind='media') AS cities
                              FROM files f JOIN objects o ON o.id=f.object_id WHERE f.status='ready' AND f.kind IN ('media','src')""").fetchone()
        rub = rubrics(conn)
    return {"items": [{**links(f), "object_title": f["object_title"] if f["kind"] == "media" else None, "object_city": f["object_city"],
                       "tags": f["tags"], "src_folder": f["src_folder"]} for f in rows],
            "years": sorted(fac["years"] or [], reverse=True), "cities": sorted(fac["cities"] or []), "rubrics": rub,
            "cats": categories(), "can_tag": p["role_code"] in ("marketer", "head")}


class TagsIn(BaseModel):
    rubric_ids: list[int] = Field(max_length=12)


@router.post("/mkt/files/{file_id}/tags")
def tags_set(file_id: int, b: TagsIn, p: dict = Depends(active)):
    _mkt(p)
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM files WHERE id=%s AND kind IN ('media','src')", (file_id,)).fetchone():
            raise HTTPException(404)
        ok = [r["id"] for r in conn.execute("SELECT id FROM mkt_rubrics WHERE id = ANY(%s)", (b.rubric_ids,)).fetchall()]
        conn.execute("DELETE FROM file_tags WHERE file_id=%s AND NOT (rubric_id = ANY(%s))", (file_id, ok))
        for r in ok:
            conn.execute("INSERT INTO file_tags (file_id, rubric_id, set_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (file_id, r, p["id"]))
        db.audit(conn, p["id"], "file_tags", "files", file_id, {"rubrics": ok})
    return {"tags": ok}


# ---------- исходники прямо в рубрику ----------
class SrcIn(BaseModel):
    client_uid: UUID
    name: str = Field(min_length=1, max_length=200)
    mime: str = Field(max_length=100)
    size: int = Field(gt=0, le=MAX_BIG)
    rubric_id: int | None = None
    title: str | None = Field(default=None, max_length=80)     # что снимали: имя папки после даты
    shoot_id: int | None = None                                # или в папку съёмки


def _src_target(conn, d, b: SrcIn, when: date) -> tuple[str, str, int]:
    """Куда ляжет исходник: (id папки, её имя, рубрика)."""
    if b.shoot_id:
        s = conn.execute("SELECT * FROM mkt_shoots WHERE id=%s", (b.shoot_id,)).fetchone()
        if not s or not s["rubric_id"]:
            raise HTTPException(400, "у съёмки нет рубрики")
        rub = conn.execute("SELECT title FROM mkt_rubrics WHERE id=%s", (s["rubric_id"],)).fetchone()["title"]
        name = s["folder_name"] or f"{s['shoot_date']} {_safe(s['title'])}"
        fid = s["drive_folder"] or src_folder(d, rub, name)
        if not s["drive_folder"]:
            conn.execute("UPDATE mkt_shoots SET drive_folder=%s, folder_name=%s WHERE id=%s", (fid, name, s["id"]))
        return fid, name, s["rubric_id"]
    r = conn.execute("SELECT * FROM mkt_rubrics WHERE id=%s AND NOT project", (b.rubric_id,)).fetchone()
    if not r:
        raise HTTPException(400, "выбери рубрику")
    if not (b.title or "").strip():
        raise HTTPException(400, "напиши, что снимали")
    name = f"{when} {_safe(b.title)}"
    return src_folder(d, r["title"], name), name, r["id"]


@router.post("/mkt/src/uploads")
def src_start(b: SrcIn, request: Request, p: dict = Depends(active)):
    """Телефон грузит исходник прямо в Google, в папку рубрики. Только видео, фото и звук."""
    _mkt(p)
    if not b.mime.startswith(("video/", "image/", "audio/")):
        raise HTTPException(400, "нужно видео, фото или звук")
    origin = request.headers.get("origin") or settings.public_origin
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT * FROM files WHERE client_uid=%s AND uploaded_by=%s AND kind='src'", (b.client_uid, p["id"])).fetchone()
        if f and f["status"] == "ready":
            return {"file_id": f["id"], "done": True}
        when = (datetime.now(timezone.utc) + timedelta(hours=5)).date()
        try:
            d = drive.Drive()
            folder, name, rub = _src_target(conn, d, b, when)
            url = d.resumable(folder, b.name, b.mime, b.size, origin)
        except HTTPException:
            raise
        except Exception as ex:
            raise drive.fail(ex)
        if not f:
            f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, uploaded_by, media_type, src_folder, note)
                                VALUES (%s, 0, 'src', %s, %s, %s, 'uploading', %s, %s, %s, %s) RETURNING *""",
                             (b.client_uid, b.name, b.mime, b.size, p["id"], "photo" if b.mime.startswith("image/") else "video", name, folder)).fetchone()
            conn.execute("INSERT INTO file_tags (file_id, rubric_id, set_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (f["id"], rub, p["id"]))
        return {"file_id": f["id"], "upload_url": url, "folder": name}


class SrcDone(BaseModel):
    drive_id: str = Field(min_length=10, max_length=100)


@router.post("/mkt/src/uploads/{file_id}/done")
def src_done(file_id: int, b: SrcDone, p: dict = Depends(active)):
    _mkt(p)
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT * FROM files WHERE id=%s AND uploaded_by=%s AND kind='src'", (file_id, p["id"])).fetchone()
        if not f:
            raise HTTPException(404)
        if f["status"] != "ready":
            try:
                m = drive.Drive().meta(b.drive_id)
            except Exception as ex:
                raise drive.fail(ex)
            if f["note"] not in m.get("parents", []) or int(m.get("size", -1)) != f["size"]:     # note — id папки, куда выдавали ссылку
                raise HTTPException(400, "file mismatch")
            f = conn.execute("UPDATE files SET drive_id=%s, status='ready', mime=%s, note=NULL WHERE id=%s RETURNING *",
                             (b.drive_id, m.get("mimeType") or f["mime"], file_id)).fetchone()
            db.audit(conn, p["id"], "file_add", "files", file_id, {"kind": "src", "folder": f["src_folder"]})
        return links({**f, "by": p["full_name"]})


# ---------- сценарий: на утверждение → HEAD → в съёмку ----------
def _idea(conn, idea_id: int) -> dict:
    r = conn.execute("SELECT * FROM mkt_ideas WHERE id=%s FOR UPDATE", (idea_id,)).fetchone()
    if not r:
        raise HTTPException(404)
    return r


@router.post("/mkt/ideas/{idea_id}/submit")
def idea_submit(idea_id: int, p: dict = Depends(active)):
    _job(p, IDEA_JOBS, "идеи")
    with db.pool.connection() as conn, conn.transaction():
        r = _idea(conn, idea_id)
        if r["status"] not in ("new", "rejected", "dropped"):
            raise HTTPException(409, "идея уже отправлена")
        if not (r["text"] or "").strip():
            raise HTTPException(400, "напиши сценарий")
        if not r["rubric_id"]:
            raise HTTPException(400, "выбери рубрику")
        head = p["role_code"] == "head"       # своё HEAD утверждает сразу
        conn.execute("UPDATE mkt_ideas SET status=%s, reviewed_by=%s, reviewed_at=%s, review_note=NULL, updated_at=now() WHERE id=%s",
                     ("approved" if head else "pending", p["id"] if head else None, datetime.now(timezone.utc) if head else None, idea_id))
        db.audit(conn, p["id"], "mkt_idea_submit", "mkt_ideas", idea_id, {"title": r["title"]})
    return {"status": "approved" if head else "pending"}


class ReviewIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


@router.post("/mkt/ideas/{idea_id}/review")
def idea_review(idea_id: int, b: ReviewIn, p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "утверждает только HEAD")
    if not b.approve and not (b.note or "").strip():
        raise HTTPException(400, "напиши, что поправить")
    with db.pool.connection() as conn, conn.transaction():
        r = _idea(conn, idea_id)
        if r["status"] != "pending":
            raise HTTPException(409, "уже решено")
        st = "approved" if b.approve else "rejected"
        conn.execute("UPDATE mkt_ideas SET status=%s, reviewed_by=%s, reviewed_at=now(), review_note=%s, updated_at=now() WHERE id=%s",
                     (st, p["id"], b.note, idea_id))
        db.audit(conn, p["id"], "mkt_idea_review", "mkt_ideas", idea_id, {"approve": b.approve, "note": b.note})
    return {"status": st}


class ToShootIn(BaseModel):
    shoot_date: date
    at_time: str | None = Field(default=None, max_length=40)
    place: str | None = Field(default=None, max_length=200)


@router.post("/mkt/ideas/{idea_id}/shoot")
def idea_to_shoot(idea_id: int, b: ToShootIn, p: dict = Depends(active)):
    """Утверждённый сценарий → съёмка с датой и папка исходников со сценарием внутри. Диск не ответил — съёмка всё равно стоит,
    папка создастся при первой загрузке исходника."""
    _job(p, SHOOT_JOBS, "съёмки")
    with db.pool.connection() as conn, conn.transaction():
        r = _idea(conn, idea_id)
        if r["status"] != "approved":
            raise HTTPException(409, "в съёмку идёт только утверждённый HEAD сценарий")
        rub = conn.execute("SELECT title FROM mkt_rubrics WHERE id=%s", (r["rubric_id"],)).fetchone()
        name = f"{b.shoot_date} {_safe(r['title'])}"
        s = conn.execute("""INSERT INTO mkt_shoots (title, shoot_date, at_time, object_id, place, idea_id, note, status, author_id, rubric_id, folder_name)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,'planned',%s,%s,%s) RETURNING id""",
                         (r["title"], b.shoot_date, b.at_time, r["object_id"], b.place, idea_id, None, p["id"], r["rubric_id"], name)).fetchone()
        conn.execute("UPDATE mkt_ideas SET status='work', updated_at=now() WHERE id=%s", (idea_id,))
        db.audit(conn, p["id"], "mkt_idea_shoot", "mkt_shoots", s["id"], {"idea": idea_id, "date": str(b.shoot_date)})
    warn = ""
    try:
        d = drive.Drive()
        folder = src_folder(d, rub["title"], name)
        if not any(f["name"] == "Сценарий.txt" for f in d.ls(folder)):
            d.upload(folder, "Сценарий.txt", (r["title"] + "\n\n" + (r["text"] or "")).encode(), "text/plain")
        with db.pool.connection() as conn:
            conn.execute("UPDATE mkt_shoots SET drive_folder=%s WHERE id=%s", (folder, s["id"]))
    except Exception:  # noqa: BLE001
        warn = "Съёмка поставлена. Папку на Диске создать не удалось — она появится при первой загрузке исходника."
    return {"shoot_id": s["id"], "folder": f"{rub['title']} / Исходники / {name}", "warn": warn}
