"""HEAD 10.11: выплаты по понедельникам — саппортам смены, всем чеки «свои деньги»; «Выплачено» у HEAD, статус у сотрудника."""
import uuid

from conftest import hdr
from test_dual_role import _shift
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401

from artgame import db


def test_weekly_payouts(client, team):  # noqa: F811
    s = _shift(client, 2000, "mural", 3)                                                   # саппорт
    client.post(f"/api/shift/{s['id']}/review", json={"approve": True}, headers=hdr(1000))
    e = client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "category": "paint",
                                           "amount": 4500, "paid_by": "own"}, headers=hdr(5000)).json()   # художник, свои деньги
    co = client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "category": "paint",
                                            "amount": 9000, "paid_by": "company"}, headers=hdr(5000)).json()
    for x in (e, co):
        client.post(f"/api/expense/{x['id']}/review", json={"approve": True}, headers=hdr(1000))
    assert client.get("/api/fin/weekly", headers=hdr(5000)).status_code == 403
    w = client.get("/api/fin/weekly", headers=hdr(1000)).json()
    rows = {r["person_id"]: r for r in w["rows"]}
    assert rows[team[2000]]["weekly"] and rows[team[2000]]["total"] == VALS["pay.support.shift"]
    assert rows[team[5000]]["total"] == 4500 and rows[team[5000]]["checks"] == 1   # «деньги компании» — не к выплате
    assert w["total"] == VALS["pay.support.shift"] + 4500 and w["monday"]
    art = rows[team[5000]]
    body = {"client_uid": str(uuid.uuid4()), "payee_id": art["payee_id"], "account": "kaspi", "op_date": w["monday"], "amount": 4000}
    assert client.post("/api/fin/weekly/pay", json=body, headers=hdr(1000)).status_code == 409   # сумма не та
    assert client.post("/api/fin/weekly/pay", json={**body, "amount": 4500}, headers=hdr(1000)).json()["paid"] == 4500
    assert client.post("/api/fin/weekly/pay", json={**body, "amount": 4500}, headers=hdr(1000)).json()["repeat"]   # повтор
    mine = {x["id"]: x for x in client.get("/api/my", headers=hdr(5000)).json()["expenses"]}
    assert mine[e["id"]]["payout_status"] == "paid"
    sup = rows[team[2000]]
    client.post("/api/fin/weekly/pay", json={"client_uid": str(uuid.uuid4()), "payee_id": sup["payee_id"], "account": "kaspi",
                                             "op_date": w["monday"], "amount": sup["total"]}, headers=hdr(1000))
    assert client.get("/api/fin/weekly", headers=hdr(1000)).json()["rows"] == []
    my = client.get("/api/fin/my?ym=2026-11", headers=hdr(2000)).json()
    assert my["paid"] == VALS["pay.support.shift"] and my["left"] == 0
    with db.pool.connection() as c:
        assert c.execute("SELECT count(*) n FROM fin_accruals").fetchone()["n"] == 0   # расчёт онлайн, ничего не пишет


def test_trip_costs_and_receipt(client, team, monkeypatch):  # noqa: F811
    """HEAD 10.11: галочка «Командировка» в проекте → пункты расходов; питание пересчитывается; выплата с чеком перевода."""
    from artgame import drive
    monkeypatch.setattr(drive, "save_receipt", lambda conn, z, name, data, deal_id=None: "drv-r")
    from psycopg.types.json import Jsonb
    with db.pool.connection() as c:
        c.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                  ("t2", Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "head"} for k, v in {**VALS, "pay.trip_food": 3000}.items()})))
    s = _shift(client, 2000, "mural", 3)
    client.post(f"/api/shift/{s['id']}/review", json={"approve": True}, headers=hdr(1000))
    d = client.get("/api/objects/731/trip-costs", headers=hdr(3000)).json()
    assert d["can_edit"] and not d["on"] and [i["code"] for i in d["items"]][:2] == ["lodging", "trip_road"]
    assert client.get("/api/objects/731/trip-costs", headers=hdr(5000)).json()["can_edit"] is False
    assert client.post("/api/objects/731/trip-set", json={"trip": True}, headers=hdr(5000)).status_code == 403
    r = client.post("/api/objects/731/trip-set", json={"trip": True}, headers=hdr(3000)).json()     # Главный художник
    assert r["on"] and r["retrip"] == 1 and r["food"]["days"] == 1 and r["food"]["amount"] == 3000
    body = {"client_uid": str(uuid.uuid4()), "item": "lodging", "amount": 45000, "note": "3 ночи"}
    r = client.post("/api/objects/731/trip-costs", json=body, headers=hdr(3000)).json()
    assert r["costs"][0]["category_title"].startswith("Проживание") and r["costs"][0]["status"] == "submitted"
    r = client.post("/api/objects/731/trip-costs", json={**body, "client_uid": str(uuid.uuid4()), "item": "trip_road", "amount": 30000,
                                                       "receipt": JPEG}, headers=hdr(1000)).json()
    road = next(c for c in r["costs"] if c["category"] == "trip_road")
    assert road["status"] == "approved" and road["paid_by"] == "company" and road["receipt_url"]
    assert r["total"] == 45000 + 30000 + 3000
    # выплата саппорту в понедельник: смена + питание, с чеком перевода; видна в «уже выплачено»
    w = client.get("/api/fin/weekly", headers=hdr(1000)).json()
    sup = next(x for x in w["rows"] if x["person_id"] == team[2000])
    assert sup["total"] == VALS["pay.support.shift"] + 3000
    client.post("/api/fin/weekly/pay", json={"client_uid": str(uuid.uuid4()), "payee_id": sup["payee_id"], "account": "kaspi",
                                             "op_date": w["monday"], "amount": sup["total"], "receipt": JPEG}, headers=hdr(1000))
    paid = client.get("/api/fin/weekly", headers=hdr(1000)).json()["paid"]
    assert paid[0]["name"] == "P2000" and paid[0]["receipt_url"]
    # наличными: без чека, сотрудник подтверждает «Получил»
    e = client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "category": "paint",
                                           "amount": 2000, "paid_by": "own"}, headers=hdr(5000)).json()
    client.post(f"/api/expense/{e['id']}/review", json={"approve": True}, headers=hdr(1000))
    art = next(x for x in client.get("/api/fin/weekly", headers=hdr(1000)).json()["rows"] if x["person_id"] == team[5000])
    client.post("/api/fin/weekly/pay", json={"client_uid": str(uuid.uuid4()), "payee_id": art["payee_id"], "account": "cash",
                                             "op_date": w["monday"], "amount": 2000}, headers=hdr(1000))
    pay = client.get("/api/fin/my?ym=2026-11", headers=hdr(5000)).json()["payments"][-1]
    assert pay["account_code"] == "cash" and pay["ack_at"] is None
    assert client.post(f"/api/fin/my/ack/{pay['id']}", headers=hdr(2000)).status_code == 404     # чужую — нельзя
    assert client.post(f"/api/fin/my/ack/{pay['id']}", headers=hdr(5000)).json()["ack_at"]
    assert client.get("/api/fin/weekly", headers=hdr(1000)).json()["paid"][0]["ack_at"]


def test_pulse_kpi(client, monkeypatch):
    """HEAD 10.11: плитки Пульта — ждут оплаты саппорт/расходы, упущено, долг клиентов, в работе."""
    from artgame import bx
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))

    def fake(method, params, fresh=False):
        f = params["filter"]
        if f.get("STAGE_SEMANTIC_ID") == "F":
            return [{"ID": "1", "UF_CRM_ARTGAME_FIN03_LOST": "280000|KZT"}, {"ID": "2", "UF_CRM_ARTGAME_FIN03_LOST": None}]
        if f.get("STAGE_ID") == "UC_AV00QK":
            return [{"ID": "3", "OPPORTUNITY": "1500000.00"}]
        return [{"ID": "4", "UF_CRM_ARTGAME_FIN03_DEBT": "500000|KZT"}, {"ID": "5", "UF_CRM_ARTGAME_FIN03_DEBT": "0|KZT"}]
    monkeypatch.setattr(bx, "read_all", fake)
    k = client.get("/api/fin/kpi", headers=hdr(1000)).json()
    assert k["lost"] == {"sum": 280000, "count": 1} and k["debt"] == {"sum": 500000, "count": 1}
    assert k["in_work"] == {"sum": 1500000, "count": 1} and k["due_support"] == 0 and k["due_expenses"] == 0
    monkeypatch.setattr(bx, "read_all", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("нет связи")))
    assert "bx_error" in client.get("/api/fin/kpi", headers=hdr(1000)).json()
