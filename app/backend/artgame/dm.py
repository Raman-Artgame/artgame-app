"""«Чат» как в Telegram (HEAD 11.11, третья версия: «объявления и вопросы к HEAD — одним, личные переписки — друг с другом»).

- «HEAD» — один чат у каждого сотрудника: объявления HEAD (всем/по ролям) + его вопросы руководству. Видят и отвечают
  ВСЕ HEAD (подпись — кто ответил); другие сотрудники чужие вопросы не видят. В dm: broadcast_id или head_id IS NULL.
- Личные чаты: любой ↔ любой (сотрудник ↔ сотрудник, HEAD ↔ сотрудник), видят только двое — таблица pm.
- Бот (HEAD 10–11.11): в Telegram уходят ТОЛЬКО объявления; о личном и вопросах бот молчит. Текст сотрудника боту → «HEAD».
Ничего не удаляется (личные чаты с HEAD до 11.11 из dm скопированы в pm, миграция 045).
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
    return conn.execute("""SELECT id, full_name, tg_id FROM people WHERE role_code='head' AND status='active'
                           ORDER BY id""").fetchall()


def _room(conn, key: str) -> tuple[str, int | None]:
    """'hq' (чат «HEAD») | 'news' | 'group' | 'head:<id>' (до 11.11) → (вид, id HEAD)."""
    if key in ("hq", "news", "group"):
        return key, None
    if key.startswith("head:") and key[5:].isdigit():
        h = conn.execute("SELECT id FROM people WHERE id=%s AND role_code='head' AND status='active'", (int(key[5:]),)).fetchone()
        if h:
            return "head", h["id"]
    raise HTTPException(404, "нет такого чата")


def _where(kind: str, hid: int | None) -> tuple[str, tuple]:
    if kind == "hq":
        return "(d.broadcast_id IS NOT NULL OR d.head_id IS NULL)", ()
    if kind == "news":
        return "d.broadcast_id IS NOT NULL", ()
    if kind == "group":
        return "d.broadcast_id IS NULL AND d.head_id IS NULL", ()
    return "d.broadcast_id IS NULL AND d.head_id = %s", (hid,)


def _items(conn, pid: int, kind: str, hid: int | None) -> list[dict]:
    w, a = _where(kind, hid)
    return conn.execute(
        f"""SELECT d.id, d.from_head, d.text, d.via, d.broadcast_id IS NOT NULL AS broadcast, d.read_at, d.created_at,
                   a.full_name AS author
            FROM dm d JOIN people a ON a.id=d.author_id WHERE d.person_id=%s AND {w} ORDER BY d.created_at, d.id""", (pid, *a)).fetchall()


def _read(conn, pid: int, kind: str, hid: int | None, by_head: bool) -> None:
    w, a = _where(kind, hid)
    conn.execute(f"UPDATE dm d SET read_at=now() WHERE d.person_id=%s AND {w} AND d.from_head=%s AND d.read_at IS NULL",
                 (pid, *a, not by_head))


def _add(conn, person_id: int, author: dict, from_head: bool, head_id: int | None, text: str, via: str = "app", bid=None) -> dict:
    row = conn.execute("""INSERT INTO dm (person_id, from_head, author_id, head_id, text, via, broadcast_id)
                          VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                       (person_id, from_head, author["id"], head_id, text, via, bid)).fetchone()
    if not bid:
        db.audit(conn, author["id"], "dm_add", "dm", row["id"], {"to": person_id if from_head else ("head:" + str(head_id) if head_id else "group"), "via": via})
    return row


def _head_unread(conn, hid: int) -> dict:
    """Непрочитанное у HEAD: вопросы в «HEAD» (общие для всех HEAD) + личные мне."""
    g = conn.execute("""SELECT count(*) AS n, count(DISTINCT person_id) AS people FROM dm
                        WHERE NOT from_head AND read_at IS NULL AND broadcast_id IS NULL AND head_id IS NULL""").fetchone()
    m = conn.execute("SELECT count(*) AS n, count(DISTINCT sender_id) AS people FROM pm WHERE recipient_id=%s AND read_at IS NULL", (hid,)).fetchone()
    return {"group": g["n"], "mine": m["n"], "people": g["people"] + m["people"]}


def _pm_unread(conn, pid: int) -> int:
    return conn.execute("SELECT count(*) AS n FROM pm WHERE recipient_id=%s AND read_at IS NULL", (pid,)).fetchone()["n"]


def _as_head(p: dict) -> bool:
    return p["role_code"] == "head" and not p.get("_view_as")


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX)


@router.get("/unread")
def unread(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        from .projchat import unread as proj
        if _as_head(p):
            u = _head_unread(conn, p["id"])
            return {"n": u["group"] + u["mine"] + proj(conn, p)}
        hq = conn.execute("""SELECT count(*) AS n FROM dm WHERE person_id=%s AND from_head AND read_at IS NULL
                             AND (broadcast_id IS NOT NULL OR head_id IS NULL)""", (p["id"],)).fetchone()["n"]
        return {"n": hq + _pm_unread(conn, p["id"]) + proj(conn, p)}


# ---------- сотрудник ----------

@router.get("/list")
def chat_list(p: dict = Depends(active)):
    """Список «Чата»: сверху «HEAD», ниже все люди команды (с перепиской — сначала, по свежести; потом по имени)."""
    me = p["id"]
    with db.pool.connection() as conn:
        if _as_head(p):
            u = _head_unread(conn, me)
            last = conn.execute("""SELECT d.text, d.created_at, pe.full_name FROM dm d JOIN people pe ON pe.id=d.person_id
                                   WHERE d.broadcast_id IS NULL AND d.head_id IS NULL ORDER BY d.created_at DESC LIMIT 1""").fetchone()
            hq = {"unread": u["group"], "last_text": last and f"{last['full_name']}: {last['text']}", "last_at": last and last["created_at"]}
        else:
            hq = conn.execute("""SELECT count(*) FILTER (WHERE d.from_head AND d.read_at IS NULL) AS unread,
                                        (array_agg(d.text ORDER BY d.created_at DESC, d.id DESC))[1] AS last_text, max(d.created_at) AS last_at
                                 FROM dm d WHERE d.person_id=%s AND (d.broadcast_id IS NOT NULL OR d.head_id IS NULL)""", (me,)).fetchone()
        people = conn.execute(
            """SELECT * FROM (SELECT pe.id, pe.full_name, pe.role_code, r.title AS role_title,
                      l.text AS last_text, l.sender_id = %(me)s AS last_mine, l.created_at AS last_at,
                      (SELECT count(*) FROM pm u WHERE u.sender_id=pe.id AND u.recipient_id=%(me)s AND u.read_at IS NULL) AS unread
               FROM people pe LEFT JOIN roles r ON r.code=pe.role_code
               LEFT JOIN LATERAL (SELECT text, sender_id, created_at FROM pm
                                  WHERE (sender_id=pe.id AND recipient_id=%(me)s) OR (sender_id=%(me)s AND recipient_id=pe.id)
                                  ORDER BY created_at DESC, id DESC LIMIT 1) l ON true
               WHERE pe.status='active' AND pe.id<>%(me)s AND pe.tg_id > 0) t
               ORDER BY unread > 0 DESC, last_at DESC NULLS LAST, role_code <> 'head', full_name""", {"me": me}).fetchall()
        from .projchat import chats
        projects = chats(conn, p)
    return {"hq": hq, "people": people, "projects": projects}


def _peer(conn, pid: int, me: int) -> dict:
    who = conn.execute("""SELECT pe.id, pe.full_name, pe.status, pe.role_code, r.title AS role_title FROM people pe
                          LEFT JOIN roles r ON r.code=pe.role_code WHERE pe.id=%s""", (pid,)).fetchone()
    if not who or who["id"] == me:
        raise HTTPException(404, "нет такого человека")
    return who


@router.get("/pm/{pid}")
def pm_dialog(pid: int, p: dict = Depends(active)):
    """Личный чат двоих. Видят только эти двое (HEAD «смотрит как» — видит глазами сотрудника, прочтение не отмечается)."""
    me = p["id"]
    with db.pool.connection() as conn:
        who = _peer(conn, pid, me)
        items = conn.execute("""SELECT m.id, m.sender_id = %(me)s AS mine, m.text, m.via, m.read_at, m.created_at
                                FROM pm m WHERE (m.sender_id=%(me)s AND m.recipient_id=%(o)s) OR (m.sender_id=%(o)s AND m.recipient_id=%(me)s)
                                ORDER BY m.created_at, m.id""", {"me": me, "o": pid}).fetchall()
        if not ctx():
            conn.execute("UPDATE pm SET read_at=now() WHERE sender_id=%s AND recipient_id=%s AND read_at IS NULL", (pid, me))
    return {"person": {k: who[k] for k in ("id", "full_name", "role_title", "status")}, "items": items}


@router.post("/pm/{pid}")
def pm_write(pid: int, b: TextIn, p: dict = Depends(active)):
    me = p["id"]
    with db.pool.connection() as conn, conn.transaction():
        who = _peer(conn, pid, me)
        if who["status"] != "active":
            raise HTTPException(409, "у человека закрыт вход")
        row = conn.execute("INSERT INTO pm (sender_id, recipient_id, text) VALUES (%s,%s,%s) RETURNING *", (me, pid, b.text.strip())).fetchone()
        conn.execute("UPDATE pm SET read_at=now() WHERE sender_id=%s AND recipient_id=%s AND read_at IS NULL", (pid, me))   # ответил — прочитал
        db.audit(conn, me, "pm_add", "pm", row["id"], {"to": pid})
    return row


@router.get("/room/{key}")
def room(key: str, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        kind, hid = _room(conn, key)
        items = _items(conn, p["id"], kind, hid)
        if not ctx():   # HEAD «смотрит как» — прочтение не отмечаем за сотрудника
            _read(conn, p["id"], kind, hid, by_head=False)
    return {"items": items}


@router.post("/room/{key}")
def write_room(key: str, b: TextIn, p: dict = Depends(active)):
    if _as_head(p):
        raise HTTPException(400, "HEAD пишет сотрудникам в своём «Чате»")
    with db.pool.connection() as conn, conn.transaction():
        kind, hid = _room(conn, key)
        if kind == "news":
            raise HTTPException(400, "в «Объявления» пишет только HEAD")
        return _add(conn, p["id"], p, False, None if kind == "hq" else hid, b.text.strip())


# ---------- HEAD (любой HEAD, одинаково) ----------

@router.get("/threads")
def threads(p: dict = Depends(require_head)):
    """Чат «HEAD» у руководства: кто задавал вопросы (непрочитанные сверху), роли для объявлений, отправленные объявления."""
    with db.pool.connection() as conn:
        group = conn.execute(
            """SELECT * FROM (SELECT pe.id, pe.full_name, r.title AS role_title, l.text AS last_text, l.from_head AS last_from_head,
                      l.author AS last_author, l.created_at AS last_at,
                      (SELECT count(*) FROM dm u WHERE u.person_id=pe.id AND u.broadcast_id IS NULL AND u.head_id IS NULL
                         AND NOT u.from_head AND u.read_at IS NULL) AS unread
               FROM people pe LEFT JOIN roles r ON r.code=pe.role_code
               JOIN LATERAL (SELECT d.text, d.from_head, a.full_name AS author, d.created_at FROM dm d JOIN people a ON a.id=d.author_id
                             WHERE d.person_id=pe.id AND d.broadcast_id IS NULL AND d.head_id IS NULL
                             ORDER BY d.created_at DESC, d.id DESC LIMIT 1) l ON true
               WHERE pe.status='active' AND pe.role_code<>'head') t
               ORDER BY unread > 0 DESC, last_at DESC, full_name""").fetchall()
        roles = conn.execute(
            """SELECT r.code, r.title, count(pe.id) AS n FROM roles r JOIN people pe ON pe.role_code=r.code
               WHERE pe.status='active' AND pe.tg_id > 0 AND r.code<>'head' GROUP BY r.code ORDER BY r.level, r.title""").fetchall()
        casts = conn.execute(
            """SELECT b.id, b.text, b.roles, b.sent, b.created_at, a.full_name AS author FROM dm_broadcasts b
               JOIN people a ON a.id=b.author_id ORDER BY b.created_at DESC LIMIT 10""").fetchall()
    return {"group": group, "roles": roles, "broadcasts": casts}


def _person(conn, pid: int) -> dict:
    who = conn.execute("""SELECT pe.id, pe.full_name, pe.tg_id, pe.role_code, pe.status, r.title AS role_title
                          FROM people pe LEFT JOIN roles r ON r.code=pe.role_code WHERE pe.id=%s""", (pid,)).fetchone()
    if not who or who["role_code"] == "head":
        raise HTTPException(404, "нет такого сотрудника")
    return who


def _hroom(room: str, p: dict) -> tuple[str, int | None]:
    if room in ("group", "hq"):   # чат «HEAD» сотрудника: объявления + вопросы
        return "hq", None
    raise HTTPException(400, "личные чаты — /api/dm/pm/{id}")


@router.get("/with/{pid}")
def dialog(pid: int, room: str = "hq", p: dict = Depends(require_head)):
    kind, hid = _hroom(room, p)
    with db.pool.connection() as conn:
        who = _person(conn, pid)
        items = _items(conn, pid, kind, hid)
        _read(conn, pid, kind, hid, by_head=True)
    return {"person": {k: who[k] for k in ("id", "full_name", "role_title", "status")}, "room": room, "items": items}


@router.post("/with/{pid}")
def write_one(pid: int, b: TextIn, room: str = "hq", p: dict = Depends(require_head)):
    kind, hid = _hroom(room, p)
    with db.pool.connection() as conn, conn.transaction():
        who = _person(conn, pid)
        if who["status"] != "active":
            raise HTTPException(409, "у сотрудника закрыт вход")
        row = _add(conn, pid, p, True, hid, b.text.strip())
        _read(conn, pid, kind, hid, by_head=True)   # ответил — значит прочитал
    return row


class CastIn(TextIn):
    roles: list[str] | None = Field(default=None, max_length=20)   # пусто — всем


@router.post("/broadcast")
def broadcast(b: CastIn, bg: BackgroundTasks, p: dict = Depends(require_head)):
    """Объявление всем активным сотрудникам (или этим ролям: основная, вторая, «и.о.»); «Тест · роль» не получают.
    Единственное, что уходит в бот текстом."""
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
        note = f"📣 {p['full_name']} · HEAD:\n{_short(text)}\n\nОтветить — в приложении: «Чат» → «HEAD»."
        jobs = []
        for who in people:
            row = _add(conn, who["id"], p, True, p["id"], text, bid=bid)
            if _real(who["tg_id"]):
                jobs.append((row["id"], who["tg_id"], note))
        db.audit(conn, p["id"], "dm_broadcast", "dm_broadcasts", bid, {"roles": roles, "sent": len(people)})
    bg.add_task(_deliver, jobs)
    return {"id": bid, "sent": len(people)}


# ---------- из Telegram (tgbot.tg_hook) ----------

def from_telegram(tg_id: int, text: str, reply_to: int | None) -> str | None:
    """Личное сообщение боту → ответ бота или None (тогда обычное приветствие).
    Сотрудник: любой текст (кроме /start), в том числе ответ свайпом на объявление, — в «Руководство», без уведомлений.
    HEAD: подсказка писать в приложении."""
    text = (text or "").strip()
    if not text or text.startswith("/"):
        return None
    with db.pool.connection() as conn, conn.transaction():
        from .deps import load_person
        p = load_person(conn, tg_id)
        if not p or p["status"] != "active":
            return None
        if p["role_code"] == "head":
            return "Сотрудникам пишите в приложении: «Ещё → Чат». Там «HEAD» (вопросы и объявления) и личные чаты."
        _add(conn, p["id"], p, False, None, text[:MAX], via="tg")
    return "✓ Передал руководству. Ответ — в приложении: «Чат» → «HEAD»."
