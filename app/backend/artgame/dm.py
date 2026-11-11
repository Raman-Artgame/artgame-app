"""«Диалог с HEAD» (HEAD 09.11: «хочу всем сотрудникам написать прямо в приложении»).

- У каждого сотрудника вкладка «HEAD» — личный диалог: HEAD пишет, сотрудник отвечает.
- HEAD в «Ещё → Сообщения»: список диалогов (непрочитанные сверху), личный ответ, «Написать всем» — всем или по ролям.
- Бот (HEAD 10.11: «личные не должны засорять бот»): текстом в Telegram уходит ТОЛЬКО рассылка HEAD (всем или по ролям).
  Личные сообщения сотрудник↔HEAD — только в приложении, в бот о них не уходит ничего (HEAD 11.11, даже уведомления).
  Ответ сотрудника свайпом на рассылку или любой текст боту (кроме /start) попадает в его диалог в приложении.
Ничего не удаляется. Диалог общий для всех HEAD (если их несколько): сотрудник пишет «HEAD», подпись — кто ответил.
"""
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .deps import require_head
from .viewas import ctx
from .work import active

router = APIRouter(prefix="/api/dm")
MAX = 4000


def send(tg_id: int, text: str) -> int | None:
    """Уведомление бота с кнопкой «Открыть ARTGAME»; возвращает message_id (для ответа свайпом)."""
    from . import tgbot
    r = tgbot.CALL("sendMessage", chat_id=tg_id, text=text, reply_markup={"inline_keyboard": [[
        {"text": "Открыть ARTGAME", "web_app": {"url": tgbot.app_url()}}]]})
    return (r or {}).get("message_id")


SEND = send   # тесты подменяют


def _bot(method: str, **params):
    from . import tgbot
    return tgbot.CALL(method, **params)


BOT = _bot   # тесты подменяют


def ping(ids: list[int]) -> None:
    """HEAD 11.11: «чтобы сообщения не приходили в чат-бот» — о личных сообщениях бот больше НЕ пишет ничего,
    даже короткое уведомление. Остаётся только уборка: уведомление, присланное 10–11.11, удаляется из чата
    при следующем сообщении или прочтении. Новое — только в приложении (цифра на вкладке, полоса, «Пульт»)."""
    for rid in dict.fromkeys(ids):
        try:
            with db.pool.connection() as conn:
                cur = conn.execute("DELETE FROM dm_notice WHERE person_id=%s RETURNING tg_id, msg_id", (rid,)).fetchone()
            if cur:
                BOT("deleteMessage", chat_id=cur["tg_id"], message_id=cur["msg_id"])
        except Exception as e:  # noqa: BLE001 — человек сам удалил или прошло 48 ч
            print("dm notice delete:", e, file=sys.stderr)


def _head_ids(conn) -> list[int]:
    return [h["id"] for h in _heads(conn)]


def _real(tg) -> bool:
    return bool(tg and tg > 0 and settings.bot_token)   # tg_id < 0 — тестовые сотрудники, в Telegram их нет


def _deliver(jobs: list[tuple[int, int, str]]) -> None:
    """[(dm.id, tg_id, текст)] — отправить и запомнить номер уведомления. Ошибка одного не мешает остальным."""
    for dm_id, tg, text in jobs:
        try:
            mid = SEND(tg, text)
        except Exception as e:  # noqa: BLE001
            print("dm notify:", e, file=sys.stderr)
            continue
        if mid:
            with db.pool.connection() as conn:
                conn.execute("UPDATE dm SET tg_msg_id=%s WHERE id=%s", (mid, dm_id))


def _short(t: str, n: int = 700) -> str:
    return t if len(t) <= n else t[:n] + "…"


def _heads(conn) -> list[dict]:
    return conn.execute("SELECT id, tg_id FROM people WHERE role_code='head' AND status='active'").fetchall()


def _to_head(conn, p: dict, text: str, via: str = "app") -> tuple[dict, list]:
    row = conn.execute("INSERT INTO dm (person_id, from_head, author_id, text, via) VALUES (%s, false, %s, %s, %s) RETURNING *",
                       (p["id"], p["id"], text, via)).fetchone()
    db.audit(conn, p["id"], "dm_add", "dm", row["id"], {"via": via})
    return row, []   # HEAD 10.11: личные — только в приложении, в бот не дублируем


def _from_head(conn, head: dict, person: dict, text: str, via: str = "app", bid: int | None = None) -> tuple[dict, list]:
    row = conn.execute("""INSERT INTO dm (person_id, from_head, author_id, text, via, broadcast_id)
                          VALUES (%s, true, %s, %s, %s, %s) RETURNING *""", (person["id"], head["id"], text, via, bid)).fetchone()
    if not bid:   # HEAD 10.11: в бот — только общая рассылка, личные остаются в приложении
        return row, []
    note = f"📣 HEAD:\n{_short(text)}\n\nОтветить — во вкладке «HEAD» в приложении."
    return row, ([(row["id"], person["tg_id"], note)] if _real(person["tg_id"]) else [])


def _items(conn, pid: int) -> list[dict]:
    return conn.execute(
        """SELECT d.id, d.from_head, d.text, d.via, d.broadcast_id IS NOT NULL AS broadcast, d.read_at, d.created_at,
                  a.full_name AS author
           FROM dm d JOIN people a ON a.id=d.author_id WHERE d.person_id=%s ORDER BY d.created_at, d.id""", (pid,)).fetchall()


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX)


# ---------- сотрудник ----------

@router.get("")
def my_dialog(bg: BackgroundTasks, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        items = _items(conn, p["id"])
        if not ctx():   # HEAD «смотрит как» — прочтение не отмечаем за сотрудника
            conn.execute("UPDATE dm SET read_at=now() WHERE person_id=%s AND from_head AND read_at IS NULL", (p["id"],))
            bg.add_task(ping, [p["id"]])   # прочитал — уведомление из бота убрать
    return {"items": items}


@router.post("")
def write_head(b: TextIn, bg: BackgroundTasks, p: dict = Depends(active)):
    if p["role_code"] == "head" and not p.get("_view_as"):
        raise HTTPException(400, "HEAD пишет сотрудникам в «Сообщениях»")
    with db.pool.connection() as conn, conn.transaction():
        row, jobs = _to_head(conn, p, b.text.strip())
        heads = _head_ids(conn)
    bg.add_task(ping, heads)
    return row


@router.get("/unread")
def unread(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        if p["role_code"] == "head" and not p.get("_view_as"):
            n = conn.execute("SELECT count(*) AS n FROM dm WHERE NOT from_head AND read_at IS NULL").fetchone()["n"]
        else:
            n = conn.execute("SELECT count(*) AS n FROM dm WHERE person_id=%s AND from_head AND read_at IS NULL", (p["id"],)).fetchone()["n"]
    return {"n": n}


# ---------- HEAD ----------

@router.get("/threads")
def threads(p: dict = Depends(require_head)):
    """Все активные сотрудники: сначала с непрочитанным, потом по последнему сообщению, потом без переписки."""
    with db.pool.connection() as conn:
        rows = conn.execute(
            """SELECT pe.id, pe.full_name, pe.role_code, r.title AS role_title, pe.tg_id < 0 AS test,
                      l.text AS last_text, l.from_head AS last_from_head, l.created_at AS last_at,
                      (SELECT count(*) FROM dm u WHERE u.person_id=pe.id AND NOT u.from_head AND u.read_at IS NULL) AS unread
               FROM people pe LEFT JOIN roles r ON r.code=pe.role_code
               LEFT JOIN LATERAL (SELECT text, from_head, created_at FROM dm WHERE person_id=pe.id ORDER BY created_at DESC, id DESC LIMIT 1) l ON true
               WHERE pe.status='active' AND pe.role_code<>'head'
               ORDER BY (SELECT count(*) FROM dm u WHERE u.person_id=pe.id AND NOT u.from_head AND u.read_at IS NULL)>0 DESC,
                        l.created_at DESC NULLS LAST, pe.full_name""").fetchall()
        roles = conn.execute(
            """SELECT r.code, r.title, count(pe.id) AS n FROM roles r JOIN people pe ON pe.role_code=r.code
               WHERE pe.status='active' AND pe.tg_id > 0 AND r.code<>'head' GROUP BY r.code ORDER BY r.level, r.title""").fetchall()
        casts = conn.execute(
            """SELECT b.id, b.text, b.roles, b.sent, b.created_at, a.full_name AS author FROM dm_broadcasts b
               JOIN people a ON a.id=b.author_id ORDER BY b.created_at DESC LIMIT 10""").fetchall()
    return {"items": rows, "roles": roles, "broadcasts": casts}


def _person(conn, pid: int) -> dict:
    who = conn.execute("""SELECT pe.id, pe.full_name, pe.tg_id, pe.role_code, pe.status, r.title AS role_title
                          FROM people pe LEFT JOIN roles r ON r.code=pe.role_code WHERE pe.id=%s""", (pid,)).fetchone()
    if not who or who["role_code"] == "head":
        raise HTTPException(404, "нет такого сотрудника")
    return who


@router.get("/with/{pid}")
def dialog(pid: int, bg: BackgroundTasks, p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        who = _person(conn, pid)
        items = _items(conn, pid)
        conn.execute("UPDATE dm SET read_at=now() WHERE person_id=%s AND NOT from_head AND read_at IS NULL", (pid,))
        bg.add_task(ping, _head_ids(conn))
    return {"person": {k: who[k] for k in ("id", "full_name", "role_title", "status")}, "items": items}


@router.post("/with/{pid}")
def write_one(pid: int, b: TextIn, bg: BackgroundTasks, p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        who = _person(conn, pid)
        if who["status"] != "active":
            raise HTTPException(409, "у сотрудника закрыт вход")
        row, jobs = _from_head(conn, p, who, b.text.strip())
        conn.execute("UPDATE dm SET read_at=now() WHERE person_id=%s AND NOT from_head AND read_at IS NULL", (pid,))   # ответил — значит прочитал
        db.audit(conn, p["id"], "dm_add", "dm", row["id"], {"to": pid})
        heads = _head_ids(conn)
    bg.add_task(ping, [pid, *heads])
    return row


class CastIn(TextIn):
    roles: list[str] | None = Field(default=None, max_length=20)   # пусто — всем


@router.post("/broadcast")
def broadcast(b: CastIn, bg: BackgroundTasks, p: dict = Depends(require_head)):
    """Всем активным сотрудникам (или только этим ролям: основная, вторая или «и.о.»). Тестовых «Тест · роль» не трогаем."""
    roles = [r for r in (b.roles or []) if r and r != "head"] or None
    text = b.text.strip()
    with db.pool.connection() as conn, conn.transaction():
        people = conn.execute(
            """SELECT id, full_name, tg_id FROM people WHERE status='active' AND role_code<>'head' AND tg_id > 0
               AND (%s::text[] IS NULL OR role_code = ANY(%s) OR extra_roles && %s OR acting_role = ANY(%s)) ORDER BY id""",
            (roles, roles, roles, roles)).fetchall()
        if not people:
            raise HTTPException(409, "некому отправить: нет активных сотрудников с такими ролями")
        bid = conn.execute("INSERT INTO dm_broadcasts (author_id, text, roles, sent) VALUES (%s,%s,%s,%s) RETURNING id",
                           (p["id"], text, roles, len(people))).fetchone()["id"]
        jobs = []
        for who in people:
            jobs += _from_head(conn, p, who, text, bid=bid)[1]
        db.audit(conn, p["id"], "dm_broadcast", "dm_broadcasts", bid, {"roles": roles, "sent": len(people)})
    bg.add_task(_deliver, jobs)
    return {"id": bid, "sent": len(people)}


# ---------- из Telegram (tgbot.tg_hook) ----------

def from_telegram(tg_id: int, text: str, reply_to: int | None) -> str | None:
    """Личное сообщение боту. Возвращает ответ бота человеку или None (тогда бот шлёт обычное приветствие).
    Сотрудник: любое сообщение (кроме /start) → в его диалог с HEAD (без уведомления HEAD в бот).
    HEAD: ответ свайпом на старое уведомление сотрудника (до 10.11) → в диалог; иначе — подсказка писать в приложении."""
    text = (text or "").strip()
    if not text or text.startswith("/"):
        return None
    text = text[:MAX]
    with db.pool.connection() as conn, conn.transaction():
        from .deps import load_person
        p = load_person(conn, tg_id)
        if not p or p["status"] != "active":
            return None
        if p["role_code"] == "head":
            src = reply_to and conn.execute("SELECT person_id FROM dm WHERE tg_msg_id=%s AND NOT from_head ORDER BY id DESC LIMIT 1",
                                            (reply_to,)).fetchone()
            if not src:
                return "Сотрудникам пишите в приложении: «Ещё → Сообщения». Там же — «Написать всем»."
            who = _person(conn, src["person_id"])
            row, jobs = _from_head(conn, p, who, text, via="tg")
            conn.execute("UPDATE dm SET read_at=now() WHERE person_id=%s AND NOT from_head AND read_at IS NULL", (who["id"],))
            db.audit(conn, p["id"], "dm_add", "dm", row["id"], {"to": who["id"], "via": "tg"})
            done = f"✓ Отправлено: {who['full_name']}"
            notify = [who["id"], *_head_ids(conn)]
        else:
            row, jobs = _to_head(conn, p, text, via="tg")
            done = "✓ Передал HEAD. Ответ — во вкладке «HEAD» в приложении."
            notify = _head_ids(conn)
    ping(notify)
    return done
