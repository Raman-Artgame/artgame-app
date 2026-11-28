"""МОП вводит всё в приложении, в Битриксе у него остаётся только переписка с клиентом (HEAD 25.11 «давай делаем»,
карта «Где что делается», шаг 1).

- Заявка по звонку: лид заводится прямо в приложении (crm.lead.add), с проверкой дубля по телефону.
- Клиент и реквизиты: контакт (физлицо) или компания (ТОО / ИП) с реквизитами и банком — правка из карточки сделки.
- Подписанный договор: файл из карточки → поле «Договор подписанный» сделки и папка «ДОКУМЕНТЫ» на Диске.

Пишет тем же вебхуком, что и остальные записи (bxw.CALL), только в свои сделки и лиды (HEAD — в любые). Ничего не
удаляет: прежняя компания или реквизиты остаются в Битриксе. Каждая запись — в audit_log (bx_write) и сверяется чтением.
"""
import base64
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import bx, bxw, db
from .work import active

router = APIRouter(prefix="/api")

# пресеты реквизитов Казахстана в нашем Битриксе (crm.requisite.preset.list)
PRESET = {"ИП": 1, "ТОО": 3, "Физлицо": 5}
TYPES = tuple(PRESET)
SOURCES_OFF = ("|",)   # WhatsApp, Instagram — их лиды создаёт сам канал, руками не выбираются
MAX_SIGNED = 12 * 1024 * 1024


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def norm_phone(s: str | None) -> str:
    """+7 777 123 45 67 / 8 777… / 777… → +77771234567. Пусто — если цифр меньше 10."""
    d = _digits(s)
    if len(d) == 11 and d[0] in "78":
        d = "7" + d[1:]
    elif len(d) == 10:
        d = "7" + d
    return "+" + d if len(d) >= 11 else ""


def _rows(method: str, params: dict) -> list:
    """Чтение через вебхук записи: шлюз чтения не отдаёт реквизиты (crm.requisite.* нет в его списке)."""
    return bx._rows(bxw.CALL(method, params))


def _audit(p: dict, entity: str, eid: int, log: dict):
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "bx_write", entity, eid, log)


def _need_write():
    if not bxw.enabled():
        raise HTTPException(409, "запись в Битрикс выключена")


# ---------- заявка по звонку ----------

def sources() -> list:
    rows = bx._rows(bx.read("crm.status.list", {"filter": {"ENTITY_ID": "SOURCE"}}, ttl=bx.TTL_DICT))
    return [{"id": s["STATUS_ID"], "name": s["NAME"]} for s in sorted(rows, key=lambda s: int(s.get("SORT") or 0))
            if not any(x in s["STATUS_ID"] for x in SOURCES_OFF)]


def dups(phone: str) -> list:
    """Открытые лиды и контакты с этим телефоном — чтобы МОП не завёл второго клиента на тот же номер."""
    out, names = [], {u["id"]: u["name"] for u in bx.users()}
    tail = phone[-10:]
    for value in {phone, "8" + tail, tail}:
        for l in bx._rows(bx.read("crm.lead.list", {"filter": {"PHONE": value, "STATUS_SEMANTIC_ID": "P"},
                                                    "select": ["ID", "TITLE", "NAME", "LAST_NAME", "ASSIGNED_BY_ID"]}, fresh=True)):
            out.append({"kind": "lead", "id": int(l["ID"]), "name": " ".join(x for x in (l.get("NAME"), l.get("LAST_NAME")) if x) or l.get("TITLE") or "",
                        "manager": names.get(int(l.get("ASSIGNED_BY_ID") or 0), "")})
        for c in bx._rows(bx.read("crm.contact.list", {"filter": {"PHONE": value}, "select": ["ID", "NAME", "LAST_NAME", "ASSIGNED_BY_ID"]}, fresh=True)):
            out.append({"kind": "contact", "id": int(c["ID"]), "name": " ".join(x for x in (c.get("NAME"), c.get("LAST_NAME")) if x),
                        "manager": names.get(int(c.get("ASSIGNED_BY_ID") or 0), "")})
    seen, uniq = set(), []
    for x in out:
        if (x["kind"], x["id"]) not in seen:
            seen.add((x["kind"], x["id"]))
            uniq.append(x)
    return uniq


class NewLeadIn(BaseModel):
    name: str
    phone: str
    city: str | None = None       # ID пункта списка городов лида
    service: str | None = None    # ID пункта «Услуга» лида
    source: str = "CALL"
    note: str = ""
    force: bool = False           # дубль по телефону уже показан — МОП всё равно заводит


@router.get("/bx/leads-new/dict")
def api_new_dict(p: dict = Depends(active)):
    from . import leads
    bx.need_bx(p)
    have = leads.fields()
    return {"sources": sources(), "cities": leads.cities(),
            "services": [{"id": k, "name": v} for k, v in leads._items(leads.L_SERVICE, have).items()] if leads.L_SERVICE in have else []}


@router.post("/bx/leads-new")
def api_new_lead(body: NewLeadIn, p: dict = Depends(active)):
    from . import leads
    scope = bx.need_bx(p)
    uid = scope or bx.bx_id(p)
    if not uid:
        raise HTTPException(409, "HEAD ещё не связал вас с пользователем Битрикса (вкладка «Команда»)")
    name, phone = body.name.strip()[:100], norm_phone(body.phone)
    if not name:
        raise HTTPException(400, "имя клиента")
    if not phone:
        raise HTTPException(400, "телефон: нужно 10–11 цифр")
    if body.source not in {s["id"] for s in sources()}:
        raise HTTPException(400, "откуда клиент — выберите из списка")
    have = leads.fields()
    if body.city and body.city not in leads._items(leads.L_CITY, have):
        raise HTTPException(400, "нет такого города")
    if body.service and leads.L_SERVICE in have and body.service not in leads._items(leads.L_SERVICE, have):
        raise HTTPException(400, "нет такой услуги")
    _need_write()
    if not body.force:
        found = dups(phone)
        if found:
            raise HTTPException(409, {"dups": found, "message": "Этот номер уже есть в Битриксе"})
    f = {"TITLE": f"{name} — {'звонок' if body.source == 'CALL' else 'заявка'}", "NAME": name, "STATUS_ID": "NEW",
         "SOURCE_ID": body.source, "ASSIGNED_BY_ID": uid, "OPENED": "Y",
         "PHONE": [{"VALUE": phone, "VALUE_TYPE": "WORK"}]}
    if body.city:
        f[leads.L_CITY] = body.city
    if body.service and leads.L_SERVICE in have:
        f[leads.L_SERVICE] = body.service
    if body.note.strip():
        f["COMMENTS"] = body.note.strip()[:2000]
    log = {"what": "новый лид из приложения", "fields": {k: v for k, v in f.items() if k != "PHONE"}, "phone": phone}
    try:
        lead_id = int(bxw.CALL("crm.lead.add", {"fields": f, "params": {"REGISTER_SONET_EVENT": "Y"}}).get("result") or 0)
        if not lead_id:
            raise RuntimeError("Битрикс не вернул номер лида")
        bxw.CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": lead_id, "ENTITY_TYPE": "lead",
                                                         "COMMENT": f"{p['full_name']} (приложение): завёл заявку"}})
        log.update(bx="ok", lead=lead_id)
        bx._cache.clear()
    except Exception as ex:  # noqa: BLE001
        log.update(bx="error", error=str(ex)[:300])
    _audit(p, "lead", log.get("lead") or 0, log)
    if log["bx"] == "error":
        raise HTTPException(502, log["error"])
    return {"bx": "ok", "lead": log["lead"]}


# ---------- клиент и реквизиты сделки ----------

def _fm(e: dict, key: str) -> tuple[str, str | None]:
    v = e.get(key) or []
    return (v[0].get("VALUE", ""), v[0].get("ID")) if isinstance(v, list) and v else ("", None)


def _req(entity_type: int, eid: int) -> dict:
    """Последние реквизиты компании (4) или контакта (3) и их первый банк."""
    rows = _rows("crm.requisite.list", {"filter": {"ENTITY_TYPE_ID": entity_type, "ENTITY_ID": eid}, "order": {"ID": "DESC"}})
    if not rows:
        return {}
    r = rows[0]
    banks = _rows("crm.requisite.bankdetail.list", {"filter": {"ENTITY_ID": int(r["ID"])}, "order": {"ID": "DESC"}})
    b = banks[0] if banks else {}
    return {"id": int(r["ID"]), "preset": int(r.get("PRESET_ID") or 0), "cname": r.get("RQ_COMPANY_NAME") or r.get("RQ_NAME") or "",
            "bin": r.get("RQ_BIN") or r.get("RQ_IIN") or "", "signer": r.get("RQ_CEO_NAME") or r.get("RQ_DIRECTOR") or "",
            "signer_pos": r.get("RQ_CEO_WORK_POS") or "", "bank_id": int(b["ID"]) if b.get("ID") else None,
            "bank": b.get("RQ_BANK_NAME") or "", "bik": b.get("RQ_BIK") or "", "iik": b.get("RQ_IIK") or b.get("RQ_ACC_NUM") or ""}


def client_of(p: dict, deal_id: int) -> dict:
    d = bx._deal(p, deal_id, fresh=True)
    cid, coid = int(d.get("CONTACT_ID") or 0), int(d.get("COMPANY_ID") or 0)
    cont = bxw.CALL("crm.contact.get", {"id": cid}).get("result") or {} if cid else {}
    comp = bxw.CALL("crm.company.get", {"id": coid}).get("result") or {} if coid else {}
    name = " ".join(x for x in (cont.get("LAST_NAME"), cont.get("NAME"), cont.get("SECOND_NAME")) if x)
    phone, _ = _fm(comp, "PHONE") if comp and _fm(comp, "PHONE")[0] else _fm(cont, "PHONE")
    email, _ = _fm(comp, "EMAIL") if comp and _fm(comp, "EMAIL")[0] else _fm(cont, "EMAIL")
    title = comp.get("TITLE") or ""
    req = _req(4, coid) if coid else _req(3, cid) if cid else {}
    kind = ("ИП" if title.upper().startswith("ИП") else "ТОО") if comp else "Физлицо"
    return {"deal": deal_id, "type": kind, "contact_id": cid or None, "company_id": coid or None,
            "name": name, "company": title, "phone": phone, "email": email,
            "bin": req.get("bin", ""), "signer": req.get("signer", ""), "signer_pos": req.get("signer_pos", ""),
            "bank": req.get("bank", ""), "bik": req.get("bik", ""), "iik": req.get("iik", "")}


class ClientIn(BaseModel):
    type: str                     # Физлицо | ТОО | ИП
    name: str = ""                # контактное лицо (у физлица — клиент)
    phone: str = ""
    email: str = ""
    company: str = ""             # «ТОО «Ромашка»» / «ИП Иванов»
    bin: str = ""                 # БИН ТОО, ИИН ИП или физлица
    signer: str = ""              # кто подписывает (ТОО)
    signer_pos: str = ""
    bank: str = ""
    bik: str = ""
    iik: str = ""


def check(b: ClientIn) -> list[str]:
    bad = []
    if b.type not in TYPES:
        bad.append("тип клиента")
    if b.type == "Физлицо" and not b.name.strip():
        bad.append("имя клиента")
    if b.type != "Физлицо" and not b.company.strip():
        bad.append("название компании")
    if b.phone.strip() and not norm_phone(b.phone):
        bad.append("телефон: нужно 10–11 цифр")
    if b.email.strip() and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", b.email.strip()):
        bad.append("почта")
    if b.bin.strip() and len(_digits(b.bin)) != 12:
        bad.append(("БИН" if b.type == "ТОО" else "ИИН") + ": 12 цифр")
    if b.bik.strip() and not re.fullmatch(r"[A-Z0-9]{8}", b.bik.strip().upper()):
        bad.append("БИК банка: 8 знаков")
    if b.iik.strip() and not re.fullmatch(r"KZ[0-9A-Z]{18}", re.sub(r"\s", "", b.iik.upper())):
        bad.append("ИИК: KZ и 18 знаков")
    return bad


def _multi(old_id, value: str, vtype: str = "WORK") -> list:
    return [{"ID": old_id, "VALUE": value, "VALUE_TYPE": vtype}] if old_id else [{"VALUE": value, "VALUE_TYPE": vtype}]


def _save_req(entity_type: int, eid: int, kind: str, b: ClientIn, name: str) -> list[str]:
    """Реквизиты и банк: правим последние, если пресет тот же; иначе заводим новые (старые не трогаем)."""
    done = []
    want = {"ИП": {"RQ_NAME": name, "RQ_IIN": _digits(b.bin)},
            "ТОО": {"RQ_COMPANY_NAME": name, "RQ_BIN": _digits(b.bin), "RQ_CEO_NAME": b.signer.strip(),
                    "RQ_CEO_WORK_POS": b.signer_pos.strip() or ("Директор" if b.signer.strip() else "")},
            "Физлицо": {"RQ_NAME": name, "RQ_IIN": _digits(b.bin)}}[kind]
    want = {k: v for k, v in want.items() if v}
    bank = {"RQ_BANK_NAME": b.bank.strip(), "RQ_BIK": b.bik.strip().upper(), "RQ_IIK": re.sub(r"\s", "", b.iik.upper())}
    bank = {k: v for k, v in bank.items() if v}
    if bank.get("RQ_IIK"):
        bank["RQ_ACC_NUM"] = bank["RQ_IIK"]   # старые реквизиты читались из RQ_ACC_NUM
    if not want and not bank:
        return done
    cur = _req(entity_type, eid)
    rid = cur.get("id") if cur.get("preset") == PRESET[kind] else None
    if rid:
        bxw.CALL("crm.requisite.update", {"id": rid, "fields": want})
        done.append("реквизиты")
    else:
        rid = int(bxw.CALL("crm.requisite.add", {"fields": {"ENTITY_TYPE_ID": entity_type, "ENTITY_ID": eid, "PRESET_ID": PRESET[kind],
                                                            "NAME": f"Реквизиты {kind}", "ACTIVE": "Y", **want}}).get("result") or 0)
        done.append("новые реквизиты")
    if bank and rid:
        if cur.get("bank_id") and cur.get("id") == rid:
            bxw.CALL("crm.requisite.bankdetail.update", {"id": cur["bank_id"], "fields": bank})
        else:
            bxw.CALL("crm.requisite.bankdetail.add", {"fields": {"ENTITY_ID": rid, "COUNTRY_ID": 6, "NAME": bank.get("RQ_BANK_NAME") or "Счёт", **bank}})
        done.append("банк")
    return done


@router.get("/bx/deals/{deal_id}/client")
def api_client(deal_id: int, p: dict = Depends(active)):
    _need_write()
    return client_of(p, deal_id)


@router.post("/bx/deals/{deal_id}/client")
def api_client_save(deal_id: int, body: ClientIn, p: dict = Depends(active)):
    bad = check(body)
    if bad:
        raise HTTPException(400, "проверьте: " + ", ".join(bad))
    _need_write()
    d = bx._deal(p, deal_id, fresh=True)   # своя сделка (HEAD — любая)
    cid, coid = int(d.get("CONTACT_ID") or 0), int(d.get("COMPANY_ID") or 0)
    uid = int(d.get("ASSIGNED_BY_ID") or 0) or bx.bx_id(p)
    phone, email = norm_phone(body.phone), body.email.strip()
    log, done = {"what": "клиент и реквизиты", "type": body.type}, []
    try:
        cont = bxw.CALL("crm.contact.get", {"id": cid}).get("result") or {} if cid else {}
        cf = {}
        if body.name.strip():
            cf.update(NAME=body.name.strip()[:100], LAST_NAME="", SECOND_NAME="")
            if " ".join(x for x in (cont.get("LAST_NAME"), cont.get("NAME"), cont.get("SECOND_NAME")) if x) == body.name.strip():
                cf = {}   # имя то же — не трогаем, как разложено в Битриксе
        if body.type == "Физлицо" or not coid:
            if phone and phone != norm_phone(_fm(cont, "PHONE")[0]):
                cf["PHONE"] = _multi(_fm(cont, "PHONE")[1], phone)
            if email and email != _fm(cont, "EMAIL")[0]:
                cf["EMAIL"] = _multi(_fm(cont, "EMAIL")[1], email)
        if cid and cf:
            bxw.CALL("crm.contact.update", {"id": cid, "fields": cf})
            done.append("контакт")
        elif not cid and (body.name.strip() or phone):
            cid = int(bxw.CALL("crm.contact.add", {"fields": {"NAME": body.name.strip() or "Клиент", "ASSIGNED_BY_ID": uid,
                                                              **({"PHONE": [{"VALUE": phone, "VALUE_TYPE": "WORK"}]} if phone else {}),
                                                              **({"EMAIL": [{"VALUE": email, "VALUE_TYPE": "WORK"}]} if email else {})}}).get("result") or 0)
            bxw.CALL("crm.deal.update", {"id": deal_id, "fields": {"CONTACT_ID": cid}})
            done.append("новый контакт")
        if body.type == "Физлицо":
            if coid:   # был ТОО/ИП, клиент — физлицо: компанию от сделки отвязываем (в Битриксе она остаётся)
                bxw.CALL("crm.deal.update", {"id": deal_id, "fields": {"COMPANY_ID": 0}})
                done.append("компания отвязана")
            if cid:
                done += _save_req(3, cid, "Физлицо", body, body.name.strip())
        else:
            title = body.company.strip()[:200]
            if body.type == "ИП" and not title.upper().startswith("ИП"):
                title = "ИП " + title
            if body.type == "ТОО" and title.upper().startswith("ИП "):
                raise ValueError("ТОО не может называться «ИП …» — выберите тип «ИП»")
            comp = bxw.CALL("crm.company.get", {"id": coid}).get("result") or {} if coid else {}
            kf = {}
            if title != (comp.get("TITLE") or ""):
                kf["TITLE"] = title
            if phone and phone != norm_phone(_fm(comp, "PHONE")[0]):
                kf["PHONE"] = _multi(_fm(comp, "PHONE")[1], phone)
            if email and email != _fm(comp, "EMAIL")[0]:
                kf["EMAIL"] = _multi(_fm(comp, "EMAIL")[1], email)
            if coid and kf:
                bxw.CALL("crm.company.update", {"id": coid, "fields": kf})
                done.append("компания")
            elif not coid:
                coid = int(bxw.CALL("crm.company.add", {"fields": {"TITLE": title, "ASSIGNED_BY_ID": uid, "COMPANY_TYPE": "CUSTOMER",
                                                                   **({"PHONE": kf["PHONE"]} if "PHONE" in kf else {}),
                                                                   **({"EMAIL": kf["EMAIL"]} if "EMAIL" in kf else {})}}).get("result") or 0)
                if not coid:
                    raise RuntimeError("Битрикс не вернул номер компании")
                bxw.CALL("crm.deal.update", {"id": deal_id, "fields": {"COMPANY_ID": coid}})
                if cid:
                    try:
                        bxw.CALL("crm.company.contact.add", {"id": coid, "fields": {"CONTACT_ID": cid}})
                    except Exception:  # noqa: BLE001 — связь контакта с компанией не обязательна
                        pass
                done.append("новая компания")
            done += _save_req(4, coid, body.type, body, title)
        if done:
            bxw.CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal",
                                                             "COMMENT": f"{p['full_name']} (приложение): клиент и реквизиты — {', '.join(done)}"}})
        bx._cache.clear()
        after = client_of(p, deal_id)
        want = {"phone": phone, "bin": _digits(body.bin), "bik": body.bik.strip().upper(), "iik": re.sub(r"\s", "", body.iik.upper())}
        bad = [k for k, v in want.items() if v and (norm_phone(after[k]) if k == "phone" else after[k]) != v]
        log.update(bx="ok" if not bad else "error", done=done)
        if bad:
            log["error"] = "не записалось: " + ", ".join(bad)
    except Exception as ex:  # noqa: BLE001
        log.update(bx="error", error=str(ex)[:300], done=done)
        after = None
    _audit(p, "deal", deal_id, log)
    if log["bx"] == "error":
        raise HTTPException(502, log["error"] + (f" (уже записано: {', '.join(done)})" if done else ""))
    return {"bx": "ok", "done": done, "client": after}


# ---------- подписанный договор ----------

class SignedIn(BaseModel):
    name: str
    data: str        # data:<mime>;base64,…


@router.post("/bx/deals/{deal_id}/signed")
def api_signed(deal_id: int, body: SignedIn, p: dict = Depends(active)):
    head, _, b64 = body.data.partition(",")
    mime = head.removeprefix("data:").removesuffix(";base64")
    if mime not in ("application/pdf", "image/jpeg", "image/png"):
        raise HTTPException(400, "нужен PDF или фото договора")
    try:
        raw = base64.b64decode(b64, validate=True)
    except ValueError:
        raise HTTPException(400, "файл не прочитался")
    if not raw or len(raw) > MAX_SIGNED:
        raise HTTPException(400, "файл больше 12 МБ — сожмите PDF или снимите фото")
    ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[mime]
    stem = re.sub(r"[\\/:*?\"<>|]+", " ", Path(body.name).stem).strip()[:80] or "договор"
    name = f"Договор подписанный {deal_id} {stem}{ext}"
    bx._deal(p, deal_id, fresh=True)
    # сначала Диск (без открытого соединения с базой надолго), потом поле сделки
    drive_id, drive_err = None, None
    with db.pool.connection() as conn:
        obj = conn.execute("SELECT * FROM objects WHERE id=%s AND id<>0", (deal_id,)).fetchone()
    if obj:
        try:
            from . import drive
            d = drive.Drive()
            with db.pool.connection() as conn:
                folder = drive.ensure_folders(conn, obj, d)["doc"]
            drive_id = d.upload(folder, name, raw, mime)
        except Exception as ex:  # noqa: BLE001 — Диск не ответил: файл всё равно уходит в сделку
            drive_err = f"{type(ex).__name__}: {str(ex)[:120]}"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ("f" + ext)
        path.write_bytes(raw)
        r = bxw.write(p, deal_id, f"подписанный договор: {name}", {}, f"загрузил подписанный договор «{name}»",
                      (path, name, bxw.F_CONTRACT), stage_for="signed")
    if r["bx"] == "error":
        raise HTTPException(502, r["error"])
    r.update(drive=drive_id, drive_error=drive_err, name=name)
    return r
