"""Живая карточка объекта (HEAD 08.11): сложность по сумме сделки, эскизы из «ДИЗАЙН» на Диске, этапы и лента «до / после»."""
import uuid

from artgame import db, drive, promo
from conftest import hdr
from test_files import JPEG, FakeDrive
from test_production import VALS, Copying, team  # noqa: F401

F = "application/vnd.google-apps.folder"


def test_guess_level_by_price():
    v = {"mural.start": 30}
    assert promo.guess_level(v, 20, 20 * 22000) == "medium"
    assert promo.guess_level(v, 20, 20 * 17500) == "easy"
    assert promo.guess_level(v, 100, 100 * 22000) == "hard" and promo.guess_level(v, 100, 100 * 45000) == "author"
    assert promo.guess_level(v, 0, 1000) is None and promo.guess_level(v, 10, None) is None
    assert promo.parse_geo("ул. 1|42.31;69.58|1855") == "42.31;69.58" and promo.parse_geo("ул. 1") is None
    assert promo.map_url("Шымкент", "ул. 1", "42.31;69.58") == "https://2gis.kz/geo/69.58,42.31"


def test_live_card(client, team):  # noqa: F811
    FakeDrive.tree = {
        "root731": [{"id": "dz", "name": "ДИЗАЙН", "mimeType": F}, {"id": "docs", "name": "Документы", "mimeType": F}],
        "dz": [{"id": "ok", "name": "Утвержденные дизайны", "mimeType": F}, {"id": "raw.ai", "name": "Исходник.ai", "mimeType": "application/postscript"},
               {"id": "v1", "name": "Вариант 1.jpg", "mimeType": "image/jpeg", "size": "10"}],
        "ok": [{"id": "fin", "name": "Финал.jpg", "mimeType": "image/jpeg", "size": "10"}],
        "docs": [{"id": "dog", "name": "Договор.pdf", "mimeType": "application/pdf"}],
    }
    with db.pool.connection() as c:
        c.execute("UPDATE objects SET drive_folder='root731', level=NULL, level_guess='hard', geo='51.1;71.4' WHERE id=731")
        c.execute("DELETE FROM deal_calc WHERE deal_id=731")
    r = client.get("/api/work/object/731", headers=hdr(2000)).json()
    assert r["complexity"] == "hard" and r["complexity_src"] == "price"
    assert r["map"] == "https://2gis.kz/geo/71.4,51.1"
    assert [s["name"] for s in r["sketches"]] == ["Финал.jpg", "Вариант 1.jpg"] and r["sketches"][0]["approved"]   # .ai и договор — нет
    # повторно Диск не сверяется (30 мин) и дублей нет
    FakeDrive.tree["ok"].append({"id": "fin2", "name": "Финал 2.jpg", "mimeType": "image/jpeg"})
    assert len(client.get("/api/work/object/731", headers=hdr(2000)).json()["sketches"]) == 2
    with db.pool.connection() as c:
        assert promo.sync_designs(c, c.execute("SELECT * FROM objects WHERE id=731").fetchone()) == 1
    # смена закрывает этап — карточка показывает ход работ и фото до/после
    uid = str(uuid.uuid4())
    client.post("/api/shifts/start", json={"client_uid": uid, "object_id": 731, "zone_code": "mural", "started_at": "2026-11-04T09:00:00+05:00",
                                           "photo_before": JPEG}, headers=hdr(2000))
    fin = {"client_uid": uid, "ended_at": "2026-11-04T19:00:00+05:00", "area_m2": 15, "work_done": "Перенёс эскиз", "photo_after": JPEG}
    assert client.post("/api/shifts/finish", json={**fin, "stage": "nope"}, headers=hdr(2000)).status_code == 400
    assert client.post("/api/shifts/finish", json={**fin, "stage": "transfer"}, headers=hdr(2000)).json()["stage"] == "transfer"
    r = client.get("/api/work/object/731", headers=hdr(5000)).json()
    assert r["done_m2"] == 15 and r["pct"] == 25
    assert [s["done"] for s in r["stages"]][:3] == [True, True, False]       # грунт считается пройденным раньше переноса
    assert r["feed"][0]["before"] and r["feed"][0]["after"] and r["feed"][0]["work_done"] == "Перенёс эскиз"
