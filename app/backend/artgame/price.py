"""Объединённый расчёт для карточки сделки (HEAD 06.11): цена клиенту + срок и состав одной формой.

Формулы — те же, что в калькуляторе рабочего места (design-kit/rm_extra.js, решения HEAD 03.11): роспись плавно от ставки a
до пола b между mural.start и E, печать по точкам print.calc.p1..p5, дизайн процентом от сметы с минимумом категории,
надбавки складываются, выезд, скидка за наличные, минимальный заказ, округление до 1 000. Числа берутся из «Значений»
в момент расчёта (здесь — только значения по умолчанию на тех же ключах). Срок и состав — bx.resources (нормы).
Сохранённый расчёт лежит в deal_calc: из него потом собираются КП и документы, руками цифры никто не переносит.
"""
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from . import bx, bxw, db
from .work import active

router = APIRouter(prefix="/api")

LEVEL_KEY = {"easy": "Лёгкий", "medium": "Средний", "hard": "Сложный", "author": "Авторский"}
LEVEL_DEF = {"easy": (17000, 12000, 100), "medium": (22000, 17000, 100), "hard": (27000, 22000, 100), "author": (50000, 27000, 400)}
PRINT_DEF = [(10, 30000), (15, 25000), (50, 20000), (100, 15000), (1000, 12000)]
FIX_DEF = {"lite": ("Лёгкий", 129000), "hard": ("Сложный", 199000), "excl": ("Эксклюзив", 279000)}
DESIGN_DEF = {"m": (3, 30000), "l": (3, 150000), "xl": (2, 400000)}
EXTRAS = [("urgent", "Срочность", "extra.urgent"), ("height", "Высота", "extra.height"), ("night", "Ночь", "extra.night"),
          ("lacquer", "Лак (защита)", "extra.lacquer")]
SERVICES = {"mural": "Художественная роспись", "print": "Настенная печать", "fix": "Готовый рисунок по фикс-прайсу", "bulk": "Покраска стен"}
KP_NAME = {"mural": "Художественная роспись стен", "print": "Принтерная печать", "bulk": "Покраска стен", "fix": "Готовый рисунок по фикс-прайсу"}
PLACES = {"base": "Астана / Шымкент", "near": "150–200 км", "far": "Другой город"}


def _fmt(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ") + " ₸"


def r1000(n: float) -> int:
    return int(math.floor(n / 1000 + .5) * 1000)


def c1000(n: float) -> int:
    return int(math.ceil(round(n) / 1000) * 1000)


def auto_design(m2: float) -> str:
    return "S" if m2 < 30 else "M" if m2 < 200 else "L" if m2 < 1000 else "XL"


class PriceIn(BaseModel):
    service: str = "mural"            # mural | print | fix | bulk
    area: float = 0
    level: str = "medium"             # роспись: easy|medium|hard|author; фикс: lite|hard|excl
    design: str | None = None         # XS|S|M|L|XL — пусто: по площади
    extras: list[str] = []            # urgent, height, night, lacquer
    outdoor: bool = False             # улица — только для нормы
    place: str = "base"               # base | near | far
    cash: float = 0                   # скидка за наличные, %
    qty: int = 1                      # фикс-прайс: количество работ
    design_urgent: bool = False
    design_concept: bool = False
    design_extra: int = 0


def compute(inp: PriceIn, v: dict) -> dict:
    """Расчёт без записи. Возвращает строки чека, итог, оплаты, предупреждения, фразу клиенту и норму (срок, состав)."""
    g = lambda k, d: float(v.get(k) if v.get(k) not in (None, "") else d)  # noqa: E731
    vat = g("vat", 16) / 100
    lines, flags = [], []
    t, m2 = inp.service, float(inp.area or 0)
    if t not in SERVICES:
        raise HTTPException(400, "неизвестная услуга")
    base, label, design, dprice = 0.0, "", None, 0
    if t == "mural":
        lk = inp.level if inp.level in LEVEL_DEF else "medium"
        a, b, e = (g(f"mural.{lk}.a", LEVEL_DEF[lk][0]), g(f"mural.{lk}.b", LEVEL_DEF[lk][1]), g(f"mural.{lk}.e", LEVEL_DEF[lk][2]))
        s0, rnd = g("mural.start", 30), g("mural.round", 1000) or 1000
        rate = a if m2 <= s0 else b if m2 >= e else a - (a - b) * (m2 - s0) / (e - s0)
        base = round(m2 * rate / rnd) * rnd
        label = f"Роспись «{LEVEL_KEY[lk]}», {m2:g} м²"
        lines.append(["ln", f"{m2:g} м² × {_fmt(rate)} (плавная ставка)", base])
        if lk == "author":
            flags.append(["head", "Авторский уровень — уникальные работы. Уровень согласовать с HEAD."])
        if 0 < m2 < 10:
            flags.append(["", "Меньше 10 м² — действует минимальный заказ."])
        if m2 >= 1000:
            flags.append(["head", "Свыше 1000 м² — цену согласовать с HEAD до отправки клиенту."])
        design = inp.design or auto_design(m2)
    elif t == "print":
        pts = [(g(f"print.calc.p{i}.m2", PRINT_DEF[i - 1][0]), g(f"print.calc.p{i}.rate", PRINT_DEF[i - 1][1])) for i in range(1, 6)]
        if m2 <= pts[0][0]:
            rate = pts[0][1]
        elif m2 >= pts[-1][0]:
            rate = pts[-1][1]
        else:
            rate = pts[-1][1]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if m2 <= x1:
                    rate = y0 + (y1 - y0) * (m2 - x0) / (x1 - x0)
                    break
        base = round(m2 * rate / 1000) * 1000
        label = f"Настенная печать, {m2:g} м²"
        lines.append(["ln", f"{m2:g} м² × {_fmt(rate)} (плавная ставка печати)", base])
        design = inp.design or auto_design(m2)
    elif t == "fix":
        lk = inp.level if inp.level in FIX_DEF else "lite"
        one = g(f"fix.{lk}", FIX_DEF[lk][1])
        qty = max(1, int(inp.qty or 1))
        base = one * qty
        label = f"Фикс-прайс «{FIX_DEF[lk][0]}» × {qty}"
        lines.append(["ln", f"{qty} × {_fmt(one)}", base])
        flags.append(["head", "Акция только в Астане и Шымкенте. Другой город — считаем по основному прайсу."])
    else:  # bulk
        rate, frm, mach = g("paint.rate_from", 5000), g("paint.min_m2", 200), g("paint.machine_from", 5000)
        base = rate * m2
        label = f"Покраска, {m2:g} м²"
        lines.append(["ln", f"{m2:g} м² × от {_fmt(rate)}", base])
        if m2 < frm:
            flags.append(["", f"Покраску берём от {frm:g} м²."])
        if m2 >= mach:
            flags.append(["info", f"От {mach:g} м² — работа аппаратами."])
        flags.append(["head", "Это цена «от». Итог подтверждает HEAD после замера."])
    total = base
    place = "base" if t == "fix" else (inp.place if inp.place in PLACES else "base")
    on = [(k, name) for k, name, key in EXTRAS if k in inp.extras] if t in ("mural", "print") else []
    if t in ("mural", "print") and "lacquer" not in inp.extras:
        flags.append(["info", "Предложите защитный лак (+10%): защищает от влаги, УФ и истирания. Скрипт С26."])
    if on:
        pc = sum(g(key, 10) for k, _, key in EXTRAS if k in inp.extras) / 100
        add = base * pc
        total += add
        lines.append(["ln add", f"Надбавки: {', '.join(n.lower() for _, n in on)} (+{round(pc * 100)}%)", add])
    if place == "near":
        pc, mn = g("travel.near.pct", 15) / 100, g("travel.near.min", 350000)
        add = total * pc
        total += add
        lines.append(["ln add", f"Выезд 150–200 км (+{round(pc * 100)}%)", add])
        if total < mn:
            lines.append(["ln add", "До минимума выезда", mn - total])
            total = mn
            flags.append(["", f"Выезд 150–200 км — от {_fmt(mn)}. Поднято до минимума."])
    if place == "far":
        if t != "fix" and m2 < g("travel.min_m2", 70):
            flags.append(["head", f"Другой город: работаем от {g('travel.min_m2', 70):g} м². Согласовать с HEAD."])
        if total < g("travel.min_budget", 1000000):
            flags.append(["head", f"Другой город: бюджет от {_fmt(g('travel.min_budget', 1000000))}. Согласовать с HEAD."])
    cash = min(max(0.0, float(inp.cash or 0)), g("cash_discount.max", 15))
    if cash > 0:
        d = total * cash / 100
        total -= d
        lines.append(["ln minus", f"Скидка за наличные {cash:g}%", -d])
    mn = g("min_order", 120000)
    if place != "far" and 0 < total < mn:
        lines.append(["ln add", "До минимального заказа", mn - total])
        total = mn
        flags.append(["", f"Минимальный заказ в Астане и Шымкенте — {_fmt(mn)}."])
    total = r1000(total)
    des = ""
    if design:
        dk = design.lower()
        if design != "XS" and auto_design(m2) != design:
            flags.append(["", f"По площади {m2:g} м² категория дизайна — {auto_design(m2)}. Другую ставим только по решению HEAD."])
        if dk in DESIGN_DEF:
            pct, mn_d = g(f"design.{dk}.pct", DESIGN_DEF[dk][0]) / 100, g(f"design.{dk}.min", DESIGN_DEF[dk][1])
            dprice = c1000(max(pct * base, mn_d))
            how = f"{round(pct * 100)}% от сметы {_fmt(base)}" if pct * base >= mn_d else f"минимум категории {design}"
            credit = int(g("design.m.credit_days", 30))
            if design == "M":
                lines.append(["ln sub", f"Дизайн M ({how}), засчитывается в роспись", dprice])
                des = f"Дизайн (категория M): {_fmt(dprice)}, 100% до начала дизайна. Сумма засчитывается в стоимость росписи, если договор подписан в течение {credit} дней."
            else:
                lines.append(["ln sub", f"Дизайн {design} ({how}), отдельно, 100% вперёд", dprice])
                des = f"Дизайн (категория {design}): {_fmt(dprice)}, 100% предоплата, оплачивается отдельно от работ."
            b0 = dprice
            if inp.design_urgent:
                x = c1000(b0 * g("design.urgent", 30) / 100)
                dprice += x
                lines.append(["ln add", "Срочный дизайн +30%", x])
            if inp.design_concept:
                x = c1000(b0 * g("design.new_concept", 50) / 100)
                dprice += x
                lines.append(["ln add", "Новая концепция вместо утверждённой +50%", x])
            if inp.design_extra > 0:
                one = c1000(b0 * g("design.revision", 5) / 100)
                x = one * inp.design_extra
                dprice += x
                lines.append(["ln add", f"Доп. правки: {inp.design_extra} × {_fmt(one)}", x])
        else:
            lines.append(["ln sub", f"Дизайн {design}", "входит"])
            des = f"Эскиз (категория {design}) входит в стоимость."
    no_vat = t == "fix"
    flags.append(["head", "Фикс-прайс — акция без НДС. Нужен счёт с НДС — сумма выше на 16%."] if no_vat
                 else ["info", "Цена без НДС для клиента — только по решению HEAD."])
    pre_pct = g("prepay.work", 50)
    pre = r1000(total * pre_pct / 100)
    pay = {"prepay_pct": pre_pct, "prepay": pre, "rest": total - pre, "design": dprice,
           "vat": round(total * (1 + vat)) if no_vat else round(total * vat / (1 + vat)), "vat_included": not no_vat}
    client = (f"{SERVICES[t]}: {label.split(', ', 1)[-1] if ', ' in label else label}.\n"
              f"Стоимость: {_fmt(total)} {'по акции, без НДС' if no_vat else 'с НДС'}.\n" + (des + "\n" if des else "")
              + f"Оплата: {pre_pct:g}% предоплата, {100 - pre_pct:g}% после завершения работ.\n"
              "Договор и закрывающие документы, фиксированная цена, гарантия от 6 месяцев.\n"
              "Команда художников ARTGAME, 10+ лет, 210+ проектов в год.")
    # лестница цены (скрипт С6/С7): ориентир → вилка → точная сумма в КП
    lo, hi = r1000(total * 0.9), r1000(total * 1.1)
    ladder = f"Ориентир по вашим размерам — около {_fmt(total)}. Вилка {_fmt(lo)}–{_fmt(hi)} в зависимости от сложности эскиза. Точную сумму зафиксирую в КП."
    out = {"service": t, "label": label, "lines": [[c, s, (round(x) if isinstance(x, (int, float)) else x)] for c, s, x in lines],
           "total": total, "base": round(base), "design": design, "dprice": dprice, "no_vat": no_vat, "pay": pay, "flags": flags,
           "client_text": client, "ladder": ladder, "rate": round(total / m2) if m2 else 0}
    if t in ("mural", "print") and m2 > 0:
        out["norm"] = bx.resources(m2, inp.level if t == "mural" else "medium", t, "height" in inp.extras, inp.outdoor, v=v)
    else:
        out["norm"] = {}
    return out


@router.post("/bx/deals/{deal_id}/price")
def api_price(deal_id: int, body: PriceIn, p: dict = Depends(active)):
    bx._deal(p, deal_id)
    return compute(body, bx._vals())


@router.post("/bx/deals/{deal_id}/price/save")
def api_price_save(deal_id: int, body: PriceIn, p: dict = Depends(active)):
    """«Записать в сделку»: сумма, площадь, сложность, смены, люди, срок → Битрикс; расчёт целиком → deal_calc для КП и договора."""
    r = compute(body, bx._vals())
    if not r["total"]:
        raise HTTPException(400, "нечего записывать")
    fields = {"OPPORTUNITY": int(r["total"])}
    parts = [f"{SERVICES[body.service]} — {_fmt(r['total'])}" + (" без НДС" if r["no_vat"] else " с НДС")]
    if body.area and body.service in ("mural", "print", "bulk"):
        fields[bx.AREA] = body.area
        parts.append(f"{body.area:g} м²")
    if r["norm"]:
        nf, _ = bxw.norm_fields(body.area, body.level if body.service == "mural" else "medium", body.service,
                                "height" in body.extras, body.outdoor)
        fields.update(nf)
        n = r["norm"]
        parts.append(f"по норме {n['shifts']:g} смен, {n['crew']} чел., {n['client']} раб. дн. клиенту")
    if r["dprice"]:
        parts.append(f"дизайн {r['design']} {_fmt(r['dprice'])}")
    out = bxw.write(p, deal_id, "расчёт цены и срока", fields, "расчёт: " + ", ".join(parts))
    if out["bx"] == "error":
        raise HTTPException(502, out["error"])
    data = {"in": body.model_dump(), "out": r, "by": p["full_name"], "at": datetime.now(timezone.utc).isoformat()}
    with db.pool.connection() as conn:
        conn.execute("""INSERT INTO deal_calc (deal_id, data, person_id) VALUES (%s, %s, %s)
                        ON CONFLICT (deal_id) DO UPDATE SET data=EXCLUDED.data, person_id=EXCLUDED.person_id, updated_at=now()""",
                     (deal_id, Jsonb(data), p["id"]))
    out["calc"] = r
    out["norm_fields"] = bx.F_SHIFTS in fields
    return out


def saved(deal_id: int) -> dict | None:
    with db.pool.connection() as conn:
        row = conn.execute("SELECT data, updated_at FROM deal_calc WHERE deal_id=%s", (deal_id,)).fetchone()
    return {**row["data"], "updated_at": row["updated_at"].isoformat()} if row else None


@router.get("/bx/deals/{deal_id}/calc")
def api_calc_get(deal_id: int, p: dict = Depends(active)):
    bx._deal(p, deal_id)
    c = saved(deal_id)
    return {**c, "kp": kp_item(c)} if c else {}


def kp_item(c: dict) -> dict:
    """Позиция КП из сохранённого расчёта — в формате генератора КП рабочего места (KPGEN.add)."""
    i, o = c["in"], c["out"]
    t, m2 = i["service"], float(i.get("area") or 0)
    sub = {"mural": f"уровень «{LEVEL_KEY.get(i.get('level'), 'Средний')}», по утверждённому эскизу", "print": "по утверждённому эскизу",
           "bulk": "цена «от», итог после замера"}.get(t, o["label"])
    if o.get("dprice") and o.get("design") == "M":
        sub += f"; дизайн M {_fmt(o['dprice'])} засчитывается в работы при договоре в течение 30 дней"
    elif o.get("dprice"):
        sub += f"; дизайн {o['design']} {_fmt(o['dprice'])} оплачивается отдельно"
    if t == "fix":
        sub += ", акция без НДС"
    qty = m2 if m2 > 0 else 1
    return {"name": KP_NAME.get(t, SERVICES[t]), "sub": sub, "qty": f"{qty:g}", "price": f"{o['total'] / qty:.2f}".rstrip("0").rstrip("."),
            "service": KP_NAME.get(t, SERVICES[t]), "vat": not o["no_vat"]}
