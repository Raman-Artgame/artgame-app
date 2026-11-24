"""Рубрики и поиск «Медиа», исходники в рубрику, сценарий → HEAD → съёмка с папкой, креативы рекламы."""
import pytest
from conftest import hdr
from test_files import FakeDrive

from artgame import db, drive


@pytest.fixture
def team(client, monkeypatch):
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    FakeDrive.tree = {}
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    for tg, job in [(2000, "smm"), (2100, "video"), (2950, "target")]:
        i = client.post("/api/register", json={"full_name": f"М{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{i}", json={"role_code": "marketer", "zones": ["marketing"], "mkt_job": job}, headers=hdr(1000))
    a = client.post("/api/register", json={"full_name": "Художник"}, headers=hdr(3000)).json()["id"]
    client.post(f"/api/people/{a}", json={"role_code": "artist", "zones": ["mural"]}, headers=hdr(1000))
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city) VALUES (731, 'Кафе Алма', 'Астана'), (745, 'Школа', 'Шымкент') ON CONFLICT DO NOTHING")
        for i, (obj, name, mt, rv, ts) in enumerate([(731, "Стена до.jpg", "photo", "approved", "2026-11-10"), (745, "Таймлапс.mp4", "video", "pending", "2025-06-01"),
                                                      (745, "Брак.mp4", "video", "rejected", "2026-11-01")]):
            c.execute("""INSERT INTO files (id, client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by, status, media_type, review, created_at)
                         VALUES (%s, gen_random_uuid(), %s, 'media', %s, 'x/y', 1, %s, %s, 'ready', %s, %s, %s)""", (900 + i, obj, name, f"d{i}", a, mt, rv, ts))


def test_library_tags_search(client, team):
    assert client.get("/api/mkt/library", headers=hdr(3000)).status_code == 403
    d = client.get("/api/mkt/library", headers=hdr(2000)).json()
    assert [x["id"] for x in d["items"]] == [900, 901] and d["years"] == [2026, 2025] and d["cities"] == ["Астана", "Шымкент"] and d["can_tag"]
    rub = {r["title"]: r["id"] for r in d["rubrics"]}
    assert len(rub) == 12 and "До/после" in rub and "Процесс росписи" in rub
    assert client.post("/api/mkt/files/900/tags", json={"rubric_ids": [rub["До/после"], rub["Готовые работы"], 99999]}, headers=hdr(2000)).json()["tags"] == [rub["До/после"], rub["Готовые работы"]]
    assert client.post("/api/mkt/files/900/tags", json={"rubric_ids": [rub["До/после"]]}, headers=hdr(3000)).status_code == 403
    q = lambda s: [x["id"] for x in client.get("/api/mkt/library?" + s, headers=hdr(2000)).json()["items"]]  # noqa: E731
    assert q(f"tag={rub['До/после']}") == [900] and q("year=2025") == [901] and q("city=Шымкент") == [901] and q("q=кафе стена") == [900]
    assert q("q=745") == [901] and q("type=video") == [901] and q("best=1") == [900] and q("q=нет такого") == []
    client.post("/api/mkt/files/900/tags", json={"rubric_ids": []}, headers=hdr(1000))
    assert q(f"tag={rub['До/после']}") == []


def test_src_upload_to_rubric(client, team):
    rub = {r["title"]: r["id"] for r in client.get("/api/mkt/rubrics", headers=hdr(2000)).json()}
    up = {"client_uid": "33333333-3333-4333-8333-333333333333", "name": "Интервью.mp4", "mime": "video/mp4", "size": 7}
    assert client.post("/api/mkt/src/uploads", json=up, headers=hdr(2000)).status_code == 400                       # без рубрики
    assert client.post("/api/mkt/src/uploads", json={**up, "rubric_id": rub["Эксперт"]}, headers=hdr(2000)).status_code == 400   # без названия
    assert client.post("/api/mkt/src/uploads", json={**up, "rubric_id": rub["До/после"], "title": "x"}, headers=hdr(2000)).status_code == 400   # метка, не папка
    assert client.post("/api/mkt/src/uploads", json={**up, "mime": "application/zip", "rubric_id": rub["Эксперт"], "title": "x"}, headers=hdr(2000)).status_code == 400
    # папка рубрики на Диске с номером впереди — находим её, а не плодим вторую
    FakeDrive.tree = {"1EZ0NkwjOkQbb7fDzshqnZPNxHVubDF75": [{"id": "rub-expert", "name": "05 ЭКСПЕРТ", "mimeType": drive.FOLDER}]}
    r = client.post("/api/mkt/src/uploads", json={**up, "rubric_id": rub["Эксперт"], "title": "Интервью: Раман/цены"}, headers=hdr(2000)).json()
    parent = FakeDrive.pending[0]
    assert parent.startswith("rub-expert/Исходники/20") and parent.endswith(" Интервью Раман цены") and r["folder"] == parent.split("/")[-1]
    assert client.post(f"/api/mkt/src/uploads/{r['file_id']}/done", json={"drive_id": "nope-nope-nope"}, headers=hdr(2000)).status_code >= 400
    FakeDrive.store["drvsrc00001"] = {"parents": [parent], "size": "7", "mimeType": "video/mp4", "data": b"1234567"}
    assert client.post(f"/api/mkt/src/uploads/{r['file_id']}/done", json={"drive_id": "drvsrc00001"}, headers=hdr(2100)).status_code == 404   # чужая загрузка
    f = client.post(f"/api/mkt/src/uploads/{r['file_id']}/done", json={"drive_id": "drvsrc00001"}, headers=hdr(2000)).json()
    assert f["kind"] == "src" and f["url"]
    items = client.get(f"/api/mkt/library?tag={rub['Эксперт']}&q=интервью", headers=hdr(1000)).json()["items"]
    assert [x["name"] for x in items] == ["Интервью.mp4"] and items[0]["object_title"] is None and items[0]["src_folder"].endswith("цены")
    assert client.post("/api/mkt/src/uploads", json={**up, "rubric_id": rub["Эксперт"], "title": "x"}, headers=hdr(2000)).json()["done"] is True


def test_idea_approval_to_shoot(client, team):
    rub = {r["title"]: r["id"] for r in client.get("/api/mkt/rubrics", headers=hdr(2000)).json()}
    i = client.post("/api/mkt/ideas", json={"title": "Как мы считаем цену", "kind": "reels"}, headers=hdr(2000)).json()["id"]
    assert client.post(f"/api/mkt/ideas/{i}/submit", headers=hdr(2000)).status_code == 400            # нет сценария
    client.post(f"/api/mkt/ideas/{i}", json={"title": "Как мы считаем цену", "text": "Кадр 1: стена"}, headers=hdr(2000))
    assert client.post(f"/api/mkt/ideas/{i}/submit", headers=hdr(2000)).status_code == 400            # нет рубрики
    body = {"title": "Как мы считаем цену", "text": "Кадр 1: стена", "rubric_id": rub["Эксперт"]}
    client.post(f"/api/mkt/ideas/{i}", json=body, headers=hdr(2000))
    assert client.post(f"/api/mkt/ideas/{i}/shoot", json={"shoot_date": "2026-12-01"}, headers=hdr(2100)).status_code == 409   # не утверждено
    assert client.post(f"/api/mkt/ideas/{i}/submit", headers=hdr(2000)).json() == {"status": "pending"}
    assert client.post(f"/api/mkt/ideas/{i}/review", json={"approve": True}, headers=hdr(2000)).status_code == 403
    assert client.post(f"/api/mkt/ideas/{i}/review", json={"approve": False}, headers=hdr(1000)).status_code == 400
    assert client.post(f"/api/mkt/ideas/{i}/review", json={"approve": False, "note": "короче"}, headers=hdr(1000)).json() == {"status": "rejected"}
    client.post(f"/api/mkt/ideas/{i}/submit", headers=hdr(2000))
    assert client.post(f"/api/mkt/ideas/{i}/review", json={"approve": True}, headers=hdr(1000)).json() == {"status": "approved"}
    # поправили сценарий после утверждения — снова черновик
    client.post(f"/api/mkt/ideas/{i}", json={**body, "text": "Кадр 1: другая стена"}, headers=hdr(2000))
    it = client.get("/api/mkt/ideas", headers=hdr(2000)).json()
    assert it["items"][0]["status"] == "new" and it["items"][0]["rubric"] == "Эксперт" and it["can_shoot"] and not it["head"]
    client.post(f"/api/mkt/ideas/{i}/submit", headers=hdr(2000))
    client.post(f"/api/mkt/ideas/{i}/review", json={"approve": True}, headers=hdr(1000))
    client.post(f"/api/mkt/ideas/{i}", json=body | {"text": "Кадр 1: другая стена", "status": "new"}, headers=hdr(2000))   # статус сменой не снять
    assert client.get("/api/mkt/ideas", headers=hdr(2000)).json()["items"][0]["status"] == "approved"
    assert client.post(f"/api/mkt/ideas/{i}/shoot", json={"shoot_date": "2026-12-01"}, headers=hdr(2950)).status_code == 403   # таргетолог съёмки не ставит
    r = client.post(f"/api/mkt/ideas/{i}/shoot", json={"shoot_date": "2026-12-01", "at_time": "10:00"}, headers=hdr(2100)).json()
    assert r["folder"] == "Эксперт / Исходники / 2026-12-01 Как мы считаем цену" and not r["warn"]
    scen = [v for v in FakeDrive.store.values() if (v.get("parents") or [""])[0].endswith("/Эксперт/Исходники/2026-12-01 Как мы считаем цену")]
    assert scen and "другая стена".encode() in scen[0]["data"]
    sh = client.get("/api/mkt/shoots?ym=2026-12", headers=hdr(2100)).json()["items"]
    assert sh[0]["id"] == r["shoot_id"] and sh[0]["idea_title"] == "Как мы считаем цену" and sh[0]["drive_folder"]
    assert client.get("/api/mkt/ideas", headers=hdr(2000)).json()["items"][0]["status"] == "work"
    # исходник — прямо в папку съёмки
    up = {"client_uid": "44444444-4444-4444-8444-444444444444", "name": "дубль1.mp4", "mime": "video/mp4", "size": 3, "shoot_id": r["shoot_id"]}
    assert client.post("/api/mkt/src/uploads", json=up, headers=hdr(2100)).json()["folder"] == "2026-12-01 Как мы считаем цену"
    assert FakeDrive.pending[0] == sh[0]["drive_folder"]
    # идея HEAD утверждается сразу
    h = client.post("/api/mkt/ideas", json={"title": "Мысль", "text": "с телефона", "rubric_id": rub["HR"]}, headers=hdr(1000)).json()["id"]
    assert client.post(f"/api/mkt/ideas/{h}/submit", headers=hdr(1000)).json() == {"status": "approved"}


def test_ad_creative_saved_on_approve(client, team):
    with db.pool.connection() as c:
        c.execute("""INSERT INTO files (id, client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by, status, media_type)
                     SELECT 950, gen_random_uuid(), 0, 'pub', 'Баннер.jpg', 'image/jpeg', 1, 'drvban', id, 'ready', 'photo' FROM people LIMIT 1""")
    FakeDrive.copied = []
    FakeDrive.copy = lambda self, fid, parent, name=None: FakeDrive.copied.append((fid, parent, name)) or "copy1"
    ad = {"title": "Акция декабрь", "kind": "ad", "plan_date": "2026-12-05", "caption": "т", "file_ids": [950]}
    p = client.post("/api/mkt/posts", json=ad, headers=hdr(2950)).json()
    client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2950))
    for _ in range(2):      # руководителя отдела нет — сразу у HEAD
        st = client.get("/api/mkt/posts?ym=2026-12", headers=hdr(1000)).json()["items"][0]["status"]
        if st == "check":
            client.post(f"/api/mkt/posts/{p['id']}/check", json={"approve": True}, headers=hdr(1000))
    r = client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(1000)).json()
    assert r["status"] == "approved" and r["ad_saved"] == "Реклама / 2026-12"
    assert FakeDrive.copied == [("drvban", f"{drive.MKT_READY_ID}/Реклама/2026-12", "Баннер.jpg")]
