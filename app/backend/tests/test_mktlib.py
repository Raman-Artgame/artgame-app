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


def test_library_project_category(client, team, monkeypatch):
    """HEAD 25.11: фильтр «Медиа» по утверждённой категории проекта из сделки (подкатегория уточняет)."""
    from artgame import bx
    enums = {"UF_CRM_ARTGAME_PROJECT_CATEGORY": {"43253": "Еда и гостеприимство", "43255": "Игры и развлечения", "43257": "Спорт", "43259": "Дети и образование"},
             "UF_CRM_ARTGAME_PROJECT_SUBCATEGORY": {"43273": "1.2. Рестораны, кафе, фастфуд", "43295": "4.2. Школы и вузы", "43293": "4.1. Детские сады"}}
    monkeypatch.setattr(bx, "enum_map", lambda code: enums[code])
    deals = {("UF_CRM_ARTGAME_PROJECT_CATEGORY", "43253"): [731], ("UF_CRM_ARTGAME_PROJECT_CATEGORY", "43259"): [745],
             ("UF_CRM_ARTGAME_PROJECT_SUBCATEGORY", "43293"): []}
    monkeypatch.setattr(bx, "read_all", lambda m, prm, fresh=False: [{"ID": str(i)} for i in deals.get(next(iter(prm["filter"].items())), [])])
    d = client.get("/api/mkt/library", headers=hdr(2000)).json()
    cats = {c["name"]: c for c in d["cats"]}
    assert [s["name"] for s in cats["Дети и образование"]["subs"]] == ["4.2. Школы и вузы", "4.1. Детские сады"]
    assert [s["id"] for s in cats["Еда и гостеприимство"]["subs"]] == ["43273"] and cats["Игры и развлечения"]["subs"] == []
    q = lambda s: [x["id"] for x in client.get("/api/mkt/library?" + s, headers=hdr(2000)).json()["items"]]  # noqa: E731
    assert q("cat=43253") == [900] and q("cat=43259") == [901] and q("cat=43259&sub=43293") == [] and q("cat=43255") == []


def test_library_sync_from_drive(client, team, monkeypatch):
    """HEAD 26.11: то, что разложено в «МЕДИА» сделки руками, само появляется в «Медиа»; второй раз не заводится."""
    from artgame import mediasync
    F = drive.FOLDER
    tree = {
        "root731": [{"id": "m731", "name": "МЕДИА", "mimeType": F}, {"id": "dz", "name": "ДИЗАЙН", "mimeType": F}],
        "m731": [{"id": "pr", "name": "Продакшн", "mimeType": F}, {"id": "rp", "name": "Отчёты", "mimeType": F}, {"id": "rl", "name": "Рилс", "mimeType": F}],
        "pr": [{"id": "pf", "name": "Фото", "mimeType": F}, {"id": "pv", "name": "Видео", "mimeType": F}],
        "pf": [{"id": "g1", "name": "Готово 1.jpg", "mimeType": "image/jpeg", "size": "10", "imageMediaMetadata": {"time": "2025:06:01 12:00:00"}},
               {"id": "d0", "name": "Стена до.jpg", "mimeType": "image/jpeg", "size": "1"}],          # уже есть в базе (drive_id d0)
        "pv": [{"id": "g2", "name": "Пролёт.mov", "mimeType": "video/quicktime", "size": "20", "createdTime": "2026-10-25T00:00:00Z",
                "modifiedTime": "2025-09-03T10:00:00Z"}],
        "rp": [{"id": "sub", "name": "день 2", "mimeType": F}, {"id": "doc", "name": "акт.pdf", "mimeType": "application/pdf"}],
        "sub": [{"id": "g3", "name": "IMG_1.jpg", "mimeType": "image/jpeg", "size": "5"}],
        "rl": [{"id": "g4", "name": "Рилс.mp4", "mimeType": "video/mp4", "size": "30"}],
    }
    monkeypatch.setattr(mediasync, "_ls", lambda d, parent: tree.get(parent, []))
    with db.pool.connection() as c:
        c.execute("UPDATE files SET drive_id='d0' WHERE id=900")
        c.execute("UPDATE objects SET drive_folder='root731' WHERE id=731")
    assert client.post("/api/mkt/library/sync", headers=hdr(2000)).status_code == 403
    r = client.post("/api/mkt/library/sync", headers=hdr(1000)).json()
    assert r["added"] == 4 and r["left"] == 0 and not r["errors"]
    with db.pool.connection() as c:
        got = {x["drive_id"]: x for x in c.execute("SELECT * FROM files WHERE note LIKE 'Диск:%%'").fetchall()}
    assert set(got) == {"g1", "g2", "g3", "g4"}
    assert (got["g1"]["media_type"], got["g1"]["review"], got["g1"]["created_at"].year) == ("photo", "approved", 2025)
    assert (got["g2"]["media_type"], got["g2"]["created_at"].year) == ("video", 2025)        # раньше из «создан/изменён»
    assert (got["g3"]["review"], got["g3"]["note"]) == (None, "Диск: МЕДИА/Отчёты/день 2")    # отчёт: без решения, не в очередь HEAD
    assert got["g4"]["media_type"] == "reels"
    q = lambda s: {x["name"] for x in client.get("/api/mkt/library?" + s, headers=hdr(2000)).json()["items"]}  # noqa: E731
    assert {"Готово 1.jpg", "Пролёт.mov", "IMG_1.jpg", "Рилс.mp4"} <= q("object_id=731") and "Готово 1.jpg" in q("year=2025&best=1")
    assert "IMG_1.jpg" not in q("best=1")
    with db.pool.connection() as c:
        c.execute("UPDATE objects SET media_synced_at=NULL")
    assert client.post("/api/mkt/library/sync", headers=hdr(1000)).json()["added"] == 0       # повтор ничего не дублирует


def test_post_parts_and_media_state(client, team):
    """HEAD 26.11: у публикации исходники, монтаж и финал; исходник в «Медиа» — «в работе», после выхода — «вышло»."""
    st = lambda s: [x["id"] for x in client.get("/api/mkt/library?" + s, headers=hdr(2000)).json()["items"]]  # noqa: E731
    assert st("state=free") == [900, 901] and st("state=work") == [] and st("vid=raw") == [900, 901] and st("vid=ready") == []
    assert client.post("/api/mkt/posts", json={"title": "x", "src_ids": [99999]}, headers=hdr(2000)).status_code == 400
    p = client.post("/api/mkt/posts", json={"title": "Кафе до/после", "kind": "reels", "plan_date": "2026-11-28", "object_id": 731,
                                             "src_ids": [900], "draft_ids": [901], "file_ids": [901]}, headers=hdr(2000)).json()
    assert [f["id"] for f in p["srcs"]] == [900] and [f["id"] for f in p["drafts"]] == [901]
    assert st("state=work") == [900, 901] and st("state=free") == []
    items = {x["id"]: x for x in client.get("/api/mkt/library", headers=hdr(2000)).json()["items"]}
    assert items[900]["state"] == "work" and items[900]["vid"] == "raw"
    client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(2000))
    client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(1000))
    assert client.post(f"/api/mkt/posts/{p['id']}/published", json={"url": "https://instagram.com/reel/x"}, headers=hdr(2000)).status_code == 200
    assert st("state=out") == [900, 901] and st("state=work") == []
