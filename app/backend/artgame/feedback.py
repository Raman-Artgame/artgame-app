"""«Написать обращение» (HEAD 08.11): любой сотрудник пишет HEAD — баг, доработка, вопрос. HEAD видит в «Пульте»,
отвечает и закрывает; ответ приходит человеку в «Кабинет» и сообщением бота. Ничего не удаляется."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .deps import require_head
from .work import active

router = APIRouter(prefix="/api")
KIND = {"bug": "🐞 Ошибка", "idea": "💡 Доработка", "question": "❓ Вопрос", "other": "✉️ Другое"}
STATUS = {"new": "новое", "work": "в работе", "done": "готово"}


def _send(tg_id, text: str) -> None:
    if not (tg_id and settings.bot_token):
        return
    try:
        from . import notify
        notify.SEND(tg_id, text)
    except Exception as e:  # noqa: BLE001
        print("feedback notify:", e)


class FeedbackIn(BaseModel):
    kind: Literal["bug", "idea", "question", "other"]
    text: str = Field(min_length=3, max_length=4000)
    place: str | None = Field(default=None, max_length=60)


@router.post("/feedback")
def send_feedback(b: FeedbackIn, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("""INSERT INTO feedback (person_id, role_code, kind, text, place) VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                           (p["id"], p["role_code"], b.kind, b.text.strip(), (b.place or "").strip() or None)).fetchone()
        db.audit(conn, p["id"], "feedback_add", "feedback", row["id"], {"kind": b.kind})
    if p["role_code"] != "head":
        _send(settings.head_tg_id, f"{KIND[b.kind]} от {p['full_name']}: {b.text.strip()[:300]}\nОтветить — «Пульт» → «Обращения».")
    return row


@router.get("/feedback/my")
def my_feedback(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {"items": conn.execute("SELECT * FROM feedback WHERE person_id=%s ORDER BY created_at DESC LIMIT 30", (p["id"],)).fetchall()}


@router.get("/feedback")
def all_feedback(status: str | None = None, p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        return {"items": conn.execute(
            """SELECT f.*, pe.full_name, r.title AS role_title FROM feedback f JOIN people pe ON pe.id=f.person_id
               LEFT JOIN roles r ON r.code=f.role_code WHERE (%s::text IS NULL OR f.status=%s)
               ORDER BY f.status='done', f.created_at DESC LIMIT 100""", (status, status)).fetchall()}


class AnswerIn(BaseModel):
    status: Literal["new", "work", "done"] | None = None
    answer: str | None = Field(default=None, max_length=4000)


@router.post("/feedback/{fid}")
def answer_feedback(fid: int, b: AnswerIn, p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT f.*, pe.tg_id FROM feedback f JOIN people pe ON pe.id=f.person_id WHERE f.id=%s", (fid,)).fetchone()
        if not f:
            raise HTTPException(404, "нет обращения")
        ans = (b.answer or "").strip() or None
        row = conn.execute("""UPDATE feedback SET status=coalesce(%s, status), answer=coalesce(%s, answer),
                              answered_by=CASE WHEN %s::text IS NOT NULL THEN %s ELSE answered_by END,
                              answered_at=CASE WHEN %s::text IS NOT NULL THEN now() ELSE answered_at END
                              WHERE id=%s RETURNING *""", (b.status, ans, ans, p["id"], ans, fid)).fetchone()
        db.audit(conn, p["id"], "feedback_answer", "feedback", fid, b.model_dump(exclude_none=True))
    if ans or b.status == "done":
        _send(f["tg_id"] if f["tg_id"] and f["tg_id"] > 0 else None,
              f"Ответ на обращение «{f['text'][:60]}»: {ans or 'сделано'}" + (" · готово" if row["status"] == "done" else ""))
    return row
