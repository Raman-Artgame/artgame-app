"""«Мастерская» без проекта (HEAD 09.11): печать — ТО принтера и т. п.; оплата как смена по часам, без плана и бонуса."""
import uuid

from artgame import db
from conftest import hdr
from test_production import VALS, Copying, team  # noqa: F401


def test_workshop_shift(client, team):  # noqa: F811
    pid = client.post("/api/register", json={"full_name": "Оператор"}, headers=hdr(6300)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "print_operator", "zones": ["print"]}, headers=hdr(1000))
    assert client.get("/api/work/dict", headers=hdr(6300)).json()["workshop"][0] == "ТО принтера"
    assert client.get("/api/work/dict", headers=hdr(5000)).json()["workshop"] is None
    uid = str(uuid.uuid4())
    body = {"client_uid": uid, "object_id": 0, "zone_code": "print", "started_at": "2026-11-05T09:00:00+05:00", "workshop": "ТО принтера"}
    assert client.post("/api/shifts/start", json={**body, "client_uid": str(uuid.uuid4())}, headers=hdr(5000)).status_code == 400   # художник
    s = client.post("/api/shifts/start", json=body, headers=hdr(6300)).json()
    assert s["kind"] == "workshop" and s["object_title"] == "Мастерская · ТО принтера" and s["object_id"] == 0
    f = client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": "2026-11-05T15:00:00+05:00", "area_m2": 30,
                                                "work_done": "Чистка головы, замена демпферов"}, headers=hdr(6300)).json()
    assert f["status"] == "submitted" and f["bonus"] is None and f["plan_m2"] is None
    # на объекте фото по-прежнему обязательно
    assert client.post("/api/shifts/start", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural",
                                                  "started_at": "2026-11-06T09:00:00+05:00"}, headers=hdr(5000)).status_code == 422
    with db.pool.connection() as c:
        c.execute("UPDATE shifts SET status='approved' WHERE person_id=%s", (pid,))
    rows = client.post("/api/fin/payroll/2026-11/compute", headers=hdr(1000)).json()["rows"]
    assert any(r["name"] == "Оператор" for r in rows)
