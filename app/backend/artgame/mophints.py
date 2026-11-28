"""Утренние подсказки МОП от ботов-аналитиков переписки (HEAD 26.11, задание сервера MOP-HINTS-01).

Робот на сервере каждое утро кладёт ARTGAME_HINTS_DIR/MOP-HINTS-ГГГГММДД.json — массив
{mop_id (ID в Битриксе), entity: deal|lead, entity_id, hint, reason, steps, prices, last_client_msg_at, date}.
Приложение только читает самый свежий файл; показываются подсказки за сегодня (поле date, иначе дата из имени файла) —
вчерашние не выдаются за сегодняшние. Оценки шагов (steps) и цены из переписки МОП не показываем (HEAD: без дизморали).

МОП — «Дожать сегодня» в «Сегодня» и строка в карточке сделки; HEAD — сводка по менеджерам на Пульте."""
import json
import os
import re
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from . import bx
from .work import active

router = APIRouter(prefix="/api")
TZ = ZoneInfo("Asia/Almaty")
NAME = re.compile(r"^MOP-HINTS-(\d{4})(\d{2})(\d{2})\.json$")
PER_MOP = 5
_cache: dict = {"path": "", "mtime": 0.0, "rows": []}
_lock = threading.Lock()


def _dir() -> str:
    return os.environ.get("ARTGAME_HINTS_DIR", "/var/lib/artgame-app/hints")


def _today() -> str:
    return datetime.now(TZ).date().isoformat()


def _clean(r: dict, day: str) -> dict | None:
    try:
        ent, eid, mop = str(r.get("entity") or ""), int(r.get("entity_id")), int(r.get("mop_id") or 0)
    except (TypeError, ValueError):
        return None
    text = str(r.get("hint") or "").strip()
    if ent not in ("deal", "lead") or not text:
        return None
    return {"mop_id": mop, "entity": ent, "id": eid, "hint": text[:400], "reason": str(r.get("reason") or "").strip()[:300],
            "at": r.get("last_client_msg_at") or None, "date": str(r.get("date") or day)[:10]}


def load() -> list:
    """Строки самого свежего файла (кэш по времени изменения). Нет папки или файл битый — пусто, экран не падает."""
    try:
        names = sorted((n for n in os.listdir(_dir()) if NAME.match(n)), reverse=True)
    except OSError:
        return []
    if not names:
        return []
    path = os.path.join(_dir(), names[0])
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    with _lock:
        if _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache["rows"]
        y, m, d = NAME.match(names[0]).groups()
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            print(f"mophints: {names[0]}: {type(e).__name__}")
            raw = []
        rows = [x for x in (_clean(r, f"{y}-{m}-{d}") for r in (raw if isinstance(raw, list) else []) if isinstance(r, dict)) if x]
        _cache.update(path=path, mtime=mtime, rows=rows)
        return rows


def today_rows() -> list:
    day = _today()
    return [r for r in load() if r["date"] == day]


def for_deal(deal_id: int) -> list:
    return [{"text": r["hint"], "reason": r["reason"], "at": r["at"], "from": "боты-аналитики"}
            for r in today_rows() if r["entity"] == "deal" and r["id"] == deal_id]


def _titles(p: dict) -> dict:
    """Названия сделок и имена лидов — из уже загруженных списков МОП (кэш), без новых запросов на каждую строку."""
    out = {}
    try:
        for d in bx.my_deals(p)["deals"]:
            out[("deal", d["id"])] = (d.get("title") or "", d.get("stage_name") or "")
    except Exception as e:  # noqa: BLE001 — без названий подсказки всё равно показываем
        print(f"mophints titles deals: {type(e).__name__}")
    try:
        from .leads import my_leads
        for x in my_leads(p)["leads"]:
            out[("lead", x["id"])] = (x.get("name") or x.get("title") or "", x.get("status_name") or "")
    except Exception as e:  # noqa: BLE001
        print(f"mophints titles leads: {type(e).__name__}")
    return out


@router.get("/bx/hints")
def api_hints(p: dict = Depends(active)):
    uid = bx.need_bx(p)          # МОП — свои, HEAD — все
    rows = today_rows()
    if uid is not None:
        rows = [r for r in rows if r["mop_id"] == uid]
    names = _titles(p)
    items = []
    for r in rows:
        t, st = names.get((r["entity"], r["id"]), ("", ""))
        items.append({**r, "title": t, "stage": st})
    out = {"date": _today(), "items": items[:PER_MOP] if uid is not None else items}
    if uid is None:
        people = {u["id"]: u["name"] for u in bx.users()}
        by: dict = {}
        for it in items:
            by.setdefault(it["mop_id"], []).append(it)
        out["by_mop"] = [{"mop_id": k, "name": people.get(k, f"ID {k}"), "count": len(v), "items": v[:PER_MOP]}
                         for k, v in sorted(by.items(), key=lambda kv: -len(kv[1]))]
    return out
