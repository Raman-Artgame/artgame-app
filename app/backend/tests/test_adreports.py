"""Отчёт таргетолога (HEAD 26.11): файл → «04 ОТЧЁТЫ / Таргет / ГГГГ-ММ», сверка с Meta и Битриксом, «Принято» / «Вернуть с вопросом»."""
from artgame import db
from conftest import hdr
from test_marketing import team  # noqa: F401


def test_target_report_flow(client, team, monkeypatch):  # noqa: F811
    from artgame import ads, adrules, constants, drive
    from test_files import FakeDrive
    FakeDrive.store = {}
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    sent = []
    from artgame import dm
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)))
    tid = client.post("/api/register", json={"full_name": "Таргетолог"}, headers=hdr(2300)).json()["id"]
    client.post(f"/api/people/{tid}", json={"role_code": "marketer", "zones": ["marketing"], "mkt_job": "target"}, headers=hdr(1000))
    with db.pool.connection() as c:
        ch = c.execute("SELECT id FROM mkt_channels WHERE title='Таргет Instagram'").fetchone()
        for ad, name, spend, msgs in [("a1", "Макет 1", 358.03, 64), ("a3", "Макет 3", 337.70, 60), ("a2", "Макет 2", 38.38, 6)]:
            c.execute("""INSERT INTO mkt_meta_ad_day (ad_id, day, account, ad_name, campaign_id, campaign_name, spend, currency, impressions, clicks, messages)
                         VALUES (%s, '2026-11-10', 'act_1', %s, 'c1', 'РК Артгейм', %s, 'USD', 50000, 200, %s)""", (ad, name, spend, msgs))
    monkeypatch.setattr(constants, "latest", lambda conn: {"mkt.cpl_plan": 3.5})
    monkeypatch.setattr(ads, "bx_by_channel", lambda t0, t1, fresh=False: ({ch["id"] if ch else 0: {"leads": 41, "deals": 3, "won": 1, "won_sum": 640000.0}}, 41, ""))
    up = {"client_uid": "22222222-2222-4222-8222-222222222222", "name": "Отчет РК.xlsx", "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "size": 9}
    assert client.post("/api/mkt/adreports/uploads", json=up, headers=hdr(2000)).status_code == 403     # контент — не таргет
    assert client.post("/api/mkt/adreports/uploads", json={**up, "mime": "video/mp4"}, headers=hdr(2300)).status_code == 400
    r = client.post("/api/mkt/adreports/uploads", json=up, headers=hdr(2300)).json()
    parent, size, mime = FakeDrive.pending
    assert parent.startswith(adrules.REPORTS_FOLDER + "/Таргет/20")
    FakeDrive.store["drvREP000001"] = {"parents": [parent], "size": "9", "mimeType": mime}
    f = client.post(f"/api/mkt/adreports/uploads/{r['file_id']}/done", json={"drive_id": "drvREP000001"}, headers=hdr(2300)).json()
    assert f["kind"] == "doc"
    body = {"period_from": "2026-10-22", "period_to": "2026-11-25", "campaigns": "РК Артгейм", "note": "Макет 1 и 3 лучше всех",
            "file_ids": [f["id"]], "rep_spend": 734.11, "rep_chats": 130}
    assert client.post("/api/mkt/adreports", json={**body, "file_ids": [999999]}, headers=hdr(2300)).status_code == 400
    rep = client.post("/api/mkt/adreports", json=body, headers=hdr(2300)).json()
    assert rep["status"] == "pending" and rep["files"][0]["name"] == "Отчет РК.xlsx"
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["adrep"] == 1
    one = client.get(f"/api/mkt/adreports/{rep['id']}", headers=hdr(1000)).json()
    assert one["cmp"]["spend"] == 734.11 and one["cmp"]["chats"] == 130 and one["cmp"]["bx"]["leads"] == 41
    assert one["cmp"]["ads"][0]["ad_name"] == "Макет 1"           # дешевле всего переписка
    v = " ".join(one["verdict"])
    assert "сходится с кабинетом" in v and "выше плана 3.5 на 61%" in v and "41 заявок" in v and "МОП" in v
    # вопрос HEAD → агентство дополняет → снова у HEAD → принято
    assert client.post(f"/api/mkt/adreports/{rep['id']}/review", json={"ok": True}, headers=hdr(2300)).status_code == 403
    assert client.post(f"/api/mkt/adreports/{rep['id']}/review", json={"ok": False}, headers=hdr(1000)).status_code == 400
    r2 = client.post(f"/api/mkt/adreports/{rep['id']}/review", json={"ok": False, "note": "Почему Макет 2 не отключили?"}, headers=hdr(1000)).json()
    assert r2["status"] == "returned" and sent[-1][0] == 2300 and "Макет 2" in sent[-1][1]
    r3 = client.post(f"/api/mkt/adreports/{rep['id']}", json={**body, "note": "Макет 2 отключили 20.11"}, headers=hdr(2300)).json()
    assert r3["status"] == "pending"
    assert client.post(f"/api/mkt/adreports/{rep['id']}/review", json={"ok": True}, headers=hdr(1000)).json()["status"] == "accepted"
    assert client.post(f"/api/mkt/adreports/{rep['id']}", json=body, headers=hdr(2300)).status_code == 409
    lst = client.get("/api/mkt/adreports", headers=hdr(2300)).json()
    assert lst["can_upload"] and not lst["head"] and lst["items"][0]["status_ru"] == "принято"
    assert client.get("/api/mkt/adreports", headers=hdr(3000)).status_code == 403
