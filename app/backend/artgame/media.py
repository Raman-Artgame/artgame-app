"""«Продакшн» (HEAD 08.11): Главный художник, Художник-Про и Мастер настенной печати загружают материал с объекта —
фото, видео, готовые рилс. Всё ложится в папку сделки «МЕДИА / Отчёты». HEAD утверждает лучшее → копия в «МЕДИА / Продакшн»;
утверждённый рилс идёт в ФОТ месяца: pay.reels за штуку, не больше pay.reels.max в месяц (лист «Значения»).

Загрузка — как у больших файлов (files.start_upload с kind=media): телефон грузит прямо в Google, сервер сверяет.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, drive
from .files import PROD, can_prod, links
from .work import active

router = APIRouter(prefix="/api")
TYPES = {"photo": "Фото", "video": "Видео", "reels": "Рилс"}
LIBRARY = {"lead_designer", "head"}   # медиатека для монтажа рилс (HEAD 10.11)

SQL = """SELECT f.*, pe.full_name AS by, o.title AS object_title, o.city AS object_city
         FROM files f JOIN people pe ON pe.id=f.uploaded_by JOIN objects o ON o.id=f.object_id
         WHERE f.kind='media' AND f.status='ready' AND {cond} ORDER BY f.created_at DESC LIMIT 200"""


def _out(f: dict) -> dict:
    return {**links(f), "object_title": f["object_title"], "object_city": f["object_city"], "reviewed_at": f["reviewed_at"]}


@router.get("/media")
def media_list(scope: str = "mine", object_id: int | None = None, type: str | None = None, p: dict = Depends(active)):
    """mine — своё (с отметками HEAD); review — ждёт решения HEAD; object — утверждённое по объекту (карточка проекта);
    object + type=video — все видео объекта (вкладка «Видео», HEAD 09.11): и ждущие HEAD, кроме возвращённых."""
    head = p["role_code"] == "head"
    if scope == "mine":
        cond, args = "f.uploaded_by=%s", [p["id"]]
    elif scope == "review":
        if not head:
            raise HTTPException(403, "только HEAD")
        cond, args = "f.review='pending'", []
    elif scope == "object" and object_id and type == "video":
        cond, args = ("f.object_id=%s AND f.media_type IN ('video', 'reels')" + ("" if head or can_prod(p) else " AND f.review <> 'rejected'")), [object_id]
    elif scope == "object" and object_id:
        cond, args = ("f.object_id=%s" + ("" if head or can_prod(p) else " AND f.review='approved'")), [object_id]
    elif scope == "library":   # HEAD 10.11: Главный дизайнер монтирует рилс — весь материал всех объектов, кроме возвращённого
        if p["role_code"] not in LIBRARY:
            raise HTTPException(403, "медиатека — у Главного дизайнера и HEAD")
        cond, args = "f.review IS DISTINCT FROM 'rejected'", []
        if type in TYPES:
            cond, args = cond + " AND coalesce(f.media_type, 'photo')=%s", [type]
        if object_id:
            cond, args = cond + " AND f.object_id=%s", args + [object_id]
    else:
        raise HTTPException(400, "bad scope")
    with db.pool.connection() as conn:
        rows = conn.execute(SQL.format(cond=cond), args).fetchall()
        v = {}
        if scope == "mine":
            from . import constants as consts
            v = consts.latest(conn)
    out = {"items": [_out(f) for f in rows], "types": TYPES}
    if scope == "mine":   # своя ставка за рилс — только если человек сам снимает рилс
        out["reels"] = {"rate": v.get("pay.reels"), "max": v.get("pay.reels.max")} if can_prod(p) else None
    return out


class ReviewIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


@router.post("/media/{file_id}/review")
def media_review(file_id: int, b: ReviewIn, p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "утверждает только HEAD")
    if not b.approve and not (b.note or "").strip():
        raise HTTPException(400, "reason required")
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT * FROM files WHERE id=%s AND kind='media' AND status='ready' FOR UPDATE", (file_id,)).fetchone()
        if not f:
            raise HTTPException(404)
        if f["review"] != "pending":
            raise HTTPException(409, "уже решено")
        prod_id = None
        if b.approve and f["media_type"] == "reels":
            prod_id = f["drive_id"]   # рилс уже лежит в «МЕДИА / Рилс» — второй копии не делаем
        elif b.approve:
            obj = conn.execute("SELECT * FROM objects WHERE id=%s", (f["object_id"],)).fetchone()
            try:
                d = drive.Drive()
                prod_id = d.copy(f["drive_id"], drive.folder_of(conn, obj, "prod", d, f["media_type"]), f["name"])
            except Exception as ex:
                raise HTTPException(502, f"drive: {ex.__class__.__name__}")
        conn.execute("""UPDATE files SET review=%s, reviewed_by=%s, reviewed_at=now(), review_note=%s, prod_drive_id=%s WHERE id=%s""",
                     ("approved" if b.approve else "rejected", p["id"], b.note, prod_id, file_id))
        db.audit(conn, p["id"], "media_review", "files", file_id, {"approve": b.approve, "type": f["media_type"], "note": b.note})
    return {"ok": True}


def reels_accruals(conn, v: dict, t0, t1) -> tuple[dict, list[str]]:
    """Утверждённые за месяц рилс по людям: {person_id: (сумма, описание, ссылки)}. Ставки — только из «Значений»."""
    rate, cap = v.get("pay.reels"), v.get("pay.reels.max")
    rows = conn.execute("""SELECT uploaded_by, array_agg(id ORDER BY reviewed_at) AS ids FROM files
                           WHERE kind='media' AND media_type='reels' AND review='approved' AND reviewed_at >= %s AND reviewed_at < %s
                           GROUP BY uploaded_by""", (t0, t1)).fetchall()
    out, warn = {}, []
    if rows and not rate:
        warn.append("рилс утверждены, но ставки pay.reels в «Значениях» нет — не начислено")
        return out, warn
    for r in rows:
        n = len(r["ids"])
        paid = min(n, int(cap)) if cap else n
        detail = f"рилс {paid} × {rate:,.0f} ₸".replace(",", " ") + (f" (утверждено {n}, в месяц до {int(cap)})" if paid < n else "")
        out[r["uploaded_by"]] = (paid * rate, detail, ",".join(str(i) for i in r["ids"][:paid]))
    return out, warn
