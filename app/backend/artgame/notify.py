"""Уведомления МОП в Telegram (HEAD 05.11.2026): новая заявка без ответа, КП без ответа, задача Битрикса на сегодня,
пора вернуться к отложенной сделке. Запускается таймером каждые 15 минут, пишет только с 8 до 21 по Алматы,
каждое событие — один раз (таблица notices). С 06.11: в 9:00 одна утренняя сводка со всем на день, остальное время —
сразу только «горит» (новая заявка, лид ждёт, пора вернуться); КП и задачи ждут сводки. Бот: ARTGAME_BOT_TOKEN, только в env сервера."""
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


_last: dict = {}


def t_queue(p: dict) -> dict:
    return _last.get(p["id"], {}).get("queue", {"hot": [], "today": []})


def events(p: dict, today: str) -> list[tuple[str, str]]:
    """(ключ, текст) для одного МОП по данным «Сегодня»."""
    t = bx.today(p)
    _last[p["id"]] = t
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


DIGEST_HOUR = 9   # утренняя сводка (HEAD 06.11): всё на день одним сообщением; до неё и после — сразу только «горит»
HOT = ("back", "new", "lead")


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
            digest = now.hour >= DIGEST_HOUR and f"digest:{today}" not in done
            fresh = [(k, txt) for k, txt in ev if k not in done and (digest or k.split(":")[0] in HOT)]
            if not fresh:
                continue
            head = ""
            if digest:
                q = t_queue(p)
                head = f"☀️ На сегодня: {len(q['hot'])} горит, {len(q['today'])} сделать.\n\n"
                fresh_keys = [(f"digest:{today}", "")] + fresh
            else:
                fresh_keys = fresh
            try:
                SEND(p["tg_id"], head + "\n\n".join(txt for _, txt in fresh))
            except Exception as ex:
                print(f"{p['full_name']}: telegram {ex}")
                continue
            for k, _ in fresh_keys:
                conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (p["id"], k))
            conn.execute("UPDATE bx_reminders SET sent_at=now() WHERE person_id=%s AND due <= current_date AND sent_at IS NULL", (p["id"],))
            db.audit(conn, p["id"], "notify", data={"keys": [k for k, _ in fresh]})
            sent += len(fresh)
    return sent


def _fmt(x: float | None) -> str:
    return f"{x:,.0f} ₸".replace(",", " ") if x else "сумма при оплате"


def head_recurring(now: datetime | None = None) -> int:
    """Постоянные оплаты HEAD (12.11): с 9:00 одно сообщение в день, пока есть что оплатить сегодня или просроченное."""
    from .recurring import due_now
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    if not DIGEST_HOUR <= now.hour < HOURS[1]:
        return 0
    today = now.date()
    key = f"recurring:{today.isoformat()}"
    sent = 0
    with db.pool.connection() as conn:
        bills = due_now(conn, today)   # заодно записывает автосписания
        auto = conn.execute("""SELECT l.amount, r.title FROM fin_ledger l JOIN fin_recurring r ON split_part(l.source_ref, ':', 2) = r.id::text
                               WHERE l.source='app' AND l.status='active' AND l.note LIKE 'Автосписание:%%'
                                 AND (l.op_date = %s OR (l.created_at AT TIME ZONE 'Asia/Almaty')::date = %s) ORDER BY l.id""", (today, today)).fetchall()
        if not bills and not auto:
            return 0
        heads = conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND role_code='head' AND tg_id IS NOT NULL").fetchall()
        for h in heads:
            if conn.execute("SELECT 1 FROM notices WHERE person_id=%s AND key=%s", (h["id"], key)).fetchone():
                continue
            now_b = [b for b in bills if b["status"] == "today"]
            late = [b for b in bills if b["status"] == "overdue"]
            lines = ["💳 <b>Постоянные оплаты</b>"]
            if now_b:
                lines += ["Сегодня:"] + [f"• {b['title']} — {_fmt(b['amount'])}" for b in now_b]
            if late:
                lines += ["Просрочено:"] + [f"• {b['title']} — {_fmt(b['amount'])}, с {b['due'][8:10]}.{b['due'][5:7]}" for b in late]
            if bills:
                lines.append("Оплатите и нажмите «Оплачено» с чеком: Финансы → Деньги.")
            if auto:
                lines += ["Списано автоматически:"] + [f"• {a['title']} — {_fmt(float(a['amount']))}" for a in auto]
                lines.append("Не та сумма — отмените строку в «Деньгах» и внесите верную.")
            try:
                SEND(h["tg_id"], "\n".join(lines))
            except Exception as ex:
                print(f"head {h['id']}: telegram {ex}")
                continue
            conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (h["id"], key))
            db.audit(conn, h["id"], "notify", data={"keys": [key], "bills": [b["id"] for b in bills]})
            sent += 1
    return sent


def main():
    if not settings.bot_token:
        print("ARTGAME_BOT_TOKEN не задан — пропуск")
        return
    db.open_pool()
    print(f"sent={run()}")
    try:
        print(f"recurring={head_recurring()}")
    except Exception as ex:  # noqa: BLE001 — не мешаем уведомлениям МОП
        print(f"recurring: {ex}")


if __name__ == "__main__":
    main()
