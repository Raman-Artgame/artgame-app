"""Бот для кандидатов (HEAD 28.11: «через телеграм бота… что бы человек сразу получал информацию», «автоматически»).

Кандидат после анкеты жмёт «Получать ответы в Telegram» → t.me/<бот>?start=c_<токен> → бот запоминает его chat id
(candidates.tg_id). Дальше бот сам пишет ему на каждом шаге: собеседование, выбор дня пробной, подтверждённое
приглашение (когда, куда, кто встретит), напоминание накануне, решение. Кнопка в сообщении — его личная страница /?me=.
Написать человеку первым бот не может (правило Telegram), поэтому без привязки у HEAD остаётся WhatsApp.
Сбой Telegram не ломает шаг — только строка в журнале службы.
"""
import sys
from datetime import date, datetime, timedelta, timezone

from . import db
from .config import settings

BOT = "artgame_team_bot"
ALMATY = timezone(timedelta(hours=5))


def me_link(c: dict) -> str:
    return f"{settings.public_origin.rstrip('/')}/?me={c['token']}"


def first(c: dict) -> str:
    return (c["full_name"] or "").split(" ")[-1]   # в анкете «Фамилия Имя», как hello() в карточке HEAD


def day_text(d: date | None) -> str:
    if not d:
        return "дата уточняется"
    wd = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][d.weekday()]
    return f"{d:%d.%m} ({wd})"


def send(c: dict, text: str, app: bool = False) -> bool:
    """Кандидату в бот. app=True — кнопка «Открыть ARTGAME» (уже принят), иначе — его страница."""
    if not (c.get("tg_id") and settings.bot_token):
        return False
    kb = {"text": "Открыть ARTGAME", "web_app": {"url": settings.public_origin.rstrip("/") + "/"}} if app else \
        {"text": "Подробнее", "url": me_link(c)}
    try:
        from .tgbot import CALL
        CALL("sendMessage", chat_id=c["tg_id"], text=text, reply_markup={"inline_keyboard": [[kb]]})
        return True
    except Exception as e:  # noqa: BLE001
        print("hrbot send:", c.get("id"), e, file=sys.stderr)
        return False


def to_staff(tg_id: int | None, text: str) -> None:
    if not (tg_id and settings.bot_token):
        return
    try:
        from . import notify as nt
        nt.SEND(tg_id, text)
    except Exception as e:  # noqa: BLE001
        print("hrbot staff:", e, file=sys.stderr)


def invite(conn, c: dict) -> dict:
    """Что кандидат должен знать о пробном дне. Одно и то же — в боте, на его странице и в WhatsApp от HEAD."""
    o = c["trial_object"] and conn.execute("SELECT title, city FROM objects WHERE id=%s", (c["trial_object"],)).fetchone()
    by = c["trial_by"] and conn.execute("SELECT full_name, phone FROM people WHERE id=%s", (c["trial_by"],)).fetchone()
    return {"day": c["trial_on"] and c["trial_on"].isoformat(), "time": c["trial_time"],
            "place": c["trial_place"] or (o and ", ".join(x for x in (o["title"], o["city"]) if x)) or None,
            "bring": c["trial_bring"], "who": by and by["full_name"], "who_phone": by and by["phone"],
            "state": c["trial_state"] or ("ok" if c["trial_on"] else "pick"),
            "sent_at": c["trial_sent_at"] and c["trial_sent_at"].isoformat()}


def invite_text(conn, c: dict) -> str:
    v = invite(conn, c)
    rows = [f"{first(c)}, ждём вас на пробный день в ARTGAME.",
            f"Когда: {day_text(c['trial_on'])}" + (f", в {v['time']}" if v["time"] else ""),
            v["place"] and f"Куда: {v['place']}",
            v["who"] and f"Встретит: {v['who']}" + (f", {v['who_phone']}" if v["who_phone"] else ""),
            v["bring"] and f"Взять с собой: {v['bring']}",
            "Пробный день оплачивается, если вас возьмут в команду. Не получается прийти — сразу напишите куратору."]
    return "\n".join(x for x in rows if x)


# ---------- шаги ----------

def on_step(conn, c: dict, old: dict) -> None:
    """После шага HEAD в карточке: что сказать кандидату. Вызывается внутри транзакции шага."""
    s = c["stage"]
    sent = False
    if s == "interview" and (old["stage"] != s or old["meet_on"] != c["meet_on"]):
        sent = send(c, f"{first(c)}, приглашаем на собеседование в ARTGAME: {day_text(c['meet_on'])}. Время и место напишем отдельно.")
    elif s == "trial" and c["trial_state"] == "pick" and (old["stage"] != s or old["trial_state"] != "pick"):
        sent = send(c, f"{first(c)}, приглашаем на пробный день в ARTGAME — день работы на объекте с куратором.\n"
                       "Выберите удобный день по кнопке «Подробнее». Куратор подтвердит и пришлёт время и адрес.")
    elif s == "trial" and c["trial_state"] == "ok" and not c["trial_sent_at"]:
        sent = send(c, invite_text(conn, c))
    elif s in ("reserve", "rejected") and old["stage"] != s and not c["self_refused"]:
        sent = send(c, f"{first(c)}, спасибо за анкету и потраченное время. Сейчас позвать в команду не можем, "
                       "но анкета осталась у нас: когда появится место, напишем.")
    elif s == "hired" and old["stage"] != s:
        sent = send(c, f"{first(c)}, вы в команде ARTGAME!\nНажмите «Открыть ARTGAME» ниже или кнопку «ARTGAME» внизу чата, "
                       f"введите имя и этот номер — {c['phone']}. Приложение покажет правила, ТБ и первые шаги.", app=True)
    if sent and s == "trial" and c["trial_state"] == "ok":
        conn.execute("UPDATE candidates SET trial_sent_at=now() WHERE id=%s", (c["id"],))


def ask_gip(conn, c: dict) -> None:
    """Кандидат (или HEAD) предложил день — куратору подтвердить."""
    g = c["trial_by"] and conn.execute("SELECT tg_id FROM people WHERE id=%s", (c["trial_by"],)).fetchone()
    to_staff(g and g["tg_id"], f"Пробный день кандидата {c['full_name']}: предложен {day_text(c['trial_on'])}. "
                               "Подтверди день, время и место или поставь другой день — карточка вверху приложения.")


def confirmed(conn, c: dict) -> None:
    if send(c, invite_text(conn, c)):
        conn.execute("UPDATE candidates SET trial_sent_at=now() WHERE id=%s", (c["id"],))


# ---------- привязка ----------

def link(chat_id: int, payload: str, first_name: str = "") -> str | None:
    """/start c_<токен> → кандидат привязан. Возвращает ответ бота или None (не наш payload)."""
    if not payload.startswith("c_"):
        return None
    token = payload[2:]
    with db.pool.connection() as conn, conn.transaction():
        c = conn.execute("SELECT * FROM candidates WHERE token=%s FOR UPDATE", (token,)).fetchone() if 16 <= len(token) <= 64 else None
        if not c:
            return "Ссылка не сработала. Откройте анкету ещё раз и нажмите «Получать ответы в Telegram»."
        conn.execute("UPDATE candidates SET tg_id=%s, updated_at=now() WHERE id=%s", (chat_id, c["id"]))
        db.audit(conn, None, "hr_tg_link", "candidates", c["id"], {})
    return (f"{first(c) or first_name}, готово! Ответ по анкете ARTGAME придёт сюда: собеседование, пробный день, решение.\n"
            "Писать сюда ничего не нужно.")


# ---------- напоминания (таймер sync_objects, каждые 10 минут) ----------

def tick(conn, now: datetime | None = None) -> dict:
    now = now or datetime.now(ALMATY)
    today = now.date()
    n = {"remind": 0, "nag": 0}
    if now.hour >= 18:   # накануне вечером — кандидату и куратору
        for c in conn.execute("""SELECT c.*, pe.tg_id AS gip_tg FROM candidates c LEFT JOIN people pe ON pe.id=c.trial_by
                                 WHERE c.stage='trial' AND c.trial_state='ok' AND c.trial_on=%s AND c.trial_remind_at IS NULL""",
                              (today + timedelta(days=1),)).fetchall():
            send(c, "Напоминаем: завтра пробный день.\n" + invite_text(conn, c))
            to_staff(c["gip_tg"], f"Завтра пробный день: {c['full_name']}, тел. {c['phone']}"
                                  + (f", в {c['trial_time']}" if c["trial_time"] else "") + ". После смены — оценка в приложении.")
            conn.execute("UPDATE candidates SET trial_remind_at=now() WHERE id=%s", (c["id"],))
            n["remind"] += 1
    if now.hour >= 10:   # день прошёл, оценки нет — куратору один раз
        for c in conn.execute("""SELECT c.*, pe.tg_id AS gip_tg FROM candidates c LEFT JOIN people pe ON pe.id=c.trial_by
                                 WHERE c.stage='trial' AND c.trial_on < %s AND c.trial_reviewed_at IS NULL AND c.trial_nag_at IS NULL""",
                              (today,)).fetchall():
            to_staff(c["gip_tg"], f"Оцени пробный день {c['full_name']}: звёзды, 7 пунктов и комментарий. Или отметь «Не пришёл». "
                                  "Карточка вверху приложения.")
            conn.execute("UPDATE candidates SET trial_nag_at=now() WHERE id=%s", (c["id"],))
            n["nag"] += 1
    return n
