import uuid

import pytest

from artgame import db, drive
from conftest import hdr
from test_work import setup_people

JPEG = "data:image/jpeg;base64,/9j/AA=="


class FakeDrive:
    """Диск в памяти: папки и файлы, без сети."""
    store = {}
    n = 0

    def __init__(self):
        pass

    def _id(self):
        FakeDrive.n += 1
        return f"drv{FakeDrive.n:08d}"

    def project_folder(self, obj):
        return "deal-" + str(obj["id"])

    def child(self, parent, name):
        return f"{parent}/{name}"

    def ls(self, parent):
        return FakeDrive.tree.get(parent, [])

    tree = {}

    def upload(self, parent, name, data, mime):
        i = self._id()
        FakeDrive.store[i] = {"parents": [parent], "size": str(len(data)), "mimeType": mime, "data": data}
        return i

    def resumable(self, parent, name, mime, size, origin):
        FakeDrive.pending = (parent, size, mime)
        return "https://upload.example/session"

    def meta(self, fid):
        return FakeDrive.store[fid]

    def stream(self, fid, rng=None):
        d = FakeDrive.store[fid]["data"]
        if rng:
            a, b = map(int, rng.split("=")[1].split("-"))
            d = d[a:b + 1]
        yield d

    def thumbnail(self, fid):
        return b"thumb"


@pytest.fixture
def fake(monkeypatch):
    FakeDrive.store = {}
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    return FakeDrive


def test_photo_upload_view_and_folders(client, fake):
    ids = setup_people(client)
    body = {"client_uid": str(uuid.uuid4()), "data": JPEG, "note": "стена до"}
    f = client.post("/api/objects/731/photos", json=body, headers=hdr(2000)).json()
    assert f["kind"] == "photo" and f["url"] and f["thumb"]
    # повтор из очереди — тот же файл, на Диск второй раз не грузится
    assert client.post("/api/objects/731/photos", json=body, headers=hdr(2000)).json()["id"] == f["id"]
    assert len(fake.store) == 1
    # подпапки созданы и запомнены
    with db.pool.connection() as c:
        o = c.execute("SELECT drive_folder, folders FROM objects WHERE id=731").fetchone()
    assert o["drive_folder"] == "deal-731" and o["folders"]["report"] == "deal-731/МЕДИА/Отчёты"
    assert set(o["folders"]) == {"v", "report", "prod_photo", "prod_video", "reels", "design", "design_ok", "site", "receipt", "doc", "income"}
    assert o["folders"]["site"] == "deal-731/ДИЗАЙН/Фото объекта" and o["folders"]["receipt"] == "deal-731/РАСХОДЫ ЧЕКИ" and o["folders"]["income"] == "deal-731/ПРИХОДЫ ЧЕКИ"
    # другой художник видит фото в приложении
    lst = client.get("/api/objects/731/files?kind=photo", headers=hdr(5000)).json()
    assert [x["id"] for x in lst] == [f["id"]] and lst[0]["by"] == "P2000"
    # просмотр по подписанной ссылке; подделка — нет
    assert client.get(f["url"]).content == b"\xff\xd8\xff\x00"
    assert client.get(f["thumb"]).content == b"thumb"
    assert client.get(f["url"].replace("sig=", "sig=0")).status_code == 403
    objs = client.get("/api/objects", headers=hdr(2000)).json()
    assert {o["id"]: o["photos"] for o in objs}[731] == 1


def test_design_big_upload_direct(client, fake):
    setup_people(client)
    with db.pool.connection() as c:
        pid = c.execute("SELECT id FROM people WHERE tg_id=2000").fetchone()["id"]
    req = {"client_uid": str(uuid.uuid4()), "kind": "design", "name": "Эскиз.psd", "mime": "image/vnd.adobe.photoshop", "size": 5}
    # художник без зоны «Дизайн» не грузит дизайн
    assert client.post("/api/objects/731/uploads", json=req, headers=hdr(2000)).status_code == 403
    client.post(f"/api/people/{pid}", json={"zones": ["mural", "design"]}, headers=hdr(1000))
    r = client.post("/api/objects/731/uploads", json=req, headers=hdr(2000)).json()
    assert r["upload_url"] == "https://upload.example/session"
    # пока не загружено — в ленте нет
    assert client.get("/api/objects/731/files?kind=design", headers=hdr(5000)).json() == []
    # телефон загрузил в Google, сервер сверяет папку и размер
    fake.store["drvBIGFILE01"] = {"parents": ["deal-731/ДИЗАЙН"], "size": "5", "mimeType": "image/vnd.adobe.photoshop", "data": b"12345"}
    fake.store["drvWRONG0001"] = {"parents": ["elsewhere"], "size": "5", "mimeType": "x", "data": b"12345"}
    assert client.post(f"/api/files/{r['file_id']}/done", json={"drive_id": "drvWRONG0001"}, headers=hdr(2000)).status_code == 400
    done = client.post(f"/api/files/{r['file_id']}/done", json={"drive_id": "drvBIGFILE01"}, headers=hdr(2000)).json()
    assert done["status"] == "ready" and done["url"]
    assert [x["name"] for x in client.get("/api/objects/731/files?kind=design", headers=hdr(5000)).json()] == ["Эскиз.psd"]
    # убрать из ленты может автор, чужой — нет
    assert client.post(f"/api/files/{r['file_id']}/archive", headers=hdr(5000)).status_code == 403
    assert client.post(f"/api/files/{r['file_id']}/archive", headers=hdr(2000)).json()["ok"]
    assert client.get("/api/objects/731/files?kind=design", headers=hdr(5000)).json() == []


def test_docs_only_for_leads(client, fake):
    setup_people(client)
    assert client.get("/api/objects/731/files?kind=doc", headers=hdr(2000)).status_code == 403
    assert client.get("/api/objects/731/files?kind=doc", headers=hdr(3000)).json() == []
    assert client.get("/api/objects/731/files?kind=receipt", headers=hdr(1000)).status_code == 403


def test_objects_from_bitrix(client, fake):
    from artgame import sync_objects
    deals = [{"ID": "812", "TITLE": "Кафе Самал ", "STAGE_ID": "FINAL_INVOICE", "CATEGORY_ID": "0"},
             {"ID": "640", "TITLE": "Школа", "STAGE_ID": "WON", "CATEGORY_ID": "0", "UF_CRM_ARTGAME_PROJECT_FOLDER_ID": "fold640"}]
    with db.pool.connection() as c:
        assert sync_objects.upsert(c, deals) == [812, 640]
        assert sync_objects.upsert(c, deals) == []
        o = c.execute("SELECT * FROM objects WHERE id=812").fetchone()
        assert o["title"] == "Кафе Самал" and o["status"] == "active"
    assert sync_objects.split_title("525", "525 · РЕСТОРАН ВОК ШЫМПЛАЗА — ШЫМКЕНТ") == ("РЕСТОРАН ВОК ШЫМПЛАЗА", "ШЫМКЕНТ")
    assert sync_objects.split_title("1213", "1213 · AKNUR - НОВОГОДНЯЯ РОСПИСЬ ОКОН — АСТАНА") == ("AKNUR - НОВОГОДНЯЯ РОСПИСЬ ОКОН", "АСТАНА")
    with db.pool.connection() as c:
        o640 = c.execute("SELECT status, drive_folder FROM objects WHERE id=640").fetchone()
        assert o640["status"] == "done" and o640["drive_folder"] == "fold640"
        o = c.execute("SELECT * FROM objects WHERE id=812").fetchone()
        drive.ensure_folders(c, o)
        assert c.execute("SELECT folders FROM objects WHERE id=812").fetchone()["folders"]["design"] == "deal-812/ДИЗАЙН"


def test_gateway_client(monkeypatch):
    """Шлюз отвечает SSE, сессия передаётся в заголовке, страницы идут по next."""
    import json as _j

    import httpx

    from artgame import sync_objects
    seen = []

    def post(url, json, headers, timeout):
        seen.append((json["method"], headers.get("Mcp-Session-Id")))
        req = httpx.Request("POST", url)
        if json["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": json["id"], "result": {}}, headers={"mcp-session-id": "S1"}, request=req)
        if "id" not in json:
            return httpx.Response(202, request=req)
        start = json["params"]["arguments"]["params"]["start"]
        page = {"result": [{"ID": str(100 + start), "TITLE": "T", "STAGE_ID": "UC_AV00QK", "CATEGORY_ID": "0"}],
                "next": 50 if start == 0 else None}
        res = {"content": [{"type": "text", "text": _j.dumps(page)}]}
        body = "event: message\ndata: " + _j.dumps({"jsonrpc": "2.0", "id": json["id"], "result": res}) + "\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}, request=req)

    monkeypatch.setattr(sync_objects.httpx, "post", post)
    monkeypatch.setattr(sync_objects.settings, "gateway_url", "http://127.0.0.1:9/mcp")
    deals = sync_objects.fetch_deals()
    assert [d["ID"] for d in deals] == ["100", "150"]
    assert seen[0] == ("initialize", None) and seen[-1] == ("tools/call", "S1")


def test_office_has_no_files(client, fake):
    """«Офис / без объекта» — только для трат: в «Объектах» не виден, файлы к нему не принимаются."""
    setup_people(client)
    assert 0 not in [o["id"] for o in client.get("/api/objects", headers=hdr(2000)).json()]
    body = {"client_uid": str(uuid.uuid4()), "data": "data:image/jpeg;base64,/9j/AA=="}
    assert client.post("/api/objects/0/photos", json=body, headers=hdr(2000)).status_code == 400


def test_deal_without_number_gets_title_city_geo(client, fake, monkeypatch):
    """HEAD 13.11: «ШКОЛА КОСШЫ» (1711) заведена прямо в Битриксе — без номера, без города в названии, вместо адреса ссылка 2ГИС."""
    from artgame import bx, bxw, sync_objects
    from artgame.promo import parse_geo
    calls = []
    monkeypatch.setattr(sync_objects.settings, "bitrix_webhook", "https://example/rest/1/x/")
    monkeypatch.setattr(bxw, "CALL", lambda m, p: calls.append((m, p)) or {"result": True})
    monkeypatch.setattr(bx, "city_name", lambda v: "Астана (Нур-Султан)" if str(v) == "12077" else "")
    url = "https://2gis.kz/astana/geo/70030077198628630/71.376512,50.990932|0;0|1975"
    deals = [{"ID": "1711", "TITLE": "ШКОЛА КОСШЫ", "STAGE_ID": "UC_AV00QK", "CATEGORY_ID": "0", "UF_CRM_6881101914D8D": "12077",
              "UF_CRM_ARTGAME_OBJECT": "Школа Косшы", "UF_CRM_1755520919823": url},
             {"ID": "1693", "TITLE": "1693 · АКАДЕМИЯ БОЛАШАК — КАРАГАНДА", "STAGE_ID": "UC_AV00QK", "CATEGORY_ID": "0"},
             {"ID": "640", "TITLE": "Школа", "STAGE_ID": "WON", "CATEGORY_ID": "0"}]
    assert sync_objects.number_titles(deals) == [1711]   # с номером и закрытые не трогаем
    assert calls == [("crm.deal.update", {"id": 1711, "fields": {"TITLE": "1711 · ШКОЛА КОСШЫ — АСТАНА"}})]
    with db.pool.connection() as c:
        sync_objects.upsert(c, deals)
        o = c.execute("SELECT title, city, address, geo FROM objects WHERE id=1711").fetchone()
    assert (o["title"], o["city"], o["address"], o["geo"]) == ("ШКОЛА КОСШЫ", "АСТАНА", None, "50.990932;71.376512")
    assert parse_geo("Караганда Ерубаева 16/6|;|1969") is None and parse_geo("x|0;0|1") is None
    assert parse_geo("ул|42.31;69.58|1") == "42.31;69.58"
