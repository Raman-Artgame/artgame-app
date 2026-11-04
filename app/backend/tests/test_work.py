import uuid

from artgame import db
from conftest import hdr

T0 = "2026-11-04T09:00:00+05:00"
T1 = "2026-11-04T19:00:00+05:00"


def setup_people(client):
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    ids = {}
    for tg, role, zones in [(2000, "artist", ["mural"]), (3000, "lead_artist", ["mural"]),
                            (4000, "print_master", ["print"]), (5000, "artist", ["mural"])]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": zones}, headers=hdr(1000))
        ids[tg] = pid
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, gip_person_id) VALUES (731, 'Кафе', 'Астана', %s)", (ids[5000],))
    return ids


def test_pending_cannot_submit(client):
    client.post("/api/register", json={"full_name": "New"}, headers=hdr(7000))
    assert client.get("/api/work/dict", headers=hdr(7000)).status_code == 403


def test_shift_flow(client):
    setup_people(client)
    d = client.get("/api/work/dict", headers=hdr(2000)).json()
    assert {o["id"] for o in d["objects"]} == {0, 731} and len(d["categories"]) == 10
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural",
            "started_at": T0, "ended_at": T1, "area_m2": 12.5, "complexity": "medium"}
    s1 = client.post("/api/shifts", json=body, headers=hdr(2000)).json()
    # повтор из офлайн-очереди — та же запись
    assert client.post("/api/shifts", json=body, headers=hdr(2000)).json()["id"] == s1["id"]
    # чужая зона — нельзя
    bad = {**body, "client_uid": str(uuid.uuid4()), "zone_code": "print"}
    assert client.post("/api/shifts", json=bad, headers=hdr(2000)).status_code == 400
    # мастер печати не видит роспись, главный художник видит
    assert client.get("/api/review", headers=hdr(4000)).json()["shifts"] == []
    assert [x["id"] for x in client.get("/api/review", headers=hdr(3000)).json()["shifts"]] == [s1["id"]]
    assert client.post(f"/api/shift/{s1['id']}/review", json={"approve": True}, headers=hdr(4000)).status_code == 403
    # отказ без причины — нельзя
    assert client.post(f"/api/shift/{s1['id']}/review", json={"approve": False}, headers=hdr(3000)).status_code == 400
    assert client.post(f"/api/shift/{s1['id']}/review", json={"approve": True}, headers=hdr(3000)).json()["status"] == "approved"
    # после проверки отменить нельзя
    assert client.post(f"/api/shift/{s1['id']}/cancel", headers=hdr(2000)).status_code == 409
    assert len(client.get("/api/my", headers=hdr(2000)).json()["shifts"]) == 1


def test_expense_flow_gip_and_payout(client):
    setup_people(client)
    e = client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural",
                                           "category": "paint", "amount": 15000}, headers=hdr(2000)).json()
    # ГИП объекта 731 видит расход
    assert [x["id"] for x in client.get("/api/review", headers=hdr(5000)).json()["expenses"]] == [e["id"]]
    client.post(f"/api/expense/{e['id']}/review", json={"approve": True}, headers=hdr(5000))
    assert client.get("/api/my", headers=hdr(2000)).json()["expenses"][0]["payout_status"] == "to_pay"
    # своё отменить можно, пока не проверено; запись остаётся
    e2 = client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 0, "zone_code": "mural",
                                            "category": "other", "amount": 500}, headers=hdr(2000)).json()
    assert client.post(f"/api/expense/{e2['id']}/cancel", headers=hdr(2000)).json()["ok"]
    statuses = sorted(x["status"] for x in client.get("/api/my", headers=hdr(2000)).json()["expenses"])
    assert statuses == ["approved", "cancelled"]
    assert client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural",
                                              "category": "nope", "amount": 1}, headers=hdr(2000)).status_code == 400
