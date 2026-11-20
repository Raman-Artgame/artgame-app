"""Звонки телефонии Битрикса для МОП (HEAD 05.11.2026, «агент по звонкам»).

Расшифровку, резюме в ленту и заполнение пустых полей делает Битрикс CoPilot в самом Битриксе (включает HEAD) —
приложение это не дублирует. Здесь — то, чего CoPilot не делает: пропущенные входящие без перезвона попадают
в «Сегодня» → «Горит», а в ленте карточки у звонка видно длительность и «пропущен».
Права вебхука — только CRM (дела), «Телефония» не нужна.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from . import bx

DAYS = 2                      # смотрим звонки за последние двое суток
ENTITY = {"1": "lead", "2": "deal"}
SELECT = ["ID", "OWNER_TYPE_ID", "OWNER_ID", "DIRECTION", "SETTINGS", "CREATED", "START_TIME", "END_TIME",
          "RESPONSIBLE_ID", "SUBJECT", "COMPLETED"]


def is_missed(a: dict) -> bool:
    return str(a.get("DIRECTION")) == "1" and bool((a.get("SETTINGS") or {}).get("MISSED_CALL"))


def duration(a: dict) -> int:
    try:
        return max(0, int((datetime.fromisoformat(a["END_TIME"]) - datetime.fromisoformat(a["START_TIME"])).total_seconds()))
    except (KeyError, TypeError, ValueError):
        return 0


def label(a: dict) -> str:
    """Подпись звонка для ленты: «Входящий от … · пропущен» / «Исходящий на … · 2:54»."""
    s = a.get("SUBJECT") or "звонок"
    if is_missed(a):
        return s + " · пропущен"
    d = duration(a)
    return s + (f" · {d // 60}:{d % 60:02d}" if d else " · не соединился" if str(a.get("DIRECTION")) == "2" else "")


def missed(fresh: bool = False) -> list:
    """Пропущенные входящие, после которых по этому лиду/сделке никто не звонил (ни входящим, ни исходящим).
    Свежие сверху; чьи они — решает вызывающий по своим сделкам и лидам."""
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat(timespec="seconds")
    try:
        rows = bx.read_all("crm.activity.list", {"filter": {"TYPE_ID": 2, ">=CREATED": since}, "order": {"ID": "DESC"},
                                                 "select": SELECT}, fresh=fresh)
    except HTTPException:
        return []
    last: dict = {}
    for a in rows:   # новые сверху: первый встреченный по владельцу — последний звонок
        key = (str(a.get("OWNER_TYPE_ID")), str(a.get("OWNER_ID")))
        last.setdefault(key, a)
    out = []
    for (tid, oid), a in last.items():
        if tid not in ENTITY or not is_missed(a):
            continue
        out.append({"entity": ENTITY[tid], "id": int(oid), "at": a.get("CREATED") or "", "subject": a.get("SUBJECT") or "",
                    "responsible": int(a.get("RESPONSIBLE_ID") or 0)})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out


def hhmm(iso: str) -> str:
    """Время звонка по Астане (UTC+5)."""
    try:
        t = datetime.fromisoformat(iso).astimezone(timezone(timedelta(hours=5)))
        return t.strftime("%d.%m %H:%M") if t.date() != datetime.now(t.tzinfo).date() else t.strftime("%H:%M")
    except ValueError:
        return ""
