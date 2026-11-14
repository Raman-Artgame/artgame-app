"""Рабочее место маркетинга (HEAD 14.11): контент-план с утверждением HEAD каждой публикации.

Маркетолог (и HEAD) ставит публикацию в план: что, где, когда, текст и материал из «Медиа» (фото/видео/рилс с объектов).
Черновик → «Отправить HEAD» → HEAD «Утверждаю» или «Вернуть» с причиной → после выхода — «Опубликовано» со ссылкой.
Неутверждённую публикацию отметить вышедшей нельзя. Ничего не удаляем: «Отменить» = status cancelled.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .files import links
from .work import active

router = APIRouter(prefix="/api")
MKT = {"marketer", "head"}
CHANNELS = {"instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube", "2gis": "2ГИС", "site": "Сайт", "other": "Другое"}
KINDS = {"reels": "Рилс", "post": "Пост", "carousel": "Карусель", "stories": "Сторис"}
EDITABLE = ("draft", "rejected")


def _mkt(p: dict) -> dict:
    if p["role_code"] not in MKT:
        raise HTTPException(403, "контент-план — у маркетинга и HEAD")
    return p


def _files(conn, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    rows = conn.execute("""SELECT f.*, pe.full_name AS by FROM files f JOIN people pe ON pe.id=f.uploaded_by
                           WHERE f.id = ANY(%s) AND f.kind='media'""", (ids,)).fetchall()
    by = {r["id"]: r for r in rows}
    return [links(by[i]) for i in ids if i in by]


def _out(conn, r: dict) -> dict:
    return {**{k: r[k] for k in ("id", "title", "channel", "kind", "plan_date", "caption", "object_id", "status", "author_id",
                                 "submitted_at", "reviewed_at", "review_note", "url", "published_at", "created_at")},
            "author": r.get("author"), "object_title": r.get("object_title"), "files": _files(conn, list(r["file_ids"] or []))}


SQL = """SELECT m.*, pe.full_name AS author, o.title AS object_title FROM mkt_posts m
         JOIN people pe ON pe.id=m.author_id LEFT JOIN objects o ON o.id=m.object_id"""


def _get(conn, post_id: int, lock: bool = False) -> dict:
    r = conn.execute(SQL + " WHERE m.id=%s" + (" FOR UPDATE OF m" if lock else ""), (post_id,)).fetchone()
    if not r:
        raise HTTPException(404)
    return r


@router.get("/mkt/dict")
def mkt_dict(p: dict = Depends(active)):
    _mkt(p)
    return {"channels": CHANNELS, "kinds": KINDS}


@router.get("/mkt/posts")
def posts(ym: str | None = None, status: str | None = None, p: dict = Depends(active)):
    """Месяц плана (ym=ГГГГ-ММ) — плюс без даты; status=pending — всё, что ждёт HEAD, за любой месяц."""
    _mkt(p)
    with db.pool.connection() as conn:
        if status:
            rows = conn.execute(SQL + " WHERE m.status=%s ORDER BY m.plan_date NULLS LAST, m.id", (status,)).fetchall()
        else:
            y, mo = map(int, (ym or date.today().strftime("%Y-%m")).split("-"))
            t0, t1 = date(y, mo, 1), date(y + mo // 12, mo % 12 + 1, 1)
            rows = conn.execute(SQL + """ WHERE m.status<>'cancelled' AND (m.plan_date IS NULL OR (m.plan_date >= %s AND m.plan_date < %s))
                                          ORDER BY m.plan_date NULLS FIRST, m.id""", (t0, t1)).fetchall()
        items = [_out(conn, r) for r in rows]
    n = {s: sum(1 for x in items if x["status"] == s) for s in ("draft", "pending", "approved", "rejected", "published")}
    return {"items": items, "counts": n, "channels": CHANNELS, "kinds": KINDS}


class PostIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    channel: str = "instagram"
    kind: str = "reels"
    plan_date: date | None = None
    caption: str | None = Field(default=None, max_length=4000)
    file_ids: list[int] = Field(default_factory=list, max_length=20)
    object_id: int | None = None


def _check(conn, b: PostIn):
    if b.channel not in CHANNELS or b.kind not in KINDS:
        raise HTTPException(400, "bad channel/kind")
    if b.file_ids:
        ok = conn.execute("SELECT count(*) AS n FROM files WHERE id = ANY(%s) AND kind='media' AND status='ready'", (b.file_ids,)).fetchone()["n"]
        if ok != len(set(b.file_ids)):
            raise HTTPException(400, "материал не найден в «Медиа»")


@router.post("/mkt/posts")
def post_add(b: PostIn, p: dict = Depends(active)):
    _mkt(p)
    with db.pool.connection() as conn, conn.transaction():
        _check(conn, b)
        r = conn.execute("""INSERT INTO mkt_posts (title, channel, kind, plan_date, caption, file_ids, object_id, author_id)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                         (b.title.strip(), b.channel, b.kind, b.plan_date, b.caption, b.file_ids, b.object_id, p["id"])).fetchone()
        db.audit(conn, p["id"], "mkt_post_add", "mkt_posts", r["id"], {"title": b.title})
        return _out(conn, _get(conn, r["id"]))


@router.post("/mkt/posts/{post_id}")
def post_edit(post_id: int, b: PostIn, p: dict = Depends(active)):
    """Править можно черновик и возвращённое; возвращённое после правки снова черновик."""
    _mkt(p)
    with db.pool.connection() as conn, conn.transaction():
        r = _get(conn, post_id, lock=True)
        if r["status"] not in EDITABLE:
            raise HTTPException(409, "править можно черновик или возвращённое")
        _check(conn, b)
        conn.execute("""UPDATE mkt_posts SET title=%s, channel=%s, kind=%s, plan_date=%s, caption=%s, file_ids=%s, object_id=%s,
                        status='draft', updated_at=now() WHERE id=%s""",
                     (b.title.strip(), b.channel, b.kind, b.plan_date, b.caption, b.file_ids, b.object_id, post_id))
        return _out(conn, _get(conn, post_id))


def _move(post_id: int, p: dict, frm: tuple, to: str, sets: str = "", args: tuple = (), action: str = "", data: dict | None = None):
    with db.pool.connection() as conn, conn.transaction():
        r = _get(conn, post_id, lock=True)
        if r["status"] not in frm:
            raise HTTPException(409, "уже не на этом шаге")
        conn.execute(f"UPDATE mkt_posts SET status=%s, updated_at=now(){sets} WHERE id=%s", (to, *args, post_id))
        db.audit(conn, p["id"], action or f"mkt_post_{to}", "mkt_posts", post_id, data or {})
        return _out(conn, _get(conn, post_id))


@router.post("/mkt/posts/{post_id}/submit")
def post_submit(post_id: int, p: dict = Depends(active)):
    _mkt(p)
    with db.pool.connection() as conn:
        r = _get(conn, post_id)
    if not r["plan_date"]:
        raise HTTPException(400, "поставь дату выхода")
    if not r["file_ids"] and not (r["caption"] or "").strip():
        raise HTTPException(400, "добавь материал или текст — HEAD должен видеть, что выйдет")
    return _move(post_id, p, EDITABLE, "pending", ", submitted_at=now(), review_note=NULL")


class ReviewIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


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
    _mkt(p)
    url = (b.url or "").strip() or None
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(400, "ссылка должна начинаться с https://")
    return _move(post_id, p, ("approved",), "published", ", url=%s, published_at=now()", (url,))


@router.post("/mkt/posts/{post_id}/cancel")
def post_cancel(post_id: int, p: dict = Depends(active)):
    _mkt(p)
    return _move(post_id, p, ("draft", "pending", "approved", "rejected"), "cancelled")
