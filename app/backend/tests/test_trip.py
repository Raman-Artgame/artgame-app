"""Доработки HEAD 08.11 (вечер): командировка по городу + МОП, дорога как смена, суточные, проживание, «Выдано и допуски»."""
import uuid
from datetime import date

from artgame import db
from conftest import hdr
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401


def test_trip_road_food_lodging(client, team):  # noqa: F811
    lead = client.post("/api/register", json={"full_name": "Главный"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{lead}", json={"role_code": "lead_artist", "zones": ["mural"], "city": "Шымкент"}, headers=hdr(1000))
    with db.pool.connection() as c:
        c.execute("UPDATE constants_versions SET values = values || '{\"pay.trip_food\": {\"value\": \"3000\", \"status\": \"Утверждено\", \"who\": \"head\"}}'::jsonb")
    # объект в Астане, Главный из Шымкента — командировка; саппорт без города — нет
    assert client.get("/api/work/object/731", headers=hdr(6000)).json()["trip"] is True
    assert client.get("/api/work/object/731", headers=hdr(2000)).json()["trip"] is False
    road = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "day": "2026-11-03T08:00:00+05:00", "direction": "there"}
    assert client.post("/api/shifts/road", json=road, headers=hdr(2000)).status_code == 400          # не командировка
    r = client.post("/api/shifts/road", json=road, headers=hdr(6000)).json()
    assert r["kind"] == "road" and r["status"] == "submitted" and r["trip"]
    assert client.post("/api/shifts/road", json={**road, "client_uid": str(uuid.uuid4())}, headers=hdr(6000)).status_code == 409
    # МОП/HEAD поправил: «нет, в городе» — дорога больше не принимается
    assert client.post("/api/objects/731/trip", json={"trip": False}, headers=hdr(5000)).status_code == 403
    assert client.post("/api/objects/731/trip", json={"trip": False}, headers=hdr(1000)).json()["trip"] is False
    assert client.get("/api/work/object/731", headers=hdr(6000)).json()["trip"] is False
    client.post("/api/objects/731/trip", json={"trip": None}, headers=hdr(1000))
    # рабочая смена в командировке
    uid = str(uuid.uuid4())
    client.post("/api/shifts/start", json={"client_uid": uid, "object_id": 731, "zone_code": "mural", "started_at": "2026-11-04T09:00:00+05:00",
                                           "photo_before": JPEG}, headers=hdr(6000))
    s = client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": "2026-11-04T19:00:00+05:00", "area_m2": 5, "work_done": "Фон",
                                                "photo_after": JPEG}, headers=hdr(6000)).json()
    assert s["trip"] is True
    with db.pool.connection() as c:
        c.execute("UPDATE shifts SET status='approved' WHERE person_id=%s", (lead,))
    # проживание — только у Главного/Про/Мастера печати
    assert "lodging" in {x["code"] for x in client.get("/api/work/dict", headers=hdr(6000)).json()["categories"]}
    assert "lodging" not in {x["code"] for x in client.get("/api/work/dict", headers=hdr(5000)).json()["categories"]}
    ym = "2026-11"
    out = client.post(f"/api/fin/payroll/{ym}/compute", headers=hdr(1000)).json()
    lines = {r["name"]: {(l["kind"], float(l["amount"])) for l in r["lines"]} for r in out["rows"]}
    assert ("trip_food", 6000.0) in lines["Главный"]                     # 2 дня: дорога + смена
    assert ("piece", 40000.0) in lines["Главный"]                        # дорога — как смена (pay.chief.shift 20000)
    assert {"label": "Суточные в командировке, за день", "amount": 3000} in client.get("/api/fin/my", headers=hdr(6000)).json()["rate"]


def test_issued_items(client, team):  # noqa: F811
    sup = team[2000]
    it = {"kind": "key", "title": "Ключ от студии", "qty": 1}
    assert client.post(f"/api/people/{sup}/items", json=it, headers=hdr(3000)).status_code == 403       # ключи выдаёт HEAD
    k = client.post(f"/api/people/{sup}/items", json=it, headers=hdr(1000)).json()
    pm = client.post(f"/api/people/{sup}/items", json={"kind": "permit", "title": "Стремянка и вышка"}, headers=hdr(3000)).json()  # допуск — Главный
    my = client.get("/api/items/my", headers=hdr(2000)).json()["items"]
    assert {x["title"] for x in my} == {"Ключ от студии", "Стремянка и вышка"} and all(x["ack_at"] is None for x in my)
    assert client.post(f"/api/items/{k['id']}/ack", headers=hdr(2000)).json()["ack_at"]
    assert client.post(f"/api/items/{k['id']}/ack", headers=hdr(5000)).status_code == 404               # чужое не подтвердить
    assert client.post(f"/api/items/{pm['id']}/close", json={"status": "returned"}, headers=hdr(5000)).status_code == 403
    assert client.post(f"/api/items/{k['id']}/close", json={"status": "returned"}, headers=hdr(1000)).json()["status"] == "returned"
    assert client.post(f"/api/items/{k['id']}/close", json={"status": "lost"}, headers=hdr(1000)).status_code == 409
    assert date.today()
