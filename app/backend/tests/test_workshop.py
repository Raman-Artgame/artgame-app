"""«Мастерская» без проекта (HEAD 09.11): печать — ТО принтера и т. п.; оплата как смена по часам, без плана и бонуса."""
import uuid

from artgame import db
from conftest import hdr
from test_backfill import _today
from test_production import VALS, Copying, team  # noqa: F401


def test_workshop_shift(client, team):  # noqa: F811
    pid = client.post("/api/register", json={"full_name": "Оператор"}, headers=hdr(6300)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "print_operator", "zones": ["print"]}, headers=hdr(1000))
    assert client.get("/api/work/dict", headers=hdr(6300)).json()["workshop"][0] == "ТО принтера"
    d5 = client.get("/api/work/dict", headers=hdr(5000)).json()   # HEAD 11.11: художникам — «Без объекта»
    assert d5["workshop_zone"] == "mural" and d5["workshop_title"] == "Без объекта" and "Эскиз и пробы" in d5["workshop"]
    uid = str(uuid.uuid4())
    body = {"client_uid": uid, "object_id": 0, "zone_code": "print", "started_at": "2026-11-05T09:00:00+05:00", "workshop": "ТО принтера"}
    assert client.post("/api/shifts/start", json={**body, "client_uid": str(uuid.uuid4())}, headers=hdr(5000)).status_code == 400   # художнику — не печать
    s = client.post("/api/shifts/start", json=body, headers=hdr(6300)).json()
    assert s["kind"] == "workshop" and s["object_title"] == "Мастерская · ТО принтера" and s["object_id"] == 0
    f = client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": "2026-11-05T15:00:00+05:00", "area_m2": 30,
                                                "work_done": "Чистка головы, замена демпферов"}, headers=hdr(6300)).json()
    assert f["status"] == "submitted" and f["bonus"] is None and f["plan_m2"] is None
    # задним числом — тоже можно мастерскую (HEAD 09.11)
    from datetime import timedelta
    from artgame.config import settings
    y = _today() - timedelta(days=1)
    settings.backfill_from, settings.backfill_until = (y - timedelta(days=3)).isoformat(), _today().isoformat()
    ps = client.post("/api/shifts/past", json={"client_uid": str(uuid.uuid4()), "object_id": 0, "zone_code": "print", "day": y.isoformat(),
                                               "hours": 4.5, "work_done": "Замена демпферов", "workshop": "Ремонт и запчасти"}, headers=hdr(6300)).json()
    assert ps["kind"] == "workshop" and ps["object_title"] == "Мастерская · Ремонт и запчасти" and ps["backfill"]
    settings.backfill_from, settings.backfill_until = "2026-11-01", "2026-11-15"
    # на объекте фото по-прежнему обязательно
    assert client.post("/api/shifts/start", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural",
                                                  "started_at": "2026-11-06T09:00:00+05:00"}, headers=hdr(5000)).status_code == 422
    with db.pool.connection() as c:
        c.execute("UPDATE shifts SET status='approved' WHERE person_id=%s", (pid,))
        c.execute("""UPDATE constants_versions SET values = values || jsonb_build_object('pay.print.operator.workshop_hour',
                     jsonb_build_object('value', '1000', 'status', 'Утверждено', 'who', 'head'))""")
    rows = client.post("/api/fin/payroll/2026-11/compute", headers=hdr(1000)).json()["rows"]
    row = next(r for r in rows if r["name"] == "Оператор")
    assert float(next(l for l in row["lines"] if l["kind"] == "piece")["amount"]) == 10500   # (6 + 4,5 задним числом) ч × 1000
    assert {"label": "Мастерская без проекта, в час", "amount": 1000} in client.get("/api/fin/my", headers=hdr(6300)).json()["rate"]


def test_artist_shift_without_object(client, team):  # noqa: F811
    """HEAD 11.11: «смену без объектов всем художникам» — как мастерская у печати, зона роспись."""
    uid = str(uuid.uuid4())
    s = client.post("/api/shifts/start", json={"client_uid": uid, "object_id": 0, "zone_code": "mural", "started_at": "2026-11-05T09:00:00+05:00",
                                               "workshop": "Эскиз и пробы"}, headers=hdr(5000)).json()
    assert s["kind"] == "workshop" and s["object_title"] == "Без объекта · Эскиз и пробы"
    f = client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": "2026-11-05T13:00:00+05:00",
                                                "work_done": "Пробы цвета на холсте"}, headers=hdr(5000)).json()
    assert f["status"] == "submitted" and f["plan_m2"] is None
    # Главный художник оценивает, HEAD видит «Без объекта»
    assert [x["object_title"] for x in client.get("/api/review", headers=hdr(3000)).json()["shifts"] if x["id"] == s["id"]] == ["Без объекта · Эскиз и пробы"]
    mine = [x for x in client.get("/api/my", headers=hdr(5000)).json()["shifts"] if x["id"] == s["id"]][0]
    assert mine["object_title"] == "Без объекта · Эскиз и пробы"
