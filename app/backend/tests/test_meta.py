"""Загрузчик Meta: расход кабинета → «Таргет Instagram», статистика Instagram; ручной расход не затирается."""
from datetime import date

from artgame import db, meta

from conftest import hdr


def fake_meta(calls, broken=()):
    def get(path, params=None):
        calls.append(path)
        params = params or {}
        if any(b in path for b in broken):
            raise meta.MetaError("Meta: (#10) нет разрешения (код 10)")
        if path == "me/adaccounts":
            return {"data": [{"id": "act_1", "name": "Artgame.kz Ads", "currency": "KZT"}, {"id": "act_2", "name": "USD", "currency": "USD"}]}
        if path == "act_1/insights" and params.get("level") == "account":
            assert params["time_increment"] == 1 and params["time_range"]["until"] == "2026-11-24"
            return {"data": [{"date_start": "2026-10-31", "spend": "1000", "impressions": "10", "reach": "9", "clicks": "1", "account_currency": "KZT"},
                             {"date_start": "2026-11-01", "spend": "5000.50", "impressions": "900", "reach": "700", "clicks": "30", "account_currency": "KZT"}],
                    "paging": {"next": "https://graph.facebook.com/next1"}}
        if path == "https://graph.facebook.com/next1":
            return {"data": [{"date_start": "2026-11-02", "spend": "7000", "impressions": "1100", "reach": "800", "clicks": "45", "account_currency": "KZT"}]}
        if path == "act_1/insights" and params.get("level") == "ad" and params.get("date_preset"):
            return {"data": [{"ad_id": "a1", "frequency": "3.6"}, {"ad_id": "a2", "frequency": "1.2"}]}
        if path == "act_1/insights" and params.get("level") == "ad":
            base = {"campaign_id": "c1", "campaign_name": "Роспись Астана", "adset_name": "Ж 25-45", "account_currency": "KZT"}
            return {"data": [{**base, "ad_id": "a1", "ad_name": "Рилс кафе", "date_start": d, "spend": "9000", "impressions": "2000", "reach": "600", "clicks": "10"}
                             for d in ("2026-11-21", "2026-11-22", "2026-11-23")] +
                            [{**base, "ad_id": "a2", "ad_name": "Фото офис", "date_start": "2026-11-23", "spend": "4000", "impressions": "900", "reach": "800", "clicks": "40",
                              "actions": [{"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "2"}, {"action_type": "lead", "value": "1"},
                                          {"action_type": "onsite_conversion.lead_grouped", "value": "1"}, {"action_type": "link_click", "value": "40"}]}]}
        if path == "act_2/insights" and params.get("level") == "ad":
            return {"data": []}
        if path == "act_2/insights":
            return {"data": [{"date_start": "2026-11-02", "spend": "20", "impressions": "5", "reach": "5", "clicks": "1", "account_currency": "USD"}]}
        if path == "me/accounts":
            return {"data": [{"name": "Artgame.kz", "instagram_business_account": {"id": "178", "username": "artgame.kz"}}]}
        if path == "178":
            return {"username": "artgame.kz", "followers_count": 3600, "media_count": 2}
        if path == "178/insights":
            return {"data": [{"name": params["metric"], "total_value": {"value": {"reach": 400, "views": 1500}.get(params["metric"], 7)}}]}
        if path == "178/media":
            return {"data": [{"id": "m1", "caption": "Роспись кафе", "media_type": "VIDEO", "media_product_type": "REELS", "permalink": "https://instagram.com/reel/1",
                              "timestamp": "2026-11-20T10:00:00+0000", "like_count": 50, "comments_count": 4},
                             {"id": "old", "media_type": "IMAGE", "media_product_type": "FEED", "timestamp": "2025-01-01T10:00:00+0000"}]}
        if path == "m1/insights":
            return {"data": [{"name": "views", "values": [{"value": 12000}]}, {"name": "reach", "values": [{"value": 8000}]},
                             {"name": "saved", "values": [{"value": 30}]}, {"name": "shares", "values": [{"value": 12}]}]}
        raise AssertionError(path)
    return get


def test_meta_loader(client, monkeypatch):
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    monkeypatch.delenv("META_TOKEN", raising=False)
    assert client.get("/api/mkt/meta", headers=hdr(1000)).json()["on"] is False
    assert client.post("/api/mkt/meta/sync", headers=hdr(1000)).status_code == 409
    monkeypatch.setenv("META_TOKEN", "t")
    calls = []
    monkeypatch.setattr(meta, "get", fake_meta(calls))
    r = meta.sync(today=date(2026, 11, 24))
    assert r["ok"] and r["errors"] == [] and r["ads"]["days"] == 4 and set(r["ads"]["months"]) == {"2026-10", "2026-11"}
    assert r["ig"]["followers"] == 3600 and r["ig"]["media"] == 1
    d = client.get("/api/mkt/meta?ym=2026-11", headers=hdr(1000)).json()
    kzt = [a for a in d["ads"] if a["currency"] == "KZT"][0]
    assert (kzt["spend"], kzt["impressions"], kzt["clicks"], kzt["upto"]) == (12000.5, 2000, 75, "2026-11-02")
    assert [a["currency"] for a in d["ads"]] == ["KZT", "USD"] and not d["manual"] and d["on"] and d["last"]["ok"]
    assert d["ig"]["followers"] == 3600 and d["ig"]["week"]["reach"] == 2800 and d["ig"]["week"]["views"] == 10500
    assert d["ig"]["top"][0]["views"] == 12000 and d["ig"]["top"][0]["kind"] == "REELS"
    # расход площадки взят из Meta: только тенге, доллары не складываем
    with db.pool.connection() as c:
        row = c.execute("SELECT s.* FROM mkt_spend s JOIN mkt_channels ch ON ch.id=s.channel_id WHERE ch.title='Таргет Instagram' AND ym='2026-11'").fetchone()
        assert float(row["amount"]) == 12000.5 and row["source"] == "meta"
        ch = row["channel_id"]
    # руками поправили — ночной сбор не затирает, пока не нажмут «Взять из Meta»
    assert client.post("/api/mkt/spend", json={"channel_id": ch, "ym": "2026-11", "amount": 99}, headers=hdr(1000)).status_code == 200
    meta.sync(today=date(2026, 11, 24))
    d = client.get("/api/mkt/meta?ym=2026-11", headers=hdr(1000)).json()
    assert d["manual"]
    with db.pool.connection() as c:
        assert float(c.execute("SELECT amount FROM mkt_spend WHERE channel_id=%s AND ym='2026-11'", (ch,)).fetchone()["amount"]) == 99
    assert client.post("/api/mkt/meta/take?ym=2026-11", headers=hdr(1000)).status_code == 200
    with db.pool.connection() as c:
        row = c.execute("SELECT amount, source FROM mkt_spend WHERE channel_id=%s AND ym='2026-11'", (ch,)).fetchone()
        assert float(row["amount"]) == 12000.5 and row["source"] == "meta"
    assert client.post("/api/mkt/meta/take?ym=2025-01", headers=hdr(1000)).status_code == 409


def test_meta_part_fails(client, monkeypatch):
    """Instagram не ответил — расход всё равно сохранён, ошибка видна."""
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    monkeypatch.setenv("META_TOKEN", "t")
    monkeypatch.setattr(meta, "get", fake_meta([], broken=("me/accounts",)))
    r = meta.sync(today=date(2026, 11, 24))
    assert not r["ok"] and "нет разрешения" in r["errors"][0] and r["ads"]["days"] == 4 and "ig" not in r
    d = client.post("/api/mkt/meta/sync", headers=hdr(1000)).json()
    assert d["errors"] and client.get("/api/mkt/meta?ym=2026-11", headers=hdr(1000)).json()["last"]["ok"] is False


def test_meta_token_not_in_error(monkeypatch):
    import httpx
    monkeypatch.setenv("META_TOKEN", "SECRET")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x access_token=SECRET")))
    try:
        meta.get("me")
    except meta.MetaError as e:
        assert "SECRET" not in str(e)


def test_ad_stats_hints_report(client, monkeypatch):
    """Кампании и объявления, подсказки «антислив» по порогам из «Значений», отчёт за неделю."""
    from psycopg.types.json import Jsonb

    from artgame import adrules, bx, notify
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    t = client.post("/api/register", json={"full_name": "Таргет"}, headers=hdr(2950)).json()["id"]
    client.post(f"/api/people/{t}", json={"role_code": "marketer", "zones": ["marketing"], "mkt_job": "target"}, headers=hdr(1000))
    monkeypatch.setenv("META_TOKEN", "t")
    monkeypatch.setattr(meta, "get", fake_meta([]))
    monkeypatch.setattr(adrules, "_today", lambda: date(2026, 11, 24))
    monkeypatch.setattr(bx, "READ", lambda method, params, **kw: {"result": [{"ID": "101", "STATUS_ID": "NEW"}] if method == "crm.lead.list" else [], "total": 1})
    sent = []
    monkeypatch.setattr(notify, "SEND", lambda tg, text: sent.append((tg, text)))
    # порогов в «Значениях» нет — правила молчат, экран говорит, чего не хватает
    r = meta.sync(today=date(2026, 11, 24))
    assert r["ads"]["ad_rows"] == 4 and r["hints"]["open"] == 0 and len(r["hints"]["missing"]) == 5 and not sent
    d = client.get("/api/mkt/adstats?days=7", headers=hdr(2950)).json()
    assert {m["key"] for m in d["missing"]} == set(adrules.KEYS) and d["hints"] == [] and d["can_edit"]
    c = d["campaigns"][0]
    assert (c["name"], c["spend"], c["impressions"], c["clicks"], c["results"], c["cpr"]) == ("Роспись Астана", 31000.0, 6900, 70, 3, 10333)
    a1, a2 = c["ads"]
    assert (a1["ad_name"], a1["spend"], a1["results"], a1["ctr"], a1["frequency"]) == ("Рилс кафе", 27000.0, 0, 0.5, 3.6)
    assert (a2["results"], a2["cpr"], a2["ctr"]) == (3, 1333, 4.44)          # лид под двумя именами не задвоился
    # HEAD задал пороги
    vals = {"mkt.cpl_plan": 5000, "mkt.nolead_x": 2, "mkt.cpl_over_pct": 30, "mkt.freq_max": 3, "mkt.ctr_min_pct": "0,8"}
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES ('x', %s)",
                     (Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "маркетинг"} for k, v in vals.items()}),))
    ch = {c["title"]: c["id"] for c in client.get("/api/mkt/channels", headers=hdr(1000)).json()}
    client.post("/api/bx/leads/101/origin", json={"channel_id": ch["Таргет Instagram"]}, headers=hdr(1000))
    h = adrules.run(date(2026, 11, 24))
    assert h == {"open": 5, "new": 5, "missing": []} and {tg for tg, _ in sent} == {1000, 2950} and "Тратит без обращений: Рилс кафе" in sent[0][1]
    d = client.get("/api/mkt/adstats?days=7", headers=hdr(1000)).json()
    assert sorted(x["rule"] for x in d["hints"]) == ["cpl3", "ctr", "freq", "nolead", "nosale"] and d["plan_cpl"] == 5000
    assert d["campaigns"][0]["ads"][0]["hint"] and not d["campaigns"][0]["ads"][1]["hint"]
    nolead = [x for x in d["hints"] if x["rule"] == "nolead"][0]
    assert "27 000 ₸" in nolead["text"] and nolead["advice"].startswith("Остановить")
    # повторный сбор новых не шлёт; «Сделано» закрывает, три дня не возвращается; прошедшее снимается само
    sent.clear()
    assert adrules.run(date(2026, 11, 24))["new"] == 0 and not sent
    marketer = client.post("/api/register", json={"full_name": "М"}, headers=hdr(2000)).json()["id"]
    client.post(f"/api/people/{marketer}", json={"role_code": "marketer", "zones": ["marketing"]}, headers=hdr(1000))
    assert client.post(f"/api/mkt/adhints/{nolead['id']}/done", json={}, headers=hdr(2000)).status_code == 403
    assert client.post(f"/api/mkt/adhints/{nolead['id']}/done", json={"note": "остановил"}, headers=hdr(2950)).status_code == 200
    adrules.run(date(2026, 11, 24))
    assert "nolead" not in [x["rule"] for x in client.get("/api/mkt/adstats", headers=hdr(1000)).json()["hints"]]
    with db.pool.connection() as conn:
        conn.execute("UPDATE mkt_meta_ad7 SET frequency=1")
    adrules.run(date(2026, 11, 24))
    with db.pool.connection() as conn:
        assert conn.execute("SELECT status FROM mkt_ad_hints WHERE rule='freq'").fetchone()["status"] == "gone"
    # отчёт за неделю 23–29.11: таргет из Meta по дням (нет строк за эту неделю в mkt_meta_day → 0), OLX руками — доля месяца
    client.post("/api/mkt/spend", json={"channel_id": ch["OLX"], "ym": "2026-11", "amount": 30000}, headers=hdr(1000))
    client.post("/api/bx/leads/101/origin", json={"channel_id": ch["OLX"]}, headers=hdr(1000))
    rep = adrules.report("week", 0, today=date(2026, 11, 24))
    assert (rep["from"], rep["to"]) == ("2026-11-23", "2026-11-29") and rep["meta"]["results"] == 3
    olx = [c for c in rep["channels"] if c["title"] == "OLX"][0]
    assert (olx["spend"], olx["approx"], olx["leads"], olx["cpl"]) == (7000, True, 1, 7000)
    mon = client.get("/api/mkt/report?period=month", headers=hdr(2000)).json()
    assert mon["period"] == "month" and "OLX" in adrules.report_csv(rep).decode()
    assert client.get("/api/mkt/report?period=year", headers=hdr(1000)).status_code == 400
