import json
import secrets

import pytest

from artgame import db, pack_places, places
from artgame.config import settings
from conftest import hdr
from test_work import setup_people

KEY = secrets.token_hex(32)


@pytest.fixture
def placed(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "content_key", KEY)
    monkeypatch.setattr(places, "ROOT", tmp_path / "places")
    monkeypatch.setattr(pack_places, "ROOT", tmp_path / "places")
    monkeypatch.setattr(places, "DL_DIR", tmp_path / "dl")
    for code in ("art", "print", "dz"):
        src = tmp_path / "src" / code
        (src / "img").mkdir(parents=True)
        (src / "index.html").write_text(f"<html><head><title>{code}</title></head><body>секретный-текст-42</body></html>")
        (src / "img" / "a.jpg").write_bytes(b"\xff\xd8jpeg")
        pack_places.pack(src, code, KEY)
    return client


def test_encrypted_on_disk(placed):
    blob = (places.ROOT / "art" / "index.html.enc").read_bytes()
    assert b"-42" not in blob and "секрет".encode() not in blob
    assert places.key_ok()


def test_places_by_role_and_serving(placed):
    setup_people(placed)
    art = placed.get("/api/places", headers=hdr(2000)).json()
    assert [p["code"] for p in art] == ["art"]
    assert [p["code"] for p in placed.get("/api/places", headers=hdr(4000)).json()] == ["print"]
    assert [p["code"] for p in placed.get("/api/places", headers=hdr(1000)).json()] == ["art", "print", "dz"]
    url = art[0]["url"]
    r = placed.get(url)
    assert r.status_code == 200 and "секретный-текст-42" in r.text and "/api/p/_shim.js" in r.text
    assert placed.get(url.replace("index.html", "img/a.jpg")).content == b"\xff\xd8jpeg"
    # чужое место по своей ссылке — нельзя; подделанная подпись — нельзя
    assert placed.get(url.replace("/p/art/", "/p/print/")).status_code == 403
    assert placed.get(url[:-15] + "0" * 4 + url[-11:]).status_code in (403, 404)
    assert placed.get("/api/p/_shim.js").status_code == 200
    # заблокированный теряет доступ даже со старой ссылкой
    with db.pool.connection() as c:
        c.execute("UPDATE people SET status='blocked' WHERE tg_id=2000")
    assert placed.get(url).status_code == 403


def test_wrong_key(placed, monkeypatch):
    setup_people(placed)
    url = placed.get("/api/places", headers=hdr(2000)).json()[0]["url"]
    monkeypatch.setattr(settings, "content_key", secrets.token_hex(32))
    assert placed.get(url).status_code == 503 and not places.key_ok()


def test_db_board_values_and_download(placed):
    setup_people(placed)
    with db.pool.connection() as c:
        c.execute("INSERT INTO constants_versions (checksum, values) VALUES ('x', %s)", (json.dumps({
            "mural.easy.a": {"value": "17 000", "who": "все", "status": "Утверждено"},
            "print.ink.cmyk_ml": {"value": "15", "who": "производство", "status": "Утверждено"},
            "design.urgent": {"value": "30", "who": "дизайн", "status": "Утверждено"},
            "pay.mop.oklad": {"value": "200000", "who": "head", "status": "Утверждено"},
            "x.wait": {"value": "1", "who": "все", "status": "Ждёт решения"}}),))
        pid = c.execute("SELECT id FROM people WHERE tg_id=1000").fetchone()["id"]
    head = {p["code"]: p["url"].removesuffix("/index.html") for p in placed.get("/api/places", headers=hdr(1000)).json()}
    v = placed.get(head["dz"] + "/_db/config/values").json()
    assert v["exists"] and v["data"]["values"] == {"mural.easy.a": 17000, "design.urgent": 30}
    assert placed.get(head["print"] + "/_db/config/values").json()["data"]["values"] == {"mural.easy.a": 17000, "print.ink.cmyk_ml": 15}
    assert placed.put(head["dz"] + "/_db/config/values", json={"values": {}}).status_code == 403
    # доска дизайна: пишет дизайнер, видит HEAD
    assert placed.get(head["dz"] + "/_db/projects").json() == {"docs": []}
    assert placed.put(head["dz"] + "/_db/projects/p1", json={"obj": "Кафе", "stage": 0}).json()["version"] == 1
    assert placed.put(head["dz"] + "/_db/projects/p1", json={"obj": "Кафе", "stage": 1}).json()["version"] == 2
    docs = placed.get(head["dz"] + "/_db/projects").json()["docs"]
    assert docs[0]["id"] == "p1" and docs[0]["data"]["stage"] == 1
    # на месте художников художник не пишет в общие документы
    art = placed.get("/api/places", headers=hdr(2000)).json()[0]["url"].removesuffix("/index.html")
    assert placed.put(art + "/_db/notes/n1", json={"a": 1}).status_code == 403
    # скачивание собранного файла
    u = placed.post(head["dz"] + "/_dl?name=КП 731.pdf", content=b"%PDF-1", headers={"Content-Type": "application/pdf"}).json()["url"]
    r = placed.get(u)
    assert r.content == b"%PDF-1" and "attachment" in r.headers["content-disposition"]
    assert pid
