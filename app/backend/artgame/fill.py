"""Обязательные поля карточки сделки (HEAD 06.11: «не чеклист, а чтобы всё заполнялось, пожёстче»).

Поля разложены по шагам карточки (Клиент → Расчёт → КП → Договор → Оплата → В работе). ЗАМОК: сделку нельзя перевести
вперёд по воронке (ни кнопкой «Стадия», ни скачанным документом), пока не заполнены поля, нужные для этой стадии —
REQUIRED. HEAD может перевести и без них (он видит, чего не хватает). Назад, в «Отложено» и в отказ — без замка.
ИИ-помощник: МОП вставляет переписку или анкету клиента → сервер достаёт город, услугу, площадь, адрес, аванс, срок,
реквизиты. С ключом ARTGAME_ANTHROPIC_KEY разбирает Claude, без ключа — простые правила (регулярные выражения).
МОП проверяет и сам нажимает «Записать» — без него ничего в Битрикс не уходит.
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import bx, db
from .config import settings
from .work import active

router = APIRouter(prefix="/api")

F_ADV, F_DAYS, F_WARR = "UF_CRM_ARTGAME_ADVANCE_PERCENT", "UF_CRM_1753295493279", "UF_CRM_ARTGAME_WARRANTY_MONTHS"
F_START, F_END = "UF_CRM_ARTGAME_PROJECT_START_ACTUAL", "UF_CRM_ARTGAME_PROJECT_END_PLAN"
STEPS = ["client", "calc", "kp", "docs", "pay", "work"]
# до какого шага карточка должна быть заполнена на этой стадии
STAGE_STEP = {"NEW": 0, "PREPARATION": 2, "UC_VZFPUP": 2, "UC_YV66BV": 2, "UC_1EXUAC": 2, "UC_VCP4VO": 0,
              "FINAL_INVOICE": 3, "UC_AV00QK": 5, "UC_BMKDS4": 5, "WON": 5}
# поле → (подпись, шаг, ключ для POST /fields или None, где заполнить)
SPEC = [
    ("name", "Клиент: имя или компания", "client", None, "в карточке клиента в Битриксе"),
    ("phone", "Телефон клиента", "client", None, "в карточке клиента в Битриксе"),
    ("city", "Город", "client", "city", ""),
    ("service", "Услуга", "client", "service", ""),
    ("address", "Адрес объекта", "client", "address", ""),
    ("area", "Площадь, м²", "client", "area", ""),
    ("sum", "Сумма сделки", "calc", None, "шаг «Расчёт» → «Записать в сделку»"),
    ("calc", "Расчёт цены и срока", "calc", None, "шаг «Расчёт» → «Записать в сделку»"),
    ("kp", "КП в сделке", "kp", None, "шаг «КП» → скачать PDF"),
    ("requisites", "Реквизиты клиента (БИН/ИИН)", "docs", None, "в Битриксе или «Договор → Заполнить из текста»"),
    ("adv", "Аванс, %", "docs", "adv", ""),
    ("days", "Срок по договору, дней", "docs", "days", ""),
    ("warranty", "Гарантия, мес.", "docs", "warranty", ""),
    ("paid", "Аванс поступил", "pay", None, "отмечает HEAD в финансах"),
    ("signed", "Подписанный договор", "pay", None, "файл в поле «Договор подписанный» в Битриксе"),
    ("start", "Старт работ (факт)", "work", "start", ""),
    ("end", "Сдача (план)", "work", "end", ""),
]


def _has(v) -> bool:
    return v not in (None, "", 0, "0", [], False) and str(v).strip() not in ("", "0")


def state(d: dict, card: dict, calc: dict | None) -> dict:
    """Что заполнено. d — сырая сделка Битрикса, card — карточка приложения (deal_full), calc — сохранённый расчёт."""
    c = card.get("client") or {}
    req = card.get("requisites")
    files = [f.get("title", "") for f in card.get("files") or []]
    val = {
        "name": c.get("name"), "phone": c.get("phone"), "city": card.get("city"), "service": card.get("service"),
        "address": card.get("address"), "area": card.get("area"), "sum": card.get("sum"),
        "calc": bool(calc) or _has((card.get("norm") or {}).get("shifts")),
        "kp": any(t.startswith("КП") for t in files),
        "requisites": True if c.get("type") == "Физлицо" else bool(req and req.get("cbin")),
        "adv": d.get(F_ADV), "days": d.get(F_DAYS), "warranty": d.get(F_WARR),
        "paid": ((card.get("pay") or {}).get("received") or 0) > 0,
        "signed": any(t.startswith("Договор подписанный") for t in files),
        "start": str(d.get(F_START) or "")[:10], "end": str(d.get(F_END) or "")[:10],
    }
    upto = STAGE_STEP.get(card.get("stage") or "", 0)
    items = []
    for key, label, step, edit, where in SPEC:
        v = val.get(key)
        items.append({"key": key, "label": label, "step": step, "ok": _has(v), "need": STEPS.index(step) <= upto,
                      "edit": edit, "where": where, "value": v if not isinstance(v, bool) else None})
    need = [x for x in items if x["need"]]
    return {"items": items, "done": sum(x["ok"] for x in items), "total": len(items),
            "need": len(need), "need_done": sum(x["ok"] for x in need),
            "missing": [x["label"] for x in need if not x["ok"]]}


# Что обязательно, чтобы сделка стояла на стадии (ключи SPEC). Реквизиты не в замке: МОП вносит их прямо в договор.
REQ_KP = ["name", "phone", "city", "service", "address", "area", "sum", "calc"]
REQ_DOG = REQ_KP + ["kp", "adv", "days", "warranty"]
REQ_WORK = REQ_DOG + ["paid", "signed", "start", "end"]
REQUIRED = {"PREPARATION": REQ_KP, "UC_VZFPUP": REQ_KP, "UC_YV66BV": REQ_KP, "UC_1EXUAC": REQ_KP,
            "FINAL_INVOICE": REQ_DOG, "UC_AV00QK": REQ_WORK, "UC_BMKDS4": REQ_WORK, "WON": REQ_WORK}
LABEL = {k: lab for k, lab, *_ in SPEC}


def blockers(fill: dict, cur: str, target: str, done: tuple = ()) -> list[str]:
    """Чего не хватает, чтобы перевести сделку из cur в target. Пусто — можно. done — что даёт сам переход (скачанный файл)."""
    if STAGE_STEP.get(target, 0) <= STAGE_STEP.get(cur, 0) and target != "WON":
        return []
    ok = {x["key"] for x in fill["items"] if x["ok"]} | set(done)
    return [LABEL[k] for k in REQUIRED.get(target, []) if k not in ok]


def for_deal(p: dict, deal_id: int) -> dict:
    """Заполненность без записи «открыл сделку» в журнал — для проверки перед сменой стадии."""
    d = bx._deal(p, deal_id, fresh=True)
    card = bx.deal_card(p, deal_id, audit=False)
    files = []
    for f, title in bx.FILES.items():
        if d.get(f):
            files.append({"title": title})
    card.update(files=files, pay={"received": bx._money(d.get(bx.FIN["received"]))}, norm={"shifts": bx._num(d.get(bx.F_SHIFTS))})
    return state(d, card, saved_calc(deal_id))


def gate(p: dict, deal_id: int, cur: str, target: str, done: tuple = ()) -> list[str]:
    if p["role_code"] == "head":
        return []
    return blockers(for_deal(p, deal_id), cur, target, done)


def saved_calc(deal_id: int) -> dict | None:
    with db.pool.connection() as conn:
        row = conn.execute("SELECT data FROM deal_calc WHERE deal_id=%s", (deal_id,)).fetchone()
    return row["data"] if row else None


# ---------- ИИ-помощник: разобрать переписку или анкету ----------

SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": "string", "description": "город объекта, как в списке городов, или пусто"},
        "service": {"type": "string", "description": "услуга из списка услуг или пусто"},
        "area": {"type": "number", "description": "площадь работ в м², 0 если не названа"},
        "address": {"type": "string", "description": "адрес объекта: улица, дом; пусто если нет"},
        "adv": {"type": "integer", "description": "аванс в %, 0 если не обсуждали"},
        "days": {"type": "integer", "description": "срок работ в календарных днях, 0 если не обсуждали"},
        "start": {"type": "string", "description": "дата старта работ ГГГГ-ММ-ДД или пусто"},
        "name": {"type": "string", "description": "имя клиента или название компании"},
        "phone": {"type": "string", "description": "телефон клиента"},
        "email": {"type": "string", "description": "e-mail клиента"},
        "bin": {"type": "string", "description": "БИН или ИИН, 12 цифр"},
        "company": {"type": "string", "description": "юрлицо: ТОО «…» или ИП …"},
        "signer": {"type": "string", "description": "кто подписывает договор, должность и ФИО"},
        "wishes": {"type": "string", "description": "что клиент хочет: тема, стиль, сроки, бюджет — одной-двумя фразами"},
    },
    "required": ["city", "service", "area", "address", "adv", "days", "start", "name", "phone", "email", "bin", "company", "signer", "wishes"],
    "additionalProperties": False,
}


def _ai(text: str, cities: list[str], services: list[str]) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_key, timeout=60, max_retries=1)
    r = client.messages.create(
        model="claude-opus-5-5", max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=("Ты помогаешь менеджеру студии росписи ARTGAME заполнить карточку сделки. Из переписки или анкеты клиента "
                "достань только то, что там прямо сказано; ничего не выдумывай, неизвестное оставь пустым или 0. "
                f"Города (выбери точное написание или пусто): {', '.join(cities)}. Услуги: {', '.join(services)}."),
        messages=[{"role": "user", "content": text[:20000]}],
    )
    if r.stop_reason == "refusal":
        raise RuntimeError("ИИ отказался разбирать текст")
    out = next((b.text for b in r.content if b.type == "text"), "{}")
    return json.loads(out)


def _rules(text: str, cities: list[str], services: list[str]) -> dict:
    t = text.replace(" ", " ")
    low = t.lower()
    out = {k: "" for k in SCHEMA["properties"]}
    out.update(area=0, adv=0, days=0)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:м2|м²|кв\.?\s*м|квадрат)", low)
    if m:
        out["area"] = float(m.group(1).replace(",", "."))
    out["city"] = next((c for c in sorted(cities, key=len, reverse=True) if c and c.lower() in low), "")
    for s in services:
        w = s.lower().split()[0] if s else ""
        if w and w[:6] in low:
            out["service"] = s
            break
    m = re.search(r"(?:ул\.|улица|пр\.|проспект|мкр\.?|микрорайон|адрес[:\s])\s*([^\n,;]+(?:,\s*\d+[^\n,;]*)?)", t, re.I)
    if m:
        out["address"] = m.group(0).replace("адрес:", "").replace("Адрес:", "").strip()
    m = re.search(r"аванс\D{0,15}(\d{1,3})\s*%", low) or re.search(r"(\d{1,3})\s*%\s*(?:аванс|предоплат)", low)
    if m:
        out["adv"] = int(m.group(1))
    m = re.search(r"(?:за|срок\D{0,10})\s*(\d{1,3})\s*(?:календарн\w*\s*)?(?:дн|дней|день)", low)
    if m:
        out["days"] = int(m.group(1))
    m = re.search(r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", t)
    if m:
        out["phone"] = m.group(0)
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", t)
    if m:
        out["email"] = m.group(0)
    m = re.search(r"(?:БИН|ИИН|BIN|IIN)\D{0,5}(\d{12})", t, re.I) or re.search(r"\b(\d{12})\b", t)
    if m:
        out["bin"] = m.group(1)
    m = re.search(r"(ТОО\s*[«\"][^»\"]+[»\"]|ИП\s+[А-ЯЁ][\w-]+(?:\s+[А-ЯЁ][\w.-]*){0,2})", t)
    if m:
        out["company"] = m.group(1)
    return out


class ExtractIn(BaseModel):
    text: str


@router.post("/bx/deals/{deal_id}/extract")
def api_extract(deal_id: int, body: ExtractIn, p: dict = Depends(active)):
    """Разобрать вставленный текст: поля сделки (с ID списков Битрикса) + данные клиента для договора. Ничего не пишет."""
    bx._deal(p, deal_id)
    text = (body.text or "").strip()
    if len(text) < 10:
        raise HTTPException(400, "вставьте переписку или анкету клиента")
    from .leads import cities as city_list
    cl = city_list()
    sv = [{"id": k, "name": v} for k, v in bx.enum_map(bx.SERVICE).items()]
    source, note = "rules", ""
    if settings.anthropic_key:
        try:
            raw, source = _ai(text, [c["name"] for c in cl], [s["name"] for s in sv]), "ai"
        except Exception as ex:  # noqa: BLE001 — ИИ недоступен: правила, и честно говорим об этом
            raw, note = _rules(text, [c["name"] for c in cl], [s["name"] for s in sv]), f"ИИ не ответил ({str(ex)[:80]}), разобрал правилами"
    else:
        raw = _rules(text, [c["name"] for c in cl], [s["name"] for s in sv])
    city = next((c for c in cl if c["name"].lower() == str(raw.get("city") or "").strip().lower()), None)
    serv = next((s for s in sv if s["name"].lower() == str(raw.get("service") or "").strip().lower()), None)
    fields = {"city": city["id"] if city else None, "cityName": city["name"] if city else "",
              "service": serv["id"] if serv else None, "serviceName": serv["name"] if serv else "",
              "area": raw.get("area") or None, "address": (raw.get("address") or "").strip() or None,
              "adv": raw.get("adv") or None, "days": raw.get("days") or None,
              "start": raw.get("start") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw.get("start") or "")) else None}
    client = {k: (raw.get(k) or "").strip() for k in ("name", "phone", "email", "bin", "company", "signer", "wishes")}
    with db.pool.connection() as conn:
        db.audit(conn, p["id"], "deal_extract", "deal", deal_id, {"source": source, "found": [k for k, v in fields.items() if v]})
    return {"source": source, "note": note, "fields": fields, "client": client}
