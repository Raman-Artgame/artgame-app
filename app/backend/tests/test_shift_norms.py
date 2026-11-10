import uuid

from artgame import constants as consts
from artgame import db
from conftest import hdr
from test_work import setup_people

ROWS = [[k, "", "", v, "", who, "Утверждено"] for k, v, who in [
    ("shift.hours", "10", "производство"), ("norm.mural.medium", "10", "производство, моп"),
    ("norm.k.height", "0,8", "производство, моп"), ("norm.k.outdoor", "0,9", "производство, моп"),
    ("norm.role.support", "0,5", "производство, моп"), ("print.plan_per_shift", "18", "производство"),
    ("print.tech.printer", "Maxwave MW-GP200", "производство"), ("pay.print.bonus_step_m2", "5", "head"),
    ("pay.print.bonus_operator", "1000", "head"), ("pay.print.bonus_master", "2000", "head")]]


def shift(client, tg, zone, m2, **kw):
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": zone, "area_m2": m2,
            "started_at": "2026-11-04T09:00:00+05:00", "ended_at": "2026-11-04T19:00:00+05:00", **kw}
    r = client.post("/api/shifts", json=body, headers=hdr(tg))
    assert r.status_code == 200, r.text
    return r.json()


def test_mural_norm_and_print_bonus(client):
    ids = setup_people(client)
    with db.pool.connection() as c:
        consts.store_if_changed(c, consts.parse_rows(ROWS))
    assert client.get("/api/work/dict", headers=hdr(4000)).json()["printer"] == "Maxwave MW-GP200"
    # роспись: Средний 10 м² × высота 0,8 × улица 0,9 = 7,2 м²; сделал 9 → КПД 125%
    s = shift(client, 2000, "mural", 9, complexity="medium", at_height=True, outdoor=True)
    assert float(s["plan_m2"]) == 7.2 and float(s["kpd"]) == 1.25 and s["bonus"] is None
    # саппорт — половина нормы художника
    client.post(f"/api/people/{ids[2000]}", json={"role_code": "support", "zones": ["mural"]}, headers=hdr(1000))
    assert float(shift(client, 2000, "mural", 5, complexity="medium")["plan_m2"]) == 5
    # печать: план 18, напечатал 29 → 2 полных шага по 5 м² → мастеру 2 × 2000
    p = shift(client, 4000, "print", 29, printer="Maxwave MW-GP200")
    assert float(p["plan_m2"]) == 18 and float(p["bonus"]) == 4000 and p["printer"] == "Maxwave MW-GP200"
    assert float(shift(client, 4000, "print", 15)["bonus"]) == 0
    # бонус видит сам человек, а проверяющий — нет; HEAD видит
    assert sorted(float(x["bonus"]) for x in client.get("/api/my", headers=hdr(4000)).json()["shifts"]) == [0, 4000]
    lead = client.get("/api/review", headers=hdr(3000)).json()["shifts"]
    assert lead and all("bonus" not in x for x in lead)
    assert any(x.get("bonus") for x in client.get("/api/review", headers=hdr(1000)).json()["shifts"])
    # неизвестная сложность — ошибка
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "complexity": "x",
            "started_at": "2026-11-04T09:00:00+05:00"}
    assert client.post("/api/shifts", json=body, headers=hdr(3000)).status_code == 400
