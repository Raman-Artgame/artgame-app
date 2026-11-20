"""HEAD 16.11: авансы с 15 по 20 число — HEAD сам видит, кто сколько заработал, и выплачивает не больше этого."""
import uuid
from datetime import date

from conftest import hdr
from test_dual_role import _shift
from test_production import VALS, Copying, team  # noqa: F401

from artgame import advances, db


def test_advance_by_head(client, team, monkeypatch):  # noqa: F811
    s = _shift(client, 2000, "mural", 3)                                         # саппорт, смена принята
    client.post(f"/api/shift/{s['id']}/review", json={"approve": True}, headers=hdr(1000))
    shift = VALS["pay.support.shift"]
    assert client.get("/api/fin/advances", headers=hdr(2000)).status_code == 403
    body = {"client_uid": str(uuid.uuid4()), "amount": 1000, "account": "kaspi"}
    monkeypatch.setattr(advances, "today", lambda: date(2026, 11, 14))
    a = client.get("/api/fin/advances", headers=hdr(1000)).json()
    assert a["open"] is False and a["rows"] == []
    monkeypatch.setattr(advances, "today", lambda: date(2026, 11, 16))
    a = client.get("/api/fin/advances", headers=hdr(1000)).json()
    sup = next(x for x in a["rows"] if x["name"] and x["earned"] == shift and x["weekly"])
    assert a["open"] and sup["max"] == shift and sup["paid"] == 0
    body["payee_id"] = sup["payee_id"]
    assert client.post("/api/fin/advances/pay", json={**body, "amount": shift + 1}, headers=hdr(1000)).status_code == 409  # больше заработанного
    assert client.post("/api/fin/advances/pay", json=body, headers=hdr(2000)).status_code == 403
    assert client.post("/api/fin/advances/pay", json=body, headers=hdr(1000)).json()["left"] == shift - 1000
    assert client.post("/api/fin/advances/pay", json=body, headers=hdr(1000)).json()["repeat"]                   # повтор
    my = client.get("/api/fin/my?ym=2026-11", headers=hdr(2000)).json()
    assert my["paid"] == 1000 and my["left"] == shift - 1000                     # аванс — в «Выплачено», вычтен из «Осталось»
    a = client.get("/api/fin/advances", headers=hdr(1000)).json()
    assert next(x for x in a["rows"] if x["payee_id"] == sup["payee_id"])["max"] == shift - 1000
    w = client.get("/api/fin/weekly", headers=hdr(1000)).json()                  # понедельник: без аванса
    assert next(x for x in w["rows"] if x["person_id"] == team[2000])["total"] == shift - 1000
    monkeypatch.setattr(advances, "today", lambda: date(2026, 11, 21))
    assert client.post("/api/fin/advances/pay", json={**body, "client_uid": str(uuid.uuid4())}, headers=hdr(1000)).status_code == 409
    with db.pool.connection() as c:
        assert c.execute("SELECT count(*) n FROM fin_accruals").fetchone()["n"] == 0   # расчёт онлайн, ничего не пишет
