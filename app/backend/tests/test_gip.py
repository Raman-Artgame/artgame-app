"""ГИП проекта (HEAD 09.11): назначают HEAD/МОП, ГИП видит всю историю проекта и принимает его смены."""
import uuid

from conftest import hdr
from test_dual_role import _shift
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401


def test_gip_assign_and_history(client, team):  # noqa: F811
    lead = team[3000]
    assert client.post("/api/objects/731/gip", json={"person_id": lead}, headers=hdr(5000)).status_code == 403   # художник не назначает
    assert client.post("/api/objects/731/gip", json={"person_id": team[5000]}, headers=hdr(1000)).status_code == 400   # художник не ГИП
    assert {c["id"] for c in client.get("/api/gip/candidates", headers=hdr(1000)).json()} == {lead}
    assert client.get("/api/objects/731/history", headers=hdr(3000)).status_code == 403
    assert client.post("/api/objects/731/gip", json={"person_id": lead}, headers=hdr(1000)).json()["gip_id"] == lead
    _shift(client, 5000, "mural", 3)
    _shift(client, 2000, "mural", 4)
    client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "category": "transport",
                                       "amount": 2000, "receipt": JPEG}, headers=hdr(5000))
    h = client.get("/api/objects/731/history", headers=hdr(3000)).json()
    assert len(h["shifts"]) == 2 and h["shifts"][0]["work_done"] and len(h["expenses"]) == 1 and h["spent"] == 2000
    assert {x["name"] for x in h["people"]} == {"P2000", "P5000"} and all(x["hours"] == 10 for x in h["people"])
    assert client.get("/api/objects/731/history", headers=hdr(5000)).status_code == 403
    # ГИП принимает смены своего объекта
    assert len(client.get("/api/review", headers=hdr(3000)).json()["shifts"]) == 2
    client.post("/api/objects/731/gip", json={"person_id": 0}, headers=hdr(1000))
    assert client.get("/api/objects/731/history", headers=hdr(3000)).status_code == 403


def test_second_gip_same_rights(client, team):  # noqa: F811
    """Второй куратор ГИП (HEAD 28.11): права те же — история, «Проверка», команда; снять первого — второй становится первым."""
    lead = team[3000]
    pm = client.post("/api/register", json={"full_name": "Мастер"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{pm}", json={"role_code": "print_master", "zones": ["print"]}, headers=hdr(1000))
    assert client.post("/api/objects/731/gip", json={"person_id": pm, "slot": 2}, headers=hdr(1000)).status_code == 400   # сначала первый
    client.post("/api/objects/731/gip", json={"person_id": lead}, headers=hdr(1000))
    assert client.post("/api/objects/731/gip", json={"person_id": lead, "slot": 2}, headers=hdr(1000)).status_code == 400   # тот же человек
    r = client.post("/api/objects/731/gip", json={"person_id": pm, "slot": 2}, headers=hdr(1000)).json()
    assert (r["gip_id"], r["gip2_id"], r["gip2_name"]) == (lead, pm, "Мастер")
    _shift(client, 5000, "mural", 3)
    for tg in (3000, 6000):
        assert client.get("/api/objects/731/history", headers=hdr(tg)).status_code == 200
        assert len(client.get("/api/review", headers=hdr(tg)).json()["shifts"]) == 1
        assert client.get("/api/objects/731/crew", headers=hdr(tg)).json()["can_edit"]
    # сняли первого — второй остаётся единственным куратором
    r = client.post("/api/objects/731/gip", json={"person_id": 0}, headers=hdr(1000)).json()
    assert (r["gip_id"], r["gip2_id"]) == (pm, None)
    assert client.get("/api/objects/731/history", headers=hdr(3000)).status_code == 403
    assert client.get("/api/objects/731/history", headers=hdr(6000)).status_code == 200
