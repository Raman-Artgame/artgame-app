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


def head_approvals(now: datetime | None = None) -> int:
    """Траты отдела продаж на одобрение (HEAD 20.11): не по одной, а одной строкой утром — сколько ждёт и на какую сумму."""
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    if not DIGEST_HOUR <= now.hour < HOURS[1]:
        return 0
    key = f"approvals:{now.date().isoformat()}"
    sent = 0
    with db.pool.connection() as conn:
        r = conn.execute("""SELECT count(*) AS n, coalesce(sum(amount),0) AS s, count(DISTINCT person_id) AS who FROM expenses
                            WHERE zone_code='sales' AND status='submitted'""").fetchone()
        if not r["n"]:
            return 0
        for h in conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND role_code='head' AND tg_id IS NOT NULL").fetchall():
            if conn.execute("SELECT 1 FROM notices WHERE person_id=%s AND key=%s", (h["id"], key)).fetchone():
                continue
            who = f" от {r['who']} сотрудников" if r["who"] > 1 else ""
            try:
                SEND(h["tg_id"], f"💳 Траты отдела продаж ждут одобрения: {r['n']} на {_fmt(float(r['s']))}"
                                 f"{who}. Вкладка «Проверка».")
            except Exception as ex:  # noqa: BLE001
                print(f"head {h['id']}: telegram {ex}")
                continue
            conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (h["id"], key))
            db.audit(conn, h["id"], "notify", data={"keys": [key], "n": r["n"]})
            sent += 1
    return sent


def design_wait_remind(now: datetime | None = None) -> int:
    """«Ждём клиента» в дизайне (HEAD 22.11): через 7 дней ожидания МОП сделки получает одно напоминание.
    МОП не нашёлся в приложении или без Telegram — напоминание HEAD."""
    from .design import WAIT_REMIND_DAYS
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    if not HOURS[0] <= now.hour < HOURS[1]:
        return 0
    sent = 0
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT * FROM design_wait WHERE ended_at IS NULL AND reminded_at IS NULL
                               AND (started_at AT TIME ZONE 'Asia/Almaty')::date <= %s""",
                            (now.date() - timedelta(days=WAIT_REMIND_DAYS),)).fetchall()
        heads = conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND role_code='head' AND tg_id IS NOT NULL ORDER BY id").fetchall()
        for w in rows:
            mop = conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND tg_id IS NOT NULL AND bitrix_user_id=%s",
                               (w["mop_bx"],)).fetchone() if w["mop_bx"] else None
            to = [mop] if mop else heads[:1]
            days = (now.date() - w["started_at"].astimezone(TZ).date()).days
            text = (f"⏸ Дизайн ждёт клиента {days} дн: {_title({'id': w['deal_id'], 'title': w['title']})}.\n"
                    f"Причина: {w['reason']}.\nНапомни клиенту в Битриксе; ответил — дизайнер жмёт «Клиент ответил».")
            ok = False
            for r in to:
                try:
                    SEND(r["tg_id"], text)
                    ok = True
                except Exception as ex:  # noqa: BLE001
                    print(f"design wait {w['id']}: telegram {ex}")
            if ok:
                conn.execute("UPDATE design_wait SET reminded_at=now() WHERE id=%s", (w["id"],))
                db.audit(conn, to[0]["id"], "notify", "design_wait", w["id"], {"keys": [f"design_wait:{w['id']}"]})
                conn.commit()
                sent += 1
    return sent


def app_bx_user() -> int | None:
    """Пользователь Битрикса, от которого пишет приложение: его номер — в адресе вебхука (/rest/<id>/<ключ>/)."""
    import re
    m = re.search(r"/rest/(\d+)/", settings.bitrix_webhook or "")
    return int(m.group(1)) if m else None


def stage_outside(now: datetime | None = None) -> int:
    """Стадии двигаются только из приложения (HEAD 25.11 «давай делаем»): сделку перевели в Битриксе руками или роботом —
    МОП сделки и HEAD получают одно сообщение, событие в журнале. Сделку не трогаем: вернуть стадию решает человек."""
    app_user = app_bx_user()
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    if not app_user or not HOURS[0] <= now.hour < HOURS[1]:
        return 0
    since = (now - timedelta(days=2)).isoformat()
    rows = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": [0], ">=MOVED_TIME": since},
                                         "select": ["ID", "TITLE", "STAGE_ID", "MOVED_TIME", "MOVED_BY_ID", "ASSIGNED_BY_ID"]}, fresh=True)
    rows = [d for d in rows if int(d.get("MOVED_BY_ID") or 0) not in (0, app_user) and not bx.is_test(d)]
    if not rows:
        return 0
    names = {u["id"]: u["name"] for u in bx.users()}
    st = bx.stages()
    sent = 0
    with db.pool.connection() as conn:
        heads = conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND role_code='head' AND tg_id IS NOT NULL ORDER BY id").fetchall()
        for d in rows:
            key = f"stage_outside:{d['ID']}:{d.get('MOVED_TIME')}"
            mop = conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND tg_id IS NOT NULL AND bitrix_user_id=%s",
                               (int(d.get("ASSIGNED_BY_ID") or 0),)).fetchone()
            to = [r for r in [mop, *heads] if r]
            to = [r for i, r in enumerate(to) if r["id"] not in {x["id"] for x in to[:i]}]
            stage = (st.get(d.get("STAGE_ID")) or {}).get("name") or d.get("STAGE_ID")
            who = names.get(int(d["MOVED_BY_ID"]), f"пользователь {d['MOVED_BY_ID']}")
            text = (f"↪️ Стадию сделки {_title({'id': d['ID'], 'title': d.get('TITLE')})} сменили в Битриксе, мимо приложения: "
                    f"{who} → «{stage}».\nСтадии двигаем только в приложении — там проверка карточки и документов. "
                    f"Если переход ошибочный, верните стадию в карточке сделки.")
            first = None
            for r in to:
                if conn.execute("SELECT 1 FROM notices WHERE person_id=%s AND key=%s", (r["id"], key)).fetchone():
                    continue
                try:
                    SEND(r["tg_id"], text)
                except Exception as ex:  # noqa: BLE001
                    print(f"stage outside {d['ID']}: telegram {ex}")
                    continue
                conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (r["id"], key))
                first = first or r
                sent += 1
            if first:
                db.audit(conn, first["id"], "stage_outside", "deal", int(d["ID"]),
                         {"stage": d.get("STAGE_ID"), "by": int(d["MOVED_BY_ID"]), "at": str(d.get("MOVED_TIME"))})
                conn.commit()
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
    try:
        print(f"approvals={head_approvals()}")
    except Exception as ex:  # noqa: BLE001
        print(f"approvals: {ex}")
    try:
        print(f"design_wait={design_wait_remind()}")
    except Exception as ex:  # noqa: BLE001
        print(f"design_wait: {ex}")
    # stage_outside выключен 25.11: разослал по одному сообщению на старые смены стадий; вернётся сводкой только по новым


if __name__ == "__main__":
    main()
