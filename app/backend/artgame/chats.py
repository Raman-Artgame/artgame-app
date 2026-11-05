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
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def last_client_wait(hist: dict) -> datetime | None:
    """Когда клиент написал последним и ему ещё не ответили — время его первого неотвеченного сообщения, иначе None."""
    msgs = sorted((hist.get("message") or {}).values(), key=lambda m: (m.get("date") or "", int(m.get("id") or 0)), reverse=True)
    users = hist.get("users") or {}
    waiting = None
    for m in msgs:
        sid = str(m.get("senderid") or "0")
        if sid == "0":                       # системные: «начал работу с диалогом», «создан лид»
            continue
        u = users.get(sid) or {}
        client = (u.get("connector") or u.get("type") == "extranet") and not str(m.get("text") or "").startswith(OUT_MARK)
        if not client:
            break                            # последнее слово за менеджером
        waiting = _dt(m.get("date"))         # идём назад до первого неотвеченного
    return waiting


def waiting(fresh: bool = False) -> tuple[list, str]:
    """Диалоги, где клиент ждёт ответа: [{entity, id, since}], и текст ошибки, если переписку прочитать нельзя."""
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat(timespec="seconds")
    try:
        acts = bx.read_all("crm.activity.list", {"filter": {"PROVIDER_ID": "IMOPENLINES_SESSION", "COMPLETED": "N",
                                                            ">=LAST_UPDATED": since}, "order": {"LAST_UPDATED": "DESC"},
                                                 "select": ["ID", "OWNER_TYPE_ID", "OWNER_ID", "ASSOCIATED_ENTITY_ID", "LAST_UPDATED"]},
                           fresh=fresh)
    except HTTPException:
        return [], ""
    out, seen, err = [], set(), ""
    for a in acts[:MAX_DIALOGS]:
        tid, oid, sid = str(a.get("OWNER_TYPE_ID")), str(a.get("OWNER_ID")), a.get("ASSOCIATED_ENTITY_ID")
        if tid not in ENTITY or not sid or (tid, oid) in seen:
            continue
        seen.add((tid, oid))
        try:
            j = bx.read("imopenlines.session.history.get", {"SESSION_ID": int(sid)}, fresh=fresh)
        except HTTPException as ex:
            err = f"переписку WhatsApp прочитать нельзя ({str(ex.detail)[:120]}) — вебхуку нужно право «Открытые линии»"
            break
        w = last_client_wait((j or {}).get("result") or {})
        if w:
            out.append({"entity": ENTITY[tid], "id": int(oid), "since": w})
    return out, err


def ago(t: datetime) -> str:
    m = int((datetime.now(timezone.utc) - t).total_seconds() // 60)
    return f"{m} мин" if m < 60 else f"{m // 60} ч" if m < 48 * 60 else f"{m // 1440} дн."
