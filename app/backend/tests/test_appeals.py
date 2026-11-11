"""Проверка в две ступени и обращения на правку (HEAD 11.11): куратор оценивает (1–5★ + комментарий), утверждает HEAD;
смены кураторов — сразу к HEAD; куратор не успел за 24 ч — к HEAD «без оценки»; «утвердить все 4–5★».
Обращение «не внёс / ошибся» идёт тем же путём; закрытый месяц не переоткрываем — разница в ФОТ месяца утверждения."""
import uuid
from datetime import date

from artgame import appeals, db, finance
from conftest import hdr
from test_finance import setup, uid

D5 = date(2026, 11, 5)


def ask(client, tg, **kw):
    return client.post("/api/appeals", json={"client_uid": uid(), **kw}, headers=hdr(tg))


def late_shift(client, tg, day="2026-11-05", hours=10, **kw):
    return ask(client, tg, kind="shift_late", why="забыл внести, был без связи", day=day, object_id=731, zone_code="mural",
               hours=hours, start_time="9:00", work_done="грунт и контур", **kw)


def approved_shift(client, tg, start, end):
    s = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 731, "zone_code": "mural", "started_at": start, "ended_at": end},
                    headers=hdr(tg)).json()
    client.post(f"/api/shift/{s['id']}/review", json={"approve": True}, headers=hdr(1000))
    return s["id"]


def piece(client, ym, pid):
    client.post(f"/api/fin/payroll/{ym}/compute", headers=hdr(1000))
    with db.pool.connection() as c:
        return {r["kind"]: (float(r["amount"]), r["detail"]) for r in c.execute(
            """SELECT a.kind, a.amount, a.detail FROM fin_accruals a JOIN fin_payees f ON f.id=a.payee_id
               WHERE a.period=%s AND f.person_id=%s AND a.status='active'""", (ym, pid)).fetchall()}


def test_curator_then_head_24h_and_bulk(client, monkeypatch):
    ids = setup(client, monkeypatch)
    s1 = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 731, "zone_code": "mural",
                                          "started_at": "2026-11-04T09:00:00+05:00", "ended_at": "2026-11-04T19:00:00+05:00"}, headers=hdr(2000)).json()
    s2 = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 731, "zone_code": "mural",
                                          "started_at": "2026-11-05T09:00:00+05:00", "ended_at": "2026-11-05T19:00:00+05:00"}, headers=hdr(2000)).json()
    own = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 731, "zone_code": "mural",
                                           "started_at": "2026-11-05T09:00:00+05:00", "ended_at": "2026-11-05T19:00:00+05:00"}, headers=hdr(3000)).json()
    pulse = lambda: client.get("/api/head/pulse", headers=hdr(1000)).json()["review"]  # noqa: E731
    p = pulse()
    assert p["shifts"] == 1 and p["curating"] == 2          # у HEAD только смена Главного; две ждут куратора
    rv = {x["id"]: x["stage"] for x in client.get("/api/review", headers=hdr(1000)).json()["shifts"]}
    assert rv == {s1["id"]: "wait", s2["id"]: "wait", own["id"]: "direct"}
    assert client.post(f"/api/shift/{s1['id']}/rate", json={"stars": 5, "note": "чисто"}, headers=hdr(3000)).json()["ok"]
    with db.pool.connection() as c:   # куратор не успел за сутки
        c.execute("UPDATE shifts SET submitted_at = now() - interval '25 hours' WHERE id=%s", (s2["id"],))
    rv = {x["id"]: x for x in client.get("/api/review", headers=hdr(1000)).json()["shifts"]}
    assert rv[s1["id"]]["stage"] == "rated" and rv[s1["id"]]["cur_name"] == "P3000" and rv[s2["id"]]["stage"] == "late"
    p = pulse()
    assert p["shifts"] == 3 and p["curating"] == 0 and p["rated_good"] == 1
    # «Утвердить все 4–5★» — только оценённые
    assert client.post("/api/review/bulk", json={"min_stars": 4}, headers=hdr(3000)).status_code == 403
    assert client.post("/api/review/bulk", json={"min_stars": 4}, headers=hdr(1000)).json()["approved"] == 1
    st = {x["id"]: x["status"] for x in client.get("/api/my", headers=hdr(2000)).json()["shifts"]}
    assert st == {s1["id"]: "approved", s2["id"]: "submitted"}
    assert ids


def test_no_curator_goes_straight_to_head(client, monkeypatch):
    setup(client, monkeypatch)
    pid = client.post("/api/register", json={"full_name": "Оператор"}, headers=hdr(9100)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "print_operator", "zones": ["print"]}, headers=hdr(1000))
    s = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 731, "zone_code": "print",
                                         "started_at": "2026-11-04T09:00:00+05:00", "ended_at": "2026-11-04T19:00:00+05:00"}, headers=hdr(9100)).json()
    assert [x["stage"] for x in client.get("/api/review", headers=hdr(1000)).json()["shifts"] if x["id"] == s["id"]] == ["direct"]


def test_late_shift_open_month(client, monkeypatch):
    ids = setup(client, monkeypatch)
    monkeypatch.setattr(finance, "now_ym", lambda: "2026-11")
    assert ask(client, 2000, kind="shift_late", why="да", day="2026-11-05").status_code == 422          # «почему» — от 5 знаков
    assert late_shift(client, 2000, day="2030-01-01").status_code == 400                                     # будущее
    a = late_shift(client, 2000).json()
    assert a["status"] == "submitted" and a["kind_title"] == "Не внёс смену"
    assert late_shift(client, 2000).status_code == 409                                                       # тот же день — уже подано
    # куратор видит обращение младшего, оценивает звёздами; утвердить не может
    cur = client.get("/api/review", headers=hdr(3000)).json()["appeals"]
    assert [x["id"] for x in cur] == [a["id"]]
    assert client.post(f"/api/appeals/{a['id']}/decide", json={"approve": True}, headers=hdr(3000)).status_code == 403
    assert client.post(f"/api/appeals/{a['id']}/rate", json={"ok": True}, headers=hdr(3000)).status_code == 400   # смене — звёзды
    assert client.post(f"/api/appeals/{a['id']}/rate", json={"stars": 4, "note": "был на объекте"}, headers=hdr(3000)).json()["ok"]
    assert client.get("/api/review", headers=hdr(3000)).json()["appeals"] == []
    h = client.get("/api/review", headers=hdr(1000)).json()["appeals"]
    assert h[0]["stage"] == "rated" and h[0]["cur_stars"] == 4 and not h[0]["closed"]
    r = client.post(f"/api/appeals/{a['id']}/decide", json={"approve": True}, headers=hdr(1000)).json()
    assert r["status"] == "approved"
    s = [x for x in client.get("/api/my", headers=hdr(2000)).json()["shifts"] if x["id"] == r["result_id"]][0]
    assert s["status"] == "approved" and s["appeal_id"] == a["id"] and s["cur_stars"] == 4 and s["pay_ym"] is None
    assert piece(client, "2026-11", ids[2000])["piece"][0] == 15000
    assert client.get("/api/appeals/my", headers=hdr(2000)).json()[0]["status"] == "approved"


def test_late_shift_closed_month_paid_now(client, monkeypatch):
    ids = setup(client, monkeypatch)
    monkeypatch.setattr(finance, "now_ym", lambda: "2026-12")   # ноябрь уже закрыт
    a = late_shift(client, 2000, day="2026-11-06").json()
    r = client.post(f"/api/appeals/{a['id']}/decide", json={"approve": True}, headers=hdr(1000)).json()   # HEAD может и без оценки
    with db.pool.connection() as c:
        assert c.execute("SELECT pay_ym FROM shifts WHERE id=%s", (r["result_id"],)).fetchone()["pay_ym"] == "2026-12"
    assert "piece" not in piece(client, "2026-11", ids[2000])                 # прошлый месяц не трогаем
    dec = piece(client, "2026-12", ids[2000])["piece"]
    assert dec[0] == 15000 and "по обращению" in dec[1]


def test_fix_shift_closed_month_delta(client, monkeypatch):
    ids = setup(client, monkeypatch)
    sid = approved_shift(client, 2000, "2026-11-04T09:00:00+05:00", "2026-11-04T19:00:00+05:00")
    monkeypatch.setattr(finance, "now_ym", lambda: "2026-12")
    assert ask(client, 2000, kind="shift_fix", target_id=sid, why="работал до 21:00, не дописал").status_code == 400   # ничего не меняет
    a = ask(client, 2000, kind="shift_fix", target_id=sid, hours=12, why="работал до 21:00, не дописал").json()
    assert a["old"]["hours"] == 10 and a["data"]["hours"] == 12
    assert client.post(f"/api/appeals/{a['id']}/rate", json={"ok": True}, headers=hdr(3000)).json()["ok"]
    r = client.post(f"/api/appeals/{a['id']}/decide", json={"approve": True}, headers=hdr(1000)).json()
    assert r["pay_delta"] == 3000                                              # 2 ч сверх 10 × 1500
    with db.pool.connection() as c:                                            # сама смена прошлого месяца не меняется
        s = c.execute("SELECT ended_at, started_at FROM shifts WHERE id=%s", (sid,)).fetchone()
        assert (s["ended_at"] - s["started_at"]).total_seconds() == 36000
    assert piece(client, "2026-12", ids[2000])["appeal"][0] == 3000


def test_fix_expense_open_month_and_reject(client, monkeypatch):
    setup(client, monkeypatch)
    monkeypatch.setattr(finance, "now_ym", lambda: "2026-11")
    e = client.post("/api/expenses", json={"client_uid": uid(), "object_id": 731, "zone_code": "mural", "category": "paint",
                                           "amount": 7000, "paid_by": "own"}, headers=hdr(2000)).json()
    client.post(f"/api/expense/{e['id']}/review", json={"approve": True}, headers=hdr(1000))
    a = ask(client, 2000, kind="expense_fix", target_id=e["id"], amount=8000, why="в чеке 8000, ошибся цифрой").json()
    assert ask(client, 2000, kind="expense_fix", target_id=e["id"], amount=9000, why="ещё раз подаю").status_code == 409
    assert client.post(f"/api/appeals/{a['id']}/decide", json={"approve": False}, headers=hdr(1000)).status_code == 400   # отказ — с причиной
    assert client.post(f"/api/appeals/{a['id']}/decide", json={"approve": True}, headers=hdr(1000)).json()["pay_delta"] is None
    x = [y for y in client.get("/api/my", headers=hdr(2000)).json()["expenses"] if y["id"] == e["id"]][0]
    assert float(x["amount"]) == 8000 and x["payout_status"] == "to_pay"
    # не внёс расход: отказ с причиной; своё — можно отменить, пока не решено
    b = ask(client, 2000, kind="expense_late", day="2026-11-05", object_id=731, zone_code="mural", category="paint",
            amount=500, why="забыл чек в машине").json()
    client.post(f"/api/appeals/{b['id']}/decide", json={"approve": False, "reason": "нет чека"}, headers=hdr(1000))
    c2 = ask(client, 2000, kind="expense_late", day="2026-11-06", object_id=731, zone_code="mural", category="paint",
             amount=600, why="забыл чек в машине").json()
    assert client.post(f"/api/appeals/{c2['id']}/cancel", headers=hdr(2000)).json()["ok"]
    st = {x["id"]: (x["status"], x["reason"]) for x in client.get("/api/appeals/my", headers=hdr(2000)).json()}
    assert st[b["id"]] == ("rejected", "нет чека") and st[c2["id"]][0] == "cancelled"
    assert uuid and D5 and appeals
