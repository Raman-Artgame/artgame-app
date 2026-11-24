"""Загрузчик Meta (HEAD 24.11): расход рекламного кабинета и статистика Instagram напрямую из Meta, без посредников.

Только чтение. Токен системного пользователя лежит на сервере в переменной META_TOKEN (в репозитории и в базе его нет).
Раз в ночь (таймер artgame-meta@<env>) и по кнопке «Обновить сейчас»:
  1) расход, показы, охват и клики рекламных кабинетов по дням → mkt_meta_day; сумма за месяц → mkt_spend площадки
     «Таргет Instagram» (source='meta'). Расход, внесённый руками, не затираем.
  2) Instagram: подписчики, охват и просмотры по дням → mkt_ig_day; публикации и рилс за 30 дней → mkt_ig_media.
Каждая часть собирается отдельно: не ответила одна — остальные сохраняются, ошибка видна в «Рекламе».
"""
import json
import os
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from . import ads, db
from .work import active

router = APIRouter(prefix="/api")
GRAPH = "https://graph.facebook.com"
CHANNEL = "Таргет Instagram"
DAYS_BACK = 35          # ночью пересобираем месяц с запасом: Meta уточняет расход задним числом
IG_DAYS = 7
MEDIA_DAYS = 30


def token() -> str:
    return os.environ.get("META_TOKEN") or os.environ.get("ARTGAME_META_TOKEN") or ""


class MetaError(Exception):
    pass


def get(path: str, params: dict | None = None) -> dict:
    """Один запрос к Meta. Токен в журнал и в текст ошибки не попадает."""
    import httpx
    ver = os.environ.get("META_API_VERSION", "").strip("/")
    url = path if path.startswith("http") else f"{GRAPH}/{ver + '/' if ver else ''}{path.lstrip('/')}"
    q = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in (params or {}).items()}
    if "access_token=" not in url:
        q["access_token"] = token()
    try:
        r = httpx.get(url, params=q, timeout=40)
        d = r.json()
    except Exception as ex:  # noqa: BLE001 — сеть или не-JSON
        raise MetaError(f"Meta не ответила ({type(ex).__name__})") from None
    if r.status_code >= 400 or "error" in d:
        e = d.get("error") or {}
        raise MetaError(f"Meta: {e.get('message') or r.status_code} (код {e.get('code', '—')})")
    return d


def get_all(path: str, params: dict | None = None, limit: int = 20) -> list[dict]:
    out, d = [], get(path, params)
    while True:
        out += d.get("data") or []
        nxt = (d.get("paging") or {}).get("next")
        limit -= 1
        if not nxt or limit <= 0:
            return out
        d = get(nxt)


def _int(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


# ---------- реклама ----------
def ad_accounts() -> list[dict]:
    only = [a.strip() for a in os.environ.get("META_AD_ACCOUNTS", "").split(",") if a.strip()]
    if only:
        return [{"id": a if a.startswith("act_") else "act_" + a, "name": a, "currency": None} for a in only]
    return [{"id": a["id"], "name": a.get("name") or a["id"], "currency": a.get("currency")}
            for a in get_all("me/adaccounts", {"fields": "id,name,currency", "limit": 50})]


def sync_ads(conn, since: date, until: date) -> dict:
    accs = ad_accounts()
    days = 0
    for a in accs:
        rows = get_all(f"{a['id']}/insights", {"fields": "spend,impressions,reach,clicks,account_currency", "level": "account",
                                               "time_increment": 1, "limit": 100,
                                               "time_range": {"since": str(since), "until": str(until)}})
        for r in rows:
            cur = r.get("account_currency") or a["currency"]
            conn.execute("""INSERT INTO mkt_meta_day (account, day, spend, currency, impressions, reach, clicks) VALUES (%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (account, day) DO UPDATE SET spend=EXCLUDED.spend, currency=EXCLUDED.currency,
                            impressions=EXCLUDED.impressions, reach=EXCLUDED.reach, clicks=EXCLUDED.clicks, fetched_at=now()""",
                         (a["id"], r["date_start"], float(r.get("spend") or 0), cur, _int(r.get("impressions")), _int(r.get("reach")),
                          _int(r.get("clicks"))))
            days += 1
    months = push_spend(conn, since, until)
    ads_n, errs = 0, []
    for a in accs:      # по объявлениям — отдельно: не ответит, общий расход уже сохранён
        try:
            ads_n += sync_ad_level(conn, a, since, until)
        except MetaError as e:
            errs.append(f"объявления: {e}")
    return {"accounts": [a["name"] for a in accs], "days": days, "months": months, "ad_rows": ads_n, "errors": errs}


def _actions(r: dict) -> tuple[int, int]:
    """Из «действий» Meta: начатые переписки и лиды с форм. Одно и то же Meta отдаёт под разными именами — берём наибольшее."""
    msg = lead = 0
    for a in r.get("actions") or []:
        t, v = a.get("action_type") or "", _int(a.get("value"))
        if t.startswith("onsite_conversion.messaging_conversation_started"):
            msg = max(msg, v)
        elif t in ("lead", "onsite_conversion.lead_grouped", "leadgen_grouped"):
            lead = max(lead, v)
    return msg, lead


def sync_ad_level(conn, a: dict, since: date, until: date) -> int:
    rows = get_all(f"{a['id']}/insights", {"fields": "campaign_id,campaign_name,adset_name,ad_id,ad_name,spend,impressions,reach,clicks,actions,account_currency",
                                           "level": "ad", "time_increment": 1, "limit": 200,
                                           "time_range": {"since": str(since), "until": str(until)}}, limit=60)
    for r in rows:
        msg, lead = _actions(r)
        conn.execute("""INSERT INTO mkt_meta_ad_day (ad_id, day, account, ad_name, adset_name, campaign_id, campaign_name, spend, currency,
                                                     impressions, reach, clicks, messages, leads)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ad_id, day) DO UPDATE SET ad_name=EXCLUDED.ad_name, adset_name=EXCLUDED.adset_name, campaign_id=EXCLUDED.campaign_id,
                        campaign_name=EXCLUDED.campaign_name, spend=EXCLUDED.spend, currency=EXCLUDED.currency, impressions=EXCLUDED.impressions,
                        reach=EXCLUDED.reach, clicks=EXCLUDED.clicks, messages=EXCLUDED.messages, leads=EXCLUDED.leads, fetched_at=now()""",
                     (r["ad_id"], r["date_start"], a["id"], r.get("ad_name"), r.get("adset_name"), r.get("campaign_id"), r.get("campaign_name"),
                      float(r.get("spend") or 0), r.get("account_currency") or a["currency"], _int(r.get("impressions")), _int(r.get("reach")),
                      _int(r.get("clicks")), msg, lead))
    for r in get_all(f"{a['id']}/insights", {"fields": "ad_id,frequency", "level": "ad", "date_preset": "last_7d", "limit": 200}, limit=10):
        conn.execute("""INSERT INTO mkt_meta_ad7 (ad_id, frequency) VALUES (%s,%s)
                        ON CONFLICT (ad_id) DO UPDATE SET frequency=EXCLUDED.frequency, fetched_at=now()""", (r["ad_id"], float(r.get("frequency") or 0)))
    return len(rows)


def push_spend(conn, since: date, until: date) -> list[str]:
    """Сумма по дням за месяц → расход площадки «Таргет Instagram». Только тенге; ручной расход не трогаем."""
    ch = conn.execute("SELECT id FROM mkt_channels WHERE title=%s", (CHANNEL,)).fetchone()
    if not ch:
        return []
    done = []
    for r in conn.execute("""SELECT to_char(day, 'YYYY-MM') AS ym, sum(spend) AS amount, count(*) AS n FROM mkt_meta_day
                             WHERE currency='KZT' AND day >= date_trunc('month', %s::date) AND day <= %s GROUP BY 1""", (since, until)).fetchall():
        full = conn.execute("SELECT sum(spend) AS s FROM mkt_meta_day WHERE currency='KZT' AND to_char(day,'YYYY-MM')=%s", (r["ym"],)).fetchone()["s"]
        n = conn.execute("""INSERT INTO mkt_spend (channel_id, ym, amount, source, note) VALUES (%s,%s,%s,'meta','из Meta, само')
                            ON CONFLICT (channel_id, ym) DO UPDATE SET amount=EXCLUDED.amount, updated_at=now()
                            WHERE mkt_spend.source='meta'""", (ch["id"], r["ym"], full)).rowcount
        if n:
            done.append(r["ym"])
    return done


# ---------- Instagram ----------
def ig_account() -> dict | None:
    only = os.environ.get("META_IG_ID", "").strip()
    if only:
        return {"id": only}
    for pg in get_all("me/accounts", {"fields": "name,instagram_business_account{id,username}", "limit": 50}):
        if pg.get("instagram_business_account"):
            return pg["instagram_business_account"]
    return None


def _total(d: dict, name: str):
    for m in d.get("data") or []:
        if m.get("name") == name:
            if "total_value" in m:
                return _int(m["total_value"].get("value"))
            vals = m.get("values") or []
            return _int(vals[-1].get("value")) if vals else None
    return None


def sync_ig(conn, today: date) -> dict:
    ig = ig_account()
    if not ig:
        raise MetaError("Instagram не найден: у токена нет страницы со связанным профилем")
    errs = []
    prof = get(ig["id"], {"fields": "username,followers_count,media_count"})
    conn.execute("""INSERT INTO mkt_ig_day (day, followers) VALUES (%s,%s)
                    ON CONFLICT (day) DO UPDATE SET followers=EXCLUDED.followers, fetched_at=now()""", (today, prof.get("followers_count")))
    for i in range(1, IG_DAYS + 1):          # вчера и раньше: за закрытые дни цифры уже не меняются
        d = today - timedelta(days=i)
        since = int(datetime(d.year, d.month, d.day, tzinfo=timezone(timedelta(hours=5))).timestamp())
        vals = {}
        for col, metric in (("reach", "reach"), ("views", "views"), ("profile_views", "profile_views"), ("interactions", "total_interactions")):
            try:
                vals[col] = _total(get(f"{ig['id']}/insights", {"metric": metric, "period": "day", "metric_type": "total_value",
                                                                 "since": since, "until": since + 86400}), metric)
            except MetaError as e:
                if i == 1:
                    errs.append(f"{metric}: {e}")
        if any(v is not None for v in vals.values()):
            conn.execute("""INSERT INTO mkt_ig_day (day, reach, views, profile_views, interactions) VALUES (%s,%s,%s,%s,%s)
                            ON CONFLICT (day) DO UPDATE SET reach=COALESCE(EXCLUDED.reach, mkt_ig_day.reach), views=COALESCE(EXCLUDED.views, mkt_ig_day.views),
                            profile_views=COALESCE(EXCLUDED.profile_views, mkt_ig_day.profile_views),
                            interactions=COALESCE(EXCLUDED.interactions, mkt_ig_day.interactions), fetched_at=now()""",
                         (d, vals.get("reach"), vals.get("views"), vals.get("profile_views"), vals.get("interactions")))
    n = 0
    edge = datetime.now(timezone.utc) - timedelta(days=MEDIA_DAYS)
    for m in get_all(f"{ig['id']}/media", {"fields": "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count",
                                           "limit": 50}, limit=3):
        ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z") if m.get("timestamp") else None
        if ts and ts < edge:
            continue
        ins = {}
        try:
            ins = get(f"{m['id']}/insights", {"metric": "views,reach,saved,shares"})
        except MetaError as e:
            if not n:
                errs.append(f"публикации: {e}")
        conn.execute("""INSERT INTO mkt_ig_media (id, kind, media_type, permalink, caption, posted_at, views, reach, likes, comments, saved, shares)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (id) DO UPDATE SET views=COALESCE(EXCLUDED.views, mkt_ig_media.views), reach=COALESCE(EXCLUDED.reach, mkt_ig_media.reach),
                        likes=EXCLUDED.likes, comments=EXCLUDED.comments, saved=COALESCE(EXCLUDED.saved, mkt_ig_media.saved),
                        shares=COALESCE(EXCLUDED.shares, mkt_ig_media.shares), caption=EXCLUDED.caption, fetched_at=now()""",
                     (m["id"], m.get("media_product_type"), m.get("media_type"), m.get("permalink"), (m.get("caption") or "")[:300], ts,
                      _total(ins, "views"), _total(ins, "reach"), m.get("like_count"), m.get("comments_count"), _total(ins, "saved"),
                      _total(ins, "shares")))
        n += 1
    return {"username": prof.get("username"), "followers": prof.get("followers_count"), "media": n, "errors": errs}


# ---------- запуск ----------
def sync(today: date | None = None, by: int | None = None) -> dict:
    """Весь сбор. Возвращает итог и пишет его в mkt_settings('meta_last') — его показывает «Реклама»."""
    today = today or (datetime.now(timezone.utc) + timedelta(hours=5)).date()
    res = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": True, "errors": []}
    if not token():
        res.update(ok=False, errors=["На сервере нет токена Meta (META_TOKEN)"])
    else:
        for key, fn in (("ads", lambda c: sync_ads(c, today - timedelta(days=DAYS_BACK), today)), ("ig", lambda c: sync_ig(c, today))):
            try:
                with db.pool.connection() as conn, conn.transaction():
                    res[key] = fn(conn)
                    res["errors"] += res[key].pop("errors", [])
            except MetaError as e:
                res["ok"] = False
                res["errors"].append(str(e))
        try:
            from . import adrules
            res["hints"] = adrules.run(today)
        except Exception as e:  # noqa: BLE001 — подсказки не должны ронять сбор
            res["errors"].append(f"подсказки: {type(e).__name__}")
    with db.pool.connection() as conn, conn.transaction():
        conn.execute("INSERT INTO mkt_settings (key, value) VALUES ('meta_last', %s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                     (json.dumps(res, ensure_ascii=False),))
        db.audit(conn, by, "meta_sync", data={"ok": res["ok"], "errors": len(res["errors"])})
    return res


def summary(conn, ym: str) -> dict:
    last = conn.execute("SELECT value FROM mkt_settings WHERE key='meta_last'").fetchone()
    ad = conn.execute("""SELECT currency, sum(spend) AS spend, sum(impressions) AS impressions, sum(clicks) AS clicks, max(day) AS upto
                         FROM mkt_meta_day WHERE to_char(day,'YYYY-MM')=%s GROUP BY 1 ORDER BY 2 DESC""", (ym,)).fetchall()
    ch = conn.execute("""SELECT s.source, s.amount FROM mkt_spend s JOIN mkt_channels c ON c.id=s.channel_id
                         WHERE c.title=%s AND s.ym=%s""", (CHANNEL, ym)).fetchone()
    fol = conn.execute("SELECT day, followers FROM mkt_ig_day WHERE followers IS NOT NULL ORDER BY day DESC LIMIT 1").fetchone()
    was = conn.execute("SELECT followers FROM mkt_ig_day WHERE followers IS NOT NULL AND day <= %s ORDER BY day DESC LIMIT 1",
                       ((fol["day"] - timedelta(days=7)) if fol else None,)).fetchone() if fol else None
    wk = conn.execute("""SELECT sum(reach) AS reach, sum(views) AS views, sum(profile_views) AS profile_views, sum(interactions) AS interactions, count(*) AS days
                         FROM (SELECT * FROM mkt_ig_day WHERE reach IS NOT NULL OR views IS NOT NULL ORDER BY day DESC LIMIT 7) t""").fetchone()
    top = conn.execute("""SELECT id, kind, permalink, caption, posted_at, views, reach, likes, comments, saved, shares FROM mkt_ig_media
                          WHERE posted_at >= now() - interval '30 days' ORDER BY views DESC NULLS LAST, posted_at DESC LIMIT 5""").fetchall()
    return {"on": bool(token()), "last": json.loads(last["value"]) if last else None,
            "ads": [{**a, "spend": float(a["spend"]), "upto": str(a["upto"])} for a in ad],
            "manual": bool(ch and ch["source"] == "manual" and ad),     # за месяц стоит ручной расход — Meta его не заменила
            "ig": {"followers": fol["followers"] if fol else None, "delta7": (fol["followers"] - was["followers"]) if fol and was else None,
                   "week": {k: (int(wk[k]) if wk[k] is not None else None) for k in ("reach", "views", "profile_views", "interactions", "days")},
                   "top": [{**t, "posted_at": t["posted_at"].isoformat() if t["posted_at"] else None} for t in top]}}


@router.get("/mkt/meta")
def meta_get(ym: str | None = None, p: dict = Depends(active)):
    ads._see(p)
    ym = ads._month(ym)[0]
    with db.pool.connection() as conn:
        return {**summary(conn, ym), "can_edit": p["role_code"] == "head" or p.get("mkt_job") in ads.EDIT_JOBS}


@router.post("/mkt/meta/sync")
def meta_sync(p: dict = Depends(active)):
    """«Обновить сейчас»: тот же сбор, что ночью."""
    ads._edit(p)
    if not token():
        raise HTTPException(409, "На сервере нет токена Meta")
    return sync(by=p["id"])


@router.post("/mkt/meta/take")
def meta_take(ym: str, p: dict = Depends(active)):
    """За месяц стоял расход, внесённый руками — заменить его цифрой из Meta и дальше обновлять самому."""
    ads._edit(p)
    ym, t0, t1 = ads._month(ym)
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM mkt_meta_day WHERE currency='KZT' AND day >= %s AND day < %s LIMIT 1", (t0, t1)).fetchone():
            raise HTTPException(409, "за этот месяц из Meta ничего не собрано")
        conn.execute("""UPDATE mkt_spend s SET source='meta', note='из Meta, само', updated_by=%s FROM mkt_channels c
                        WHERE c.id=s.channel_id AND c.title=%s AND s.ym=%s""", (p["id"], CHANNEL, ym))
        push_spend(conn, t0, t1 - timedelta(days=1))
        db.audit(conn, p["id"], "meta_take", "mkt_spend", None, {"ym": ym})
    return {"ok": True}
