"""Рабочее место маркетинга (HEAD 14.11): роль «Маркетолог», «Медиа» из материала объектов, контент-план,
каждая публикация — через «Утверждаю» HEAD; без утверждения «Опубликовано» не поставить."""
import pytest

from artgame import db
from conftest import hdr


@pytest.fixture
def team(client):
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    ids = {}
    for tg, role, zones in [(2000, "marketer", ["marketing"]), (3000, "artist", ["mural"])]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        assert client.post(f"/api/people/{pid}", json={"role_code": role, "zones": zones}, headers=hdr(1000)).status_code == 200
        ids[tg] = pid
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (731, 'Кафе', 'Астана', 'UC_AV00QK')")
        for i, (t, rv) in enumerate([("reels", "approved"), ("photo", "pending"), ("video", "rejected")], 1):
            c.execute("""INSERT INTO files (id, client_uid, object_id, kind, name, mime, size, status, drive_id, uploaded_by, media_type, review)
                         VALUES (%s, gen_random_uuid(), 731, 'media', %s, 'video/mp4', 1, 'ready', %s, %s, %s, %s)""",
                      (900 + i, f"f{i}", f"d{i}", ids[3000], t, rv))
    return ids


def test_library_for_marketer(client, team):
    assert client.get("/api/media?scope=library&type=reels", headers=hdr(2000)).json()["items"][0]["id"] == 901
    assert client.get("/api/media?scope=library&type=video", headers=hdr(2000)).json()["items"] == []     # возвращённое не видно
    assert [x["id"] for x in client.get("/api/media?scope=library&type=photo&best=1", headers=hdr(2000)).json()["items"]] == []
    assert client.get("/api/media?scope=library", headers=hdr(3000)).status_code == 403
    assert client.get("/api/mkt/posts", headers=hdr(3000)).status_code == 403


def test_post_needs_head_approval(client, team):
    p = client.post("/api/mkt/posts", json={"title": "Рилс Кафе", "file_ids": [901], "object_id": 731}, headers=hdr(2000)).json()
    assert p["status"] == "draft" and p["files"][0]["id"] == 901 and p["object_title"] == "Кафе"
    assert client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2000)).status_code == 400            # нет даты
    p = client.post(f"/api/mkt/posts/{p['id']}", json={"title": "Рилс Кафе", "plan_date": "2026-11-20", "file_ids": [901],
                                                        "caption": "До/после"}, headers=hdr(2000)).json()
    assert client.post(f"/api/mkt/posts/{p['id']}/published", json={}, headers=hdr(2000)).status_code == 409  # без HEAD нельзя
    assert client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2000)).json()["status"] == "pending"
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["posts"] == 1
    assert client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(2000)).status_code == 403
    assert client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": False}, headers=hdr(1000)).status_code == 400
    r = client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": False, "note": "другой трек"}, headers=hdr(1000)).json()
    assert r["status"] == "rejected" and r["review_note"] == "другой трек"
    client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2000))
    assert client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(1000)).json()["status"] == "approved"
    assert client.post(f"/api/mkt/posts/{p['id']}", json={"title": "x"}, headers=hdr(2000)).status_code == 409   # утверждённое не правим
    assert client.post(f"/api/mkt/posts/{p['id']}/published", json={"url": "ftp://x"}, headers=hdr(2000)).status_code == 400
    d = client.post(f"/api/mkt/posts/{p['id']}/published", json={"url": "https://instagram.com/p/1"}, headers=hdr(2000)).json()
    assert d["status"] == "published" and d["url"].endswith("/p/1")
    plan = client.get("/api/mkt/posts?ym=2026-11", headers=hdr(2000)).json()
    assert plan["counts"]["published"] == 1 and plan["items"][0]["author"] == "P2000"
    assert client.get("/api/mkt/posts?ym=2026-12", headers=hdr(1000)).json()["items"] == []


def test_bad_media_and_cancel(client, team):
    assert client.post("/api/mkt/posts", json={"title": "x", "file_ids": [12345]}, headers=hdr(2000)).status_code == 400
    p = client.post("/api/mkt/posts", json={"title": "Сторис", "kind": "stories", "channel": "tiktok"}, headers=hdr(1000)).json()
    assert client.post(f"/api/mkt/posts/{p['id']}/cancel", headers=hdr(2000)).json()["status"] == "cancelled"
    assert client.get("/api/mkt/posts", headers=hdr(2000)).json()["items"] == []


def test_result_csv_ideas_shoots(client, team):
    p = client.post("/api/mkt/posts", json={"title": "Рилс", "plan_date": "2026-11-20", "caption": "т"}, headers=hdr(2000)).json()
    assert client.post(f"/api/mkt/posts/{p['id']}/result", json={"result": "good"}, headers=hdr(2000)).status_code == 409   # не вышла
    client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2000))
    client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(1000))
    client.post(f"/api/mkt/posts/{p['id']}/published", json={}, headers=hdr(2000))
    r = client.post(f"/api/mkt/posts/{p['id']}/result", json={"result": "good", "views": 12000, "leads": 3}, headers=hdr(2000)).json()
    assert r["result"] == "good" and r["leads"] == 3
    csv = client.get("/api/mkt/posts.csv?ym=2026-11", headers=hdr(2000))
    assert csv.status_code == 200 and "дала результат" in csv.text and "12000" in csv.text
    i = client.post("/api/mkt/ideas", json={"title": "Говорящая голова: HEAD о бренде", "text": "1. Крупно…"}, headers=hdr(2000)).json()["id"]
    s = client.post("/api/mkt/shoots", json={"title": "Интервью", "shoot_date": "2026-11-18", "at_time": "11:00", "place": "Студия",
                                             "crew": [team[2000]], "idea_id": i}, headers=hdr(2000)).json()["id"]
    assert client.get("/api/mkt/ideas", headers=hdr(2000)).json()["items"][0]["status"] == "work"
    sh = client.get("/api/mkt/shoots?ym=2026-11", headers=hdr(1000)).json()
    assert sh["items"][0]["crew_names"] == ["P2000"] and sh["items"][0]["idea_title"].startswith("Говорящая")
    client.post(f"/api/mkt/shoots/{s}", json={"title": "Интервью", "shoot_date": "2026-11-18", "idea_id": i, "status": "done"}, headers=hdr(2000))
    assert client.get("/api/mkt/ideas", headers=hdr(2000)).json()["items"][0]["status"] == "done"
    assert client.get("/api/mkt/shoots", headers=hdr(3000)).status_code == 403


def test_ready_upload_and_review_day(client, team, monkeypatch):
    """Готовый рилс грузят прямо в публикацию (не в медиа объекта); HEAD утверждает все на день одной кнопкой."""
    from artgame import drive
    from test_files import FakeDrive
    FakeDrive.store = {}
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    up = {"client_uid": "11111111-1111-4111-8111-111111111111", "name": "Сторис.mp4", "mime": "video/mp4", "size": 8}
    assert client.post("/api/mkt/uploads", json=up, headers=hdr(3000)).status_code == 403
    assert client.post("/api/mkt/uploads", json={**up, "mime": "application/pdf"}, headers=hdr(2000)).status_code == 400
    r = client.post("/api/mkt/uploads", json=up, headers=hdr(2000)).json()
    parent, size, mime = FakeDrive.pending
    assert parent.startswith(drive.MKT_READY_ID)
    assert client.post("/api/mkt/posts", json={"title": "x", "file_ids": [r["file_id"]]}, headers=hdr(2000)).status_code == 400   # ещё не долетел
    FakeDrive.store["drvREADY00001"] = {"parents": ["другая"], "size": "8", "mimeType": mime}
    assert client.post(f"/api/mkt/uploads/{r['file_id']}/done", json={"drive_id": "drvREADY00001"}, headers=hdr(2000)).status_code == 400
    FakeDrive.store["drvREADY00001"]["parents"] = [parent]
    f = client.post(f"/api/mkt/uploads/{r['file_id']}/done", json={"drive_id": "drvREADY00001"}, headers=hdr(2000)).json()
    assert f["kind"] == "pub" and f["url"]
    assert client.get("/api/media?scope=library&type=reels", headers=hdr(2000)).json()["items"][0]["id"] == 901   # в «Медиа» объектов не попал
    assert all(x["id"] != f["id"] for x in client.get("/api/media?scope=library&type=reels", headers=hdr(2000)).json()["items"])
    ids = []
    for t, day in [("Сторис 1", "2026-11-21"), ("Сторис 2", "2026-11-21"), ("Рилс", "2026-11-22")]:
        p = client.post("/api/mkt/posts", json={"title": t, "kind": "stories", "plan_date": day, "file_ids": [f["id"]]}, headers=hdr(2000)).json()
        assert p["files"][0]["id"] == f["id"]
        client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2000))
        ids.append(p["id"])
    assert client.post("/api/mkt/review_day", json={"plan_date": "2026-11-21"}, headers=hdr(2000)).status_code == 403
    assert client.post("/api/mkt/review_day", json={"plan_date": "2026-11-21"}, headers=hdr(1000)).json() == {"approved": 2}
    assert [x["id"] for x in client.get("/api/mkt/posts?status=pending", headers=hdr(1000)).json()["items"]] == [ids[2]]


def test_jobs_lead_checks_first_and_norms(client, team):
    """Отдел: исполнитель → руководитель («Проверено») → HEAD; сторис-мейкер правит только своё; таргетолог план не трогает."""
    ids = {}
    for tg, job in [(2100, "lead"), (2200, "stories"), (2300, "target"), (2400, "video")]:
        pid = client.post("/api/register", json={"full_name": f"M{tg}"}, headers=hdr(tg)).json()["id"]
        r = client.post(f"/api/people/{pid}", json={"role_code": "marketer", "zones": ["marketing"], "mkt_job": job}, headers=hdr(1000))
        assert r.status_code == 200 and r.json()["mkt_job"] == job
        ids[tg] = pid
    assert client.post(f"/api/people/{ids[2400]}", json={"mkt_job": "boss"}, headers=hdr(1000)).status_code == 400
    assert client.get("/api/me", headers=hdr(2100)).json()["mkt_job"] == "lead"
    body = {"title": "Сторис утро", "kind": "stories", "plan_date": "2026-11-20", "caption": "т"}
    assert client.post("/api/mkt/posts", json=body, headers=hdr(2300)).status_code == 403      # таргетолог
    assert client.post("/api/mkt/posts", json=body, headers=hdr(2400)).status_code == 403      # видеограф
    assert client.post("/api/mkt/shoots", json={"title": "Объект", "shoot_date": "2026-11-18"}, headers=hdr(2400)).status_code == 200
    assert client.post("/api/mkt/shoots", json={"title": "Объект", "shoot_date": "2026-11-18"}, headers=hdr(2200)).status_code == 403
    p = client.post("/api/mkt/posts", json=body, headers=hdr(2200)).json()
    other = client.post("/api/mkt/posts", json={**body, "title": "Рилс"}, headers=hdr(2000)).json()
    assert client.post(f"/api/mkt/posts/{other['id']}", json=body, headers=hdr(2200)).status_code == 403   # чужое
    assert client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2200)).json()["status"] == "check"
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["posts"] == 0                # до HEAD ещё не дошло
    assert client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(1000)).status_code == 409
    assert client.post(f"/api/mkt/posts/{p['id']}/check", json={"approve": True}, headers=hdr(2200)).status_code == 403
    r = client.post(f"/api/mkt/posts/{p['id']}/check", json={"approve": False, "note": "логотип мелко"}, headers=hdr(2100)).json()
    assert r["status"] == "rejected" and r["reviewer"] == "M2100"
    client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2200))
    assert client.get("/api/mkt/posts?ym=2026-11", headers=hdr(2100)).json()["to_check"] == 1
    r = client.post(f"/api/mkt/posts/{p['id']}/check", json={"approve": True}, headers=hdr(2100)).json()
    assert r["status"] == "pending" and r["checked"] == "M2100"
    assert client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(1000)).json()["status"] == "approved"
    lead_post = client.post("/api/mkt/posts", json={**body, "title": "От руководителя"}, headers=hdr(2100)).json()
    assert client.post(f"/api/mkt/posts/{lead_post['id']}/submit", headers=hdr(2100)).json()["status"] == "pending"   # руководитель — сразу HEAD
    client.post(f"/api/mkt/posts/{p['id']}/published", json={}, headers=hdr(2200))
    norms = {n["kind"]: n for n in client.get("/api/mkt/posts?ym=2026-11", headers=hdr(2300)).json()["norms"]}
    assert norms["stories"] == {"kind": "stories", "title": "Сторис", "per_month": 70, "planned": 3, "done": 1}
    assert norms["reels"]["per_month"] == 8 and norms["reels"]["planned"] == 0
    assert client.post("/api/mkt/norms", json={"kind": "stories", "per_month": 60}, headers=hdr(2100)).status_code == 403
    assert client.post("/api/mkt/norms", json={"kind": "stories", "per_month": 60}, headers=hdr(1000)).status_code == 200
    assert client.get("/api/mkt/posts?ym=2026-11", headers=hdr(1000)).json()["norms"][2]["per_month"] == 60


def test_shoot_hints(client, team):
    """Подсказки съёмок: проект на «Выполнении» без смен — «до»; со свежей сменой — старт; запрет клиента и стоящая съёмка — молчим."""
    with db.pool.connection() as c:
        c.execute("""INSERT INTO objects (id, title, city, bitrix_stage, publish_ok) VALUES (745, 'Школа', 'Шымкент', 'UC_AV00QK', true),
                     (750, 'Запрет', 'Астана', 'UC_AV00QK', false), (760, 'Счёт', 'Астана', 'FINAL_INVOICE', NULL)""")
        c.execute("""INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at)
                     VALUES (gen_random_uuid(), %s, 745, 'mural', now() - interval '1 day', now() - interval '20 hours')""", (team[3000],))
    assert client.get("/api/mkt/hints", headers=hdr(3000)).status_code == 403
    h = client.get("/api/mkt/hints", headers=hdr(2000)).json()["items"]
    assert [(x["object_id"], x["why"], x["ask_client"]) for x in h] == [(745, "start", False), (731, "before", True)]
    client.post("/api/mkt/shoots", json={"title": "Процесс", "shoot_date": str(__import__("datetime").date.today()), "object_id": 745}, headers=hdr(2000))
    assert [x["object_id"] for x in client.get("/api/mkt/hints", headers=hdr(2000)).json()["items"]] == [731]
    i = client.post("/api/mkt/ideas", json={"title": "Говорящая голова"}, headers=hdr(2000)).json()["id"]
    assert client.get("/api/mkt/hints", headers=hdr(1000)).json()["ideas"][0]["id"] == i


def test_brand_folder(client, team, monkeypatch):
    """«Бренд»: папка Диска как есть; файл отдаётся только по подписанной ссылке из списка; чужую папку не открыть."""
    from artgame import brand, drive
    from test_files import FakeDrive
    F = drive.FOLDER
    FakeDrive.tree = {brand.BRAND_ID: [{"id": "fLOGO", "name": "Лого", "mimeType": F}, {"id": "bookPDF", "name": "Брендбук.pdf", "mimeType": "application/pdf", "size": "4"},
                                       {"id": "gdoc", "name": "Заметки", "mimeType": "application/vnd.google-apps.document"}],
                      "fLOGO": [{"id": "logoPNG", "name": "logo.png", "mimeType": "image/png", "size": "3"}]}
    FakeDrive.store = {"bookPDF": {"name": "Брендбук.pdf", "size": "4", "mimeType": "application/pdf", "data": b"%PDF"},
                       "logoPNG": {"name": "logo.png", "size": "3", "mimeType": "image/png", "data": b"png"},
                       "secret": {"name": "s", "size": "1", "mimeType": "text/plain", "data": b"x", "parents": ["other"]}}
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    brand.PARENT.clear()
    assert client.get("/api/mkt/brand", headers=hdr(3000)).status_code == 403
    root = client.get("/api/mkt/brand", headers=hdr(2000)).json()
    assert [f["name"] for f in root["folders"]] == ["Лого"] and [f["name"] for f in root["files"]] == ["Брендбук.pdf"] and root["path"] == []
    sub = client.get("/api/mkt/brand?folder=fLOGO", headers=hdr(2000)).json()
    assert sub["path"] == [{"id": "fLOGO", "name": "Лого"}] and sub["files"][0]["thumb"]
    r = client.get(sub["files"][0]["url"])
    assert r.status_code == 200 and r.content == b"png"
    assert "attachment" in client.get(root["files"][0]["url"] + "&dl=1").headers["content-disposition"]
    assert client.get(sub["files"][0]["url"].replace("logoPNG", "secret")).status_code == 403     # подпись — только на показанное
    assert client.get("/api/mkt/brand?folder=secret", headers=hdr(2000)).status_code == 404       # не папка «Бренда»


def test_ads_kind_and_shoot_upload(client, team, monkeypatch):
    """Реклама утверждается как публикация; таргетолог ставит только её. Маркетинг кладёт снятое в папку сделки, но не «рилс в оплату»."""
    from artgame import drive
    from test_files import FakeDrive
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    pid = client.post("/api/register", json={"full_name": "T"}, headers=hdr(2300)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "marketer", "zones": ["marketing"], "mkt_job": "target"}, headers=hdr(1000))
    ad = {"title": "Кампания: роспись фасадов", "kind": "ad", "channel": "instagram", "plan_date": "2026-11-20", "caption": "Текст объявления"}
    assert client.post("/api/mkt/posts", json={**ad, "kind": "reels"}, headers=hdr(2300)).status_code == 403
    p = client.post("/api/mkt/posts", json=ad, headers=hdr(2300)).json()
    assert client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2300)).json()["status"] == "pending"   # руководителя нет — сразу HEAD
    norms = {n["kind"]: n for n in client.get("/api/mkt/posts?ym=2026-11", headers=hdr(2300)).json()["norms"]}
    assert norms["ad"]["per_month"] == 2 and norms["ad"]["planned"] == 1
    up = {"client_uid": "22222222-2222-4222-8222-222222222222", "kind": "media", "name": "Процесс.mp4", "mime": "video/mp4", "size": 9}
    assert client.post("/api/objects/731/uploads", json={**up, "media_type": "reels"}, headers=hdr(2000)).status_code == 400
    assert client.post("/api/objects/731/uploads", json={**up, "media_type": "video"}, headers=hdr(2000)).status_code == 200


def test_ads_channels_origin_report(client, team, monkeypatch):
    """«Реклама»: площадка лида — сама по фразе из ссылки или отметка МОП; отчёт: расход, заявки, сделки, цена заявки, «сливает»."""
    from artgame import ads, bx, chats
    leads = [{"ID": "101", "STATUS_ID": "CONVERTED"}, {"ID": "102", "STATUS_ID": "NEW"}, {"ID": "103", "STATUS_ID": "NEW"}, {"ID": "104", "STATUS_ID": "CONVERTED"}]
    deals = [{"ID": "9001", "LEAD_ID": "101", "OPPORTUNITY": "450000", "STAGE_SEMANTIC_ID": "S"},
             {"ID": "9002", "LEAD_ID": "104", "OPPORTUNITY": "200000", "STAGE_SEMANTIC_ID": "P"}]

    def read(method, params):
        if method == "crm.lead.list":
            return {"result": leads, "total": len(leads)}
        if method == "crm.deal.list":
            rows = [d for d in deals if int(d["LEAD_ID"]) in params["filter"]["LEAD_ID"]]
            return {"result": rows, "total": len(rows)}
        return {"result": []}
    monkeypatch.setattr(bx, "READ", read)
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"]}, headers=hdr(1000))
    ch = {c["title"]: c["id"] for c in client.get("/api/mkt/channels", headers=hdr(6000)).json()}
    assert {"OLX", "Таргет Instagram", "2ГИС"} <= set(ch)
    assert client.get("/api/mkt/channels", headers=hdr(3000)).status_code == 403
    # сама: первая фраза клиента из ссылки OLX
    hist = {"users": {"7": {"connector": True}}, "message": {"1": {"id": "1", "senderid": "7", "text": "Здравствуйте! Пишу с OLX. Сколько стоит?", "date": "2026-11-10T10:00:00+05:00"},
                                                              "2": {"id": "2", "senderid": "5", "text": "Добрый день", "date": "2026-11-10T10:05:00+05:00"}}}
    chats._origin(101, hist)
    chats._origin(102, {"users": {"7": {"connector": True}}, "message": {"1": {"id": "1", "senderid": "7", "text": "Привет", "date": "2026-11-10"}}})
    with db.pool.connection() as c:
        assert ads.origin_of(c, 101)["title"] == "OLX" and ads.origin_of(c, 101)["auto"] and ads.origin_of(c, 102) is None
    # МОП отмечает сам; маркетолог за МОП не отмечает
    assert client.post("/api/bx/leads/102/origin", json={"channel_id": ch["Таргет Instagram"]}, headers=hdr(2000)).status_code == 403
    r = client.post("/api/bx/leads/102/origin", json={"channel_id": ch["Таргет Instagram"]}, headers=hdr(6000)).json()
    assert r == {"channel_id": ch["Таргет Instagram"], "title": "Таргет Instagram", "auto": False}
    # расход: обычный маркетолог не вносит, HEAD вносит
    sp = {"channel_id": ch["OLX"], "ym": "2026-11", "amount": 30000}
    assert client.post("/api/mkt/spend", json=sp, headers=hdr(2000)).status_code == 403
    for title, amount in [("OLX", 30000), ("Таргет Instagram", 120000), ("2ГИС", 15000)]:
        assert client.post("/api/mkt/spend", json={"channel_id": ch[title], "ym": "2026-11", "amount": amount}, headers=hdr(1000)).status_code == 200
    d = client.get("/api/mkt/ads?ym=2026-11&fresh=1", headers=hdr(2000)).json()
    row = {x["title"]: x for x in d["items"]}
    assert (row["OLX"]["leads"], row["OLX"]["deals"], row["OLX"]["won"], row["OLX"]["won_sum"], row["OLX"]["cpl"], row["OLX"]["verdict"]) == (1, 1, 1, 450000.0, 30000, "works")
    assert (row["Таргет Instagram"]["leads"], row["Таргет Instagram"]["cpl"], row["Таргет Instagram"]["verdict"]) == (1, 120000, "weak")
    assert row["2ГИС"]["verdict"] == "burns" and row["2ГИС"]["leads"] == 0
    assert d["unknown"]["leads"] == 2 and d["unknown"]["deals"] == 1 and d["total"] == {"leads": 4, "spend": 165000.0} and not d["can_edit"]
    # ссылки появляются после номера WhatsApp; площадку не удаляем, а выключаем; одинаковую фразу двум площадкам нельзя
    assert row["OLX"]["link"] is None
    assert client.post("/api/mkt/wa_phone", json={"phone": "+7 (705) 123-45-67"}, headers=hdr(1000)).json() == {"wa_phone": "77051234567"}
    d = client.get("/api/mkt/ads?ym=2026-11", headers=hdr(1000)).json()
    assert d["can_edit"] and [x for x in d["items"] if x["title"] == "OLX"][0]["link"].startswith("https://wa.me/77051234567?text=%D0%97")
    assert client.post("/api/mkt/channels", json={"title": "Крыша", "phrase": "здравствуйте пишу с olx"}, headers=hdr(1000)).status_code == 409
    new = client.post("/api/mkt/channels", json={"title": "Крыша", "phrase": "Пишу с Крыши"}, headers=hdr(1000)).json()["id"]
    assert client.post(f"/api/mkt/channels/{new}", json={"title": "Крыша", "active": False}, headers=hdr(1000)).status_code == 200
    assert "Крыша" not in [c["title"] for c in client.get("/api/mkt/channels", headers=hdr(6000)).json()]
