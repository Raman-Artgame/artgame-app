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
