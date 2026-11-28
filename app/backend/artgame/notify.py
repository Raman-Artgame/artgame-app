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


DESIGN_WAIT_EVERY = 3   # дней: как часто напоминать МОП про задание «ждём клиента»


def _dtask(t: dict) -> str:
    return f"{_title({'id': t['deal_id'], 'title': t['deal_title']})} · {t['title']}"


def design_deadlines(now: datetime | None = None) -> int:
    """Сроки заданий дизайнеров (HEAD 28.11 «чтобы соблюдались и ребятам были постоянные напоминания»).
    С 9:00 дизайнеру одно сообщение в день: просрочено / срок сегодня / срок завтра — пока задание не сдвинется.
    Задание без дизайнера — Главному дизайнеру. «Ждём клиента» — МОП (кто ставил задание) раз в 3 дня: дожать клиента."""
    from .designtasks import LATE_STAGES
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    if not DIGEST_HOUR <= now.hour < HOURS[1]:
        return 0
    today = now.date()
    sent = 0
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT t.id, t.deal_id, t.deal_title, t.title, t.deadline, t.designer_id FROM design_tasks t
                               WHERE t.status='active' AND t.stage = ANY(%s) AND t.deadline <= %s ORDER BY t.deadline, t.id""",
                            (list(LATE_STAGES), today + timedelta(days=1))).fetchall()
        leads = conn.execute("SELECT id FROM people WHERE status='active' AND role_code='lead_designer' AND tg_id IS NOT NULL ORDER BY id").fetchall()
        by: dict = {}
        for t in rows:
            for pid in ([t["designer_id"]] if t["designer_id"] else [x["id"] for x in leads]):
                by.setdefault(pid, []).append(t)
        key = f"design_deadline:{today.isoformat()}"
        for pid, ts in by.items():
            pe = conn.execute("SELECT id, tg_id FROM people WHERE id=%s AND status='active' AND tg_id IS NOT NULL", (pid,)).fetchone()
            if not pe or conn.execute("SELECT 1 FROM notices WHERE person_id=%s AND key=%s", (pid, key)).fetchone():
                continue
            late = [t for t in ts if t["deadline"] < today]
            now_t = [t for t in ts if t["deadline"] == today]
            tom = [t for t in ts if t["deadline"] > today]
            lines = ["🎨 <b>Сроки по дизайну</b>"]
            if late:
                lines += ["Просрочено:"] + [f"• {_dtask(t)} — {(today - t['deadline']).days} дн." for t in late]
            if now_t:
                lines += ["Срок сегодня:"] + [f"• {_dtask(t)}" for t in now_t]
            if tom:
                lines += ["Срок завтра:"] + [f"• {_dtask(t)}" for t in tom]
            lines.append("Сдайте эскиз в задании. Не успеваете или ждёте клиента — смените стадию или срок, чтобы МОП это видел.")
            try:
                SEND(pe["tg_id"], "\n".join(lines))
            except Exception as ex:  # noqa: BLE001
                print(f"design deadline {pid}: telegram {ex}")
                continue
            conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (pid, key))
            db.audit(conn, pid, "notify", data={"keys": [key], "tasks": [t["id"] for t in ts]})
            conn.commit()
            sent += 1
        # «Ждём клиента»: МОП раз в 3 дня, одним сообщением
        waits = conn.execute("""SELECT t.id, t.deal_id, t.deal_title, t.title, t.created_by,
                                       %s - (t.updated_at AT TIME ZONE 'Asia/Almaty')::date AS days
                                FROM design_tasks t WHERE t.status='active' AND t.stage='wait'
                                  AND %s - (t.updated_at AT TIME ZONE 'Asia/Almaty')::date >= %s ORDER BY t.updated_at""",
                             (today, today, DESIGN_WAIT_EVERY)).fetchall()
        by_mop: dict = {}
        for t in waits:
            k = f"design_task_wait:{t['id']}:{t['days'] // DESIGN_WAIT_EVERY}"
            if not conn.execute("SELECT 1 FROM notices WHERE person_id=%s AND key=%s", (t["created_by"], k)).fetchone():
                by_mop.setdefault(t["created_by"], []).append((k, t))
        for pid, items in by_mop.items():
            pe = conn.execute("SELECT id, tg_id FROM people WHERE id=%s AND status='active' AND tg_id IS NOT NULL", (pid,)).fetchone()
            if not pe:
                continue
            text = ("⏸ Дизайн ждёт клиента:\n" + "\n".join(f"• {_dtask(t)} — {t['days']} дн." for _, t in items[:15])
                    + (f"\n…и ещё {len(items) - 15}" if len(items) > 15 else "")
                    + "\nНапомните клиенту. Ответил — напишите дизайнеру в задании, он вернёт его в работу.")
            try:
                SEND(pe["tg_id"], text)
            except Exception as ex:  # noqa: BLE001
                print(f"design task wait {pid}: telegram {ex}")
                continue
            for k, _ in items:
                conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (pid, k))
            db.audit(conn, pid, "notify", data={"keys": [k for k, _ in items]})
            conn.commit()
            sent += 1
    return sent


def app_bx_user() -> int | None:
    """Пользователь Битрикса, от которого пишет приложение: его номер — в адресе вебхука (/rest/<id>/<ключ>/)."""
    import re
    m = re.search(r"/rest/(\d+)/", settings.bitrix_webhook or "")
    return int(m.group(1)) if m else None


STAGE_HEAD_HOUR = 20   # HEAD — одна сводка за день вечером


def stage_outside(now: datetime | None = None) -> int:
    """Стадии двигаются только из приложения (HEAD 25.11 «давай делаем»): сделку перевели в Битриксе руками или роботом —
    событие в журнале, МОП сделки — одно сообщение со всеми своими сделками за проход, HEAD — одна сводка за день в 20:00.
    Первый проход только запоминает, что уже было (25.11 рассылка ушла по старым сменам, по одной — HEAD попросил так не делать).
    Сделку не трогаем: вернуть стадию решает человек."""
    app_user = app_bx_user()
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    if not app_user:
        return 0
    rows = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": [0], ">=MOVED_TIME": (now - timedelta(days=2)).isoformat()},
                                         "select": ["ID", "TITLE", "STAGE_ID", "MOVED_TIME", "MOVED_BY_ID", "ASSIGNED_BY_ID"]}, fresh=True)
    rows = [d for d in rows if int(d.get("MOVED_BY_ID") or 0) not in (0, app_user) and not bx.is_test(d)]
    sent = 0
    with db.pool.connection() as conn:
        seen = {(r["entity_id"], r["at"]) for r in conn.execute(
            "SELECT entity_id, data->>'at' AS at FROM audit_log WHERE action='stage_outside' AND at > now() - interval '4 days'").fetchall()}
        started = conn.execute("SELECT 1 FROM audit_log WHERE action='stage_outside_start'").fetchone()
        new = [d for d in rows if (str(d["ID"]), str(d.get("MOVED_TIME"))) not in seen]
        names = {u["id"]: u["name"] for u in bx.users()} if new or started else {}
        st = bx.stages() if new or started else {}
        for d in new:
            db.audit(conn, None, "stage_outside", "deal", int(d["ID"]),
                     {"stage": d.get("STAGE_ID"), "by": int(d["MOVED_BY_ID"]), "mop": int(d.get("ASSIGNED_BY_ID") or 0),
                      "title": d.get("TITLE") or "", "at": str(d.get("MOVED_TIME")), "quiet": not started})
        if not started:
            db.audit(conn, None, "stage_outside_start", data={"known": len(new)})
            conn.commit()
            return 0
        conn.commit()

        def line(x: dict) -> str:
            stage = (st.get(x["stage"]) or {}).get("name") or x["stage"]
            return f"• {_title({'id': x['id'], 'title': x['title']})}: {names.get(x['by'], 'пользователь ' + str(x['by']))} → «{stage}»"

        tail = "\nСтадии двигаем в приложении — там проверка карточки и документов. Ошибочный переход верните в карточке сделки."
        if HOURS[0] <= now.hour < HOURS[1]:
            by_mop: dict = {}
            for d in new:
                by_mop.setdefault(int(d.get("ASSIGNED_BY_ID") or 0), []).append(
                    {"id": d["ID"], "title": d.get("TITLE"), "stage": d.get("STAGE_ID"), "by": int(d["MOVED_BY_ID"])})
            for bxid, items in by_mop.items():
                mop = conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND tg_id IS NOT NULL AND bitrix_user_id=%s "
                                   "AND role_code IN ('mop', 'mop_vip')", (bxid,)).fetchone()
                if not mop:
                    continue
                try:
                    SEND(mop["tg_id"], "↪️ Стадию сменили в Битриксе, мимо приложения:\n" + "\n".join(line(x) for x in items[:10])
                         + (f"\n…и ещё {len(items) - 10}" if len(items) > 10 else "") + tail)
                    sent += 1
                except Exception as ex:  # noqa: BLE001
                    print(f"stage outside mop {bxid}: telegram {ex}")
        if now.hour >= STAGE_HEAD_HOUR:
            key = f"stage_outside_day:{now.date().isoformat()}"
            day = [dict(r["data"], id=r["entity_id"]) for r in conn.execute(
                """SELECT entity_id, data FROM audit_log WHERE action='stage_outside' AND data ? 'mop' AND NOT coalesce((data->>'quiet')::bool, false)
                   AND (at AT TIME ZONE 'Asia/Almaty')::date = %s ORDER BY id""", (now.date(),)).fetchall()]
            for h in conn.execute("SELECT id, tg_id FROM people WHERE status='active' AND role_code='head' AND tg_id IS NOT NULL").fetchall():
                if not day or conn.execute("SELECT 1 FROM notices WHERE person_id=%s AND key=%s", (h["id"], key)).fetchone():
                    continue
                try:
                    SEND(h["tg_id"], f"↪️ За день {len(day)} смен стадий в Битриксе мимо приложения:\n"
                         + "\n".join(line(x) for x in day[:15]) + (f"\n…и ещё {len(day) - 15}" if len(day) > 15 else ""))
                except Exception as ex:  # noqa: BLE001
                    print(f"stage outside head: telegram {ex}")
                    continue
                conn.execute("INSERT INTO notices (person_id, key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (h["id"], key))
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
    try:
        print(f"approvals={head_approvals()}")
    except Exception as ex:  # noqa: BLE001
        print(f"approvals: {ex}")
    try:
        print(f"design_wait={design_wait_remind()}")
    except Exception as ex:  # noqa: BLE001
        print(f"design_wait: {ex}")
    try:
        print(f"design_deadlines={design_deadlines()}")
    except Exception as ex:  # noqa: BLE001
        print(f"design_deadlines: {ex}")
    try:
        print(f"stage_outside={stage_outside()}")
    except Exception as ex:  # noqa: BLE001
        print(f"stage_outside: {ex}")


if __name__ == "__main__":
    main()
