"""Закрытие сделки через HEAD (HEAD 12.11 «Да, по рекомендациям»; документ «Закрытие сделки через HEAD»).

В «Оплата получена» сделку переводит только HEAD. МОП со стадии «Оплата+закрывающие документы» жмёт «На закрытие» —
кнопка работает, когда выполнены все 11 пунктов (их проверяет приложение, галочек руками нет). HEAD получает заявку
на Пульт и в бот, открывает паспорт сделки: деньги, затраты, прибыль и маржа, план и факт, документы и фото, красные
флаги. «Закрыть» — приложение само переводит сделку в «Оплата получена» и пишет «Окончание факт»; паспорт сохраняется
навсегда (снимок), PDF — в папку сделки «ДОКУМЕНТЫ»; смены и расходы на объект больше не вносятся, даже задним числом.
«Вернуть» — с причиной или отмеченными пунктами: сделка остаётся на стадии, МОП и ГИП получают сообщение в чате «HEAD».
Решения HEAD 12.11: 1) отказы закрываются без HEAD, как раньше; 2) «Без документов (наличные/перевод)» — без договора,
счёта и АВР; 3) прибыль и маржа — только у HEAD в приложении, в Битрикс не пишем; 4) сделку, которую перетащили
в «Оплата получена» прямо в Битриксе, Пульт показывает красным — назад сама она не двигается.
"""
import sys
from datetime import date, datetime
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, bxw, db, deal_money, dm, drive, finance
from . import constants as consts
from .deps import require_head
from .fin_bx import F_END as F_END_FACT, _day, _entered
from .work import TZ, active

router = APIRouter(prefix="/api")

READY, WON = "UC_BMKDS4", "WON"   # «Оплата+закрывающие документы» → «Оплата получена»
NO_DOCS = "2071"                  # «Без документов (наличные/перевод)»: без договора, счёта и АВР (решение 2)
MYCO = {"1103": "ИП Яковлев", "2069": "ИП Артамонов", "2071": "Без документов (наличные/перевод)"}
FROM = date(2026, 11, 12)         # с этого дня сделка в «Оплата получена» без паспорта — «закрыта мимо HEAD»
F_LAYOUT = "UF_CRM_ARTGAME_APPROVED_LAYOUT"   # «Эскиз» (утверждённый макет) в сделке
MODEL = "fin.margin.model"        # норма маржи сделки, % — лист «Значения»; нет ключа — маржа без сравнения и без флага
TRIP = ("lodging", "trip_road", "trip_local", "trip_other")
EDIT_DONE = {"head", "mop", "mop_vip"}   # «Работы сданы» отмечают ГИП объекта, МОП и HEAD
TEST_DEAL = "Тестовая сделка — её не закрываем через паспорт"


def _fmt(x: float) -> str:
    return f"{int(round(x or 0)):,}".replace(",", " ") + " ₸"


def _dmy(x: date | None) -> str:
    return f"{x:%d.%m.%Y}" if x else ""


def _name(d: dict) -> str:
    """Название сделки без номера впереди («1710 · ШКОЛА…» → «ШКОЛА…»): номер в сообщениях уже есть."""
    return (d.get("TITLE") or "").removeprefix(f"{d['ID']} · ")


def _pl(n: float, one: str, few: str, many: str) -> str:
    n = int(n)
    return one if n % 10 == 1 and n % 100 != 11 else few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def _myco(d: dict) -> str:
    return MYCO.get(str(d.get("MYCOMPANY_ID") or ""), "не указано")


# ---------- 11 пунктов ----------

def _obj(conn, did: int) -> dict:
    return conn.execute("""SELECT o.id, o.title, o.city, o.drive_folder, o.folders, o.gip_person_id, o.done_on, o.closed_at, o.status,
                                  o.design_synced_at, g.full_name AS gip, b.full_name AS done_by
                           FROM objects o LEFT JOIN people g ON g.id=o.gip_person_id LEFT JOIN people b ON b.id=o.done_by
                           WHERE o.id=%s AND o.id<>0""", (did,)).fetchone() or {}


def checks(conn, d: dict, money: dict, o: dict | None = None) -> list[dict]:
    """Что должно быть выполнено, чтобы сделку можно было отправить на закрытие. ok — выполнено (или не нужно: skip)."""
    did, opp = int(d["ID"]), bx._money(d.get("OPPORTUNITY"))
    o = o if o is not None else _obj(conn, did)
    no_docs = str(d.get("MYCOMPANY_ID") or "") == NO_DOCS
    out: list[dict] = []

    def add(key, title, ok, detail, where, who, skip=False):
        out.append({"key": key, "title": title, "short": TITLES[key], "ok": bool(ok or skip), "skip": bool(skip and not ok), "detail": detail,
                    "where": where, "who": who})

    add("debt", "Долг 0: поступило = сумме сделки", opp > 0 and money["debt"] == 0,
        "в сделке нет суммы" if opp <= 0 else f"долг {_fmt(money['debt'])}" if money["debt"] else f"поступило {_fmt(money['received'])}",
        "шаг «Оплата» → «Внести оплату» с фото чека", "МОП или Анна")
    on = [x for x in money["items"] if x["on_check"]]
    add("checked", "Все оплаты сверены HEAD", not on, f"на сверке {len(on)} на {_fmt(sum(x['amount'] for x in on))}" if on else "ни одной на сверке",
        "HEAD: «Проверка» → оплаты клиентов → ✓", "HEAD")
    add("overpaid", "Переплаты нет или возврат внесён", money["overpaid"] == 0,
        f"переплата {_fmt(money['overpaid'])}" if money["overpaid"] else "переплаты нет",
        "возврат клиенту вносит HEAD: «Финансы» → «Движение денег» → «+ Операция» → «Возврат клиенту»", "МОП и HEAD")
    for key, f, title, where in (
            ("contract", bxw.F_CONTRACT, "Подписанный договор", "файл в поле «Договор подписанный» в Битриксе"),
            ("invoice", bxw.F_INVOICES, "Счёт на оплату", "шаг «Договор» → скачать счёт (ляжет в «Счета»)"),
            ("act", bxw.F_ACTS, "Подписанный акт (АВР)", "шаг «Договор» → акт; подписанный — файлом в поле «АВР» в Битриксе")):
        has = bool(d.get(f))
        add(key, title, has, "в сделке" if has else "не нужен: сделка «Без документов»" if no_docs else "нет файла", where, "МОП", skip=no_docs)
    end = _day(d.get(F_END_FACT)) or o.get("done_on")
    add("end", "Окончание работ (факт)", end,
        (f"{_dmy(end)}" + (f" · отметил {o['done_by']}" if o.get("done_on") and not d.get(F_END_FACT) and o.get("done_by") else "")) if end else "дата не отмечена",
        "«Проекты» → объект → «Работы сданы» (или здесь, ниже)", "ГИП")
    ph = conn.execute("""SELECT count(*) AS n FROM files WHERE object_id=%s AND status='ready' AND kind IN ('photo','media')
                         AND coalesce(mime,'') LIKE 'image/%%'""", (did,)).fetchone()["n"] if o else 0
    add("photos", "Фото готового объекта", ph > 0, f"фото: {ph}" if ph else "фото нет",
        "фото «после» в смене или «Продакшн» → загрузить (ляжет в «МЕДИА / Отчёты»)", "ГИП")
    ds = conn.execute("""SELECT count(*) AS n, count(*) FILTER (WHERE note ILIKE '%%утвержд%%') AS ok FROM files
                         WHERE object_id=%s AND status='ready' AND kind='design'""", (did,)).fetchone() if o else {"n": 0, "ok": 0}
    layout = bool(d.get(F_LAYOUT))
    add("design", "Утверждённый дизайн, если дизайн был", ds["ok"] > 0 or layout,
        "в «Утверждённых дизайнах»" if ds["ok"] else "«Эскиз» в сделке" if layout else
        f"эскизов {ds['n']}, утверждённого нет" if ds["n"] else "дизайна по сделке не было",
        "папка сделки «ДИЗАЙН / Утвержденные дизайны»", "дизайнер", skip=not ds["n"] and not layout)
    sh = conn.execute("""SELECT count(*) FILTER (WHERE status='open') AS open, count(*) FILTER (WHERE status='submitted') AS sub
                         FROM shifts WHERE object_id=%s""", (did,)).fetchone()
    add("shifts", "Ни одной открытой или непроверенной смены", not sh["open"] and not sh["sub"],
        ", ".join(x for x in (f"идёт {sh['open']}" if sh["open"] else "", f"на проверке {sh['sub']}" if sh["sub"] else "") if x) or "все проверены",
        "«Проверка»: оценка куратора, потом ✓ HEAD; идущую смену закрывает сотрудник", "кураторы и HEAD")
    ex = conn.execute("""SELECT count(*) AS n, coalesce(sum(amount), 0) AS s, count(*) FILTER (WHERE category = ANY(%s)) AS trip
                         FROM expenses WHERE status='submitted' AND (object_id=%s OR deal_id=%s)""", (list(TRIP), did, did)).fetchone()
    add("expenses", "Ни одного расхода на проверке, командировка закрыта", not ex["n"],
        (f"на проверке {ex['n']} на {_fmt(float(ex['s']))}" + (f", из них командировка {ex['trip']}" if ex["trip"] else "")) if ex["n"] else "все проверены",
        "«Проверка» → расходы; командировка — блок «Командировка» в карточке проекта", "ГИП и HEAD")
    return out


TITLES = {"debt": "Долг 0", "checked": "Оплаты сверены", "overpaid": "Переплата", "contract": "Подписанный договор", "invoice": "Счёт",
          "act": "АВР", "end": "Окончание работ (факт)", "photos": "Фото объекта", "design": "Утверждённый дизайн",
          "shifts": "Смены", "expenses": "Расходы и командировка"}


# ---------- паспорт сделки ----------

def _vals(conn) -> dict:
    """Числа «Значений» + время ночи («22:00» — строка, finance.vals её отбрасывает), чтобы ночь считалась, как в правилах."""
    v = consts.latest(conn)
    return {**finance.vals(conn), **{k: x for k, x in v.items() if k in ("pay.night.from", "pay.night.to")}}


def costs(conn, did: int) -> dict:
    """Затраты по объекту: ФОТ по сменам (кто, часы, деньги), материалы и расходы по чекам, командировка, дизайн, продажи."""
    v = _vals(conn)
    rows = conn.execute("""SELECT s.id, s.person_id, s.started_at, s.ended_at, s.kind, s.trip, s.bonus, s.zone_code,
                                  coalesce(s.role_code, pe.role_code) AS role, pe.full_name, r.title AS role_title
                           FROM shifts s JOIN people pe ON pe.id=s.person_id LEFT JOIN roles r ON r.code=coalesce(s.role_code, pe.role_code)
                           WHERE s.object_id=%s AND s.status='approved' ORDER BY s.started_at""", (did,)).fetchall()
    people: dict = {}
    warn: set = set()
    for s in rows:
        pay, miss = finance.one_shift_pay(v, s["role"], s["kind"], s["started_at"], s["ended_at"])
        salary = s["role"] in finance.SALARY_ROLE
        if miss and not salary:
            warn.add(miss)
        hours = (s["ended_at"] - s["started_at"]).total_seconds() / 3600 if s["ended_at"] else float(v.get("shift.hours") or 10)
        k = (s["person_id"], s["zone_code"] == "design")
        x = people.setdefault(k, {"name": s["full_name"], "role": s["role_title"] or s["role"], "design": k[1], "shifts": 0, "hours": 0.0,
                                  "pay": 0.0, "days": set(), "salary": salary})
        x["shifts"] += 1
        x["hours"] += hours
        x["pay"] += (0.0 if salary else pay) + float(s["bonus"] or 0)
        if s["trip"]:
            x["days"].add(s["started_at"].astimezone(TZ).date())
    food = float(v.get("pay.trip_food") or 0)
    food_days = sum(len(x["days"]) for x in people.values())
    if food_days and not food:
        warn.add("нет pay.trip_food в «Значениях» — питание в командировке не посчитано")
    ex = conn.execute("""SELECT e.id, e.category, c.title, c.article, e.amount, e.paid_by, e.zone_code, e.created_at, e.receipt_file_id,
                                e.note, pe.full_name AS person
                         FROM expenses e JOIN expense_categories c ON c.code=e.category JOIN people pe ON pe.id=e.person_id
                         WHERE (e.object_id=%s OR e.deal_id=%s) AND e.status='approved' ORDER BY e.created_at""", (did, did)).fetchall()

    def grp_of(e):
        return "trip" if e["category"] in TRIP else "sales" if e["article"] == "sales" else "design" if e["zone_code"] == "design" else "materials"

    def person_row(x):
        return {"name": x["name"], "role": x["role"], "shifts": x["shifts"], "hours": round(x["hours"], 1), "sum": round(x["pay"], 2),
                "note": "оклад — в затраты сделки не входит" if x["salary"] else ""}

    groups = {"fot": {"title": "ФОТ по сменам", "rows": [person_row(x) for x in people.values() if not x["design"]]},
              "materials": {"title": "Материалы и расходы", "rows": []}, "trip": {"title": "Командировка", "rows": []},
              "design": {"title": "Дизайн", "rows": [person_row(x) for x in people.values() if x["design"]]},
              "sales": {"title": "Продажи (привлечение)", "rows": []}}
    items: dict = {k: [] for k in groups}
    if food_days and food:
        groups["trip"]["rows"].append({"name": f"Питание · {food_days} дн. × {_fmt(food)}", "sum": food_days * food})
    by: dict = {}
    for e in ex:
        g = grp_of(e)
        r = by.setdefault((g, e["title"]), {"name": e["title"], "count": 0, "sum": 0.0})
        r["count"] += 1
        r["sum"] += float(e["amount"])
        items[g].append({"id": e["id"], "day": e["created_at"].astimezone(TZ).date().isoformat(), "person": e["person"], "title": e["title"],
                         "amount": float(e["amount"]), "paid_by": e["paid_by"], "note": e["note"] or "", "receipt_file_id": e["receipt_file_id"]})
    for (g, _), r in by.items():
        groups[g]["rows"].append(r)
    out = []
    for k, g in groups.items():
        total = round(sum(float(r["sum"]) for r in g["rows"]), 2)
        if g["rows"] or k == "fot":
            out.append({"key": k, "title": g["title"], "total": total, "rows": g["rows"], "items": items[k]})
    fact = sum(1 for s in rows if s["kind"] in (None, "work"))
    last = max((s["started_at"].astimezone(TZ).date() for s in rows), default=None)
    return {"groups": out, "total": round(sum(g["total"] for g in out), 2), "warn": sorted(warn), "shifts_fact": fact, "last_shift": last}


def _docs(d: dict) -> list[dict]:
    out = []
    for k, title in bx.FILES.items():
        v = d.get(k)
        n = len([x for x in (v if isinstance(v, list) else [v]) if x]) if v else 0
        out.append({"title": title, "n": n})
    return out


def _photos(conn, did: int) -> tuple[list[dict], int]:
    rows = conn.execute("""SELECT id, name, review, prod_drive_id FROM files WHERE object_id=%s AND status='ready' AND kind IN ('photo','media')
                           AND coalesce(mime,'') LIKE 'image/%%' ORDER BY created_at DESC LIMIT 6""", (did,)).fetchall()
    n = conn.execute("""SELECT count(*) AS n FROM files WHERE object_id=%s AND status='ready' AND kind IN ('photo','media')
                        AND coalesce(mime,'') LIKE 'image/%%'""", (did,)).fetchone()["n"]
    return [{"id": r["id"], "name": r["name"], "prod": r["review"] == "approved"} for r in rows], n


def passport(conn, p: dict, d: dict, money: dict, cks: list[dict], o: dict) -> dict:
    """Паспорт сделки на одном экране (только HEAD): сделка, деньги, затраты, итог, план и факт, документы и фото, флаги."""
    did = int(d["ID"])
    card = bx.deal_card(p, did, audit=False)
    names = {u["id"]: u["name"] for u in bx.users()}
    vat = deal_money._vat()
    opp = bx._money(d.get("OPPORTUNITY"))
    net = round(opp / (1 + vat / 100), 2) if vat else opp
    c = costs(conn, did)
    profit = round(net - c["total"], 2)
    margin = round(profit / net * 100, 1) if net > 0 else None
    model = consts.latest(conn).get(MODEL)
    model = float(model) if isinstance(model, (int, float)) else None
    start, end_plan = _day(d.get(bxw.F_START)), _day(d.get(bxw.F_END))
    end_fact = _day(d.get(F_END_FACT)) or o.get("done_on")
    term = bx._num(d.get(bxw.F_DAYS)) or bx._num(d.get(bx.F_TERM))
    norm = bx._num(d.get(bx.F_SHIFTS))
    flags = []
    if norm and c["shifts_fact"] > norm:
        flags.append(f"Затраты выше расчёта: смен {c['shifts_fact']} при расчёте {norm:g} (+{round((c['shifts_fact'] / norm - 1) * 100)}%)")
    if end_plan and end_fact and end_fact > end_plan:
        flags.append(f"Срок сорван: сдали {_dmy(end_fact)}, по плану {_dmy(end_plan)} (+{(end_fact - end_plan).days} дн.)")
    if model is not None and margin is not None and margin < model:
        flags.append(f"Маржа {margin:g}% ниже нормы {model:g}%")
    cash = [x for x in money["items"] if x.get("account_code") == deal_money.CASH and not x.get("receipt_file_id") and x["amount"] > 0]
    if cash:
        flags.append(f"Наличные без фото чека: {len(cash)} на {_fmt(sum(x['amount'] for x in cash))}")
    if end_fact and c["last_shift"] and c["last_shift"] > end_fact:
        flags.append(f"Последняя смена {_dmy(c['last_shift'])} — позже окончания работ {_dmy(end_fact)}")
    flags += [f"«Значения»: {w}" for w in c["warn"]]   # невыполненные пункты — в «Пунктах закрытия», не дублируем
    photos, n_photos = _photos(conn, did)
    signed = _entered(did, "UC_AV00QK")
    items = [{k: x.get(k) for k in ("id", "op_date", "amount", "account_title", "account_code", "source", "on_check", "author", "receipt_file_id", "note")}
             for x in money["items"]]
    return {
        "deal": {"id": did, "title": d.get("TITLE") or "", "client": (card.get("client") or {}).get("name") or "", "client_type": (card.get("client") or {}).get("type") or "",
                 "myco": _myco(d), "mop": names.get(int(d.get("ASSIGNED_BY_ID") or 0), ""), "gip": o.get("gip") or "", "city": card.get("city") or "",
                 "object": card.get("object") or "", "address": card.get("address") or "", "area": card.get("area") or 0, "service": card.get("service") or "",
                 "stage": d.get("STAGE_ID"), "dates": {"signed": signed.isoformat() if signed else "", "start": start.isoformat() if start else "",
                                                       "end_plan": end_plan.isoformat() if end_plan else "", "end_fact": end_fact.isoformat() if end_fact else ""}},
        "money": {"sum": opp, "net": net, "vat": round(opp - net, 2), "vat_pct": vat, "received": money["received"], "debt": money["debt"],
                  "overpaid": money["overpaid"], "items": items, "history": money["history"]},
        "costs": c["groups"], "costs_total": c["total"],
        "result": {"net": net, "costs": c["total"], "profit": profit, "margin": margin, "model": model},
        "plan": {"term": term or None, "days": (end_fact - start).days + 1 if start and end_fact else None,
                 "shifts_plan": norm or None, "shifts_fact": c["shifts_fact"]},
        "docs": _docs(d), "photos": photos, "photos_total": n_photos,
        "folder": f"https://drive.google.com/drive/folders/{o['drive_folder']}" if o.get("drive_folder") else "",
        "bitrix": (bxw.portal() + f"/crm/deal/details/{did}/") if bxw.portal() else "",
        "flags": flags, "built_at": datetime.now(TZ).isoformat(),
    }


def _sign(pas: dict) -> dict:
    """Ссылки на чеки и фото подписываются при каждом показе (живут 12 ч), в снимке хранятся только номера файлов."""
    from .files import sign
    for x in pas["money"]["items"]:
        x["receipt_url"] = sign(x["receipt_file_id"], "content") if x.get("receipt_file_id") else None
    for g in pas["costs"]:
        for x in g.get("items") or []:
            x["receipt_url"] = sign(x["receipt_file_id"], "content") if x.get("receipt_file_id") else None
    for x in pas["photos"]:
        x["thumb"], x["url"] = sign(x["id"], "thumb"), sign(x["id"], "content")
    return pas


# ---------- МОП: шаг «Закрытие» в карточке сделки ----------

def _last(conn, did: int) -> dict | None:
    r = conn.execute("""SELECT c.id, c.status, c.via, c.sent_at, c.decided_at, c.reason, c.points, c.pdf_drive_id, c.pdf_error, c.bx,
                               s.full_name AS sent_by, h.full_name AS decided_by
                        FROM deal_close c LEFT JOIN people s ON s.id=c.sent_by LEFT JOIN people h ON h.id=c.decided_by
                        WHERE c.deal_id=%s AND c.status <> 'cancelled' ORDER BY c.id DESC LIMIT 1""", (did,)).fetchone()
    if r:
        r["points"] = [{"key": k, "title": TITLES.get(k, k)} for k in r["points"] or []]
        r["pdf"] = f"https://drive.google.com/file/d/{r['pdf_drive_id']}/view" if r["pdf_drive_id"] else ""
    return r


def _state(conn, p: dict, d: dict) -> dict:
    did = int(d["ID"])
    money = deal_money.card(d)
    o = _obj(conn, did)
    if o:
        from .promo import maybe_sync   # эскизы с Диска свежие — пункт «Утверждённый дизайн»
        maybe_sync(conn, o)
    cks = checks(conn, d, money, o)
    return {"id": did, "stage": d["STAGE_ID"], "ready": d["STAGE_ID"] == READY, "won": d["STAGE_ID"] == WON, "test": bx.is_test(d),
            "myco": _myco(d), "no_docs": str(d.get("MYCOMPANY_ID") or "") == NO_DOCS, "checks": cks, "ok": all(x["ok"] for x in cks),
            "object": bool(o), "done_on": o.get("done_on").isoformat() if o.get("done_on") else "", "closed_at": o.get("closed_at"),
            "request": _last(conn, did), "head": p["role_code"] == "head", "money": money, "o": o}


@router.get("/bx/deals/{deal_id}/close")
def close_state(deal_id: int, p: dict = Depends(active)):
    d = bx._deal(p, deal_id, fresh=True)
    with db.pool.connection() as conn:
        s = _state(conn, p, d)
    s.pop("money"), s.pop("o")
    return s


def _tell_heads(jobs: list[tuple[int, str]]) -> None:
    for tg, text in jobs:
        try:
            dm.SEND(tg, text)
        except Exception as e:  # noqa: BLE001 — бот недоступен: заявка всё равно на Пульте
            print("closing notify:", e, file=sys.stderr)


@router.post("/bx/deals/{deal_id}/close")
def close_send(deal_id: int, bg: BackgroundTasks, p: dict = Depends(active)):
    """«На закрытие»: МОП (своя сделка) со стадии «Оплата+закрывающие документы», когда выполнены все пункты."""
    d = bx._deal(p, deal_id, fresh=True)
    if bx.is_test(d):
        raise HTTPException(400, TEST_DEAL)
    if d["STAGE_ID"] != READY:
        raise HTTPException(409, "«На закрытие» — со стадии «Оплата+закрывающие документы», когда работы сданы")
    names = {u["id"]: u["name"] for u in bx.users()}
    with db.pool.connection() as conn, conn.transaction():
        s = _state(conn, p, d)
        miss = [x["title"] for x in s["checks"] if not x["ok"]]
        if miss:
            raise HTTPException(409, "сначала: " + "; ".join(miss))
        old = conn.execute("SELECT * FROM deal_close WHERE deal_id=%s AND status='sent'", (deal_id,)).fetchone()
        if old:
            return {"ok": True, "request": _last(conn, deal_id), "again": True}
        if conn.execute("SELECT 1 FROM deal_close WHERE deal_id=%s AND status='closed'", (deal_id,)).fetchone():
            raise HTTPException(409, "сделка уже закрыта")
        row = conn.execute("""INSERT INTO deal_close (deal_id, title, amount, sent_by) VALUES (%s,%s,%s,%s) RETURNING id""",
                           (deal_id, d.get("TITLE") or "", bx._money(d.get("OPPORTUNITY")), p["id"])).fetchone()
        db.audit(conn, p["id"], "deal_close_send", "deal", deal_id, {"request": row["id"]})
        text = (f"🔒 На закрытие: № {deal_id} · {_name(d)}\n{_fmt(bx._money(d.get('OPPORTUNITY')))} · МОП "
                f"{names.get(int(d.get('ASSIGNED_BY_ID') or 0), p['full_name'])}\nПаспорт сделки — в приложении: Пульт → «Сделки на закрытие».")
        jobs = [(h["tg_id"], text) for h in dm._heads(conn) if dm._real(h["tg_id"])]
        out = {"ok": True, "request": _last(conn, deal_id)}
    bg.add_task(_tell_heads, jobs)   # заявка приходит HEAD на Пульт и в бот (документ, утверждён 12.11)
    return out


class DoneIn(BaseModel):
    day: date | None = None   # пусто — снять отметку


def _can_done(conn, p: dict, oid: int) -> bool:
    if p.get("_view_as"):
        return False
    if p["role_code"] in EDIT_DONE:
        return True
    o = conn.execute("SELECT gip_person_id FROM objects WHERE id=%s", (oid,)).fetchone()
    return bool(o and o["gip_person_id"] == p["id"])


@router.get("/objects/{oid}/done")
def done_get(oid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        o = _obj(conn, oid)
        if not o:
            raise HTTPException(404, "объекта ещё нет в приложении")
        last = conn.execute("""SELECT max((started_at AT TIME ZONE 'Asia/Almaty')::date) AS d FROM shifts
                               WHERE object_id=%s AND status IN ('submitted','approved')""", (oid,)).fetchone()["d"]
        return {"done_on": o["done_on"].isoformat() if o.get("done_on") else "", "done_by": o.get("done_by") or "",
                "closed": bool(o.get("closed_at")), "can_edit": _can_done(conn, p, oid) and not o.get("closed_at"),
                "last_shift": last.isoformat() if last else ""}


@router.post("/objects/{oid}/done")
def done_set(oid: int, b: DoneIn, p: dict = Depends(active)):
    """«Работы сданы» (окончание работ, факт): ГИП объекта, МОП или HEAD. В Битрикс уходит при закрытии сделки."""
    if b.day and (b.day > datetime.now(TZ).date() or b.day < date(2025, 1, 1)):
        raise HTTPException(400, "дата сдачи — не позже сегодня")
    with db.pool.connection() as conn, conn.transaction():
        o = _obj(conn, oid)
        if not o:
            raise HTTPException(404, "объекта ещё нет в приложении")
        if not _can_done(conn, p, oid):
            raise HTTPException(403, "сдачу отмечают ГИП объекта, МОП и HEAD")
        if o.get("closed_at"):
            raise HTTPException(409, "сделка закрыта HEAD — дату не меняем")
        conn.execute("UPDATE objects SET done_on=%s, done_by=%s WHERE id=%s", (b.day, p["id"] if b.day else None, oid))
        db.audit(conn, p["id"], "object_done", "objects", oid, {"day": b.day.isoformat() if b.day else None})
    return done_get(oid, p)


# ---------- HEAD: заявки, паспорт, «Закрыть» / «Вернуть» ----------

def _bypass(closed: set[int]) -> list[dict]:
    """Сделки, которые с FROM перевели в «Оплата получена» мимо паспорта (прямо в Битриксе)."""
    rows = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": [0], "STAGE_ID": [WON], "STAGE_SEMANTIC_ID": "S", ">=MOVED_TIME": FROM.isoformat()},
                                         "select": ["ID", "TITLE", "OPPORTUNITY", "MOVED_TIME", "MOVED_BY_ID", "ASSIGNED_BY_ID", "STAGE_ID"]})
    names = {u["id"]: u["name"] for u in bx.users()} if rows else {}
    out = []
    for d in rows:
        moved = _day(d.get("MOVED_TIME"))
        if d.get("STAGE_ID") != WON or int(d["ID"]) in closed or bx.is_test(d) or not moved or moved < FROM:
            continue
        out.append({"deal_id": int(d["ID"]), "title": d.get("TITLE") or "", "amount": bx._money(d.get("OPPORTUNITY")), "moved": moved.isoformat(),
                    "moved_by": names.get(int(d.get("MOVED_BY_ID") or 0), ""), "mop": names.get(int(d.get("ASSIGNED_BY_ID") or 0), "")})
    return sorted(out, key=lambda x: x["moved"], reverse=True)


@router.get("/head/closing")
def closing_list(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        q = """SELECT c.id, c.deal_id, c.title, c.amount, c.status, c.via, c.sent_at, c.decided_at, c.reason, c.pdf_drive_id,
                      s.full_name AS sent_by, h.full_name AS decided_by, c.passport->'result' AS result
               FROM deal_close c LEFT JOIN people s ON s.id=c.sent_by LEFT JOIN people h ON h.id=c.decided_by WHERE c.status=%s """
        sent = conn.execute(q + "ORDER BY c.sent_at", ("sent",)).fetchall()
        closed = conn.execute(q + "ORDER BY c.decided_at DESC LIMIT 20", ("closed",)).fetchall()
        ids = {r["deal_id"] for r in conn.execute("SELECT deal_id FROM deal_close WHERE status='closed'").fetchall()}
    err, bypass = "", []
    try:
        bypass = _bypass(ids)
    except Exception as ex:  # noqa: BLE001 — Битрикс недоступен: заявки из базы всё равно видны
        err = f"Битрикс не ответил: {str(ex)[:120]}"
    for r in sent + closed:
        r["amount"] = float(r["amount"] or 0)
    return {"sent": sent, "bypass": bypass, "closed": closed, "error": err}


@router.get("/head/closing/{deal_id}")
def closing_one(deal_id: int, p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        done = conn.execute("""SELECT c.*, h.full_name AS decided_name FROM deal_close c LEFT JOIN people h ON h.id=c.decided_by
                               WHERE c.deal_id=%s AND c.status='closed'""", (deal_id,)).fetchone()
        if done and done["passport"]:   # закрытая сделка — паспорт как сохранили при закрытии
            return {**_sign(done["passport"]), "frozen": True, "request": _last(conn, deal_id), "checks": done["passport"].get("checks") or []}
    d = bx._deal(p, deal_id, fresh=True)
    with db.pool.connection() as conn:
        s = _state(conn, p, d)
        pas = passport(conn, p, d, s["money"], s["checks"], s["o"])
    return {**_sign(pas), "frozen": False, "checks": s["checks"], "ok": s["ok"], "request": s["request"], "ready": s["ready"],
            "won": s["won"], "test": s["test"], "object": s["object"], "bypass": s["won"]}


class DecideIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
    points: list[str] = Field(default_factory=list, max_length=11)


def _people_of(conn, d: dict, o: dict) -> list[int]:
    """Кому сообщить о решении: МОП сделки (по пользователю Битрикса) и ГИП объекта."""
    ids = []
    m = conn.execute("SELECT id FROM people WHERE bitrix_user_id=%s AND status='active' AND role_code<>'head' ORDER BY id LIMIT 1",
                     (int(d.get("ASSIGNED_BY_ID") or 0),)).fetchone()
    if m:
        ids.append(m["id"])
    if o.get("gip_person_id") and o["gip_person_id"] not in ids:
        g = conn.execute("SELECT id FROM people WHERE id=%s AND status='active' AND role_code<>'head'", (o["gip_person_id"],)).fetchone()
        if g:
            ids.append(g["id"])
    return ids


@router.post("/head/closing/{deal_id}/close")
def closing_close(deal_id: int, bg: BackgroundTasks, p: dict = Depends(require_head)):
    """«Закрыть» — только когда выполнены все пункты (HEAD 12.11, и для закрытой мимо паспорта тоже: иначе только «Вернуть»):
    сделка → «Оплата получена» (и «Окончание факт», если его нет), паспорт — снимком навсегда, PDF — в «ДОКУМЕНТЫ»,
    объект закрыт для смен и расходов, МОП и ГИП — сообщение. Закрытую мимо HEAD (уже в «Оплата получена») — только паспорт."""
    d = bx._deal(p, deal_id, fresh=True)
    if bx.is_test(d):
        raise HTTPException(400, TEST_DEAL)
    if d["STAGE_ID"] not in (READY, WON):
        raise HTTPException(409, "Закрыть можно со стадии «Оплата+закрывающие документы»")
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM deal_close WHERE deal_id=%s AND status='closed'", (deal_id,)).fetchone():
            raise HTTPException(409, "сделка уже закрыта")
        s = _state(conn, p, d)
        miss = [x["short"] for x in s["checks"] if not x["ok"]]
        if miss:
            raise HTTPException(409, "Закрыть можно, только когда выполнены все пункты. Не выполнено: " + ", ".join(miss))
        pas = passport(conn, p, d, s["money"], s["checks"], s["o"])
    o = s["o"]
    via = "bitrix" if d["STAGE_ID"] == WON else "app"
    fields = {} if via == "bitrix" else {"STAGE_ID": WON}
    if not d.get(F_END_FACT) and o.get("done_on"):
        fields[bxw.F_END_FACT] = o["done_on"].isoformat()
    r = {"bx": "skip"}
    if fields:   # в Битрикс — только стадия и дата; прибыль и маржа туда не пишутся (решение 3)
        r = bxw.write(p, deal_id, "закрытие сделки", fields, "закрыл сделку: паспорт сделки сохранён в приложении" if via == "app" else None)
        if r["bx"] == "error":
            raise HTTPException(502, f"Битрикс не принял: {r.get('error')}")
    pas["checks"] = s["checks"]
    pas["closed"] = {"at": datetime.now(TZ).isoformat(), "by": p["full_name"], "via": via}
    with db.pool.connection() as conn, conn.transaction():
        from psycopg.types.json import Jsonb
        row = conn.execute("""UPDATE deal_close SET status='closed', decided_by=%s, decided_at=now(), passport=%s, bx=%s, via=%s
                              WHERE deal_id=%s AND status='sent' RETURNING id""", (p["id"], Jsonb(pas), r["bx"], via, deal_id)).fetchone()
        if not row:   # HEAD закрыл сам, без заявки МОП, или принял закрытие мимо паспорта
            row = conn.execute("""INSERT INTO deal_close (deal_id, title, amount, status, via, decided_by, decided_at, passport, bx)
                                  VALUES (%s,%s,%s,'closed',%s,%s,now(),%s,%s) RETURNING id""",
                               (deal_id, d.get("TITLE") or "", bx._money(d.get("OPPORTUNITY")), via, p["id"], Jsonb(pas), r["bx"])).fetchone()
        conn.execute("UPDATE objects SET closed_at=now() WHERE id=%s AND closed_at IS NULL", (deal_id,))
        db.audit(conn, p["id"], "deal_close", "deal", deal_id, {"request": row["id"], "via": via, "bx": r["bx"], "fields": list(fields)})
        text = (f"✅ Сделка № {deal_id} «{_name(d)}» закрыта. Паспорт сохранён; смены и расходы на объект больше не вносятся.")
        for pid in _people_of(conn, d, o):
            dm._add(conn, pid, p, True, None, text)
    bg.add_task(save_pdf, row["id"])
    return {"ok": True, "bx": r["bx"], "via": via, "id": row["id"]}


@router.post("/head/closing/{deal_id}/return")
def closing_return(deal_id: int, b: DecideIn, p: dict = Depends(require_head)):
    """«Вернуть»: причина или отмеченные пункты; сделка остаётся на стадии (закрытую мимо паспорта — назад
    в «Оплата+закрывающие документы»), МОП и ГИП получают сообщение со списком в чате «HEAD»."""
    reason = (b.reason or "").strip()
    points = [k for k in dict.fromkeys(b.points) if k in TITLES]
    if not reason and not points:
        raise HTTPException(400, "напишите причину или отметьте пункты")
    d = bx._deal(p, deal_id, fresh=True)
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM deal_close WHERE deal_id=%s AND status='closed'", (deal_id,)).fetchone():
            raise HTTPException(409, "сделка уже закрыта")
        o = _obj(conn, deal_id)
    r = {"bx": "skip"}
    if d["STAGE_ID"] == WON:   # перетащили в «Оплата получена» мимо HEAD — HEAD возвращает на «Оплата+закрывающие»
        r = bxw.write(p, deal_id, "возврат с закрытия", {"STAGE_ID": READY}, "вернул сделку на «Оплата+закрывающие документы»: закрытие — через паспорт")
        if r["bx"] == "error":
            raise HTTPException(502, f"Битрикс не принял: {r.get('error')}")
    with db.pool.connection() as conn, conn.transaction():
        from psycopg.types.json import Jsonb
        row = conn.execute("""UPDATE deal_close SET status='returned', decided_by=%s, decided_at=now(), reason=%s, points=%s
                              WHERE deal_id=%s AND status='sent' RETURNING id""", (p["id"], reason or None, Jsonb(points), deal_id)).fetchone()
        if not row:
            row = conn.execute("""INSERT INTO deal_close (deal_id, title, amount, status, via, decided_by, decided_at, reason, points, bx)
                                  VALUES (%s,%s,%s,'returned',%s,%s,now(),%s,%s,%s) RETURNING id""",
                               (deal_id, d.get("TITLE") or "", bx._money(d.get("OPPORTUNITY")), "bitrix" if d["STAGE_ID"] == WON else "app",
                                p["id"], reason or None, Jsonb(points), r["bx"])).fetchone()
        db.audit(conn, p["id"], "deal_close_return", "deal", deal_id, {"request": row["id"], "points": points, "reason": reason})
        text = (f"↩️ Сделка № {deal_id} «{_name(d)}» возвращена с закрытия." + (f"\nПричина: {reason}" if reason else "")
                + (f"\nДоделать: {'; '.join(TITLES[k] for k in points)}" if points else "")
                + "\nКогда готово — снова «На закрытие» в карточке сделки (шаг «Закрытие»).")
        sent = _people_of(conn, d, o)
        for pid in sent:
            dm._add(conn, pid, p, True, None, text)
    return {"ok": True, "told": len(sent), "bx": r["bx"]}


@router.post("/head/closing/{deal_id}/prod/{file_id}")
def closing_prod(deal_id: int, file_id: int, p: dict = Depends(require_head)):
    """Лучшее фото из паспорта — сразу в «МЕДИА / Продакшн / Фото» (копия, оригинал остаётся в «Отчётах»)."""
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("""SELECT * FROM files WHERE id=%s AND object_id=%s AND status='ready' AND kind IN ('photo','media')
                            AND coalesce(mime,'') LIKE 'image/%%' FOR UPDATE""", (file_id, deal_id)).fetchone()
        if not f:
            raise HTTPException(404, "нет такого фото")
        if f["review"] == "approved":
            return {"ok": True, "prod": True}
        obj = conn.execute("SELECT * FROM objects WHERE id=%s", (deal_id,)).fetchone()
        try:
            dr = drive.Drive()
            prod = dr.copy(f["drive_id"], drive.folder_of(conn, obj, "prod", dr, "photo"), f["name"])
        except Exception as ex:  # noqa: BLE001
            raise drive.fail(ex)
        conn.execute("UPDATE files SET review='approved', reviewed_by=%s, reviewed_at=now(), prod_drive_id=%s WHERE id=%s", (p["id"], prod, file_id))
        db.audit(conn, p["id"], "media_review", "files", file_id, {"approve": True, "via": "closing", "deal": deal_id})
    return {"ok": True, "prod": True}


@router.post("/head/closing/{deal_id}/pdf")
def closing_pdf(deal_id: int, p: dict = Depends(require_head)):
    """PDF паспорта ещё раз (если Диск не ответил при закрытии)."""
    with db.pool.connection() as conn:
        row = conn.execute("SELECT id FROM deal_close WHERE deal_id=%s AND status='closed'", (deal_id,)).fetchone()
    if not row:
        raise HTTPException(404, "сделка ещё не закрыта")
    save_pdf(row["id"])
    with db.pool.connection() as conn:
        return _last(conn, deal_id)


# ---------- PDF паспорта → папка сделки «ДОКУМЕНТЫ» ----------

def _t(rows: list[list], head: list[str] | None = None) -> str:
    th = "".join(f"<th style='text-align:left;border:1px solid #999;padding:4px'>{escape(str(h))}</th>" for h in head) if head else ""
    tr = "".join("<tr>" + "".join(f"<td style='border:1px solid #999;padding:4px'>{escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table style='border-collapse:collapse;width:100%'>{('<tr>' + th + '</tr>') if th else ''}{tr}</table>"


def pdf_html(pas: dict) -> str:
    dl, m, r, pl = pas["deal"], pas["money"], pas["result"], pas["plan"]
    dt = dl["dates"]
    iso = lambda s: _dmy(date.fromisoformat(s)) if s else "—"  # noqa: E731
    h = [f"<h1>Паспорт сделки № {dl['id']}</h1><p>{escape(dl['title'])}</p>",
         f"<p>Закрыта {iso(pas['closed']['at'][:10])} · {escape(pas['closed']['by'])}" + (" · закрыта в Битриксе мимо паспорта" if pas["closed"]["via"] == "bitrix" else "") + "</p>",
         "<h2>Сделка</h2>", _t([["Клиент", f"{dl['client']} ({dl['client_type']})" if dl["client_type"] else dl["client"]], ["Исполнитель", dl["myco"]],
                                 ["МОП", dl["mop"]], ["ГИП", dl["gip"] or "—"], ["Город", dl["city"]], ["Объект", dl["object"]], ["Адрес", dl["address"]],
                                 ["Площадь", f"{dl['area']:g} м²" if dl["area"] else "—"], ["Услуга", dl["service"]],
                                 ["Договор (в работу)", iso(dt["signed"])], ["Старт (факт)", iso(dt["start"])], ["Сдача (план)", iso(dt["end_plan"])],
                                 ["Сдача (факт)", iso(dt["end_fact"])]]),
         "<h2>Деньги</h2>", _t([["Сумма с НДС", _fmt(m["sum"])], [f"Без НДС ({m['vat_pct']:g}%)", _fmt(m["net"])], ["НДС", _fmt(m["vat"])],
                                 ["Поступило", _fmt(m["received"])], ["Долг", _fmt(m["debt"])]]),
         _t([[iso(x["op_date"]), x["account_title"], _fmt(x["amount"]), "чек есть" if x.get("receipt_file_id") else "без чека"] for x in m["items"]],
            ["Дата", "Счёт", "Сумма", "Чек"]) if m["items"] else "",
         "<h2>Затраты</h2>"]
    for g in pas["costs"]:
        h.append(f"<h3>{escape(g['title'])}: {_fmt(g['total'])}</h3>")
        if g["rows"]:
            h.append(_t([[x["name"] + (f" · {x['role']}" if x.get("role") else ""), (f"{x['shifts']} {_pl(x['shifts'], 'смена', 'смены', 'смен')}, {x['hours']:g} ч" if "shifts" in x
                           else f"{x['count']} {_pl(x['count'], 'запись', 'записи', 'записей')}" if x.get("count") else ""),
                          _fmt(x["sum"]) + (f" ({x['note']})" if x.get("note") else "")] for x in g["rows"]]))
    h += [f"<p><b>Итого затрат: {_fmt(pas['costs_total'])}</b></p>", "<h2>Итог</h2>",
          _t([["Выручка без НДС", _fmt(r["net"])], ["Затраты", _fmt(r["costs"])], ["Прибыль", _fmt(r["profit"])],
              ["Маржа", (f"{r['margin']:g}%" if r["margin"] is not None else "—") + (f" (норма {r['model']:g}%)" if r["model"] is not None else "")],
              ["Срок, дней: план / факт", f"{pl['term'] or '—'} / {pl['days'] or '—'}"],
              ["Смены: по расчёту / факт", f"{pl['shifts_plan'] if pl['shifts_plan'] is not None else '—'} / {pl['shifts_fact']}"]]),
          "<h2>Красные флаги</h2>", ("<ul>" + "".join(f"<li>{escape(f)}</li>" for f in pas["flags"]) + "</ul>") if pas["flags"] else "<p>нет</p>",
          "<h2>Пункты закрытия</h2>", _t([[x["title"], "не нужно" if x.get("skip") else "да" if x["ok"] else "нет", x.get("detail") or ""]
                                          for x in pas.get("checks") or []]),
          "<h2>Документы</h2>", _t([[x["title"], f"файлов: {x['n']}" if x["n"] else "нет"] for x in pas["docs"]]),
          f"<p>Фото объекта: {pas['photos_total']}. Папка сделки: {escape(pas['folder'] or '—')}</p>"]
    return "<html><head><meta charset='utf-8'></head><body style='font-family:Arial;font-size:11pt'>" + "".join(h) + "</body></html>"


def save_pdf(row_id: int) -> None:
    with db.pool.connection() as conn:
        row = conn.execute("SELECT * FROM deal_close WHERE id=%s", (row_id,)).fetchone()
        obj = conn.execute("SELECT * FROM objects WHERE id=%s AND id<>0", (row["deal_id"],)).fetchone() if row else None
        if not row or not row["passport"]:
            return
        try:
            if not obj:
                raise RuntimeError("объекта сделки нет в приложении — нет папки")
            d = drive.Drive()
            folder = drive.ensure_folders(conn, obj, d)["doc"]
            name = f"Паспорт сделки {row['deal_id']} {row['decided_at'].astimezone(TZ):%Y-%m-%d}.pdf"
            fid = d.pdf_from_html(folder, name, pdf_html(row["passport"]))
            conn.execute("UPDATE deal_close SET pdf_drive_id=%s, pdf_error=NULL WHERE id=%s", (fid, row_id))
        except Exception as ex:  # noqa: BLE001 — Диск не ответил: паспорт в приложении есть, PDF — кнопкой ещё раз
            conn.execute("UPDATE deal_close SET pdf_error=%s WHERE id=%s", (f"{ex.__class__.__name__}: {str(ex)[:200]}", row_id))
