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
F_START, F_END = "UF_CRM_ARTGAME_PROJECT_START_ACTUAL", "UF_CRM_ARTGAME_PROJECT_END_PLAN"
WRITABLE = {"OPPORTUNITY", "STAGE_ID", F_START, F_END, bx.AREA, bx.SERVICE, bx.ADDR, bx.CITY, F_ADV, F_DAYS, F_WARR, F_INV_SUM, F_INV_PURPOSE, F_REASON,
            F_KP, F_CONTRACT, F_INVOICES, F_OTHER, bx.F_LEVEL, bx.F_SHIFTS, bx.F_CREW, bx.F_TERM, "TITLE", bx.OBJECT, *bx.PROJECT}
KEEP_EMPTY = {k for k, (_, kind) in bx.PROJECT.items() if kind in ("bool", "users")}   # «нет» и пустой список — тоже значение
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
# Причины отказа (HEAD 06.11 «причины ок»): одна из восьми + строка комментария. Поле-список в Битриксе создаст Кодекс,
# до этого причина пишется текстом в поле причины и в ленту. «Прочее» нет нарочно — иначе отчёт пустеет.
REASONS = [("price", "Дорого: бюджет клиента ниже"), ("competitor", "Выбрал другого подрядчика"), ("postponed", "Передумал или отложил проект"),
           ("silent", "Не вышел на связь"), ("profile", "Не наш профиль: услуга, город или объём меньше минимума"),
           ("terms", "Не устроили сроки"), ("sketch", "Не согласовали эскиз"), ("spam", "Дубль, спам, ошибочная заявка")]
REASON = dict(REASONS)
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


def _same(got, want) -> bool:
    """Сверка после записи: «60» = 60.0, дата «2026-11-06» = «2026-11-06T03:00:00+03:00», адрес — до «|»,
    списки — без порядка, да/нет — 1/Y/true."""
    if isinstance(want, list) or isinstance(got, list):
        norm = lambda x: {str(i) for i in (x if isinstance(x, list) else [x]) if i not in (None, "", False)}  # noqa: E731
        return norm(got) == norm(want)
    if want in ("Y", "N"):
        return (str(got) in ("1", "Y", "True", "true")) == (want == "Y")
    a, b = str(got or "").split("|")[0], str(want).split("|")[0]
    if a == b:
        return True
    if len(b) == 10 and b[4] == "-" and a[:10] == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def write(p: dict, deal_id: int, what: str, fields: dict | None = None, comment: str | None = None,
          file: tuple[Path, str, str] | None = None, stage_for: str | None = None) -> dict:
    """Одна запись: поля + файл + комментарий в ленту. Проверка прав по текущей сделке из Битрикса."""
    d = bx._deal(p, deal_id, fresh=True)
    fields = {k: v for k, v in (fields or {}).items() if k in WRITABLE and (k in KEEP_EMPTY and v is not None or v not in (None, "", 0, "0"))}
    held = []
    if stage_for and stage_for in STAGE_FLOW:
        to, allowed = STAGE_FLOW[stage_for]
        if d["STAGE_ID"] in allowed:
            from . import fill
            # что даёт сама запись: скачанный файл и поля из документа (аванс, срок, гарантия, адрес, площадь)
            given = {F_ADV: "adv", F_DAYS: "days", F_WARR: "warranty", bx.ADDR: "address", bx.AREA: "area", "OPPORTUNITY": "sum"}
            done = tuple(v for k, v in given.items() if fields.get(k)) + ((stage_for,) if stage_for in ("kp", "signed") else ())
            held = fill.gate(p, deal_id, d["STAGE_ID"], to, done=done)
            if not held:
                fields["STAGE_ID"] = to
    log = {"what": what, "fields": {k: (v if not isinstance(v, dict) else "файл") for k, v in fields.items()}}
    if held:
        log["held"] = held   # файл записан, стадию не двигаем: карточка не заполнена (HEAD 06.11)
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
        bad = [k for k, v in fields.items() if k not in MULTI_FILE and not isinstance(v, dict) and not _same(after.get(k), v)]
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
    return {"bx": "ok", "fields": log["fields"], "stage": fields.get("STAGE_ID"), "held": held}


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


def norm_fields(area, level, service="mural", height=False, outdoor=False) -> tuple[dict, dict]:
    """Поля сделки «Сложность / Смен по норме / Художников по норме / Срок» из расчёта. Пишем только те поля,
    что уже созданы в Битриксе (до задания Кодексу BX-MOP-FIELDS-20261105 их нет)."""
    r = bx.resources(area, level, service, height, outdoor)
    if not r:
        return {}, {}
    have = bx.deal_fields()
    fields = {}
    if bx.F_SHIFTS in have:
        fields.update({bx.F_SHIFTS: r["shifts"], bx.F_CREW: r["crew"], bx.F_TERM: r["client"]})
    if r["level"] and bx.F_LEVEL in have:
        lid = next((i for i, v in bx.enum_map(bx.F_LEVEL).items() if v == bx.LEVELS[r["level"]]), None)
        if lid:
            fields[bx.F_LEVEL] = lid
    return fields, r


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
        nf, r = norm_fields(area, f.get("level") or "", f.get("service") or "mural", bool(f.get("height")), bool(f.get("outdoor")))
        fields.update(nf)
        if r:
            parts.append(f"по норме {r['shifts']:g} смен, {r['crew']} чел., срок {r['client']} дн.")
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
    reason_code: str | None = None   # одна из REASONS — обязательна при отказе
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
    if st[body.stage]["semantic"] not in ("failure", "apology") and body.stage != POSTPONED:
        from . import fill
        cur = bx._deal(p, deal_id, fresh=True)["STAGE_ID"]
        miss = fill.gate(p, deal_id, cur, body.stage)
        if miss:   # замок (HEAD 06.11): вперёд по воронке — только с заполненной карточкой
            raise HTTPException(409, "сначала заполните: " + ", ".join(miss))
    if st[body.stage]["semantic"] in ("failure", "apology"):
        if body.reason_code not in REASON:
            raise HTTPException(400, "выберите причину отказа из списка")
        body.reason = REASON[body.reason_code] + (f". {body.reason.strip()}" if body.reason and body.reason.strip() else "")
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


class CalcIn(BaseModel):
    area: float
    level: str = "medium"
    service: str = "mural"
    height: bool = False
    outdoor: bool = False


@router.post("/bx/deals/{deal_id}/calc")
def api_calc(deal_id: int, body: CalcIn, p: dict = Depends(active)):
    """Расчёт из карточки: площадь и сложность → смены, люди, срок по нормам → в сделку. МОП руками не вводит."""
    if body.area <= 0:
        raise HTTPException(400, "укажите площадь")
    fields, r = norm_fields(body.area, body.level, body.service, body.height, body.outdoor)
    if not r:
        raise HTTPException(400, "нечего считать")
    fields[bx.AREA] = body.area
    lvl = bx.LEVELS.get(r["level"], "") if r["level"] else "печать"
    out = write(p, deal_id, "расчёт срока и ресурсов", fields,
                f"расчёт: {body.area:g} м² {lvl}: {r['shifts']:g} смен, {r['crew']} чел., {r['client']} раб. дн. клиенту")
    if out["bx"] == "error":
        raise HTTPException(502, out["error"])
    out["calc"] = r
    out["norm_fields"] = bx.F_SHIFTS in fields
    return out


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


@router.get("/bx/reasons")
def api_reasons(p: dict = Depends(active)):
    return [{"code": c, "name": n} for c, n in REASONS]


class FieldsIn(BaseModel):
    area: float | None = None
    service: str | None = None    # ID пункта списка «Услуга»
    city: str | None = None       # ID пункта списка «Город»
    address: str | None = None
    adv: int | None = None        # аванс, %
    days: int | None = None       # срок по договору, календарных дней
    warranty: int | None = None   # гарантия, месяцев
    start: date | None = None     # старт факт
    end: date | None = None       # окончание план
    object: str | None = None     # «Объект» — из него и города собирается название сделки
    project: dict | None = None   # поля проекта: {model, category, …} (bx.PROJECT)


def _project_fields(vals: dict) -> tuple[dict, list]:
    """Поля проекта из карточки → коды Битрикса и строка для ленты. Неизвестные ключи и чужие значения — мимо."""
    pd = bx.project_dict()
    users = {u["id"]: u["name"] for u in pd["users"]}
    fields, parts = {}, []
    for key, val in vals.items():
        code = bx.PROJECT_KEY.get(key)
        if not code or key not in pd["have"]:
            continue
        _, kind = bx.PROJECT[code]
        title = (bx.deal_fields().get(code) or {}).get("listLabel") or (bx.deal_fields().get(code) or {}).get("formLabel") or key
        if kind == "enum":
            opts = {o["id"]: o["name"] for o in pd.get(key, [])}
            if str(val) not in opts:
                continue
            fields[code], txt = str(val), opts[str(val)]
        elif kind == "bool":
            fields[code], txt = ("Y" if val else "N"), ("да" if val else "нет")
        elif kind == "user":
            if str(val) not in users:
                continue
            fields[code], txt = int(val), users[str(val)]
        elif kind == "users":
            ids = [str(x) for x in (val or []) if str(x) in users]
            fields[code], txt = [int(x) for x in ids], ", ".join(users[x] for x in ids) or "никого"
        elif kind == "date":
            if not val:
                continue
            fields[code], txt = str(val)[:10], f"{str(val)[8:10]}.{str(val)[5:7]}.{str(val)[:4]}"
        else:
            if not str(val).strip():
                continue
            fields[code], txt = str(val).strip()[:200], str(val).strip()[:200]
        parts.append(f"{title}: {txt}")
    return fields, parts


@router.post("/bx/deals/{deal_id}/fields")
def api_fields(deal_id: int, body: FieldsIn, p: dict = Depends(active)):
    """Квалификация из шага «Клиент»: город, услуга, площадь, адрес — в сделку Битрикса."""
    fields, parts = {}, []
    if body.area:
        fields[bx.AREA] = body.area
        parts.append(f"{body.area:g} м²")
    if body.service:
        fields[bx.SERVICE] = body.service
        parts.append(bx.enum_map(bx.SERVICE).get(str(body.service), "услуга"))
    if body.city:
        fields[bx.CITY] = body.city
        parts.append(bx.city_name(body.city) or "город")
    if body.address is not None and body.address.strip():
        fields[bx.ADDR] = body.address.strip()
        parts.append(body.address.strip())
    for val, key, txt in ((body.adv, F_ADV, "аванс {}%"), (body.days, F_DAYS, "срок {} дн."), (body.warranty, F_WARR, "гарантия {} мес."),
                          (body.start, F_START, "старт {}"), (body.end, F_END, "сдача план {}")):
        if val:
            fields[key] = val.isoformat() if isinstance(val, date) else (str(val) if key == F_DAYS else val)
            parts.append(txt.format(val.strftime("%d.%m.%Y") if isinstance(val, date) else val))
    if body.project:
        pf, pp = _project_fields(body.project)
        fields.update(pf)
        parts += pp
    if (body.object is not None and body.object.strip()) or body.city:
        # название по правилу «№ · ОБЪЕКТ — ГОРОД» — из «Объекта» и «Города» (HEAD 06.11)
        d = bx._deal(p, deal_id, fresh=True)
        obj = body.object.strip() if body.object and body.object.strip() else (d.get(bx.OBJECT) or "")
        if body.object and body.object.strip() and body.object.strip() != (d.get(bx.OBJECT) or ""):
            fields[bx.OBJECT] = body.object.strip()[:120]
            parts.append("объект " + body.object.strip()[:120])
        if obj:
            title = bx.make_title(deal_id, obj, bx.city_name(body.city or d.get(bx.CITY)))
            if title != (d.get("TITLE") or ""):
                fields["TITLE"] = title
    if not fields:
        raise HTTPException(400, "нечего менять")
    r = write(p, deal_id, "карточка сделки", fields, "уточнил: " + ", ".join(parts) if parts else None)
    if r["bx"] == "error":
        raise HTTPException(502, r["error"])
    return r


@router.get("/bx/dict")
def api_dict(p: dict = Depends(active)):
    """Справочники для карточки: города и услуги сделки (списки Битрикса)."""
    bx.need_bx(p)
    return {"cities": bx.deal_cities(), "services": [{"id": k, "name": v} for k, v in bx.enum_map(bx.SERVICE).items()],
            "project": bx.project_dict()}


class ContactIn(BaseModel):
    name: str | None = None
    phone: str | None = None


@router.post("/bx/deals/{deal_id}/contact")
def api_contact(deal_id: int, body: ContactIn | None = None, p: dict = Depends(active)):
    """Сделка без «Контакта» (перевели в Битриксе «Сделка» без «Контакт»): контакт из лида или из того, что ввёл МОП."""
    body = body or ContactIn()
    d = bx._deal(p, deal_id, fresh=True)
    if int(d.get("CONTACT_ID") or 0) or int(d.get("COMPANY_ID") or 0):
        raise HTTPException(409, "у сделки уже есть клиент")
    lead = bx._entity("crm.lead.get", d.get("LEAD_ID")) if d.get("LEAD_ID") else {}
    phone = (body.phone or "").strip() or bx._fm(lead, "PHONE")
    name = (body.name or "").strip() or " ".join(x.strip() for x in (lead.get("NAME"), lead.get("LAST_NAME")) if x and x.strip())
    if not phone:
        raise HTTPException(400, "нет телефона: введите номер клиента")
    if not enabled():
        raise HTTPException(409, "запись в Битрикс выключена")
    log = {"what": "контакт из лида" if lead else "контакт"}
    try:
        j = CALL("crm.contact.add", {"fields": {"NAME": name or "Клиент", "PHONE": [{"VALUE": phone, "VALUE_TYPE": "WORK"}],
                                                "ASSIGNED_BY_ID": int(d.get("ASSIGNED_BY_ID") or 0) or None,
                                                "SOURCE_ID": lead.get("SOURCE_ID") or None, "LEAD_ID": int(d.get("LEAD_ID") or 0) or None}})
        cid = int(j.get("result") or 0)
        if not cid:
            raise RuntimeError("Битрикс не вернул номер контакта")
        CALL("crm.deal.update", {"id": deal_id, "fields": {"CONTACT_ID": cid}})
        CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal",
                                                     "COMMENT": f"{p['full_name']} (приложение): добавил контакт {name} {phone}"}})
        log.update(bx="ok", contact=cid)
        bx._cache.clear()
    except Exception as ex:
        log.update(bx="error", error=str(ex)[:300])
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "bx_write", "deal", deal_id, log)
    if log["bx"] == "error":
        raise HTTPException(502, log["error"])
    return {"bx": "ok", "contact": log["contact"]}


@router.get("/bx/stages")
def api_stages(p: dict = Depends(active)):
    bx.need_bx(p)
    return [{"id": k, **v} for k, v in bx.stages().items() if not k.startswith("C")]


def portal() -> str:
    """Адрес портала из вебхука: https://artgame.bitrix24.kz — для ссылок «открыть в Битриксе» (звонок, Wazzup — там)."""
    from urllib.parse import urlsplit
    u = urlsplit(settings.bitrix_webhook or "")
    return f"{u.scheme}://{u.netloc}" if u.netloc else ""


@router.get("/bx/status")
def api_status(p: dict = Depends(active)):
    return {"write": enabled(), "portal": portal()}
