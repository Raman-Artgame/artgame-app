"""Статистика рекламы и подсказки таргетологу «антислив» (HEAD 24.11).

Таблица кампаний и объявлений — из ночного сбора Meta (meta.py). «Обращения» здесь — то, что считает сама Meta:
начатые переписки и лиды с форм. Заявки и продажи по площадке — из Битрикса (ads.bx_by_channel).
Подсказки проверяются после каждого сбора. Плановую цену заявки и пороги задаёт HEAD в листе «Значения»;
в коде порогов нет: нет ключа — правило молчит, а экран говорит, какого значения не хватает.
"""
import csv
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import ads, constants, db, meta, notify
from .work import active

router = APIRouter(prefix="/api")
KEYS = {"mkt.cpl_plan": "плановая цена заявки (в валюте рекламного кабинета)", "mkt.nolead_x": "во сколько цен заявки объявление может потратить без обращений",
        "mkt.cpl_over_pct": "на сколько % цена заявки может быть выше плановой", "mkt.freq_max": "предельная частота показа за 7 дней",
        "mkt.ctr_min_pct": "минимальный CTR, %"}
MIN_IMPR = 1000         # меньше показов — про CTR судить рано (это не порог HEAD, а здравый минимум выборки)
ADVICE = {"nolead": "Остановить объявление или поменять креатив.", "cpl3": "Пересобрать аудиторию или креатив.",
          "freq": "Аудитория выгорела: нужен новый креатив или новая аудитория.", "ctr": "Креатив не цепляет: поменять первый кадр и текст.",
          "nosale": "Заявки нецелевые: проверить аудиторию и оффер, спросить МОП, кто пишет."}
RULE_RU = {"nolead": "Тратит без обращений", "cpl3": "Дорогая заявка", "freq": "Высокая частота", "ctr": "Низкий CTR", "nosale": "Заявки без продаж"}


def _today() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=5)).date()


def _tg(n, cur: str | None = "KZT") -> str:
    """Деньги в валюте кабинета: HEAD 25.11 — рекламу можно оставить в долларах, без пересчёта."""
    if cur and cur != "KZT":
        return f"{n:,.2f}".replace(",", " ") + (" $" if cur == "USD" else f" {cur}")
    return f"{round(n):,}".replace(",", " ") + " ₸"


def _ad_rows(conn, t0: date, t1: date) -> list[dict]:
    return conn.execute("""SELECT d.ad_id, max(d.ad_name) AS ad_name, max(d.adset_name) AS adset_name, max(d.campaign_id) AS campaign_id,
                                  max(d.campaign_name) AS campaign_name, sum(d.spend)::float AS spend, sum(d.impressions)::bigint AS impressions,
                                  sum(d.clicks)::bigint AS clicks, sum(d.messages)::int AS messages, sum(d.leads)::int AS leads,
                                  max(f.frequency)::float AS frequency, max(d.currency) AS currency
                           FROM mkt_meta_ad_day d LEFT JOIN mkt_meta_ad7 f ON f.ad_id=d.ad_id
                           WHERE d.day >= %s AND d.day <= %s GROUP BY d.ad_id ORDER BY sum(d.spend) DESC""", (t0, t1)).fetchall()


def _calc(x: dict) -> dict:
    res = (x["messages"] or 0) + (x["leads"] or 0)
    return {**x, "results": res, "ctr": round(x["clicks"] / x["impressions"] * 100, 2) if x["impressions"] else None,
            "cpc": round(x["spend"] / x["clicks"], 2) if x["clicks"] else None, "cpr": round(x["spend"] / res, 2) if res else None}


def find(conn, today: date) -> tuple[list[dict], list[str]]:
    """Что сработало сейчас. Возвращает подсказки и список ключей «Значений», которых не хватает."""
    k = constants.latest(conn)
    v = {key: k.get(key) for key in KEYS}
    missing = [key for key, val in v.items() if not isinstance(val, (int, float)) or val <= 0]
    ok = lambda *keys: not any(x in missing for x in keys)  # noqa: E731
    out = []
    week = [_calc(x) for x in _ad_rows(conn, today - timedelta(days=7), today - timedelta(days=1))]
    for x in week:
        name = x["ad_name"] or x["ad_id"]
        where = f"Кампания «{x['campaign_name'] or '—'}», объявление «{name}»"
        if ok("mkt.cpl_plan", "mkt.nolead_x") and not x["results"] and x["spend"] > v["mkt.cpl_plan"] * v["mkt.nolead_x"]:
            out.append({"rule": "nolead", "obj_id": x["ad_id"], "title": name,
                        "text": f"{where}: за 7 дней потрачено {_tg(x['spend'], x['currency'])} и ни одного обращения. Плановая цена заявки {_tg(v['mkt.cpl_plan'], x['currency'])}."})
        if ok("mkt.freq_max") and (x["frequency"] or 0) > v["mkt.freq_max"]:
            out.append({"rule": "freq", "obj_id": x["ad_id"], "title": name,
                        "text": f"{where}: частота показа {x['frequency']:.1f} за 7 дней, порог {v['mkt.freq_max']}."})
        if ok("mkt.ctr_min_pct") and x["impressions"] >= MIN_IMPR and x["ctr"] is not None and x["ctr"] < v["mkt.ctr_min_pct"]:
            out.append({"rule": "ctr", "obj_id": x["ad_id"], "title": name,
                        "text": f"{where}: CTR {x['ctr']}% за 7 дней при {x['impressions']} показах, порог {v['mkt.ctr_min_pct']}%."})
    if ok("mkt.cpl_plan", "mkt.cpl_over_pct"):
        d3 = [_calc(x) for x in _ad_rows(conn, today - timedelta(days=3), today - timedelta(days=1))]
        spend, res = sum(x["spend"] for x in d3), sum(x["results"] for x in d3)
        limit = v["mkt.cpl_plan"] * (1 + v["mkt.cpl_over_pct"] / 100)
        if spend > limit and (not res or spend / res > limit):
            cur = d3[0]["currency"] if d3 else "KZT"
            fact = f"цена обращения {_tg(spend / res, cur)}" if res else "обращений нет"
            out.append({"rule": "cpl3", "obj_id": "meta", "title": "Таргет Instagram",
                        "text": f"За 3 дня потрачено {_tg(spend, cur)}, {fact}. Плановая цена заявки {_tg(v['mkt.cpl_plan'], cur)}, допуск {v['mkt.cpl_over_pct']}%."})
    return out, missing


def find_nosale(conn, today: date) -> list[dict]:
    """Заявки с таргета есть, а продаж за 30 дней нет — по Битриксу. Битрикс не ответил — правило молчит."""
    ch = conn.execute("SELECT id FROM mkt_channels WHERE title=%s", (meta.CHANNEL,)).fetchone()
    if not ch:
        return []
    by, _, err = ads.bx_by_channel(today - timedelta(days=30), today + timedelta(days=1))
    b = by.get(ch["id"])
    if err or not b or not b["leads"] or b["won"]:
        return []
    return [{"rule": "nosale", "obj_id": "meta", "title": "Таргет Instagram",
             "text": f"За 30 дней с таргета пришло заявок: {b['leads']}, сделок: {b['deals']}, продаж нет."}]


def run(today: date | None = None) -> dict:
    """После сбора: новые подсказки открыть, прошедшие сами — снять, о новых написать таргетологу и HEAD."""
    today = today or _today()
    with db.pool.connection() as conn:
        found, missing = find(conn, today)
    with db.pool.connection() as conn:
        found += find_nosale(conn, today)
    new = []
    with db.pool.connection() as conn, conn.transaction():
        keep = set()
        for h in found:
            keep.add((h["rule"], h["obj_id"]))
            if conn.execute("""SELECT 1 FROM mkt_ad_hints WHERE rule=%s AND obj_id=%s AND status='done' AND closed_at > now() - interval '3 days'""",
                            (h["rule"], h["obj_id"])).fetchone():
                continue        # только что отметили «сделано» — даём изменениям три дня
            r = conn.execute("""INSERT INTO mkt_ad_hints (rule, obj_id, title, text, advice) VALUES (%s,%s,%s,%s,%s)
                                ON CONFLICT (rule, obj_id) WHERE status='open' DO UPDATE SET text=EXCLUDED.text, title=EXCLUDED.title, updated_at=now()
                                RETURNING (xmax = 0) AS fresh""", (h["rule"], h["obj_id"], h["title"], h["text"], ADVICE[h["rule"]])).fetchone()
            if r["fresh"]:
                new.append(h)
        for r in conn.execute("SELECT id, rule, obj_id FROM mkt_ad_hints WHERE status='open'").fetchall():
            if (r["rule"], r["obj_id"]) not in keep:
                conn.execute("UPDATE mkt_ad_hints SET status='gone', closed_at=now() WHERE id=%s", (r["id"],))
        who = conn.execute("""SELECT tg_id FROM people WHERE status='active' AND tg_id IS NOT NULL
                              AND (role_code='head' OR (role_code='marketer' AND mkt_job='target'))""").fetchall() if new else []
    if new:
        text = "Реклама: новые подсказки (" + str(len(new)) + ")\n" + "\n".join(f"• {RULE_RU[h['rule']]}: {h['title']}" for h in new[:8]) + \
               "\nОткрой «Маркетинг → Реклама»."
        for w in who:
            try:
                notify.SEND(w["tg_id"], text)
            except Exception:  # noqa: BLE001
                pass
    return {"open": len(found), "new": len(new), "missing": missing}


def _period(period: str, shift: int, today: date) -> tuple[date, date]:
    if period == "month":
        y, m = today.year, today.month + shift
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        return date(y, m, 1), date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)
    if period == "week":
        mon = today - timedelta(days=today.weekday()) + timedelta(weeks=shift)
        return mon, mon + timedelta(days=6)
    raise HTTPException(400, "period: week | month")


@router.get("/mkt/adstats")
def adstats(days: int = 7, p: dict = Depends(active)):
    """Кампании и объявления Meta за последние N дней (включая сегодня) и открытые подсказки."""
    ads._see(p)
    if days not in (1, 7, 30):
        raise HTTPException(400, "days: 1 | 7 | 30")
    today = _today()
    with db.pool.connection() as conn:
        rows = [_calc(x) for x in _ad_rows(conn, today - timedelta(days=days - 1), today)]
        hints = conn.execute("SELECT id, rule, obj_id, title, text, advice, created_at FROM mkt_ad_hints WHERE status='open' ORDER BY created_at DESC").fetchall()
        k = constants.latest(conn)
    camps: dict = {}
    for x in rows:
        c = camps.setdefault(x["campaign_id"], {"campaign_id": x["campaign_id"], "name": x["campaign_name"] or "Без названия", "spend": 0.0,
                                                "impressions": 0, "clicks": 0, "messages": 0, "leads": 0, "ads": []})
        for f in ("spend", "impressions", "clicks", "messages", "leads"):
            c[f] += x[f] or 0
        c["ads"].append({f: x[f] for f in ("ad_id", "ad_name", "adset_name", "spend", "impressions", "clicks", "results", "ctr", "cpc", "cpr", "frequency")})
    flagged = {h["obj_id"] for h in hints}
    for c in camps.values():
        c.update({f: _calc(c)[f] for f in ("results", "ctr", "cpc", "cpr")})
        for a in c["ads"]:
            a["hint"] = a["ad_id"] in flagged
    return {"days": days, "currency": rows[0]["currency"] if rows else None, "campaigns": sorted(camps.values(), key=lambda c: -c["spend"]),
            "hints": [{**h, "rule_ru": RULE_RU.get(h["rule"], h["rule"]), "created_at": h["created_at"].isoformat()} for h in hints],
            "missing": [{"key": key, "what": KEYS[key]} for key in KEYS if not isinstance(k.get(key), (int, float)) or k.get(key) <= 0],
            "plan_cpl": k.get("mkt.cpl_plan") if isinstance(k.get("mkt.cpl_plan"), (int, float)) else None,
            "can_edit": p["role_code"] == "head" or p.get("mkt_job") in ads.EDIT_JOBS}


class DoneIn(BaseModel):
    note: str | None = Field(default=None, max_length=300)


@router.post("/mkt/adhints/{hint_id}/done")
def hint_done(hint_id: int, b: DoneIn, p: dict = Depends(active)):
    ads._edit(p)
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("UPDATE mkt_ad_hints SET status='done', closed_by=%s, closed_at=now(), note=%s WHERE id=%s AND status='open' RETURNING rule, title",
                         (p["id"], b.note, hint_id)).fetchone()
        if not r:
            raise HTTPException(404, "подсказка уже закрыта")
        db.audit(conn, p["id"], "mkt_hint_done", "mkt_ad_hints", hint_id, {"rule": r["rule"], "title": r["title"], "note": b.note})
    return {"ok": True}


def report(period: str, shift: int = 0, fresh: bool = False, today: date | None = None) -> dict:
    """Отчёт за неделю или месяц: потрачено → заявок → сделок → продаж → цена заявки, по площадкам."""
    t0, t1 = _period(period, shift, today or _today())
    by, n_leads, err = ads.bx_by_channel(t0, t1 + timedelta(days=1), fresh)
    days = (t1 - t0).days + 1
    with db.pool.connection() as conn:
        chans = ads.channels(conn, only_active=False)
        m = conn.execute("""SELECT COALESCE(sum(spend),0)::float AS spend, COALESCE(sum(impressions),0)::bigint AS impressions,
                                   COALESCE(sum(clicks),0)::bigint AS clicks, count(*) AS n FROM mkt_meta_day
                            WHERE currency='KZT' AND day >= %s AND day <= %s""", (t0, t1)).fetchone()
        res = conn.execute("SELECT COALESCE(sum(messages + leads),0)::int AS n FROM mkt_meta_ad_day WHERE day >= %s AND day <= %s",
                           (t0, t1)).fetchone()["n"]
        usd = conn.execute("""SELECT COALESCE(sum(spend),0)::float AS spend, COALESCE(sum(impressions),0)::bigint AS impressions,
                                     COALESCE(sum(clicks),0)::bigint AS clicks FROM mkt_meta_day
                              WHERE currency='USD' AND day >= %s AND day <= %s""", (t0, t1)).fetchone()
        # расход, внесённый раз в месяц: на неделю берём долю по дням и помечаем «≈»
        months = conn.execute("""SELECT s.channel_id, s.ym, s.amount::float AS amount, s.source FROM mkt_spend s
                                 WHERE s.ym IN (%s, %s)""", (t0.strftime("%Y-%m"), t1.strftime("%Y-%m"))).fetchall()
        ig = conn.execute("""SELECT sum(reach)::int AS reach, sum(views)::int AS views, sum(profile_views)::int AS profile_views FROM mkt_ig_day
                             WHERE day >= %s AND day <= %s""", (t0, t1)).fetchone()
        f1 = conn.execute("SELECT followers FROM mkt_ig_day WHERE followers IS NOT NULL AND day <= %s ORDER BY day DESC LIMIT 1", (t1,)).fetchone()
        f0 = conn.execute("SELECT followers FROM mkt_ig_day WHERE followers IS NOT NULL AND day < %s ORDER BY day DESC LIMIT 1", (t0,)).fetchone()
        mch = conn.execute("SELECT id FROM mkt_channels WHERE title=%s", (meta.CHANNEL,)).fetchone()

    def manual(cid: int) -> float:
        total = 0.0
        for r in months:
            if r["channel_id"] != cid:
                continue
            y, mo = map(int, r["ym"].split("-"))
            first, last = date(y, mo, 1), date(y + mo // 12, mo % 12 + 1, 1) - timedelta(days=1)
            over = (min(t1, last) - max(t0, first)).days + 1
            if over > 0:
                total += r["amount"] * over / last.day
        return total

    rows = []
    for c in chans:
        b = by.get(c["id"], {"leads": 0, "deals": 0, "won": 0, "won_sum": 0.0})
        from_meta = bool(mch and c["id"] == mch["id"] and m["n"] and not any(r["channel_id"] == c["id"] and r["source"] == "manual" for r in months))
        spend = m["spend"] if from_meta else manual(c["id"])
        if not spend and not b["leads"]:
            continue
        rows.append({"id": c["id"], "title": c["title"], "paid": c["paid"], **b, "spend": round(spend), "approx": bool(spend) and not from_meta and period == "week",
                     "cpl": round(spend / b["leads"]) if spend and b["leads"] else None, "cps": round(spend / b["won"]) if spend and b["won"] else None})
    un = by.get(None, {"leads": 0, "deals": 0, "won": 0, "won_sum": 0.0})
    tot = {"spend": sum(r["spend"] for r in rows), "leads": n_leads, "deals": sum(b["deals"] for b in by.values()),
           "won": sum(b["won"] for b in by.values()), "won_sum": sum(b["won_sum"] for b in by.values())}
    tot["cpl"] = round(tot["spend"] / tot["leads"]) if tot["spend"] and tot["leads"] else None
    return {"period": period, "shift": shift, "from": str(t0), "to": str(t1), "days": days, "channels": rows, "unknown": un, "total": tot, "err": err,
            "meta": {"spend": m["spend"], "spend_usd": usd["spend"], "impressions": m["impressions"] + usd["impressions"],
                     "clicks": m["clicks"] + usd["clicks"], "results": res},
            "ig": {"reach": ig["reach"], "views": ig["views"], "profile_views": ig["profile_views"],
                   "followers": f1["followers"] if f1 else None, "delta": (f1["followers"] - f0["followers"]) if f1 and f0 else None}}


@router.get("/mkt/report")
def report_get(period: str = "week", shift: int = 0, fresh: int = 0, p: dict = Depends(active)):
    ads._see(p)
    if not -60 <= shift <= 0:
        raise HTTPException(400, "shift")
    return report(period, shift, bool(fresh))


def report_csv(r: dict) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow([f"Реклама: {r['from']} — {r['to']}"])
    w.writerow(["Площадка", "Потрачено, ₸", "Заявок", "Сделок", "Продаж", "Сумма продаж, ₸", "Цена заявки, ₸", "Цена продажи, ₸"])
    for c in r["channels"]:
        w.writerow([c["title"], ("≈" if c["approx"] else "") + str(c["spend"]), c["leads"], c["deals"], c["won"], round(c["won_sum"]), c["cpl"] or "", c["cps"] or ""])
    w.writerow(["Без площадки", "", r["unknown"]["leads"], r["unknown"]["deals"], r["unknown"]["won"], round(r["unknown"]["won_sum"]), "", ""])
    t = r["total"]
    w.writerow(["Итого", t["spend"], t["leads"], t["deals"], t["won"], round(t["won_sum"]), t["cpl"] or "", ""])
    w.writerow([])
    if r["meta"].get("spend_usd"):
        w.writerow(["Meta: расход кабинета, $", r["meta"]["spend_usd"]])
    w.writerow(["Meta: показы", r["meta"]["impressions"], "клики", r["meta"]["clicks"], "обращения", r["meta"]["results"]])
    w.writerow(["Instagram: охват", r["ig"]["reach"] or "", "просмотры", r["ig"]["views"] or "", "подписчики", r["ig"]["followers"] or "", "прирост", r["ig"]["delta"] if r["ig"]["delta"] is not None else ""])
    return ("﻿" + out.getvalue()).encode()


REPORTS_FOLDER = "1i1ckGREFDbUFxU4WLrs5C3a4zGSeRpqj"     # Диск: 06 МАРКЕТИНГ / 04 ОТЧЁТЫ


def export_week(today: date | None = None) -> str:
    """По понедельникам: отчёт за прошлую неделю файлом в «04 ОТЧЁТЫ / Неделя». Возвращает имя файла."""
    from . import drive
    r = report("week", -1, fresh=True, today=today)
    d = drive.Drive()
    name = f"Reklama_{r['from']}_{r['to']}.csv"
    folder = d.child(REPORTS_FOLDER, "Неделя")
    if not any(f["name"] == name for f in d.ls(folder)):
        d.upload(folder, name, report_csv(r), "text/csv")
    return name
