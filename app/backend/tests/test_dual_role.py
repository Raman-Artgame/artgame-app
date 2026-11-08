"""Две роли у одного человека (HEAD 08.11, «Оба способа»): «Я сейчас» + роль смены по объекту, ФОТ по ставке роли смены."""
import uuid

from artgame import db
from conftest import hdr
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401


def _shift(client, tg, zone, day, role=None):
    uid = str(uuid.uuid4())
    body = {"client_uid": uid, "object_id": 731, "zone_code": zone, "started_at": f"2026-11-{day:02d}T09:00:00+05:00", "photo_before": JPEG}
    if role:
        body["role"] = role
    s = client.post("/api/shifts/start", json=body, headers=hdr(tg)).json()
    client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": f"2026-11-{day:02d}T19:00:00+05:00", "area_m2": 5, "work_done": "Работа",
                                            "photo_after": JPEG}, headers=hdr(tg))
    return s


def test_dual_role(client, team):  # noqa: F811
    pid = client.post("/api/register", json={"full_name": "Оператор Саппорт"}, headers=hdr(6100)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "print_operator", "zones": ["print", "mural"]}, headers=hdr(1000))
    assert client.post(f"/api/people/{pid}", json={"extra_roles": ["nope"]}, headers=hdr(1000)).status_code == 400
    assert client.post(f"/api/people/{pid}", json={"extra_roles": ["support", "head", "print_operator"]}, headers=hdr(1000)).json()["extra_roles"] == ["support"]
    with db.pool.connection() as c:
        c.execute("UPDATE constants_versions SET values = values || '{\"pay.print.operator\": {\"value\": \"15000\", \"status\": \"Утверждено\", \"who\": \"head\"}}'::jsonb")
    me = client.get("/api/me", headers=hdr(6100)).json()
    assert me["role_code"] == "print_operator" and me["roles"] == ["print_operator", "support"]
    # «Я сейчас: Саппорт» — права и меню от саппорта; чужую роль сервер не даёт
    assert client.get("/api/me", headers={**hdr(6100), "X-Act-Role": "support"}).json()["role_code"] == "support"
    assert client.get("/api/me", headers={**hdr(6100), "X-Act-Role": "head"}).json()["role_code"] == "print_operator"
    assert client.get("/api/me", headers={**hdr(6100), "X-Act-Role": "artist"}).json()["role_code"] == "print_operator"
    # роль смены: по зоне объекта (роспись → саппорт, печать → оператор), либо выбранная
    assert _shift(client, 6100, "mural", 3)["role_code"] == "support"
    assert _shift(client, 6100, "print", 4)["role_code"] == "print_operator"
    assert _shift(client, 6100, "mural", 5, role="print_operator")["role_code"] == "print_operator"
    with db.pool.connection() as c:
        c.execute("UPDATE shifts SET status='approved' WHERE person_id=%s", (pid,))
    out = client.post("/api/fin/payroll/2026-11/compute", headers=hdr(1000)).json()
    row = next(r for r in out["rows"] if r["name"] == "Оператор Саппорт")
    piece = next(l for l in row["lines"] if l["kind"] == "piece")
    assert float(piece["amount"]) == 10000 + 15000 * 2 and "Саппорт 1" in piece["detail"]
    rate = client.get("/api/fin/my", headers=hdr(6100)).json()["rate"]
    assert {x["label"] for x in rate} >= {"Оператор настенного принтера · Смена 10 ч", "Саппорт · Смена 10 ч"}
