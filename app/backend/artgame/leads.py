"""Лиды Битрикса для МОП (HEAD 05.11.2026): список, карточка, обязательные поля, итог звонка, «В сделку», отказ.

Читает и пишет тем же вебхуком, что и сделки (bx.read / bxw.CALL). Видимость как у сделок: МОП — где он ответственный,
HEAD — все. Поля «Услуга» и «Площадь» лида создаёт Кодекс (BX-MOP-FIELDS-20261105): пока их нет в crm.lead.fields,
приложение их не спрашивает и не пишет. Ничего не удаляется; каждая запись — в audit_log (bx_write, entity=lead).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import bx, bxw, db
from .work import active

router = APIRouter(prefix="/api")

L_CITY, L_ENTRY = "UF_CRM_1753202309", "UF_CRM_ARTGAME_ENTRY_POINT"
L_SERVICE, L_AREA = "UF_CRM_ARTGAME_LEAD_SERVICE", "UF_CRM_ARTGAME_LEAD_AREA"
NEW = {"NEW", "UC_93GBZP"}          # «Новый лид»
CONVERTED = "CONVERTED"
LIST_SELECT = ["ID", "TITLE", "NAME", "LAST_NAME", "STATUS_ID", "SOURCE_ID", "DATE_CREATE", "DATE_MODIFY", "ASSIGNED_BY_ID",
               "OPPORTUNITY", "PHONE", "CONTACT_ID", "COMPANY_ID", L_CITY, L_SERVICE, L_AREA]


# ---------- справочники ----------

def statuses() -> dict:
    out = {}
    for s in bx._rows(bx.read("crm.status.list", {"filter": {"ENTITY_ID": "STATUS"}}, ttl=bx.TTL_DICT)):
        out[s["STATUS_ID"]] = {"name": s["NAME"], "sort": int(s.get("SORT") or 0),
                               "semantic": (s.get("EXTRA") or {}).get("SEMANTICS") or "process"}
    return out


def fields() -> dict:
    j = bx.read("crm.lead.fields", {}, ttl=bx.TTL_DICT)
    return j.get("result", j) if isinstance(j, dict) else {}


def _items(code: str, src: dict | None = None) -> dict:
    return {str(i["ID"]): i["VALUE"] for i in ((src or fields()).get(code) or {}).get("items") or []}


def _city(raw: str) -> str:
    return raw.split(",", 1)[-1].strip() if raw else ""


def _phone(l: dict) -> str:
    v = l.get("PHONE") or []
    return v[0].get("VALUE", "") if isinstance(v, list) and v else ""


def _name(l: dict) -> str:
    n = " ".join(x.strip() for x in (l.get("NAME"), l.get("LAST_NAME")) if x and x.strip())
    return n or l.get("TITLE") or f"Лид № {l.get('ID')}"


def missing(l: dict, have: dict) -> list[str]:
    """Что нужно заполнить до «В сделку». Поля, которых ещё нет в Битриксе, не требуем."""
    out = []
    if not _phone(l):
        out.append("телефон")
    if not l.get(L_CITY):
        out.append("город")
    if L_SERVICE in have and not l.get(L_SERVICE):
        out.append("услуга")
    if L_AREA in have and not bx._num(l.get(L_AREA)):
        out.append("площадь")
    return out


def _row(l: dict, st: dict, have: dict, names: dict) -> dict:
    s = st.get(l.get("STATUS_ID")) or {}
    return {"id": int(l["ID"]), "title": l.get("TITLE") or "", "name": _name(l), "phone": _phone(l),
            "status": l.get("STATUS_ID"), "status_name": s.get("name", l.get("STATUS_ID")), "new": l.get("STATUS_ID") in NEW,
            "created": l.get("DATE_CREATE"), "modified": l.get("DATE_MODIFY"), "sum": bx._num(l.get("OPPORTUNITY")),
            "city": _city(_items(L_CITY, have).get(str(l.get(L_CITY) or ""), "")),
            "service": _items(L_SERVICE, have).get(str(l.get(L_SERVICE) or ""), "") if L_SERVICE in have else "",
            "area": bx._num(l.get(L_AREA)), "missing": missing(l, have),
            "manager": names.get(int(l.get("ASSIGNED_BY_ID") or 0), "")}


# ---------- чтение ----------

def my_leads(p: dict, fresh: bool = False) -> dict:
    uid = bx.need_bx(p)
    flt = {"STATUS_SEMANTIC_ID": "P"}
    if uid is not None:
        flt["ASSIGNED_BY_ID"] = uid
    rows = bx.read_all("crm.lead.list", {"filter": flt, "select": LIST_SELECT, "order": {"DATE_CREATE": "DESC"}}, fresh=fresh)
    st, have = statuses(), fields()
    names = {u["id"]: u["name"] for u in bx.users()} if uid is None else {}
    return {"leads": [_row(l, st, have, names) for l in rows], "all": uid is None}


def _lead(p: dict, lead_id: int, fresh: bool = False) -> dict:
    uid = bx.need_bx(p)
    j = bx.read("crm.lead.get", {"id": lead_id}, fresh=fresh)
    l = j.get("result", j) if isinstance(j, dict) else None
    if not l or not l.get("ID"):
        raise HTTPException(404, "Лид не найден")
    if uid is not None and int(l.get("ASSIGNED_BY_ID") or 0) != uid:
        raise HTTPException(403, "Это лид другого менеджера")
    return l


def feed(entity: str, eid: int, names: dict, fresh: bool = False) -> list:
    """Лента: комментарии + дела (звонки, чаты WhatsApp/Instagram, письма) одной лентой, новые сверху."""
    out = []
    tid = {"deal": 2, "lead": 1}[entity]
    try:
        for c in bx._rows(bx.read("crm.timeline.comment.list", {"filter": {"ENTITY_ID": eid, "ENTITY_TYPE": entity}, "order": {"ID": "DESC"}}, fresh=fresh))[:30]:
            out.append({"at": c.get("CREATED"), "who": names.get(int(c.get("AUTHOR_ID") or 0), ""), "text": c.get("COMMENT") or "", "kind": "comment"})
    except Exception as ex:
        print(f"timeline {entity} {eid}: {ex}")
    try:
        for a in bx._rows(bx.read("crm.activity.list", {"filter": {"OWNER_ID": eid, "OWNER_TYPE_ID": tid}, "order": {"ID": "DESC"},
                                                         "select": ["ID", "SUBJECT", "TYPE_ID", "PROVIDER_ID", "COMPLETED", "DEADLINE", "CREATED",
                                                                    "RESPONSIBLE_ID", "DIRECTION"]}, fresh=fresh))[:30]:
            prov = str(a.get("PROVIDER_ID") or "")
            kind = "chat" if prov in ("IMOPENLINES_SESSION", "CRM_WHATSAPP") or str(a.get("TYPE_ID")) == "6" else \
                {"1": "meeting", "2": "call", "3": "task", "4": "email"}.get(str(a.get("TYPE_ID")), "activity")
            out.append({"at": a.get("CREATED"), "who": names.get(int(a.get("RESPONSIBLE_ID") or 0), ""), "text": a.get("SUBJECT") or "",
                        "kind": kind, "dir": {"1": "in", "2": "out"}.get(str(a.get("DIRECTION")), ""),
                        "done": a.get("COMPLETED") == "Y", "deadline": a.get("DEADLINE")})
    except Exception as ex:
        print(f"activity {entity} {eid}: {ex}")
    out.sort(key=lambda x: x["at"] or "", reverse=True)
    return out[:40]


def lead_full(p: dict, lead_id: int, fresh: bool = False) -> dict:
    l = _lead(p, lead_id, fresh)
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "deal_open", "lead", lead_id, {"title": l.get("TITLE") or ""})
    st, have = statuses(), fields()
    names = {u["id"]: u["name"] for u in bx.users()}
    row = _row(l, st, have, names)
    row.update({"manager": names.get(int(l.get("ASSIGNED_BY_ID") or 0), ""), "comments": l.get("COMMENTS") or "",
                "city_id": str(l.get(L_CITY) or ""), "service_id": str(l.get(L_SERVICE) or ""),
                "feed": feed("lead", lead_id, names, fresh),
                "has": {"service": L_SERVICE in have, "area": L_AREA in have},
                "services": [{"id": k, "name": v} for k, v in _items(L_SERVICE, have).items()],
                "fail": [{"id": k, "name": v["name"]} for k, v in sorted(st.items(), key=lambda x: x[1]["sort"])
                         if v["semantic"] == "failure" and k != CONVERTED]})
    return row


def cities() -> list:
    return sorted(({"id": k, "name": _city(v)} for k, v in _items(L_CITY).items()), key=lambda x: x["name"])


# ---------- запись ----------

def lwrite(p: dict, lead_id: int, what: str, flds: dict | None = None, comment: str | None = None) -> dict:
    _lead(p, lead_id, fresh=True)
    flds = {k: v for k, v in (flds or {}).items() if v not in (None, "")}
    log = {"what": what, "fields": flds}
    if not bxw.enabled():
        log["bx"] = "off"
    else:
        try:
            if flds:
                bxw.CALL("crm.lead.update", {"id": lead_id, "fields": flds, "params": {"REGISTER_SONET_EVENT": "Y"}})
            if comment:
                bxw.CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": lead_id, "ENTITY_TYPE": "lead",
                                                                 "COMMENT": f"{p['full_name']} (приложение): {comment}"}})
            log["bx"] = "ok"
            bx._cache.clear()
        except Exception as ex:
            log["bx"], log["error"] = "error", str(ex)[:300]
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "bx_write", "lead", lead_id, log)
    if log["bx"] == "error":
        raise HTTPException(502, log["error"])
    return {"bx": log["bx"]}


class LeadIn(BaseModel):
    city: str | None = None       # ID пункта списка городов лида
    service: str | None = None    # ID пункта «Услуга» лида
    area: float | None = None
    sum: float | None = None


@router.get("/bx/leads")
def api_leads(fresh: int = 0, p: dict = Depends(active)):
    return my_leads(p, bool(fresh))


@router.get("/bx/leads/cities")
def api_cities(p: dict = Depends(active)):
    bx.need_bx(p)
    return cities()


@router.get("/bx/leads/{lead_id}")
def api_lead(lead_id: int, fresh: int = 0, p: dict = Depends(active)):
    return lead_full(p, lead_id, bool(fresh))


@router.post("/bx/leads/{lead_id}")
def api_lead_save(lead_id: int, body: LeadIn, p: dict = Depends(active)):
    have = fields()
    f, parts = {}, []
    if body.city:
        if body.city not in _items(L_CITY, have):
            raise HTTPException(400, "нет такого города")
        f[L_CITY] = body.city
        parts.append("город " + _city(_items(L_CITY, have)[body.city]))
    if body.service and L_SERVICE in have:
        f[L_SERVICE] = body.service
        parts.append("услуга " + _items(L_SERVICE, have).get(body.service, body.service))
    if body.area and L_AREA in have:
        f[L_AREA] = body.area
        parts.append(f"{body.area:g} м²")
    if body.sum:
        f["OPPORTUNITY"] = int(round(body.sum))
        parts.append(f"сумма {int(round(body.sum)):,} ₸".replace(",", " "))
    if not f:
        raise HTTPException(400, "нечего сохранять")
    return lwrite(p, lead_id, "поля лида", f, "заполнил: " + ", ".join(parts))


class StatusIn(BaseModel):
    status: str
    reason: str = ""


@router.post("/bx/leads/{lead_id}/status")
def api_lead_status(lead_id: int, body: StatusIn, p: dict = Depends(active)):
    st = statuses()
    if body.status not in st or body.status == CONVERTED:
        raise HTTPException(400, "нет такого статуса")
    if st[body.status]["semantic"] == "failure" and not body.reason.strip():
        raise HTTPException(400, "укажите причину отказа")
    note = f"перевёл в «{st[body.status]['name']}»" + (f": {body.reason.strip()}" if body.reason.strip() else "")
    return lwrite(p, lead_id, f"статус → {st[body.status]['name']}", {"STATUS_ID": body.status}, note)


@router.post("/bx/leads/{lead_id}/convert")
def api_convert(lead_id: int, p: dict = Depends(active)):
    """«В сделку»: контакт (если у лида его нет) → сделка в «1.1 Продажи РК» на первой стадии → лид «Сконвертирован».
    Город, услуга и площадь переносятся по названию в поля сделки."""
    l = _lead(p, lead_id, fresh=True)
    have = fields()
    miss = missing(l, have)
    if miss:
        raise HTTPException(400, "сначала заполните: " + ", ".join(miss))
    if not bxw.enabled():
        raise HTTPException(409, "запись в Битрикс выключена")
    uid = int(l.get("ASSIGNED_BY_ID") or 0) or bx.bx_id(p)
    log = {"what": "лид → сделка"}
    try:
        contact = int(l.get("CONTACT_ID") or 0)
        if not contact and not int(l.get("COMPANY_ID") or 0):
            j = bxw.CALL("crm.contact.add", {"fields": {"NAME": l.get("NAME") or _name(l), "LAST_NAME": l.get("LAST_NAME") or "",
                                                        "PHONE": [{"VALUE": _phone(l), "VALUE_TYPE": "WORK"}], "ASSIGNED_BY_ID": uid,
                                                        "SOURCE_ID": l.get("SOURCE_ID") or "", "LEAD_ID": lead_id}})
            contact = int(j.get("result") or 0)
        df = bx.deal_fields()
        deal = {"TITLE": l.get("TITLE") or _name(l), "CATEGORY_ID": 0, "STAGE_ID": "NEW", "ASSIGNED_BY_ID": uid, "LEAD_ID": lead_id,
                "OPPORTUNITY": bx._num(l.get("OPPORTUNITY")) or None, "SOURCE_ID": l.get("SOURCE_ID") or None,
                "CONTACT_ID": contact or None, "COMPANY_ID": int(l.get("COMPANY_ID") or 0) or None}
        city = _city(_items(L_CITY, have).get(str(l.get(L_CITY) or ""), ""))
        if city:
            deal[bx.CITY] = next((k for k, v in bx.enum_map(bx.CITY).items() if _city(v).lower() == city.lower()), None)
        svc = _items(L_SERVICE, have).get(str(l.get(L_SERVICE) or ""), "") if L_SERVICE in have else ""
        if svc:
            deal[bx.SERVICE] = next((k for k, v in bx.enum_map(bx.SERVICE).items() if v.lower() == svc.lower()), None)
        if bx._num(l.get(L_AREA)) and bx.AREA in df:
            deal[bx.AREA] = bx._num(l.get(L_AREA))
        deal = {k: v for k, v in deal.items() if v not in (None, "")}
        j = bxw.CALL("crm.deal.add", {"fields": deal, "params": {"REGISTER_SONET_EVENT": "Y"}})
        deal_id = int(j.get("result") or 0)
        if not deal_id:
            raise RuntimeError("Битрикс не вернул номер сделки")
        bxw.CALL("crm.lead.update", {"id": lead_id, "fields": {"STATUS_ID": CONVERTED}})
        bxw.CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal",
                                                         "COMMENT": f"{p['full_name']} (приложение): создал из лида № {lead_id}"}})
        log.update(bx="ok", deal=deal_id, contact=contact)
        bx._cache.clear()
    except Exception as ex:
        log.update(bx="error", error=str(ex)[:300])
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "bx_write", "lead", lead_id, log)
    if log["bx"] == "error":
        raise HTTPException(502, log["error"])
    return {"bx": "ok", "deal": log["deal"]}


# ---------- итог звонка: и для лида, и для сделки ----------

RESULTS = {"reached": "дозвонился", "no_answer": "не дозвонился", "callback": "просил перезвонить", "chat": "написал в WhatsApp"}


class CallIn(BaseModel):
    result: str
    text: str = ""
    next: date | None = None   # когда перезвонить: задача в Битриксе + напоминание бота


@router.post("/bx/{entity}/{eid}/call")
def api_call(entity: str, eid: int, body: CallIn, p: dict = Depends(active)):
    if entity not in ("deals", "leads") or body.result not in RESULTS:
        raise HTTPException(400, "не тот звонок")
    if body.next and body.next < date.today():
        raise HTTPException(400, "дата перезвона уже прошла")
    note = RESULTS[body.result] + (f": {body.text.strip()}" if body.text.strip() else "") + \
        (f". Перезвонить {body.next:%d.%m.%Y}" if body.next else "")
    ent = entity[:-1]
    if ent == "deal":
        r = bxw.write(p, eid, "итог звонка", None, note)
        if r["bx"] == "error":
            raise HTTPException(502, r["error"])
    else:
        r = lwrite(p, eid, "итог звонка", None, note)
    if body.next:
        r.update(remind(p, ent, eid, body.next, note))
    return r


def remind(p: dict, entity: str, eid: int, due: date, note: str) -> dict:
    """Задача в Битриксе с дедлайном + напоминание бота в этот день (как «Отложено»)."""
    out = {"task": None}
    uid = bx.bx_id(p)
    if bxw.enabled() and uid:
        try:
            j = bxw.CALL("tasks.task.add", {"fields": {"TITLE": f"Перезвонить: {'сделка' if entity == 'deal' else 'лид'} № {eid}",
                                                       "RESPONSIBLE_ID": uid, "CREATED_BY": uid, "DEADLINE": f"{due.isoformat()}T10:00:00+05:00",
                                                       "DESCRIPTION": note, "UF_CRM_TASK": [f"{'D' if entity == 'deal' else 'L'}_{eid}"]}})
            out["task"] = int(((j.get("result") or {}).get("task") or {}).get("id") or 0) or None
        except Exception as ex:
            out["task_error"] = str(ex)[:200]
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO bx_reminders (person_id, deal_id, due, note, entity) VALUES (%s, %s, %s, %s, %s)",
                     (p["id"], eid, due, note, entity))
    return out
