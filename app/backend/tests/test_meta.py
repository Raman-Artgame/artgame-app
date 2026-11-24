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
        if path == "act_1/insights":
            assert params["time_increment"] == 1 and params["time_range"]["until"] == "2026-11-24"
            return {"data": [{"date_start": "2026-10-31", "spend": "1000", "impressions": "10", "reach": "9", "clicks": "1", "account_currency": "KZT"},
                             {"date_start": "2026-11-01", "spend": "5000.50", "impressions": "900", "reach": "700", "clicks": "30", "account_currency": "KZT"}],
                    "paging": {"next": "https://graph.facebook.com/next1"}}
        if path == "https://graph.facebook.com/next1":
            return {"data": [{"date_start": "2026-11-02", "spend": "7000", "impressions": "1100", "reach": "800", "clicks": "45", "account_currency": "KZT"}]}
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
