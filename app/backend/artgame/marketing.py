"""Рабочее место маркетинга (HEAD 14.11): контент-план с утверждением HEAD каждой публикации.

Маркетолог (и HEAD) ставит публикацию в план: что, где, когда, текст и материал из «Медиа» (фото/видео/рилс с объектов).
Черновик → «Отправить HEAD» → HEAD «Утверждаю» или «Вернуть» с причиной → после выхода — «Опубликовано» со ссылкой.
Неутверждённую публикацию отметить вышедшей нельзя. Ничего не удаляем: «Отменить» = status cancelled.
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import db, drive
from .config import settings
from .files import MAX_BIG, links
from .work import active

router = APIRouter(prefix="/api")
MKT = {"marketer", "head"}
CHANNELS = {"instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube", "2gis": "2ГИС", "olx": "OLX", "site": "Сайт", "other": "Другое"}
KINDS = {"reels": "Рилс", "post": "Пост", "carousel": "Карусель", "stories": "Сторис", "ad": "Реклама"}
EDITABLE = ("draft", "rejected")
# Задача человека в отделе (HEAD 14.11): руководитель видит всё и проверяет первой; остальные делают своё.
JOBS = {"lead": "Руководитель", "smm": "Контент и публикации", "stories": "Сторис и баннеры", "target": "Таргет", "video": "Съёмка"}
POST_JOBS = {None, "lead", "smm", "stories", "target"}   # кто ставит публикации в план; таргетолог — только формат «Реклама»
ALL_POSTS = {None, "lead", "smm"}                   # кто правит и чужие публикации; сторис-мейкер — только свои
IDEA_JOBS = {None, "lead", "smm", "stories", "video"}
SHOOT_JOBS = {None, "lead", "smm", "video"}


def _job(p: dict, allowed: set, what: str):
    """HEAD можно всё; маркетологу — по его задаче в отделе."""
    _mkt(p)
    if p["role_code"] != "head" and p.get("mkt_job") not in allowed:
        raise HTTPException(403, f"{what} — не твоя задача в отделе")
    return p


def _own(p: dict, r: dict):
    if p["role_code"] != "head" and p.get("mkt_job") not in ALL_POSTS and r["author_id"] != p["id"]:
        raise HTTPException(403, "это публикация коллеги")


def _mkt(p: dict) -> dict:
    if p["role_code"] not in MKT:
        raise HTTPException(403, "контент-план — у маркетинга и HEAD")
    return p


def _files(conn, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    rows = conn.execute("""SELECT f.*, pe.full_name AS by FROM files f JOIN people pe ON pe.id=f.uploaded_by
                           WHERE f.id = ANY(%s) AND f.kind IN ('media','pub')""", (ids,)).fetchall()
    by = {r["id"]: r for r in rows}
    return [links(by[i]) for i in ids if i in by]


def _out(conn, r: dict) -> dict:
    return {**{k: r[k] for k in ("id", "title", "channel", "kind", "plan_date", "caption", "object_id", "status", "author_id",
                                 "submitted_at", "reviewed_at", "review_note", "url", "published_at", "created_at",
                                 "result", "result_note", "views", "leads", "checked_at")},
            "author": r.get("author"), "checked": r.get("checked"), "reviewer": r.get("reviewer"), "object_title": r.get("object_title"), "files": _files(conn, list(r["file_ids"] or []))}


SQL = """SELECT m.*, pe.full_name AS author, o.title AS object_title, ck.full_name AS checked,
                CASE WHEN rv.role_code='head' THEN 'HEAD' ELSE rv.full_name END AS reviewer
         FROM mkt_posts m JOIN people pe ON pe.id=m.author_id LEFT JOIN objects o ON o.id=m.object_id
         LEFT JOIN people ck ON ck.id=m.checked_by LEFT JOIN people rv ON rv.id=m.reviewed_by"""


def _get(conn, post_id: int, lock: bool = False) -> dict:
    r = conn.execute(SQL + " WHERE m.id=%s" + (" FOR UPDATE OF m" if lock else ""), (post_id,)).fetchone()
    if not r:
        raise HTTPException(404)
    return r


@router.get("/mkt/dict")
def mkt_dict(p: dict = Depends(active)):
    _mkt(p)
    return {"channels": CHANNELS, "kinds": KINDS, "jobs": JOBS}


def _norms(conn, t0: date, t1: date) -> list[dict]:
    """Объём месяца по договору: сколько положено, сколько в плане и сколько вышло. Карусель считается постом."""
    got = {r["k"]: r for r in conn.execute(
        """SELECT CASE WHEN kind='carousel' THEN 'post' ELSE kind END AS k, count(*) AS planned,
                  count(*) FILTER (WHERE status='published') AS done
           FROM mkt_posts WHERE status<>'cancelled' AND plan_date >= %s AND plan_date < %s GROUP BY 1""", (t0, t1)).fetchall()}
    return [{"kind": n["kind"], "title": n["title"], "per_month": n["per_month"],
             "planned": got.get(n["kind"], {}).get("planned", 0), "done": got.get(n["kind"], {}).get("done", 0)}
            for n in conn.execute("SELECT * FROM mkt_norms WHERE per_month > 0 ORDER BY sort").fetchall()]


class NormIn(BaseModel):
    kind: str
    per_month: int = Field(ge=0, le=1000)


@router.post("/mkt/norms")
def norm_set(b: NormIn, p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "объём по договору правит HEAD")
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("UPDATE mkt_norms SET per_month=%s, updated_by=%s, updated_at=now() WHERE kind=%s RETURNING kind",
                         (b.per_month, p["id"], b.kind)).fetchone()
        if not r:
            raise HTTPException(404)
        db.audit(conn, p["id"], "mkt_norm", "mkt_norms", None, b.model_dump())
    return {"ok": True}


@router.get("/mkt/posts")
def posts(ym: str | None = None, status: str | None = None, p: dict = Depends(active)):
    """Месяц плана (ym=ГГГГ-ММ) — плюс без даты; status=pending — всё, что ждёт HEAD, за любой месяц."""
    _mkt(p)
    norms = []
    with db.pool.connection() as conn:
        if status:
            rows = conn.execute(SQL + " WHERE m.status=%s ORDER BY m.plan_date NULLS LAST, m.id", (status,)).fetchall()
        else:
            y, mo = map(int, (ym or date.today().strftime("%Y-%m")).split("-"))
            t0, t1 = date(y, mo, 1), date(y + mo // 12, mo % 12 + 1, 1)
            rows = conn.execute(SQL + """ WHERE m.status<>'cancelled' AND (m.plan_date IS NULL OR (m.plan_date >= %s AND m.plan_date < %s))
                                          ORDER BY m.plan_date NULLS FIRST, m.id""", (t0, t1)).fetchall()
            norms = _norms(conn, t0, t1)
        items = [_out(conn, r) for r in rows]
        to_check = conn.execute("SELECT count(*) AS n FROM mkt_posts WHERE status='check'").fetchone()["n"]
    n = {s: sum(1 for x in items if x["status"] == s) for s in ("draft", "check", "pending", "approved", "rejected", "published")}
    return {"items": items, "counts": n, "channels": CHANNELS, "kinds": KINDS, "norms": norms, "to_check": to_check}


class PostIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    channel: str = "instagram"
    kind: str = "reels"
    plan_date: date | None = None
    caption: str | None = Field(default=None, max_length=4000)
    file_ids: list[int] = Field(default_factory=list, max_length=20)
    object_id: int | None = None


def _check(conn, b: PostIn, p: dict | None = None):
    if b.channel not in CHANNELS or b.kind not in KINDS:
        raise HTTPException(400, "bad channel/kind")
    if p and p["role_code"] != "head" and p.get("mkt_job") == "target" and b.kind != "ad":
        raise HTTPException(403, "таргетолог ставит только рекламу")
    if b.file_ids:
        ok = conn.execute("SELECT count(*) AS n FROM files WHERE id = ANY(%s) AND kind IN ('media','pub') AND status='ready'", (b.file_ids,)).fetchone()["n"]
        if ok != len(set(b.file_ids)):
            raise HTTPException(400, "материал не найден в «Медиа»")


@router.post("/mkt/posts")
def post_add(b: PostIn, p: dict = Depends(active)):
    _job(p, POST_JOBS, "публикации")
    with db.pool.connection() as conn, conn.transaction():
        _check(conn, b, p)
        r = conn.execute("""INSERT INTO mkt_posts (title, channel, kind, plan_date, caption, file_ids, object_id, author_id)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                         (b.title.strip(), b.channel, b.kind, b.plan_date, b.caption, b.file_ids, b.object_id, p["id"])).fetchone()
        db.audit(conn, p["id"], "mkt_post_add", "mkt_posts", r["id"], {"title": b.title})
        return _out(conn, _get(conn, r["id"]))


@router.post("/mkt/posts/{post_id}")
def post_edit(post_id: int, b: PostIn, p: dict = Depends(active)):
    """Править можно черновик и возвращённое; возвращённое после правки снова черновик."""
    _job(p, POST_JOBS, "публикации")
    with db.pool.connection() as conn, conn.transaction():
        r = _get(conn, post_id, lock=True)
        _own(p, r)
        if r["status"] not in EDITABLE:
            raise HTTPException(409, "править можно черновик или возвращённое")
        _check(conn, b, p)
        conn.execute("""UPDATE mkt_posts SET title=%s, channel=%s, kind=%s, plan_date=%s, caption=%s, file_ids=%s, object_id=%s,
                        status='draft', updated_at=now() WHERE id=%s""",
                     (b.title.strip(), b.channel, b.kind, b.plan_date, b.caption, b.file_ids, b.object_id, post_id))
        return _out(conn, _get(conn, post_id))


def _move(post_id: int, p: dict, frm: tuple, to: str, sets: str = "", args: tuple = (), action: str = "", data: dict | None = None, own: bool = False):
    with db.pool.connection() as conn, conn.transaction():
        r = _get(conn, post_id, lock=True)
        if own:
            _own(p, r)
        if r["status"] not in frm:
            raise HTTPException(409, "уже не на этом шаге")
        conn.execute(f"UPDATE mkt_posts SET status=%s, updated_at=now(){sets} WHERE id=%s", (to, *args, post_id))
        db.audit(conn, p["id"], action or f"mkt_post_{to}", "mkt_posts", post_id, data or {})
        return _out(conn, _get(conn, post_id))


@router.post("/mkt/posts/{post_id}/submit")
def post_submit(post_id: int, p: dict = Depends(active)):
    """Исполнитель отправляет руководителю отдела; руководитель и HEAD (или когда руководителя нет) — сразу HEAD."""
    _job(p, POST_JOBS, "публикации")
    with db.pool.connection() as conn:
        r = _get(conn, post_id)
        _own(p, r)
        lead = conn.execute("SELECT 1 FROM people WHERE status='active' AND role_code='marketer' AND mkt_job='lead' LIMIT 1").fetchone()
    if not r["plan_date"]:
        raise HTTPException(400, "поставь дату выхода")
    if not r["file_ids"] and not (r["caption"] or "").strip():
        raise HTTPException(400, "добавь материал или текст — HEAD должен видеть, что выйдет")
    if p["role_code"] == "head" or p.get("mkt_job") == "lead" or not lead:
        return _move(post_id, p, EDITABLE, "pending", ", submitted_at=now(), review_note=NULL, checked_by=NULL, checked_at=NULL", own=True)
    return _move(post_id, p, EDITABLE, "check", ", submitted_at=now(), review_note=NULL, checked_by=NULL, checked_at=NULL", own=True)


class ReviewIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


@router.post("/mkt/posts/{post_id}/check")
def post_check(post_id: int, b: ReviewIn, p: dict = Depends(active)):
    """Первая проверка руководителем отдела: «Проверено» — уходит HEAD, «Вернуть» — автору с причиной."""
    _job(p, {"lead"}, "первая проверка")
    if not b.approve and not (b.note or "").strip():
        raise HTTPException(400, "reason required")
    if b.approve:
        return _move(post_id, p, ("check",), "pending", ", checked_by=%s, checked_at=now()", (p["id"],), "mkt_post_check", {"approve": True})
    return _move(post_id, p, ("check",), "rejected", ", reviewed_by=%s, reviewed_at=now(), review_note=%s", (p["id"], b.note),
                 "mkt_post_check", {"approve": False, "note": b.note})


@router.post("/mkt/posts/{post_id}/review")
def post_review(post_id: int, b: ReviewIn, p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "утверждает только HEAD")
    if not b.approve and not (b.note or "").strip():
        raise HTTPException(400, "reason required")
    return _move(post_id, p, ("pending",), "approved" if b.approve else "rejected",
                 ", reviewed_by=%s, reviewed_at=now(), review_note=%s", (p["id"], b.note), "mkt_post_review", {"approve": b.approve, "note": b.note})


class PublishedIn(BaseModel):
    url: str | None = Field(default=None, max_length=500)


@router.post("/mkt/posts/{post_id}/published")
def post_published(post_id: int, b: PublishedIn, p: dict = Depends(active)):
    _job(p, POST_JOBS, "публикации")
    url = (b.url or "").strip() or None
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(400, "ссылка должна начинаться с https://")
    return _move(post_id, p, ("approved",), "published", ", url=%s, published_at=now()", (url,))


@router.post("/mkt/posts/{post_id}/cancel")
def post_cancel(post_id: int, p: dict = Depends(active)):
    _job(p, POST_JOBS, "публикации")
    return _move(post_id, p, ("draft", "check", "pending", "approved", "rejected"), "cancelled", own=True)


class DayIn(BaseModel):
    plan_date: date


@router.post("/mkt/review_day")
def review_day(b: DayIn, p: dict = Depends(active)):
    """HEAD: «Утвердить все на день» — всё, что ждёт решения с этой датой выхода."""
    if p["role_code"] != "head":
        raise HTTPException(403, "утверждает только HEAD")
    with db.pool.connection() as conn, conn.transaction():
        rows = conn.execute("""UPDATE mkt_posts SET status='approved', reviewed_by=%s, reviewed_at=now(), review_note=NULL, updated_at=now()
                               WHERE status='pending' AND plan_date=%s RETURNING id""", (p["id"], b.plan_date)).fetchall()
        for r in rows:
            db.audit(conn, p["id"], "mkt_post_review", "mkt_posts", r["id"], {"approve": True, "day": str(b.plan_date)})
    return {"approved": len(rows)}


# ---------- «Загрузить готовое»: рилс / сторис / баннер от агентства — прямо в публикацию (HEAD 14.11) ----------

def _ready_folder(d, when) -> str:
    """«06 МАРКЕТИНГ / 04 Готовые публикации / ГГГГ / ММ МЕСЯЦ» — по дате начала загрузки."""
    return d.child(d.child(drive.MKT_READY_ID, str(when.year)), f"{when.month:02d} {drive.MONTHS[when.month - 1]}")


class UpIn(BaseModel):
    client_uid: UUID
    name: str = Field(min_length=1, max_length=200)
    mime: str = Field(max_length=100)
    size: int = Field(gt=0, le=MAX_BIG)


@router.post("/mkt/uploads")
def upload_start(b: UpIn, request: Request, p: dict = Depends(active)):
    """Телефон грузит файл прямо в Google; сервер выдаёт ссылку. Только видео и картинки."""
    _job(p, POST_JOBS, "публикации")
    if not b.mime.startswith(("video/", "image/")):
        raise HTTPException(400, "нужно видео или картинка")
    origin = request.headers.get("origin") or settings.public_origin
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, uploaded_by, media_type)
                            VALUES (%s, 0, 'pub', %s, %s, %s, 'uploading', %s, %s) ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
                         (b.client_uid, b.name, b.mime, b.size, p["id"], "reels" if b.mime.startswith("video/") else "photo")).fetchone()
        if not f:
            f = conn.execute("SELECT * FROM files WHERE client_uid=%s AND uploaded_by=%s AND kind='pub'", (b.client_uid, p["id"])).fetchone()
            if not f:
                raise HTTPException(409, "повтори загрузку")
            if f["status"] == "ready":
                return {"file_id": f["id"], "done": True, "file": links({**f, "by": p["full_name"]})}
        try:
            d = drive.Drive()
            url = d.resumable(_ready_folder(d, f["created_at"]), b.name, b.mime, b.size, origin)
        except Exception as ex:
            raise drive.fail(ex)
        return {"file_id": f["id"], "upload_url": url}


class UpDone(BaseModel):
    drive_id: str = Field(min_length=10, max_length=100)


@router.post("/mkt/uploads/{file_id}/done")
def upload_done(file_id: int, b: UpDone, p: dict = Depends(active)):
    """Загрузка закончена: сервер сверяет папку и размер, только потом файл можно ставить в публикацию."""
    _mkt(p)
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT * FROM files WHERE id=%s AND uploaded_by=%s AND kind='pub'", (file_id, p["id"])).fetchone()
        if not f:
            raise HTTPException(404)
        if f["status"] != "ready":
            try:
                d = drive.Drive()
                m = d.meta(b.drive_id)
                folder = _ready_folder(d, f["created_at"])
            except Exception as ex:
                raise drive.fail(ex)
            if folder not in m.get("parents", []) or int(m.get("size", -1)) != f["size"]:
                raise HTTPException(400, "file mismatch")
            f = conn.execute("UPDATE files SET drive_id=%s, status='ready', mime=%s WHERE id=%s RETURNING *",
                             (b.drive_id, m.get("mimeType") or f["mime"], file_id)).fetchone()
            db.audit(conn, p["id"], "file_add", "files", file_id, {"kind": "pub"})
        return links({**f, "by": p["full_name"]})


# ---------- итог публикации, выгрузка плана (HEAD 14.11: «что выполнено, что даёт результат, а что нет») ----------

class ResultIn(BaseModel):
    result: str = Field(pattern="^(good|weak)$")
    views: int | None = Field(default=None, ge=0)
    leads: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


@router.post("/mkt/posts/{post_id}/result")
def post_result(post_id: int, b: ResultIn, p: dict = Depends(active)):
    _job(p, ALL_POSTS | {"target"}, "итог публикации")
    with db.pool.connection() as conn, conn.transaction():
        r = _get(conn, post_id, lock=True)
        if r["status"] != "published":
            raise HTTPException(409, "итог — после выхода")
        conn.execute("UPDATE mkt_posts SET result=%s, views=%s, leads=%s, result_note=%s, updated_at=now() WHERE id=%s",
                     (b.result, b.views, b.leads, b.note, post_id))
        db.audit(conn, p["id"], "mkt_post_result", "mkt_posts", post_id, b.model_dump())
        return _out(conn, _get(conn, post_id))


STATUS_RU = {"draft": "черновик", "check": "на проверке", "pending": "у HEAD", "approved": "утверждено", "rejected": "вернул", "published": "вышло"}


@router.get("/mkt/posts.csv")
def posts_csv(ym: str, p: dict = Depends(active)):
    """Выгрузка контент-плана месяца (откроется в Excel / Google Таблицах)."""
    import csv
    import io
    from fastapi.responses import Response
    d = posts(ym=ym, p=p)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата", "Где", "Формат", "Что", "Проект", "Статус", "Ссылка", "Итог", "Просмотры", "Заявки", "Текст", "Автор"])
    for x in d["items"]:
        w.writerow([x["plan_date"] or "", CHANNELS[x["channel"]], KINDS[x["kind"]], x["title"], x["object_title"] or "",
                    STATUS_RU.get(x["status"], x["status"]), x["url"] or "",
                    {"good": "дала результат", "weak": "без результата"}.get(x["result"] or "", ""), x["views"] or "", x["leads"] or "",
                    x["caption"] or "", x["author"]])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=content-plan-{ym}.csv"})


# ---------- идеи и сценарии ----------

IDEA_ST = {"new": "новая", "work": "в работе", "done": "снято", "dropped": "отложено"}


class IdeaIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str | None = Field(default=None, max_length=8000)
    kind: str = "reels"
    object_id: int | None = None
    status: str = Field(default="new", pattern="^(new|work|done|dropped)$")


@router.get("/mkt/ideas")
def ideas(p: dict = Depends(active)):
    _mkt(p)
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT i.*, pe.full_name AS author, o.title AS object_title FROM mkt_ideas i
                               JOIN people pe ON pe.id=i.author_id LEFT JOIN objects o ON o.id=i.object_id
                               ORDER BY i.status IN ('done','dropped'), i.updated_at DESC LIMIT 300""").fetchall()
    return {"items": rows, "statuses": IDEA_ST, "kinds": KINDS}


@router.post("/mkt/ideas")
@router.post("/mkt/ideas/{idea_id}")
def idea_save(b: IdeaIn, idea_id: int | None = None, p: dict = Depends(active)):
    _job(p, IDEA_JOBS, "идеи")
    if b.kind not in KINDS:
        raise HTTPException(400, "bad kind")
    with db.pool.connection() as conn, conn.transaction():
        if idea_id:
            r = conn.execute("""UPDATE mkt_ideas SET title=%s, text=%s, kind=%s, object_id=%s, status=%s, updated_at=now()
                                WHERE id=%s RETURNING id""", (b.title.strip(), b.text, b.kind, b.object_id, b.status, idea_id)).fetchone()
            if not r:
                raise HTTPException(404)
        else:
            r = conn.execute("""INSERT INTO mkt_ideas (title, text, kind, object_id, status, author_id) VALUES (%s,%s,%s,%s,%s,%s)
                                RETURNING id""", (b.title.strip(), b.text, b.kind, b.object_id, b.status, p["id"])).fetchone()
        db.audit(conn, p["id"], "mkt_idea_save", "mkt_ideas", r["id"], {"title": b.title, "status": b.status})
    return {"id": r["id"]}


# ---------- графики съёмок ----------

class ShootIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    shoot_date: date
    at_time: str | None = Field(default=None, max_length=40)
    object_id: int | None = None
    place: str | None = Field(default=None, max_length=200)
    crew: list[int] = Field(default_factory=list, max_length=20)
    idea_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="planned", pattern="^(planned|done|cancelled)$")


@router.get("/mkt/shoots")
def shoots(ym: str | None = None, p: dict = Depends(active)):
    _mkt(p)
    y, mo = map(int, (ym or date.today().strftime("%Y-%m")).split("-"))
    t0, t1 = date(y, mo, 1), date(y + mo // 12, mo % 12 + 1, 1)
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT s.*, o.title AS object_title, i.title AS idea_title,
                                      (SELECT array_agg(full_name ORDER BY full_name) FROM people WHERE id = ANY(s.crew)) AS crew_names
                               FROM mkt_shoots s LEFT JOIN objects o ON o.id=s.object_id LEFT JOIN mkt_ideas i ON i.id=s.idea_id
                               WHERE s.status<>'cancelled' AND s.shoot_date >= %s AND s.shoot_date < %s
                               ORDER BY s.shoot_date, s.at_time NULLS LAST, s.id""", (t0, t1)).fetchall()
        team = conn.execute("""SELECT id, full_name, role_code FROM people WHERE status='active'
                               AND (role_code IN ('marketer','head','lead_designer') OR reels) ORDER BY role_code<>'marketer', full_name""").fetchall()
    return {"items": rows, "team": team}


HINTS = {"before": ("Скоро старт", "Сними стену «до»: общий план и детали, пока она пустая."),
         "start": ("Только начали", "Сними первые линии и команду за работой."),
         "process": ("Идёт работа", "Сними процесс: руки, краску, таймлапс."),
         "final": ("Работа сдана", "Сними финал: общий план, детали, отзыв клиента.")}


@router.get("/mkt/hints")
def shoot_hints(p: dict = Depends(active)):
    """«Что снять на этой неделе» (HEAD 14.11: видеограф всегда знает, что и где снимать).

    Берём проекты на «Выполнении»: ещё без смен — «до»; первые смены — старт; смены за 3 дня — процесс; сдан за 7 дней — финал.
    Не подсказываем, если клиент запретил публикацию или съёмка по объекту уже стоит (или была за последние 5 дней)."""
    _mkt(p)
    from .sync_objects import WORK
    with db.pool.connection() as conn:
        rows = conn.execute(
            """SELECT o.id, o.title, o.city, o.address, o.publish_ok, o.done_on, g.full_name AS gip,
                      sh.first_at, sh.last_at, coalesce(sh.n, 0) AS shifts,
                      (SELECT count(*) FROM files f WHERE f.object_id=o.id AND f.kind='media' AND f.status='ready') AS media
               FROM objects o LEFT JOIN people g ON g.id=o.gip_person_id
               LEFT JOIN LATERAL (SELECT min(started_at) AS first_at, max(started_at) AS last_at, count(*) AS n
                                  FROM shifts s WHERE s.object_id=o.id AND s.kind='work' AND s.status<>'cancelled') sh ON true
               WHERE o.id<>0 AND o.status='active' AND o.bitrix_stage=%s AND o.closed_at IS NULL AND o.publish_ok IS DISTINCT FROM false
                 AND NOT EXISTS (SELECT 1 FROM mkt_shoots m WHERE m.object_id=o.id AND m.status<>'cancelled'
                                 AND m.shoot_date >= current_date - 5)
               ORDER BY o.id DESC""", (WORK,)).fetchall()
        ideas = conn.execute("""SELECT i.id, i.title, i.kind FROM mkt_ideas i WHERE i.status='new'
                                AND NOT EXISTS (SELECT 1 FROM mkt_shoots m WHERE m.idea_id=i.id AND m.status<>'cancelled')
                                ORDER BY i.updated_at DESC LIMIT 5""").fetchall()
    today = date.today()
    out = []
    for r in rows:
        last = r["last_at"].date() if r["last_at"] else None
        first = r["first_at"].date() if r["first_at"] else None
        if r["done_on"] and (today - r["done_on"]).days <= 7:
            k = "final"
        elif r["done_on"]:
            continue
        elif not r["shifts"]:
            k = "before"
        elif (today - first).days <= 3:
            k = "start"
        elif (today - last).days <= 3:
            k = "process"
        else:
            continue
        out.append({"object_id": r["id"], "title": r["title"], "city": r["city"], "address": r["address"], "gip": r["gip"],
                    "why": k, "label": HINTS[k][0], "what": HINTS[k][1], "media": r["media"], "ask_client": r["publish_ok"] is None})
    order = {"final": 0, "start": 1, "before": 2, "process": 3}
    out.sort(key=lambda x: (order[x["why"]], x["media"]))
    return {"items": out[:12], "ideas": ideas}


@router.post("/mkt/shoots")
@router.post("/mkt/shoots/{shoot_id}")
def shoot_save(b: ShootIn, shoot_id: int | None = None, p: dict = Depends(active)):
    _job(p, SHOOT_JOBS, "съёмки")
    vals = (b.title.strip(), b.shoot_date, b.at_time, b.object_id, b.place, b.crew, b.idea_id, b.note, b.status)
    with db.pool.connection() as conn, conn.transaction():
        if shoot_id:
            cur = conn.execute("SELECT status FROM mkt_shoots WHERE id=%s", (shoot_id,)).fetchone()
            if cur and cur["status"] == "proposed" and b.status != "cancelled":   # ждёт ГИП — подтверждают в карточке проекта (HEAD 14.11)
                vals = (*vals[:-1], "proposed")
            r = conn.execute("""UPDATE mkt_shoots SET title=%s, shoot_date=%s, at_time=%s, object_id=%s, place=%s, crew=%s, idea_id=%s,
                                note=%s, status=%s, updated_at=now() WHERE id=%s RETURNING id""", (*vals, shoot_id)).fetchone()
            if not r:
                raise HTTPException(404)
        else:
            r = conn.execute("""INSERT INTO mkt_shoots (title, shoot_date, at_time, object_id, place, crew, idea_id, note, status, author_id)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (*vals, p["id"])).fetchone()
        if b.idea_id and b.status != "cancelled":   # идею взяли в съёмку — «в работе», сняли — «снято»
            conn.execute("UPDATE mkt_ideas SET status=%s, updated_at=now() WHERE id=%s AND status IN ('new','work')",
                         ("done" if b.status == "done" else "work", b.idea_id))
        db.audit(conn, p["id"], "mkt_shoot_save", "mkt_shoots", r["id"], {"title": b.title, "status": b.status})
    return {"id": r["id"]}
