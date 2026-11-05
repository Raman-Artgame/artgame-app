"""Запись в Битрикс из приложения — решение HEAD 05.11.2026 (вариант А: приложение пишет само, сразу).

Ключ — входящий вебхук Битрикса с правами CRM, только в env сервера (ARTGAME_BITRIX_WEBHOOK). В репозитории его нет.
Что можно: только поля из WRITABLE, только в сделки, где человек ответственный (HEAD — любые), стадия только по
переходам STAGE_FLOW или явным выбором МОП среди открытых стадий, комментарий в ленту, файл в поле документа.
Ничего не удаляется. Каждая запись — в audit_log (bx_write, data.bx = ok | error | off) и сверяется повторным чтением.
Массовые правки и настройки Битрикса по-прежнему только через Кодекса и «да» HEAD.
"""
import base64
import json
from datetime import date
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import bx, db
from .config import settings
from .work import active

router = APIRouter(prefix="/api")

F_KP, F_CONTRACT, F_INVOICES, F_OTHER = "UF_CRM_1753202415", "UF_CRM_1753202391", "UF_CRM_ARTGAME_DOC05_INVOICES", "UF_CRM_ARTGAME_DOC05_OTHER"
F_ADV, F_DAYS, F_WARR = "UF_CRM_ARTGAME_ADVANCE_PERCENT", "UF_CRM_1753295493279", "UF_CRM_ARTGAME_WARRANTY_MONTHS"
F_INV_SUM, F_INV_PURPOSE, F_REASON = "UF_CRM_ARTGAME_INVOICE_AMOUNT", "UF_CRM_ARTGAME_INVOICE_PURPOSE", "UF_CRM_1753381316974"
WRITABLE = {"OPPORTUNITY", "STAGE_ID", bx.AREA, bx.SERVICE, bx.ADDR, F_ADV, F_DAYS, F_WARR, F_INV_SUM, F_INV_PURPOSE, F_REASON,
            F_KP, F_CONTRACT, F_INVOICES, F_OTHER}
MULTI_FILE = {F_KP, F_CONTRACT, F_INVOICES, F_OTHER}
# Переходы по документам: двигаем только вперёд и только из перечисленных стадий.
STAGE_FLOW = {
    "kp": ("PREPARATION", {"NEW"}),
    "dogovor": ("FINAL_INVOICE", {"NEW", "PREPARATION", "UC_VZFPUP", "UC_YV66BV", "UC_1EXUAC"}),
    "invoice": ("FINAL_INVOICE", {"NEW", "PREPARATION", "UC_VZFPUP", "UC_YV66BV", "UC_1EXUAC"}),
    "signed": ("UC_AV00QK", {"NEW", "PREPARATION", "UC_VZFPUP", "UC_YV66BV", "UC_1EXUAC", "FINAL_INVOICE"}),
}
KIND_FIELD = {"kp": F_KP, "dogovor": F_OTHER, "eskiz": F_OTHER, "invoice": F_INVOICES, "avr": F_OTHER, "signed": F_CONTRACT}
POSTPONED = "UC_VCP4VO"   # «Отложено»: только с датой возврата — задача в Битриксе и напоминание бота
KIND_TITLE = {"kp": "КП", "dogovor": "договор", "eskiz": "договор на эскиз", "invoice": "счёт", "avr": "акт", "signed": "подписанный договор"}


def _call(method: str, params: dict) -> dict:
    url = settings.bitrix_webhook.rstrip("/") + "/" + method
    r = httpx.post(url, json=params, timeout=60)
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError(f"Битрикс {r.status_code}")
    if "error" in j:
        raise RuntimeError(j.get("error_description") or j["error"])
    return j


CALL = _call  # тесты подменяют


def enabled() -> bool:
    return bool(settings.bitrix_webhook)


def _fmt(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ") + " ₸"


def _file_data(path: Path, name: str) -> dict:
    return {"fileData": [name, base64.b64encode(path.read_bytes()).decode()]}


def write(p: dict, deal_id: int, what: str, fields: dict | None = None, comment: str | None = None,
          file: tuple[Path, str, str] | None = None, stage_for: str | None = None) -> dict:
    """Одна запись: поля + файл + комментарий в ленту. Проверка прав по текущей сделке из Битрикса."""
    d = bx._deal(p, deal_id, fresh=True)
    fields = {k: v for k, v in (fields or {}).items() if k in WRITABLE and v not in (None, "", 0, "0")}
    if stage_for and stage_for in STAGE_FLOW:
        to, allowed = STAGE_FLOW[stage_for]
        if d["STAGE_ID"] in allowed:
            fields["STAGE_ID"] = to
    log = {"what": what, "fields": {k: (v if not isinstance(v, dict) else "файл") for k, v in fields.items()}}
    if not enabled():
        log["bx"] = "off"
        with db.pool.connection() as conn:
            db.audit(conn, p["id"], "bx_write", "deal", deal_id, log)
        return {"bx": "off", "fields": log["fields"]}
    try:
        if file:
            path, name, fkey = file
            if fkey in MULTI_FILE:
                old = d.get(fkey) or []
                fields[fkey] = [{"id": int(x["id"] if isinstance(x, dict) else x)} for x in old if x] + [_file_data(path, name)]
            else:
                fields[fkey] = _file_data(path, name)
        if fields:
            CALL("crm.deal.update", {"id": deal_id, "fields": fields, "params": {"REGISTER_SONET_EVENT": "Y"}})
        if comment:
            CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal",
                                                         "COMMENT": f"{p['full_name']} (приложение): {comment}"}})
        # сверка: перечитываем и сравниваем простые поля
        after = bx._deal(p, deal_id, fresh=True)
        bad = [k for k, v in fields.items() if k not in MULTI_FILE and not isinstance(v, dict)
               and str(after.get(k) or "").split("|")[0] != str(v).split("|")[0]]
        log["bx"] = "ok" if not bad else "error"
        if bad:
            log["error"] = f"не записалось: {', '.join(bad)}"
        bx._cache.clear()
    except Exception as ex:
        log["bx"], log["error"] = "error", str(ex)[:300]
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "bx_write", "deal", deal_id, log)
    if log["bx"] == "error":
        return {"bx": "error", "error": log["error"], "fields": log["fields"]}
    return {"bx": "ok", "fields": log["fields"], "stage": fields.get("STAGE_ID")}


# ---------- документ скачан на странице МОП ----------

def kind_of(name: str) -> str | None:
    n = name.lower()
    if n.startswith("кп "):
        return "kp"
    if "dogovor_eskiz" in n:
        return "eskiz"
    if "dogovor" in n:
        return "dogovor"
    if "schet" in n:
        return "invoice"
    if "avr" in n:
        return "avr"
    return None


def doc_saved(p: dict, deal_id: int, name: str, fid: str, f: dict) -> dict:
    from .places import DL_DIR
    kind = kind_of(name)
    if not kind:
        return {"bx": "skip"}
    path = DL_DIR / f"{fid}.bin" if fid and fid.isalnum() else None
    file = (path, name, KIND_FIELD[kind]) if path and path.exists() else None
    fields, parts = {}, []
    total, area = float(f.get("total") or 0), float(f.get("area") or 0)
    if kind in ("kp", "dogovor") and total:
        fields["OPPORTUNITY"] = int(round(total))
        parts.append("сумма " + _fmt(total))
    if kind in ("kp", "dogovor") and area:
        fields[bx.AREA] = area
        parts.append(f"{area:g} м²")
    if kind == "dogovor":
        fields.update({F_ADV: int(f.get("adv") or 0) or None, F_DAYS: str(f.get("days") or "") or None,
                       F_WARR: int(f.get("warr") or 0) or None, bx.ADDR: f.get("objAddr") or None})
        if f.get("adv"):
            parts.append(f"аванс {int(f['adv'])}%")
    if kind == "invoice" and f.get("invSum"):
        fields[F_INV_SUM] = f"{int(round(float(f['invSum'])))}|KZT"
        parts.append("на " + _fmt(float(f["invSum"])))
    comment = f"скачал {KIND_TITLE[kind]} «{name}»" + (": " + ", ".join(parts) if parts else "")
    return write(p, deal_id, f"{KIND_TITLE[kind]}: {name}", fields, comment, file, stage_for=kind)


# ---------- стадия и заметка из вкладки «Сделки» ----------

class StageIn(BaseModel):
    stage: str
    reason: str | None = None
    until: date | None = None   # для «Отложено»: когда вернуться к сделке


def postpone(p: dict, deal_id: int, until: date, reason: str | None) -> dict:
    """«Отложено до…»: в Битриксе — задача ответственному с дедлайном (если вебхук с правом «Задачи»),
    в приложении — напоминание бота в этот день и строка в «Сегодня»."""
    out = {"task": None}
    uid = bx.bx_id(p)
    if enabled() and uid:
        try:
            j = CALL("tasks.task.add", {"fields": {"TITLE": f"Вернуться к сделке № {deal_id}", "RESPONSIBLE_ID": uid,
                                                   "CREATED_BY": uid, "DEADLINE": f"{until.isoformat()}T10:00:00+05:00",
                                                   "DESCRIPTION": reason or "", "UF_CRM_TASK": [f"D_{deal_id}"]}})
            out["task"] = int(((j.get("result") or {}).get("task") or {}).get("id") or 0) or None
        except Exception as ex:
            out["task_error"] = str(ex)[:200]
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO bx_reminders (person_id, deal_id, due, note) VALUES (%s, %s, %s, %s)",
                     (p["id"], deal_id, until, reason))
    return out


@router.post("/bx/deals/{deal_id}/stage")
def api_stage(deal_id: int, body: StageIn, p: dict = Depends(active)):
    st = bx.stages()
    if body.stage not in st:
        raise HTTPException(400, "нет такой стадии")
    fields = {"STAGE_ID": body.stage}
    if st[body.stage]["semantic"] in ("failure", "apology"):
        if not body.reason:
            raise HTTPException(400, "укажите причину отказа")
        fields[F_REASON] = body.reason
    note = f"перевёл в «{st[body.stage]['name']}»"
    if body.stage == POSTPONED:
        if not body.until or body.until <= date.today():
            raise HTTPException(400, "укажите дату возврата к сделке (позже сегодня)")
        note = f"отложил до {body.until:%d.%m.%Y}"
    if body.reason:
        note += f": {body.reason}"
    r = write(p, deal_id, f"стадия → {st[body.stage]['name']}", fields, note)
    if r["bx"] == "error":
        raise HTTPException(502, r["error"])
    if body.stage == POSTPONED:
        r.update(postpone(p, deal_id, body.until, body.reason))
    return r


class NoteIn(BaseModel):
    text: str


@router.post("/bx/deals/{deal_id}/note")
def api_note(deal_id: int, body: NoteIn, p: dict = Depends(active)):
    if not body.text.strip():
        raise HTTPException(400, "пустая заметка")
    r = write(p, deal_id, "заметка", None, body.text.strip()[:2000])
    if r["bx"] == "error":
        raise HTTPException(502, r["error"])
    return r


@router.get("/bx/stages")
def api_stages(p: dict = Depends(active)):
    bx.need_bx(p)
    return [{"id": k, **v} for k, v in bx.stages().items() if not k.startswith("C")]


@router.get("/bx/status")
def api_status(p: dict = Depends(active)):
    return {"write": enabled()}
