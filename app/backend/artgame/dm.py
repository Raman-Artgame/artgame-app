"""«Чат» (HEAD 09.11 «написать всем прямо в приложении»; 11.11 «грамотный блок чат: обращения общие к HEAD и личные»).

Подгруппы у сотрудника: 📣 «Объявления» (рассылки любого HEAD, только чтение), 🏢 «Руководство» (видят и отвечают
ВСЕ HEAD, подпись — кто ответил), 👤 личный чат с КАЖДЫМ HEAD отдельно (видят только двое).
У каждого HEAD одинаково: «Руководство» — всё от всех, личные чаты — только свои, «Написать всем» (всем или по ролям).
Бот (HEAD 10–11.11): в Telegram уходят ТОЛЬКО объявления; о личном и «Руководстве» бот молчит. Текст сотрудника боту
(кроме /start) попадает в «Руководство». Ничего не удаляется. В таблице dm: head_id — личный чат с этим HEAD,
NULL (не рассылка) — «Руководство», broadcast_id — «Объявления».
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
    """'news' | 'group' | 'head:<id>' → (вид, id HEAD)."""
    if key in ("news", "group"):
        return key, None
    if key.startswith("head:") and key[5:].isdigit():
        h = conn.execute("SELECT id FROM people WHERE id=%s AND role_code='head' AND status='active'", (int(key[5:]),)).fetchone()
        if h:
            return "head", h["id"]
    raise HTTPException(404, "нет такого чата")


def _where(kind: str, hid: int | None) -> tuple[str, tuple]:
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
    """Непрочитанное у HEAD: «Руководство» (общее) + его личные чаты."""
    return conn.execute("""SELECT count(*) FILTER (WHERE head_id IS NULL) AS group, count(*) FILTER (WHERE head_id = %s) AS mine,
                                  count(DISTINCT person_id) AS people FROM dm
                           WHERE NOT from_head AND read_at IS NULL AND broadcast_id IS NULL AND (head_id IS NULL OR head_id = %s)""",
                        (hid, hid)).fetchone()


def _as_head(p: dict) -> bool:
    return p["role_code"] == "head" and not p.get("_view_as")


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX)


@router.get("/unread")
def unread(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        if _as_head(p):
            u = _head_unread(conn, p["id"])
            return {"n": u["group"] + u["mine"]}
        return {"n": conn.execute("SELECT count(*) AS n FROM dm WHERE person_id=%s AND from_head AND read_at IS NULL",
                                  (p["id"],)).fetchone()["n"]}


# ---------- сотрудник ----------

@router.get("/rooms")
def rooms(p: dict = Depends(active)):
    """Подгруппы сотрудника: Объявления, Руководство, личный чат с каждым HEAD."""
    with db.pool.connection() as conn:
        def info(kind, hid):
            w, a = _where(kind, hid)
            return conn.execute(f"""SELECT count(*) FILTER (WHERE d.from_head AND d.read_at IS NULL) AS unread,
                                           (array_agg(d.text ORDER BY d.created_at DESC, d.id DESC))[1] AS last_text,
                                           max(d.created_at) AS last_at
                                    FROM dm d WHERE d.person_id=%s AND {w}""", (p["id"], *a)).fetchone()
        out = [{"key": "news", "kind": "news", "title": "Объявления", "about": "рассылки HEAD всем", **info("news", None)},
               {"key": "group", "kind": "group", "title": "Руководство", "about": "видят и отвечают все HEAD", **info("group", None)}]
        for h in _heads(conn):
            if h["id"] != p["id"]:
                out.append({"key": f"head:{h['id']}", "kind": "head", "title": h["full_name"], "about": "личный чат, видите только вы двое",
                            **info("head", h["id"])})
    return {"rooms": out}


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
            raise HTTPException(400, "в «Объявления» пишет только HEAD — ответить можно в «Руководство» или лично")
        return _add(conn, p["id"], p, False, hid, b.text.strip())


# ---------- HEAD (любой HEAD, одинаково) ----------

@router.get("/threads")
def threads(p: dict = Depends(require_head)):
    """«Руководство» — все, кто писал руководству; «Личные» — все активные сотрудники и мой личный чат с каждым."""
    with db.pool.connection() as conn:
        def lst(cond, a, only_with):
            return conn.execute(
                f"""SELECT * FROM (SELECT pe.id, pe.full_name, r.title AS role_title, l.text AS last_text, l.from_head AS last_from_head,
                           l.author AS last_author, l.created_at AS last_at,
                           (SELECT count(*) FROM dm u WHERE u.person_id=pe.id AND {cond.replace('d.', 'u.')} AND NOT u.from_head AND u.read_at IS NULL) AS unread
                    FROM people pe LEFT JOIN roles r ON r.code=pe.role_code
                    LEFT JOIN LATERAL (SELECT d.text, d.from_head, a.full_name AS author, d.created_at FROM dm d JOIN people a ON a.id=d.author_id
                                       WHERE d.person_id=pe.id AND {cond} ORDER BY d.created_at DESC, d.id DESC LIMIT 1) l ON true
                    WHERE pe.status='active' AND pe.role_code<>'head' {"AND l.created_at IS NOT NULL" if only_with else ""}) t
                    ORDER BY unread > 0 DESC, last_at DESC NULLS LAST, full_name""", (*a, *a)).fetchall()
        group = lst("d.broadcast_id IS NULL AND d.head_id IS NULL", (), True)
        mine = lst("d.broadcast_id IS NULL AND d.head_id = %s", (p["id"],), False)
        roles = conn.execute(
            """SELECT r.code, r.title, count(pe.id) AS n FROM roles r JOIN people pe ON pe.role_code=r.code
               WHERE pe.status='active' AND pe.tg_id > 0 AND r.code<>'head' GROUP BY r.code ORDER BY r.level, r.title""").fetchall()
        casts = conn.execute(
            """SELECT b.id, b.text, b.roles, b.sent, b.created_at, a.full_name AS author FROM dm_broadcasts b
               JOIN people a ON a.id=b.author_id ORDER BY b.created_at DESC LIMIT 10""").fetchall()
    return {"group": group, "items": mine, "roles": roles, "broadcasts": casts}


def _person(conn, pid: int) -> dict:
    who = conn.execute("""SELECT pe.id, pe.full_name, pe.tg_id, pe.role_code, pe.status, r.title AS role_title
                          FROM people pe LEFT JOIN roles r ON r.code=pe.role_code WHERE pe.id=%s""", (pid,)).fetchone()
    if not who or who["role_code"] == "head":
        raise HTTPException(404, "нет такого сотрудника")
    return who


def _hroom(room: str, p: dict) -> tuple[str, int | None]:
    if room == "group":
        return "group", None
    if room == "me":
        return "head", p["id"]
    raise HTTPException(400, "room: group или me")


@router.get("/with/{pid}")
def dialog(pid: int, room: str = "me", p: dict = Depends(require_head)):
    kind, hid = _hroom(room, p)
    with db.pool.connection() as conn:
        who = _person(conn, pid)
        items = _items(conn, pid, kind, hid)
        _read(conn, pid, kind, hid, by_head=True)
    return {"person": {k: who[k] for k in ("id", "full_name", "role_title", "status")}, "room": room, "items": items}


@router.post("/with/{pid}")
def write_one(pid: int, b: TextIn, room: str = "me", p: dict = Depends(require_head)):
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
        note = f"📣 {p['full_name']} · HEAD:\n{_short(text)}\n\nОтветить — в приложении: «Чат»."
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
            return "Сотрудникам пишите в приложении: «Ещё → Чат». Там «Руководство», личные чаты и «Написать всем»."
        _add(conn, p["id"], p, False, None, text[:MAX], via="tg")
    return "✓ Передал руководству. Ответ — в приложении: «Чат» → «Руководство»."
