"""HEAD 10.11: выплаты по понедельникам — саппортам смены, всем чеки «свои деньги»; «Выплачено» у HEAD, статус у сотрудника."""
import uuid

from conftest import hdr
from test_dual_role import _shift
from test_files import JPEG  # noqa: F401
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
