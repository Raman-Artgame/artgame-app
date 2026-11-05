"""Сделки Битрикса для МОП — только чтение, через шлюз ARTGAME (bitrix_read). Своего ключа у приложения нет.

Кто что видит: МОП и VIP МОП — сделки, где он ответственный (people.bitrix_user_id = ASSIGNED_BY_ID); HEAD — все.
Связку человек ↔ пользователь Битрикса ставит HEAD во вкладке «Команда».
Ответы кешируются на 2 минуты (кнопка «Обновить» — без кеша), справочники (стадии, города) — на час.
Запись в Битрикс отсюда невозможна: шлюз отдаёт только методы чтения.
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
LIST_SELECT = ["ID", "TITLE", "STAGE_ID", "CATEGORY_ID", "OPPORTUNITY", "ASSIGNED_BY_ID", "CONTACT_ID", "COMPANY_ID",
               "DATE_MODIFY", CITY, AREA]
TTL, TTL_DICT, MAX_PAGES = 120, 3600, 10

_cache: dict = {}
_lock = threading.Lock()
_gw = None


# ---------- чтение через шлюз ----------

def _gateway_read(method: str, params: dict):
    global _gw
    if not settings.gateway_url:
        raise HTTPException(503, "Битрикс не подключён (нет адреса шлюза)")
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
    return j if isinstance(j, list) else (j or {}).get("result", [])


def read_all(method: str, params: dict, fresh: bool = False) -> list:
    out, start = [], 0
    for _ in range(MAX_PAGES):
        j = read(method, {**params, "start": start}, fresh=fresh)
        out += _rows(j)
        start = None if isinstance(j, list) else j.get("next")
        if start is None:
            break
    return out


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
              "manager": names.get(int(d.get("ASSIGNED_BY_ID") or 0), "") if uid is None else ""} for d in rows]
    return {"deals": deals, "all": uid is None, "updated": time.time()}


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


def deal_card(p: dict, deal_id: int, fresh: bool = False) -> dict:
    d = _deal(p, deal_id, fresh)
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
    st = stages().get(d["STAGE_ID"]) or {}
    addr = d.get(ADDR)
    return {"id": int(d["ID"]), "title": d.get("TITLE") or "", "stage": d["STAGE_ID"], "stage_name": st.get("name", d["STAGE_ID"]),
            "sum": _num(d.get("OPPORTUNITY")), "area": _num(d.get(AREA)), "city": city_name(d.get(CITY)),
            "address": addr.split("|")[0] if isinstance(addr, str) else "",
            "service": enum_map(SERVICE).get(str(d.get(SERVICE) or ""), ""),
            "object": d.get("UF_CRM_ARTGAME_OBJECT") or "", "client": client, "contact": contact,
            "requisites": requisites(d.get("COMPANY_ID")) if comp else None}


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
                   "bx_write", "place_doc_set", "file_add")


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
        return doc_saved(p, int(args.get("deal") or 0), str(args.get("name") or ""), str(args.get("fid") or ""), args.get("fields") or {})
    if tool == "deal_card":
        return deal_card(p, int(args.get("id") or 0), bool(args.get("fresh")))
    return crm_tool(p, tool, args, _allowed.setdefault(p["id"], set()))
