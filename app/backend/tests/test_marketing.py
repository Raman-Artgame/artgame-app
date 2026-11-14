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
