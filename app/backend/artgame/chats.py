"""Переписка WhatsApp (Wazzup → открытые линии Битрикса) для МОП (HEAD 05.11.2026, «агент по переписке»).

Резюме переписки и заполнение полей из чата делает сам Битрикс («Анализ чатов» BitrixGPT/CoPilot в лидах и сделках,
включает HEAD) — приложение это не дублирует. Здесь — то, чего Битрикс не делает: если клиент написал последним и ему
не ответили дольше mop.today.chat_minutes (по умолчанию 30 мин) — «Сегодня» → «Горит», «клиент ждёт ответа».
Чтение диалога — imopenlines.session.history.get (вебхуку нужно право «Открытые линии»; без него — предупреждение).
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from . import bx

DAYS = 3            # открытые диалоги, где что-то было за последние трое суток
MAX_DIALOGS = 40    # сколько диалогов читаем за один раз (каждый — отдельный запрос, кеш 2 мин)
ENTITY = {"1": "lead", "2": "deal"}
OUT_MARK = "=== Исходящее сообщение"   # Wazzup так помечает то, что менеджер отправил с телефона


def _dt(s: str):
    try:
        t = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _vals(x) -> list:
    """Битрикс отдаёт набор то словарём {id: …}, то списком (пустой — всегда [])."""
    return list(x.values()) if isinstance(x, dict) else list(x) if isinstance(x, list) else []


def last_client_wait(hist: dict) -> datetime | None:
    """Когда клиент написал последним и ему ещё не ответили — время его первого неотвеченного сообщения, иначе None."""
    if not isinstance(hist, dict):
        return None
    msgs = [m for m in _vals(hist.get("message")) if isinstance(m, dict)]
    msgs.sort(key=lambda m: (str(m.get("date") or ""), int(m.get("id") or 0) if str(m.get("id") or "0").isdigit() else 0), reverse=True)
    us = hist.get("users")
    users = {str(k): u for k, u in us.items()} if isinstance(us, dict) else \
        {str(u.get("id")): u for u in _vals(us) if isinstance(u, dict)}
    waiting = None
    for m in msgs:
        sid = str(m.get("senderid") or "0")
        if sid == "0":                       # системные: «начал работу с диалогом», «создан лид»
            continue
        u = users.get(sid) or {}
        client = (u.get("connector") or u.get("type") == "extranet") and not str(m.get("text") or "").startswith(OUT_MARK)
        if not client:
            break                            # последнее слово за менеджером
        waiting = _dt(m.get("date")) or waiting   # идём назад до первого неотвеченного
    return waiting


def first_client_text(hist) -> str:
    """Первое сообщение клиента в диалоге — в нём фраза из ссылки площадки («Пишу с OLX»)."""
    if not isinstance(hist, dict):
        return ""
    us = hist.get("users")
    users = {str(k): u for k, u in us.items()} if isinstance(us, dict) else \
        {str(u.get("id")): u for u in _vals(us) if isinstance(u, dict)}
    msgs = [m for m in _vals(hist.get("message")) if isinstance(m, dict)]
    msgs.sort(key=lambda m: (str(m.get("date") or ""), int(m.get("id") or 0) if str(m.get("id") or "0").isdigit() else 0))
    for m in msgs:
        u = users.get(str(m.get("senderid") or "0")) or {}
        text = str(m.get("text") or "")
        if (u.get("connector") or u.get("type") == "extranet") and not text.startswith(OUT_MARK):
            return text
    return ""


def _origin(lead_id: int, hist) -> None:
    """Площадка лида по первой фразе клиента (HEAD 14.11). Сбой здесь не должен ломать «Сегодня»."""
    try:
        text = first_client_text(hist)
        if text:
            from . import ads
            ads.auto_origin(lead_id, text)
    except Exception as e:  # noqa: BLE001
        print("lead origin:", e)


def waiting(fresh: bool = False, owners: set | None = None) -> tuple[list, str]:
    """Диалоги, где клиент ждёт ответа: [{entity, id, since}], и текст ошибки, если переписку прочитать нельзя.
    owners — {(«deal»|«lead», id)} своих сделок и лидов: чужие диалоги не читаем (у HEAD — None, все).
    Переписка читается одной пачкой (bx.read_many), а не запросом на каждый диалог — иначе «Сегодня» не успевал открыться."""
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat(timespec="seconds")
    try:
        acts = bx.read_all("crm.activity.list", {"filter": {"PROVIDER_ID": "IMOPENLINES_SESSION", "COMPLETED": "N",
                                                            ">=LAST_UPDATED": since}, "order": {"LAST_UPDATED": "DESC"},
                                                 "select": ["ID", "OWNER_TYPE_ID", "OWNER_ID", "ASSOCIATED_ENTITY_ID", "LAST_UPDATED"]},
                           fresh=fresh)
    except HTTPException:
        return [], ""
    want, seen = {}, set()
    for a in acts:
        tid, oid, sid = str(a.get("OWNER_TYPE_ID")), str(a.get("OWNER_ID")), str(a.get("ASSOCIATED_ENTITY_ID") or "")
        if tid not in ENTITY or not sid.isdigit() or not oid.isdigit() or (tid, oid) in seen:
            continue
        if owners is not None and (ENTITY[tid], int(oid)) not in owners:
            continue
        seen.add((tid, oid))
        want[f"s{sid}"] = (ENTITY[tid], int(oid), int(sid))
        if len(want) >= MAX_DIALOGS:
            break
    res, err = bx.read_many("imopenlines.session.history.get", {k: {"SESSION_ID": v[2]} for k, v in want.items()}, fresh=fresh)
    if err:
        err = f"переписку WhatsApp прочитать нельзя ({err[:120]}) — вебхуку нужно право «Открытые линии»"
    out = []
    for k, (ent, oid, _) in want.items():
        j = res.get(k)
        hist = (j or {}).get("result") if isinstance(j, dict) else None
        if ent == "lead":
            _origin(oid, hist)
        w = last_client_wait(hist)
        if w:
            out.append({"entity": ent, "id": oid, "since": w})
    return out, err


def ago(t: datetime) -> str:
    m = int((datetime.now(timezone.utc) - t).total_seconds() // 60)
    return f"{m} мин" if m < 60 else f"{m // 60} ч" if m < 24 * 60 else f"{m // 1440} дн."   # до суток — часы, дальше дни (HEAD 14.11)
