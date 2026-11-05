"""Уведомления МОП в Telegram (HEAD 05.11.2026): новая заявка без ответа, КП без ответа, задача Битрикса на сегодня,
пора вернуться к отложенной сделке. Запускается таймером каждые 15 минут, пишет только с 8 до 21 по Алматы,
каждое событие — один раз (таблица notices). Бот: ARTGAME_BOT_TOKEN, только в env сервера."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import httpx

from . import bx, db
from .config import settings

TZ = ZoneInfo("Asia/Almaty")
HOURS = (8, 21)


def send(tg_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    r = httpx.post(url, json={"chat_id": tg_id, "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": [[
        {"text": "Открыть приложение", "web_app": {"url": settings.public_origin + "/"}}]]}}, timeout=30)
    r.raise_for_status()


SEND = send  # тесты подменяют


def _title(d: dict) -> str:
    import re
    t = re.sub(rf"^№?\s*{d['id']}\s*·?\s*", "", d["title"] or "")
    return f"№ {d['id']} {t}".strip()


def events(p: dict, today: str) -> list[tuple[str, str]]:
    """(ключ, текст) для одного МОП по данным «Сегодня»."""
    t = bx.today(p)
    ev = []
    for d in t["back"]:
        ev.append((f"back:{d['id']}:{d['due']}", f"⏰ Пора вернуться к сделке {_title(d)}" + (f"\n{d['note']}" if d.get("note") else "")))
    for d in t["new"]:
        ev.append((f"new:{d['id']}", f"🆕 Новая заявка без ответа: {_title(d)}"))
    for d in t["kp"]:
        ev.append((f"kp:{d['id']}:{today}", f"📄 КП без ответа {t['limits']['kp_days']:g}+ дня: {_title(d)}"))
    for x in t.get("queue", {}).get("hot", []):
        if x["entity"] == "lead":
            ev.append((f"lead:{x['id']}:{today}", f"📞 Лид {x['name'] or x['title']}: {x['why']}"))
    for x in t["tasks"]:
        if (x.get("deadline") or "")[:10] == today:
            ev.append((f"task:{x['id']}:{today}", f"✅ Задача на сегодня: {x['title']}" + (f" (сделка № {x['deal']})" if x.get("deal") else "")))
    return ev


def run(now: datetime | None = None) -> int:
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    if not HOURS[0] <= now.hour < HOURS[1]:
        return 0
    today = now.date().isoformat()
    sent = 0
    with db.pool.connection() as conn:
        people = conn.execute("SELECT id, tg_id, full_name, role_code, status FROM people WHERE status='active' "
                              "AND bitrix_user_id IS NOT NULL AND role_code IN ('mop', 'mop_vip')").fetchall()
    for p in people:
        p = dict(p)
        try:
            ev = events(p, today)
        except Exception as ex:
            print(f"{p['full_name']}: {ex}")
            continue
        with db.pool.connection() as conn:
            done = {r["key"] for r in conn.execute("SELECT key FROM notices WHERE person_id=%s AND sent_at > now() - interval '3 days'",
                                                   (p["id"],)).fetchall()}
            fresh = [(k, txt) for k, txt in ev if k not in done]
            if not fresh:
                continue
            try:
                SEND(p["tg_id"], "\n\n".join(txt for _, txt in fresh))
            except Exception as ex:
                print(f"{p['full_name']}: telegram {ex}")
                continue
            for k, _ in fresh:
                conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (p["id"], k))
            conn.execute("UPDATE bx_reminders SET sent_at=now() WHERE person_id=%s AND due <= current_date AND sent_at IS NULL", (p["id"],))
            db.audit(conn, p["id"], "notify", data={"keys": [k for k, _ in fresh]})
            sent += len(fresh)
    return sent


def main():
    if not settings.bot_token:
        print("ARTGAME_BOT_TOKEN не задан — пропуск")
        return
    db.open_pool()
    print(f"sent={run()}")


if __name__ == "__main__":
    main()
