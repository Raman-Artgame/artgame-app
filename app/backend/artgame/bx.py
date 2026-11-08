"""Сделки Битрикса для МОП — чтение (шлюз ARTGAME, а если он не задан — вебхук приложения). Запись — bxw.py, лиды — leads.py.

Кто что видит: МОП и VIP МОП — сделки, где он ответственный (people.bitrix_user_id = ASSIGNED_BY_ID); HEAD — все.
Связку человек ↔ пользователь Битрикса ставит HEAD во вкладке «Команда».
Ответы кешируются на 2 минуты (кнопка «Обновить» — без кеша), справочники (стадии, города) — на час.
"""
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from . import db
from .config import settings
from .work import active

router = APIRouter(prefix="/api")

SEE_ALL = {"head"}
BX_ROLES = {"mop", "mop_vip", "head"}
CATEGORIES = (0, 13)                       # 1.1 Продажи РК, Дизайн РК
CITY = "UF_CRM_6881101914D8D"
ADDR = "UF_CRM_1755520919823"
SERVICE = "UF_CRM_1753294730602"
AREA = "UF_CRM_ARTGAME_AREA_M2"
# Срок и ресурсы — считает приложение по нормам «Значений», МОП руками не вводит (HEAD 05.11). Поля создаёт Кодекс.
F_LEVEL, F_SHIFTS, F_CREW, F_TERM = "UF_CRM_ARTGAME_COMPLEXITY", "UF_CRM_ARTGAME_NORM_SHIFTS", "UF_CRM_ARTGAME_NORM_CREW", "UF_CRM_ARTGAME_TERM_DAYS"
LEVELS = {"easy": "Лёгкий", "medium": "Средний", "hard": "Сложный", "author": "Авторский"}
OBJECT = "UF_CRM_ARTGAME_OBJECT"
# Поля проекта (HEAD 07.11 «модели и всех этих пунктов нет»): код → (ключ в приложении, тип)
PROJECT = {"UF_CRM_ARTGAME_PROJECT_MODEL": ("model", "enum"), "UF_CRM_ARTGAME_PROJECT_CATEGORY": ("category", "enum"),
           "UF_CRM_ARTGAME_PROJECT_SUBCATEGORY": ("subcategory", "enum"), "UF_CRM_ARTGAME_PROJECT_SIZE": ("size", "enum"),
           "UF_CRM_ARTGAME_PROJECT_VIP": ("vip", "bool"), "UF_CRM_ARTGAME_PROJECT_CURATOR": ("curator", "user"),
           "UF_CRM_ARTGAME_RESP_EXECUTOR": ("executor", "user"), "UF_CRM_1753381517": ("artists", "users"),
           "UF_CRM_ARTGAME_DESIGNER": ("designer", "user"), "UF_CRM_ARTGAME_DESIGN_COMPLEXITY": ("design_level", "enum"),
           "UF_CRM_ARTGAME_DESIGN_DEADLINE": ("design_deadline", "date"), "UF_CRM_6AD5EF400C4B9": ("entry", "enum"),
           "UF_CRM_1753292354197": ("contract_no", "text")}
PROJECT_KEY = {v[0]: k for k, v in PROJECT.items()}
LIST_SELECT = ["ID", "TITLE", "STAGE_ID", "CATEGORY_ID", "OPPORTUNITY", "ASSIGNED_BY_ID", "CONTACT_ID", "COMPANY_ID", "LEAD_ID", OBJECT,
               "DATE_MODIFY", "DATE_CREATE", "LAST_ACTIVITY_TIME", CITY, AREA]
FUNNELS = {0: "Продажи", 13: "Дизайн"}
TTL, TTL_DICT, MAX_PAGES = 120, 3600, 10

_cache: dict = {}
_lock = threading.Lock()
_gw = None


# ---------- чтение через шлюз ----------

def _webhook_read(method: str, params: dict):
    """Чтение тем же вебхуком, что и запись (шлюз ARTGAME-MCP на сервере только под OAuth, 05.11).
    Битрикс пускает ~2 запроса в секунду: на QUERY_LIMIT_EXCEEDED ждём и повторяем; сеть/таймаут — 502, а не 500."""
    import httpx
    for attempt in range(4):
        try:
            r = httpx.post(settings.bitrix_webhook.rstrip("/") + "/" + method, json=params, timeout=30)
        except httpx.HTTPError as ex:
            if attempt < 1:
                continue
            raise HTTPException(502, f"Битрикс не ответил: {type(ex).__name__}")
        try:
            j = r.json()
        except ValueError:
            raise HTTPException(502, f"Битрикс не ответил: {r.status_code}")
        if isinstance(j, dict) and j.get("error") == "QUERY_LIMIT_EXCEEDED" and attempt < 3:
            time.sleep(1 + attempt)
            continue
        if isinstance(j, dict) and "error" in j:
            raise HTTPException(502, f"Битрикс: {str(j.get('error_description') or j['error'])[:200]}")
        return j
    raise HTTPException(502, "Битрикс: слишком много запросов, повторите через минуту")


def _gateway_read(method: str, params: dict):
    global _gw
    if not settings.gateway_url:
        if settings.bitrix_webhook:
            return _webhook_read(method, params)
        raise HTTPException(503, "Битрикс не подключён (нет адреса шлюза и вебхука)")
    from .sync_objects import Gateway
    for attempt in (1, 2):
        try:
            if _gw is None:
                _gw = Gateway(settings.gateway_url, settings.gateway_token).open()
            return _gw.bitrix_read(method, params)
        except Exception as ex:  # сессия шлюза могла истечь — один раз переоткрываем
            _gw = None
            if attempt == 2:
                raise HTTPException(502, f"Битрикс не ответил: {str(ex)[:200]}")


READ = _gateway_read  # тесты подменяют


def read(method: str, params: dict, ttl: int = TTL, fresh: bool = False):
    key = (method, repr(sorted(params.items())))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit and not fresh and now - hit[0] < ttl:
        return hit[1]
    data = READ(method, params)
    with _lock:
        _cache[key] = (now, data)
    return data


def _rows(j):
    """Список строк из ответа Битрикса: [..] | {"result": [..]} | {"result": {"items": [..]}} (crm.stagehistory, crm.item)."""
    r = j if isinstance(j, list) else (j or {}).get("result", [])
    if isinstance(r, dict):
        r = r.get("items") or r.get("tasks") or []
    return r if isinstance(r, list) else []


def read_all(method: str, params: dict, fresh: bool = False) -> list:
    out, start = [], 0
    for _ in range(MAX_PAGES):
        j = read(method, {**params, "start": start}, fresh=fresh)
        out += _rows(j)
        start = None if isinstance(j, list) else j.get("next")
        if start is None:
            break
    return out


def read_many(method: str, plist: dict, fresh: bool = False) -> tuple[dict, str]:
    """Много однотипных чтений ({ключ: параметры}) → ({ключ: ответ}, текст первой ошибки).
    Через вебхук — пачками batch по 50 (один запрос вместо пятидесяти), иначе по одному до первой ошибки."""
    from urllib.parse import urlencode
    out, todo, now = {}, {}, time.time()
    for k, prm in plist.items():
        with _lock:
            hit = _cache.get((method, repr(sorted(prm.items()))))
        if hit and not fresh and now - hit[0] < TTL:
            out[k] = hit[1]
        else:
            todo[k] = prm
    if not todo:
        return out, ""
    if READ is _gateway_read and not settings.gateway_url and settings.bitrix_webhook:
        keys, err = list(todo), ""
        for i in range(0, len(keys), 50):
            part = keys[i:i + 50]
            try:
                j = _webhook_read("batch", {"halt": 0, "cmd": {k: method + "?" + urlencode(todo[k]) for k in part}})
            except HTTPException as ex:
                return out, str(ex.detail)
            res = j.get("result") if isinstance(j, dict) else None
            ok = (res or {}).get("result") if isinstance(res, dict) else None
            bad = (res or {}).get("result_error") if isinstance(res, dict) else None
            ok, bad = ok if isinstance(ok, dict) else {}, bad if isinstance(bad, dict) else {}
            for k in part:
                if k in ok:
                    out[k] = {"result": ok[k]}
                    with _lock:
                        _cache[(method, repr(sorted(todo[k].items())))] = (now, out[k])
                elif k in bad and not err:
                    e = bad[k]
                    err = "Битрикс: " + str((e.get("error_description") or e.get("error")) if isinstance(e, dict) else e)[:200]
        return out, err
    for k, prm in todo.items():
        try:
            out[k] = read(method, prm, fresh=fresh)
        except HTTPException as ex:
            return out, str(ex.detail)
    return out, ""


# ---------- справочники ----------

def stages() -> dict:
    out = {}
    for ent in ("DEAL_STAGE", "DEAL_STAGE_13", "DEAL_STAGE_1"):
        try:
            for s in _rows(read("crm.status.list", {"filter": {"ENTITY_ID": ent}}, ttl=TTL_DICT)):
                out[s["STATUS_ID"]] = {"name": s["NAME"], "sort": int(s.get("SORT") or 0),
                                       "semantic": (s.get("EXTRA") or {}).get("SEMANTICS") or "process"}
        except HTTPException:
            pass
    return out


def deal_fields() -> dict:
    j = read("crm.deal.fields", {}, ttl=TTL_DICT)
    return j.get("result", j) if isinstance(j, dict) else {}


def enum_map(code: str) -> dict:
    items = (deal_fields().get(code) or {}).get("items") or []
    return {str(i["ID"]): i["VALUE"] for i in items}


def city_name(v) -> str:
    raw = enum_map(CITY).get(str(v or ""), "")
    return raw.split(",", 1)[-1].strip() if raw else ""


def deal_cities() -> list:
    """Города СДЕЛКИ (свой список Битрикса, ID не совпадают с городами лида) — для карточки сделки."""
    return sorted(({"id": k, "name": v.split(",", 1)[-1].strip()} for k, v in enum_map(CITY).items()), key=lambda x: x["name"])


def city_find(name: str) -> str | None:
    """ID города сделки по названию: «Астана» найдёт «Казахстан, Астана (Нур-Султан)»."""
    n = (name or "").strip().lower()
    if not n:
        return None
    best = None
    for k, v in enum_map(CITY).items():
        c = v.split(",", 1)[-1].strip().lower()
        if c == n:
            return k
        if best is None and c.split(" (")[0] == n:
            best = k
    return best


def make_title(deal_id: int, obj: str, city: str) -> str:
    """Правило названия сделки (как у старых сделок): «1237 · ШКОЛА №12 — ШАХТИНСК». Город без скобок."""
    obj, city = (obj or "").strip(), (city or "").split(" (")[0].strip()
    return f"{deal_id} · {obj.upper()}" + (f" — {city.upper()}" if city else "")


def users() -> list:
    rows = _rows(read("user.get", {"ACTIVE": True}, ttl=TTL_DICT))
    return [{"id": int(u["ID"]), "name": " ".join(x.strip() for x in (u.get("NAME"), u.get("LAST_NAME")) if x and x.strip()),
             "position": u.get("WORK_POSITION") or "", "phone": u.get("PERSONAL_MOBILE") or u.get("WORK_PHONE") or ""}
            for u in rows if u.get("USER_TYPE", "employee") == "employee"]


# ---------- доступ ----------

def bx_id(p: dict) -> int | None:
    with db.pool.connection() as conn:
        r = conn.execute("SELECT bitrix_user_id FROM people WHERE id=%s", (p["id"],)).fetchone()
    return r["bitrix_user_id"] if r else None


def need_bx(p: dict) -> int | None:
    """None — видит все сделки (HEAD); иначе ID ответственного в Битриксе."""
    if p["role_code"] not in BX_ROLES:
        raise HTTPException(403, "Сделки видят МОП и HEAD")
    if p["role_code"] in SEE_ALL:
        return None
    uid = bx_id(p)
    if not uid:
        raise HTTPException(409, "HEAD ещё не связал вас с пользователем Битрикса (вкладка «Команда»)")
    return uid


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------- сделки ----------

def my_deals(p: dict, fresh: bool = False, manager: int | None = None) -> dict:
    uid = need_bx(p)
    flt = {"CATEGORY_ID": list(CATEGORIES), "STAGE_SEMANTIC_ID": "P"}
    if uid is not None:
        flt["ASSIGNED_BY_ID"] = uid
    elif manager:
        flt["ASSIGNED_BY_ID"] = manager
    rows = read_all("crm.deal.list", {"filter": flt, "select": LIST_SELECT, "order": {"DATE_MODIFY": "DESC"}}, fresh=fresh)
    st = stages()
    names = {u["id"]: u["name"] for u in users()} if uid is None else {}
    deals = [{"id": int(d["ID"]), "title": d.get("TITLE") or "", "stage": d["STAGE_ID"],
              "stage_name": (st.get(d["STAGE_ID"]) or {}).get("name", d["STAGE_ID"]),
              "stage_sort": (st.get(d["STAGE_ID"]) or {}).get("sort", 0),
              "category": int(d.get("CATEGORY_ID") or 0), "sum": _num(d.get("OPPORTUNITY")),
              "area": _num(d.get(AREA)), "city": city_name(d.get(CITY)), "modified": d.get("DATE_MODIFY"),
              "created": d.get("DATE_CREATE"), "active": d.get("LAST_ACTIVITY_TIME") or d.get("DATE_MODIFY"),
              "manager_id": int(d.get("ASSIGNED_BY_ID") or 0), "lead_id": int(d.get("LEAD_ID") or 0), "object": d.get(OBJECT) or "",
              "manager": names.get(int(d.get("ASSIGNED_BY_ID") or 0), "") if uid is None else ""} for d in rows]
    return {"deals": deals, "all": uid is None, "updated": time.time(), "funnels": FUNNELS,
            "managers": sorted({(d["manager_id"], d["manager"]) for d in deals if d["manager"]}, key=lambda x: x[1]) if uid is None else []}


def _deal(p: dict, deal_id: int, fresh: bool = False) -> dict:
    uid = need_bx(p)
    j = read("crm.deal.get", {"id": deal_id}, fresh=fresh)
    d = j.get("result", j) if isinstance(j, dict) else None
    if not d or not d.get("ID"):
        raise HTTPException(404, "Сделка не найдена")
    if uid is not None and int(d.get("ASSIGNED_BY_ID") or 0) != uid:
        raise HTTPException(403, "Это сделка другого менеджера")
    return d


def _fm(e: dict, key: str) -> str:
    v = e.get(key) or []
    return v[0].get("VALUE", "") if isinstance(v, list) and v else ""


def _entity(method: str, eid) -> dict:
    if not eid or str(eid) in ("0", "None"):
        return {}
    try:
        j = read(method, {"id": int(eid)})
        return j.get("result", j) if isinstance(j, dict) else {}
    except HTTPException:
        return {}


def requisites(company_id) -> dict | None:
    """Реквизиты компании (crm.requisite.list). Если шлюз не даёт этот метод — None, МОП вводит вручную."""
    if not company_id or str(company_id) == "0":
        return None
    try:
        rows = _rows(read("crm.requisite.list", {"filter": {"ENTITY_TYPE_ID": 4, "ENTITY_ID": int(company_id)}}))
    except HTTPException:
        return None
    if not rows:
        return {}
    r = rows[0]
    out = {"cname": r.get("RQ_COMPANY_NAME") or r.get("RQ_NAME") or "", "cbin": r.get("RQ_BIN") or r.get("RQ_IIN") or "",
           "signer": r.get("RQ_DIRECTOR") or ""}
    try:
        banks = _rows(read("crm.requisite.bankdetail.list", {"filter": {"ENTITY_ID": int(r["ID"])}}))
        if banks:
            b = banks[0]
            out.update(cbank=b.get("RQ_BANK_NAME") or "", cbik=b.get("RQ_BIK") or "", ciik=b.get("RQ_ACC_NUM") or "")
    except HTTPException:
        pass
    return {k: v for k, v in out.items() if v}


def deal_card(p: dict, deal_id: int, fresh: bool = False, audit: bool = True) -> dict:
    d = _deal(p, deal_id, fresh)
    if audit:
        with db.pool.connection() as conn:
            db.audit(conn, p["id"], "deal_open", "deal", deal_id, {"title": d.get("TITLE") or "", "stage": d["STAGE_ID"]})
    comp = _entity("crm.company.get", d.get("COMPANY_ID"))
    cont = _entity("crm.contact.get", d.get("CONTACT_ID"))
    if comp:
        title = comp.get("TITLE") or ""
        ctype = "ИП" if title.upper().startswith("ИП") else "ТОО"
        client = {"type": ctype, "name": title, "phone": _fm(comp, "PHONE") or _fm(cont, "PHONE"),
                  "email": _fm(comp, "EMAIL") or _fm(cont, "EMAIL")}
    else:
        name = " ".join(x for x in (cont.get("LAST_NAME"), cont.get("NAME"), cont.get("SECOND_NAME")) if x)
        client = {"type": "Физлицо", "name": name, "phone": _fm(cont, "PHONE"), "email": _fm(cont, "EMAIL")}
    contact = " ".join(x for x in (cont.get("NAME"), cont.get("LAST_NAME")) if x)
    lead_id = int(d.get("LEAD_ID") or 0)
    client["no_contact"] = not cont and not comp
    if not client.get("phone") and lead_id:
        # сделку завели в Битриксе без «Контакта» — телефон остался на лиде (HEAD 07.11, список Анны)
        lead = _entity("crm.lead.get", lead_id)
        client["phone"] = _fm(lead, "PHONE")
        client["phone_from"] = "lead" if client["phone"] else ""
        if not client.get("name"):
            client["name"] = " ".join(x for x in (lead.get("NAME"), lead.get("LAST_NAME")) if x and x.strip())
    st = stages().get(d["STAGE_ID"]) or {}
    addr = d.get(ADDR)
    return {"id": int(d["ID"]), "title": d.get("TITLE") or "", "stage": d["STAGE_ID"], "stage_name": st.get("name", d["STAGE_ID"]),
            "sum": _num(d.get("OPPORTUNITY")), "area": _num(d.get(AREA)), "city": city_name(d.get(CITY)),
            "address": addr.split("|")[0] if isinstance(addr, str) else "",
            "service": enum_map(SERVICE).get(str(d.get(SERVICE) or ""), ""),
            "object": d.get(OBJECT) or "", "client": client, "contact": contact, "lead_id": lead_id,
            "project": project_values(d),
            "requisites": requisites(d.get("COMPANY_ID")) if comp else None}


def project_values(d: dict) -> dict:
    """Поля проекта сделки в виде {ключ: значение} — ID пунктов списков и пользователей строками, VIP — True/False."""
    out = {}
    for code, (key, kind) in PROJECT.items():
        v = d.get(code)
        if kind == "users":
            out[key] = [str(x) for x in (v if isinstance(v, list) else [v] if v else []) if x]
        elif kind == "bool":
            out[key] = str(v) in ("1", "Y", "True", "true")
        elif kind == "date":
            out[key] = str(v or "")[:10]
        else:
            out[key] = str(v or "") if v not in (None, False) else ""
    return out


def project_dict() -> dict:
    """Варианты для полей проекта: списки Битрикса и сотрудники."""
    f = deal_fields()
    out = {key: [{"id": str(i["ID"]), "name": i["VALUE"]} for i in (f.get(code) or {}).get("items") or []]
           for code, (key, kind) in PROJECT.items() if kind == "enum"}
    out["have"] = [key for code, (key, _) in PROJECT.items() if code in f]
    out["users"] = [{"id": str(u["id"]), "name": u["name"], "position": u["position"]} for u in users() if u["name"]]
    return out


# ---------- карточка сделки в приложении: история стадий, лента, файлы, оплаты ----------

FIN = {"received": "UF_CRM_ARTGAME_FIN03_RECEIVED", "debt": "UF_CRM_ARTGAME_FIN03_DEBT", "next": "UF_CRM_ARTGAME_FIN03_NEXT",
       "net": "UF_CRM_ARTGAME_FIN03_NET"}
FILES = {"UF_CRM_1753202415": "КП", "UF_CRM_1753202391": "Договор подписанный", "UF_CRM_ARTGAME_DOC05_INVOICES": "Счета",
         "UF_CRM_ARTGAME_DOC05_ACTS": "АВР", "UF_CRM_ARTGAME_DOC05_OTHER": "Прочие документы", "UF_CRM_ARTGAME_APPROVED_LAYOUT": "Эскиз"}


def _money(v) -> float:
    return _num(str(v or "").split("|")[0])


def deal_full(p: dict, deal_id: int, fresh: bool = False) -> dict:
    card = deal_card(p, deal_id, fresh)
    d = _deal(p, deal_id)
    st = stages()
    names = {u["id"]: u["name"] for u in users()}
    from .leads import feed as _feed
    hist, files = [], []
    try:
        for h in _rows(read("crm.stagehistory.list", {"entityTypeId": 2, "filter": {"OWNER_ID": deal_id}, "order": {"ID": "DESC"}}, fresh=fresh))[:20]:
            hist.append({"at": h.get("CREATED_TIME"), "stage": (st.get(h.get("STAGE_ID")) or {}).get("name", h.get("STAGE_ID"))})
    except Exception as ex:  # история — не главное, карточка открывается и без неё
        print(f"stagehistory {deal_id}: {ex}")
    feed = _feed("deal", deal_id, names, fresh)
    if card.get("lead_id"):
        # звонки и WhatsApp до перевода остаются на лиде — показываем их в сделке
        seen = {(x["at"], x["text"]) for x in feed}
        feed += [{**x, "lead": True} for x in _feed("lead", card["lead_id"], names, fresh) if (x["at"], x["text"]) not in seen]
        feed.sort(key=lambda x: x["at"] or "", reverse=True)
        feed = feed[:50]
    for k, title in FILES.items():
        v = d.get(k)
        if not v:
            continue
        items = v if isinstance(v, list) else [v]
        for it in items:
            if isinstance(it, dict):
                files.append({"title": title, "url": it.get("downloadUrl") or it.get("url") or "", "id": it.get("id")})
            elif isinstance(it, str) and it.startswith("http"):
                files.append({"title": title, "url": it})
    card.update({"history": hist, "feed": feed, "files": files, "manager": names.get(int(d.get("ASSIGNED_BY_ID") or 0), ""),
                 "created": d.get("DATE_CREATE"), "modified": d.get("DATE_MODIFY"), "comments": d.get("COMMENTS") or "",
                 "pay": {k: (_money(d.get(f)) if k != "next" else d.get(f)) for k, f in FIN.items()}, "category": int(d.get("CATEGORY_ID") or 0),
                 "level": level_key(d.get(F_LEVEL)), "norm": {"shifts": _num(d.get(F_SHIFTS)), "crew": _num(d.get(F_CREW)), "term": _num(d.get(F_TERM))},
                 "norm_fields": all(k in deal_fields() for k in (F_SHIFTS, F_CREW, F_TERM))})
    from .sales_exp import for_deal
    card["acq"] = for_deal(deal_id)   # траты отдела продаж по сделке — стоимость привлечения
    from . import fill
    card["fill"] = fill.state(d, card, fill.saved_calc(deal_id))
    card["fill"].update(required=fill.REQUIRED, step_of=fill.STAGE_STEP, free=p["role_code"] == "head")   # для замка в приложении
    return card


# ---------- срок и ресурсы по нормам ----------

def level_key(name) -> str:
    """«Средний» / ID пункта списка / ключ → ключ нормы (easy|medium|hard|author) или ''."""
    n = str(name or "").strip().lower()
    if n in LEVELS:
        return n
    n = enum_map(F_LEVEL).get(n, n).lower() if n else n
    return next((k for k, v in LEVELS.items() if v.lower() == n), "")


def resources(area: float, level: str = "medium", service: str = "mural", height: bool = False, outdoor: bool = False,
              surface: bool = False, white: bool = False, v: dict | None = None) -> dict:
    """Смены, люди, дни — по norm.* и print.* из «Значений» (утверждены 04–05.11). Нулевая площадь → пусто."""
    import math
    v = v if v is not None else _vals()
    area = float(area or 0)
    if area <= 0:
        return {}
    crew_m2 = float(v.get("norm.crew_per_m2") or 20)
    crew = int(min(12, max(2, math.ceil(area / crew_m2))))
    ink = 0.0
    if service == "print":
        shifts = area / float(v.get("print.plan_per_shift") or 18)
        ink = area * float(v.get("print.ink.white_ml" if white else "print.ink.cmyk_ml") or (30 if white else 15))
    else:
        lk = level_key(level) or "medium"
        k = (float(v.get("norm.k.height") or 0.8) if height else 1) * (float(v.get("norm.k.outdoor") or 0.9) if outdoor else 1) \
            * (float(v.get("norm.k.surface") or 0.85) if surface else 1)
        shifts = area / (float(v.get(f"norm.mural.{lk}") or {"easy": 20, "medium": 10, "hard": 5, "author": 2}[lk]) * k)
    shifts = math.ceil(shifts * 10) / 10
    prep = int(v.get("norm.prep_days.big") or 2) if area > float(v.get("norm.prep_threshold") or 100) else int(v.get("norm.prep_days.small") or 1)
    work = math.ceil(shifts / crew)
    days = prep + work
    client = math.ceil(days * (1 + float(v.get("norm.client_reserve") or 20) / 100))
    return {"shifts": shifts, "crew": crew, "prep": prep, "work": work, "days": days, "client": client, "ink": round(ink),
            "level": level_key(level) if service != "print" else "", "service": service}


# ---------- «Сегодня»: что требует действия ----------

def _days(iso: str | None) -> float:
    from datetime import datetime, timezone
    if not iso:
        return 0.0
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 86400
    except ValueError:
        return 0.0


_today_locks: dict = {}
_today_last: dict = {}


def today(p: dict, fresh: bool = False) -> dict:
    """Один расчёт на человека за раз: экран, счётчики меню и уведомления, пришедшие одновременно, получают один ответ."""
    t0 = time.time()
    with _lock:
        lk = _today_locks.setdefault(p["id"], threading.Lock())
    with lk:
        hit = _today_last.get(p["id"])
        if hit and hit[0] >= t0:          # посчитано, пока мы ждали
            return hit[1]
        out = _today(p, fresh)
        _today_last[p["id"]] = (time.time(), out)
        return out


def _tasks(p: dict, fresh: bool):
    uid = bx_id(p)
    if not uid:
        return []
    j = read("tasks.task.list", {"filter": {"RESPONSIBLE_ID": uid, "<REAL_STATUS": 5}, "order": {"DEADLINE": "asc"},
                                 "select": ["ID", "TITLE", "DEADLINE", "UF_CRM_TASK"]}, fresh=fresh)
    res = j.get("result", j) if isinstance(j, dict) else {}
    return (res.get("tasks") if isinstance(res, dict) else res) or []


def _today(p: dict, fresh: bool = False) -> dict:
    """Сделки, по которым пора действовать. Сроки — из «Значений» (mop.today.*), иначе по умолчанию.
    Сделки, лиды, звонки и задачи читаются из Битрикса параллельно; упал один источник — экран открывается
    без него с пометкой (warn), а не ошибкой."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    from . import calls
    from .leads import my_leads
    vals = _vals()
    new_h = float(vals.get("mop.today.new_hours") or 4)
    kp_d = float(vals.get("mop.today.kp_days") or 2)
    idle_d = float(vals.get("mop.today.idle_days") or 3)
    with ThreadPoolExecutor(4) as ex:
        f_deals, f_leads = ex.submit(my_deals, p, fresh), ex.submit(my_leads, p, fresh)
        f_calls, f_tasks = ex.submit(calls.missed, fresh), ex.submit(_tasks, p, fresh)
    warns = []

    def got(f, what, empty):
        try:
            return f.result()
        except HTTPException as e:
            if e.status_code in (403, 409):
                raise
            warns.append(f"{what}: {str(e.detail)[:120]}")
        except Exception as e:  # noqa: BLE001 — экран «Сегодня» не должен падать из-за одного источника
            warns.append(f"{what}: {type(e).__name__}")
        return empty

    deals = got(f_deals, "сделки не загрузились", {"deals": []})["deals"]
    out = {"new": [], "kp": [], "idle": [], "back": [], "tasks": [], "limits": {"new_hours": new_h, "kp_days": kp_d, "idle_days": idle_d}}
    with db.pool.connection() as conn:
        # последнее напоминание по каждой сделке/лиду: дата в будущем — «ждём ответа», не горит (HEAD 07.11);
        # дата пришла — «пора вернуться». Старше двух недель не показываем.
        rem = conn.execute("SELECT DISTINCT ON (entity, deal_id) entity, deal_id, due, note FROM bx_reminders "
                           "WHERE person_id=%s AND due >= current_date - 14 ORDER BY entity, deal_id, id DESC", (p["id"],)).fetchall()
    today_ = date.today()
    due = {r["deal_id"]: r for r in rem if r["entity"] == "deal" and r["due"] <= today_}
    lead_due = {r["deal_id"]: r for r in rem if r["entity"] == "lead" and r["due"] <= today_}
    waiting = {(r["entity"], r["deal_id"]): r for r in rem if r["due"] > today_}
    q = {"hot": [], "today": [], "later": []}
    item = lambda kind, d, why, **kw: {"entity": kind, "id": d["id"], "title": d.get("title") or d.get("name") or "", "why": why,  # noqa: E731
                                       "sum": d.get("sum") or 0, "stage": d.get("stage_name") or d.get("status_name") or "",
                                       "phone": d.get("phone") or "", "name": d.get("name") or "", **kw}
    for d in deals:
        # «новая заявка» — только недавно созданная сделка на первой стадии продаж; старые в NEW — «стоит»
        age, since_new = _days(d["active"]), _days(d["created"])
        code, sales = d["stage"].split(":")[-1], d["category"] == 0
        if d["id"] in due:
            r = due[d["id"]]
            out["back"].append({**d, "due": r["due"].isoformat(), "note": r["note"]})
            q["hot"].append(item("deal", d, "пора вернуться" + (f": {r['note']}" if r["note"] else "")))
        elif sales and code == "NEW" and since_new <= kp_d and since_new * 24 >= new_h:
            out["new"].append(d)
            q["hot"].append(item("deal", d, f"новая заявка без ответа {int(since_new * 24)} ч", action="call"))
        elif sales and code == "NEW" and since_new <= kp_d:
            q["today"].append(item("deal", d, "новая заявка", action="call"))
        elif sales and code == "PREPARATION" and age >= kp_d:
            out["kp"].append(d)
            q["today"].append(item("deal", d, f"КП без ответа {int(age)} дн.", action="call"))
        elif code != "UC_VCP4VO" and age >= idle_d:
            out["idle"].append(d)
            q["later"].append(item("deal", d, ("дизайн: " if not sales else "") + f"без движения {int(age)} дн." +
                                   (" в «Взаимном информировании»" if sales and code == "NEW" else "")))
    try:
        lst = got(f_leads, "лиды не загрузились", {"leads": []})["leads"]
    except HTTPException:
        lst = []                          # лиды МОП без связки с Битриксом — не повод ронять сделки
    leads_by_id = {l["id"]: l for l in lst}
    for l in lst:
        age = _days(l["created"] if l["new"] else l["modified"])
        if l["id"] in lead_due:
            n = lead_due[l["id"]]["note"]
            q["hot"].append(item("lead", l, "перезвонить" + (f": {n}" if n else ""), action="call"))
        elif l["new"] and age * 24 >= new_h:
            q["hot"].append(item("lead", l, f"новый лид без ответа {int(age * 24)} ч", action="call"))
        elif l["new"]:
            q["today"].append(item("lead", l, "новый лид", action="call"))
        elif age >= idle_d:
            q["later"].append(item("lead", l, f"лид без движения {int(age)} дн.", action="call"))
    # пропущенные входящие без перезвона — наверх «Горит» (calls.py; резюме разговоров делает CoPilot в Битриксе).
    # Чей звонок — по своим сделкам и лидам (у HEAD — все).
    deals_by_id = {d["id"]: d for d in deals}
    # звонки и чаты, оставшиеся на лиде после перевода в сделку, — это уже сделка
    lead2deal = {d["lead_id"]: d["id"] for d in deals if d.get("lead_id")}

    def owner(e: str, i: int) -> tuple[str, int]:
        return ("deal", lead2deal[i]) if e == "lead" and i not in leads_by_id and i in lead2deal else (e, i)
    seen = set()
    for m in got(f_calls, "звонки не загрузились", []):
        m["entity"], m["id"] = owner(m["entity"], m["id"])
        src = (deals_by_id if m["entity"] == "deal" else leads_by_id).get(m["id"])
        if not src or (m["entity"], m["id"]) in seen:
            continue
        seen.add((m["entity"], m["id"]))
        for b in q.values():
            b[:] = [x for x in b if (x["entity"], x["id"]) != (m["entity"], m["id"])]
        q["hot"].insert(len(seen) - 1, item(m["entity"], src, f"пропущенный звонок {calls.hhmm(m['at'])} — перезвонить", action="call"))
    # клиент написал в WhatsApp и ждёт ответа дольше нормы — тоже наверх (chats.py; резюме чатов делает Битрикс)
    from datetime import datetime, timezone
    from . import chats
    chat_min = float(vals.get("mop.today.chat_minutes") or vals.get("mop.reply_min") or 30)
    own = None if need_bx(p) is None else \
        {("deal", i) for i in deals_by_id} | {("lead", i) for i in leads_by_id} | {("lead", i) for i in lead2deal}
    try:
        waits, cw = chats.waiting(fresh, own)
    except Exception as e:  # noqa: BLE001
        waits, cw = [], f"переписка не загрузилась: {type(e).__name__}"
    warns += [cw] if cw else []
    for w in sorted(waits, key=lambda x: x["since"]):
        w["entity"], w["id"] = owner(w["entity"], w["id"])
        src = (deals_by_id if w["entity"] == "deal" else leads_by_id).get(w["id"])
        if not src or (w["entity"], w["id"]) in seen or (datetime.now(timezone.utc) - w["since"]).total_seconds() < chat_min * 60:
            continue
        seen.add((w["entity"], w["id"]))
        for b in q.values():
            b[:] = [x for x in b if (x["entity"], x["id"]) != (w["entity"], w["id"])]
        q["hot"].insert(len(seen) - 1, item(w["entity"], src, f"клиент ждёт ответа в WhatsApp {chats.ago(w['since'])}", action="chat"))
    out["limits"]["chat_minutes"] = chat_min
    # «Жду ответа» / «Перезвонить» с датой: до этого дня сделка/лид не горит — уходит в «Позже» с пометкой
    for key, r in waiting.items():
        src = (deals_by_id if key[0] == "deal" else leads_by_id).get(key[1])
        if not src:
            continue
        for b in q.values():
            b[:] = [x for x in b if (x["entity"], x["id"]) != key]
        q["later"].insert(0, item(key[0], src, f"ждём до {r['due']:%d.%m}" + (f": {r['note']}" if r["note"] else ""), action="call", wait=r["due"].isoformat()))
    for k in ("new", "kp", "idle"):   # и бот про них до этой даты не пишет
        out[k] = [d for d in out[k] if ("deal", d["id"]) not in waiting]
    for t in got(f_tasks, "задачи не загрузились", []):
        try:
            deal = next((int(x[2:]) for x in (t.get("ufCrmTask") or t.get("UF_CRM_TASK") or []) if str(x).startswith("D_")), None)
            x = {"id": int(t.get("id") or t.get("ID")), "title": t.get("title") or t.get("TITLE") or "",
                 "deadline": t.get("deadline") or t.get("DEADLINE"), "deal": deal}
        except (TypeError, ValueError, AttributeError):
            continue
        out["tasks"].append(x)
        dl, now = (x["deadline"] or "")[:10], date.today().isoformat()
        tq = {"entity": "task", "id": x["id"], "title": x["title"], "why": "задача" + (f" до {dl[8:10]}.{dl[5:7]}" if dl else ""),
              "deal": deal, "sum": 0, "stage": "", "phone": "", "name": ""}
        q["hot" if dl and dl < now else "today" if dl == now else "later"].append(tq)
    out["warn"] = "; ".join(warns)
    out["queue"] = q
    return out


# ---------- «Мой месяц»: выручка и ступень МОП ----------

def _vals() -> dict:
    from . import constants as consts
    with db.pool.connection() as conn:
        row = conn.execute("SELECT values FROM constants_versions ORDER BY id DESC LIMIT 1").fetchone()
    return {k: consts.num(v["value"]) for k, v in (row["values"] if row else {}).items() if str(v.get("value", "")).strip()}


def month(p: dict, fresh: bool = False, ym: str | None = None) -> dict:
    """Выручка месяца и процент МОП по «Значениям» (pay.mop.*).
    Источник (HEAD 05.11): лист «Проекты <год>» финансовой таблицы — по дате завершения работ, с НДС; менеджер — из
    Битрикса по номеру сделки. Если лист недоступен — выигранные сделки Битрикса по CLOSEDATE (хуже: дата перевода в «успех»).
    Решение HEAD 03.11: ступень 3/4/5% определяется по ВСЕЙ выручке компании за месяц без НДС и считается от всей
    выручки, не от превышения; бонус за план — при 3-й ступени. Свои сделки МОП видит отдельно, HEAD — всех менеджеров."""
    from datetime import date
    from . import fin
    uid = need_bx(p)
    y, m = (int(x) for x in ym.split("-")) if ym else (date.today().year, date.today().month)
    names = {u["id"]: u["name"] for u in users()}
    source, warn = "sheet", ""
    try:
        rows = fin.month_rows(y, m, fresh)
        if not rows:
            raise LookupError("в листе за этот месяц пока нет строк")
        ids = [r["id"] for r in rows]
        who = {}
        for i in range(0, len(ids), 50):
            for d in read_all("crm.deal.list", {"filter": {"ID": ids[i:i + 50]}, "select": ["ID", "ASSIGNED_BY_ID"]}, fresh=fresh):
                who[int(d["ID"])] = int(d.get("ASSIGNED_BY_ID") or 0)
        deals = [{"id": r["id"], "title": r["title"], "sum": r["sum"], "closed": r["closed"], "city": r["city"],
                  "manager_id": who.get(r["id"], 0), "manager": names.get(who.get(r["id"], 0), "")} for r in rows]
    except Exception as e:  # noqa: BLE001 — лист недоступен: считаем по Битриксу и говорим об этом
        source, warn = "bitrix", "" if isinstance(e, LookupError) else f"Лист «Проекты {y}» не прочитан ({e}); цифры по дате закрытия сделок в Битриксе."
        start, end = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)
        flt = {"CATEGORY_ID": list(CATEGORIES), "STAGE_SEMANTIC_ID": "S", ">=CLOSEDATE": start.isoformat(), "<CLOSEDATE": end.isoformat()}
        rows = read_all("crm.deal.list", {"filter": flt, "select": ["ID", "TITLE", "OPPORTUNITY", "CLOSEDATE", "ASSIGNED_BY_ID", "CATEGORY_ID"],
                                          "order": {"CLOSEDATE": "DESC"}}, fresh=fresh)
        deals = [{"id": int(d["ID"]), "title": d.get("TITLE") or "", "sum": _num(d.get("OPPORTUNITY")), "closed": (d.get("CLOSEDATE") or "")[:10],
                  "city": "", "manager_id": int(d.get("ASSIGNED_BY_ID") or 0), "manager": names.get(int(d.get("ASSIGNED_BY_ID") or 0), "")} for d in rows]
    deals.sort(key=lambda d: d["closed"], reverse=True)
    v = _vals()
    vat = float(v.get("vat") or 0)
    steps = [(float(v.get(f"pay.mop.step{i}.from") or 0), float(v.get(f"pay.mop.step{i}.pct") or 0)) for i in (1, 2, 3)]
    salary, bonus_plan = float(v.get("pay.mop.salary") or 0), float(v.get("pay.mop.bonus_plan") or 0)
    net_of = lambda ds: sum(d["sum"] for d in ds) / (1 + vat / 100)  # noqa: E731

    net = net_of(deals)
    step = max([i for i, (frm, _) in enumerate(steps, 1) if frm and net > frm] or [0])
    pct = steps[step - 1][1] if step else 0.0
    nxt = next(((i, frm) for i, (frm, _) in enumerate(steps, 1) if frm and net <= frm), None)
    company = {"count": len(deals), "gross": round(sum(d["sum"] for d in deals)), "net": round(net), "step": step, "pct": pct,
               "bonus": round(net * pct / 100), "plan_bonus": bonus_plan if step == 3 else 0,
               "next": {"step": nxt[0], "from": nxt[1], "left": round(nxt[1] - net)} if nxt else None}
    company["earn"] = round(salary + company["bonus"] + company["plan_bonus"])
    # План месяца (HEAD 06.11): темп — выручка на сегодня, растянутая на весь месяц; ступень и заработок по темпу.
    today_ = date.today()
    if (y, m) == (today_.year, today_.month):
        import calendar
        days = calendar.monthrange(y, m)[1]
        f_net = net / today_.day * days if today_.day else net
        f_step = max([i for i, (frm, _) in enumerate(steps, 1) if frm and f_net > frm] or [0])
        f_pct = steps[f_step - 1][1] if f_step else 0.0
        company["pace"] = {"day": today_.day, "days": days, "net": round(f_net), "step": f_step, "pct": f_pct,
                           "earn": round(salary + f_net * f_pct / 100 + (bonus_plan if f_step == 3 else 0))}
    out = {"month": f"{y}-{m:02d}", "vat": vat, "salary": salary, "bonus_plan": bonus_plan, "steps": [{"from": f, "pct": c} for f, c in steps],
           "all": uid is None, "company": company, "source": source, "warn": warn if uid is None else ""}
    if uid is None:
        by: dict = {}
        for d in deals:
            by.setdefault(d["manager_id"], []).append(d)
        out["managers"] = sorted([{"id": k, "name": names.get(k, "без менеджера" if not k else str(k)), "deals": ds, "count": len(ds),
                                   "gross": round(sum(d["sum"] for d in ds)), "net": round(net_of(ds))} for k, ds in by.items()],
                                 key=lambda x: -x["net"])
    else:
        mine = [d for d in deals if d["manager_id"] == uid]
        out["mine"] = {"deals": mine, "count": len(mine), "gross": round(sum(d["sum"] for d in mine)), "net": round(net_of(mine)),
                       "share": round(net_of(mine) / net * 100) if net else 0}
    return out


@router.get("/bx/month")
def api_month(fresh: int = 0, ym: str | None = None, p: dict = Depends(active)):
    return month(p, bool(fresh), ym)


@router.get("/bx/today")
def api_today(fresh: int = 0, p: dict = Depends(active)):
    return today(p, bool(fresh))


@router.get("/bx/deals/{deal_id}/full")
def api_deal_full(deal_id: int, fresh: int = 0, p: dict = Depends(active)):
    return deal_full(p, deal_id, bool(fresh))


# ---------- совместимость со страницей КП (раньше ходила в Битрикс через коннектор Claude: crm_get / crm_fields) ----------

def _camel(code: str) -> str:
    if code.startswith("UF_CRM_"):
        rest = code[7:]
        # crm.item: UF_CRM_6881101914D8D → ufCrm_6881101914D8D, UF_CRM_ARTGAME_OBJECT → ufCrmArtgameObject
        if rest[:1].isdigit():
            return "ufCrm_" + rest
        return "ufCrm" + "".join(w.capitalize() for w in rest.split("_"))
    parts = code.lower().split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


def crm_tool(p: dict, tool: str, args: dict, allowed: set) -> dict:
    if tool == "crm_fields":
        f = deal_fields()
        return {_camel(k): {"title": v.get("formLabel") or v.get("title") or k,
                            **({"items": [{"id": i["ID"], "value": i["VALUE"]} for i in v["items"]]} if v.get("items") else {})}
                for k, v in f.items()}
    if tool != "crm_get":
        raise HTTPException(400, "unknown tool")
    ent, eid = args.get("entity"), int(args.get("id") or 0)
    if ent == "deal":
        d = _deal(p, eid)
        with db.pool.connection() as conn:
            db.audit(conn, p["id"], "deal_open", "deal", eid, {"title": d.get("TITLE") or "", "stage": d["STAGE_ID"], "via": "kp"})
        allowed.update({("company", int(d.get("COMPANY_ID") or 0)), ("contact", int(d.get("CONTACT_ID") or 0))})
        out = {_camel(k): v for k, v in d.items()}
        out["id"] = int(d["ID"])
        out["ufCrm_ARTGAME_AREA_M2"] = d.get(AREA)
        out["companyId"], out["contactId"] = int(d.get("COMPANY_ID") or 0), int(d.get("CONTACT_ID") or 0)
        return out
    if ent in ("company", "contact"):
        if p["role_code"] not in SEE_ALL and (ent, eid) not in allowed:
            raise HTTPException(403, "Сначала откройте сделку")
        e = _entity(f"crm.{ent}.get", eid)
        return {_camel(k): v for k, v in e.items()}
    raise HTTPException(400, "unknown entity")


# ---------- API ----------

@router.get("/bx/deals")
def api_deals(fresh: int = 0, manager: int | None = None, p: dict = Depends(active)):
    return my_deals(p, bool(fresh), manager)


@router.get("/bx/deals/{deal_id}")
def api_deal(deal_id: int, fresh: int = 0, p: dict = Depends(active)):
    return deal_card(p, deal_id, bool(fresh))


# ---------- журнал действий ----------

JOURNAL_ACTIONS = ("deal_open", "place_download", "shift_add", "expense_add", "shift_cancel", "expense_cancel",
                   "bx_write", "place_doc_set", "file_add", "view_as_start", "view_as_stop")


@router.get("/journal")
def api_journal(person: int | None = None, days: int = 30, p: dict = Depends(active)):
    """Свои действия по дням (HEAD — любого человека и сводку). Ничего не удаляется: это тот же audit_log."""
    pid = p["id"]
    if person and person != pid:
        if p["role_code"] != "head":
            raise HTTPException(403, "только свой журнал")
        pid = person
    with db.pool.connection() as conn:
        rows = conn.execute(
            """SELECT a.id, a.at, a.action, a.entity, a.entity_id, a.data, p.full_name
               FROM audit_log a LEFT JOIN people p ON p.id=a.person_id
               WHERE a.person_id=%s AND a.at > now() - make_interval(days => %s) AND a.action = ANY(%s)
               ORDER BY a.at DESC LIMIT 500""", (pid, min(max(days, 1), 365), list(JOURNAL_ACTIONS))).fetchall()
        summary = None
        if p["role_code"] == "head":
            summary = conn.execute(
                """SELECT p.id, p.full_name, p.role_code, count(*) FILTER (WHERE a.at > now() - interval '1 day') AS today,
                          count(*) FILTER (WHERE a.action='deal_open' AND a.at > now() - interval '1 day') AS deals_today,
                          count(*) FILTER (WHERE a.action='place_download' AND a.at > now() - interval '1 day') AS files_today,
                          max(a.at) AS last_at
                   FROM people p JOIN audit_log a ON a.person_id=p.id
                   WHERE p.role_code IN ('mop','mop_vip') GROUP BY p.id ORDER BY p.full_name""").fetchall()
    return {"items": rows, "summary": summary}


@router.get("/bx/users")
def api_users(p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "head only")
    return users()


# Внутри страницы места (МОП, Калькулятор) — по подписанной ссылке места, как _db.
_allowed: dict[int, set] = {}


@router.post("/p/{code}/{tok}/_bx/{tool}")
async def place_bx(code: str, tok: str, tool: str, request: Request):
    from .places import BX_PLACES, person_by_token
    if code not in BX_PLACES:
        raise HTTPException(404)
    p = person_by_token(code, tok)
    try:
        args = await request.json()
    except ValueError:
        args = {}
    args = args if isinstance(args, dict) else {}
    if tool == "my_deals":
        return my_deals(p, bool(args.get("fresh")))
    if tool == "doc_saved":
        from .bxw import doc_saved
        from .places import read_only
        read_only(p)
        return doc_saved(p, int(args.get("deal") or 0), str(args.get("name") or ""), str(args.get("fid") or ""), args.get("fields") or {})
    if tool == "deal_card":
        return deal_card(p, int(args.get("id") or 0), bool(args.get("fresh")))
    return crm_tool(p, tool, args, _allowed.setdefault(p["id"], set()))
