"""HEAD 12.11: график постоянных оплат — напоминание в день оплаты (Пульт и бот), «Оплачено» с чеком, подписки — автосписание."""
import uuid
from datetime import date, datetime

from psycopg.types.json import Jsonb

from conftest import hdr
from test_files import JPEG

from artgame import db, notify, recurring
from artgame.finance import TZ

VALS = {"fin.fixed.rent_studio_ast": 300000, "fin.fixed.sub.claude": 50000, "fin.fixed.bitrix_year": 350000, "fin.fixed.telephony": 15000}


def _setup(client):
    with db.pool.connection() as c:
        c.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                  ("r", Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "head"} for k, v in VALS.items()})))
        c.execute("UPDATE fin_recurring SET start_date='2026-01-01'")
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))


def _by(conn, today, title):
    return next(x for x in recurring.items(conn, today) if x["title"] == title)


def test_cycles_and_statuses(client):
    _setup(client)
    with db.pool.connection() as c:
        c.execute("UPDATE fin_recurring SET start_date='2026-11-12'")   # 1.11 — до приложения, долга нет
        assert _by(c, date(2026, 11, 20), "Аренда студии, Астана")["status"] == "later"
        assert _by(c, date(2026, 11, 29), "Аренда студии, Астана")["status"] == "soon"
        x = _by(c, date(2026, 12, 1), "Аренда студии, Астана")
        assert x["status"] == "today" and x["cycle"] == "2026-12" and x["amount"] == 300000     # сумма — из «Значений»
        y = _by(c, date(2027, 1, 3), "Аренда студии, Астана")
        assert y["status"] == "overdue" and y["cycle"] == "2026-12"                             # не оплачено — висит
        b = _by(c, date(2027, 8, 14), "Битрикс24, за год")
        assert b["status"] == "today" and b["cycle"] == "2027" and b["amount"] == 350000
        assert _by(c, date(2026, 12, 1), "Аренда магазина")["amount"] is None                   # ключа нет — сумма при оплате
        assert recurring.cycles({"every": "month", "day": 31}, date(2026, 12, 5))[1:] == [("2026-12", date(2026, 12, 31)), ("2027-01", date(2027, 1, 31))]
        assert recurring.cycles({"every": "month", "day": 31}, date(2027, 2, 5))[1][1] == date(2027, 2, 28)


def test_pay_with_receipt_and_cash(client, monkeypatch):
    from artgame import drive
    monkeypatch.setattr(drive, "save_receipt", lambda conn, z, name, data, deal_id=None: "drv-rec")
    _setup(client)
    with db.pool.connection() as c:
        rid = c.execute("SELECT id FROM fin_recurring WHERE title='Баланс телефонии'").fetchone()["id"]
    today = datetime.now(TZ).date()
    cyc = f"{today:%Y-%m}"
    with db.pool.connection() as c:
        c.execute("UPDATE fin_recurring SET start_date=%s", (today.replace(day=1),))   # прошлый месяц — до приложения
    body = {"client_uid": str(uuid.uuid4()), "cycle": cyc, "account": "kaspi", "op_date": str(today), "amount": 17500}
    assert client.post(f"/api/fin/recurring/{rid}/pay", json=body, headers=hdr(1000)).status_code == 400    # переводом — без чека нельзя
    assert client.post(f"/api/fin/recurring/{rid}/pay", json={**body, "cycle": "2026"}, headers=hdr(1000)).status_code == 400
    r = client.post(f"/api/fin/recurring/{rid}/pay", json={**body, "receipt": JPEG}, headers=hdr(1000)).json()
    assert r["ok"] and r["ledger"]
    assert client.post(f"/api/fin/recurring/{rid}/pay", json={**body, "receipt": JPEG}, headers=hdr(1000)).json()["repeat"]
    again = {**body, "client_uid": str(uuid.uuid4()), "account": "cash"}
    assert client.post(f"/api/fin/recurring/{rid}/pay", json=again, headers=hdr(1000)).status_code == 409    # период уже оплачен
    with db.pool.connection() as c:
        row = c.execute("SELECT * FROM fin_ledger WHERE id=%s", (r["ledger"],)).fetchone()
        assert row["article_code"] == "telephony" and row["direction"] == "out" and float(row["amount"]) == 17500 and row["receipt_file_id"]
        assert row["period"] == cyc and row["source_ref"] == f"recurring:{rid}:{cyc}"
    lst = client.get("/api/fin/recurring", headers=hdr(1000)).json()
    tel = next(x for x in lst["items"] if x["id"] == rid)
    assert tel["status"] in ("paid", "later", "soon") and tel["last_paid"]["amount"] == 17500
    assert lst["paid"][0]["title"] == "Баланс телефонии" and lst["paid"][0]["receipt_url"]
    # наличными — без чека можно
    with db.pool.connection() as c:
        rid2 = c.execute("SELECT id FROM fin_recurring WHERE title='Аренда студии, Астана'").fetchone()["id"]
    assert client.post(f"/api/fin/recurring/{rid2}/pay", json={**again, "client_uid": str(uuid.uuid4()), "amount": 300000},
                       headers=hdr(1000)).json()["ok"]
    assert client.get("/api/fin/recurring", headers=hdr(1000)).status_code == 200
    assert client.post(f"/api/fin/recurring/{rid}", json={"title": "Телефон", "article": "telephony", "every": "month", "day": 3},
                       headers=hdr(1000)).json()["ok"]
    assert client.post("/api/fin/recurring", json={"title": "Коммуналка мастерской", "article": "rent_workshop", "every": "month", "day": 11},
                       headers=hdr(1000)).json()["id"]
    assert client.post("/api/fin/recurring", json={"title": "x", "article": "payroll", "every": "month", "day": 1}, headers=hdr(1000)).status_code == 422
    assert client.post("/api/fin/recurring", json={"title": "Год", "article": "bitrix", "every": "year", "day": 1}, headers=hdr(1000)).status_code == 400


def test_auto_and_bot(client, monkeypatch):
    _setup(client)
    sent = []
    monkeypatch.setattr(notify, "SEND", lambda tg, text: sent.append((tg, text)))
    with db.pool.connection() as c:
        c.execute("UPDATE fin_recurring SET active = (title IN ('Claude', 'Аренда студии, Астана'))")
        c.execute("UPDATE fin_recurring SET day=12 WHERE title='Claude'")
        c.execute("UPDATE fin_recurring SET day=12, start_date='2026-11-12' WHERE title='Аренда студии, Астана'")
    now = datetime(2026, 11, 12, 9, 5, tzinfo=TZ)
    monkeypatch.setattr(recurring, "_today", lambda: now.date())
    assert notify.head_recurring(datetime(2026, 11, 12, 8, 30, tzinfo=TZ)) == 0     # до 9:00 молчим
    assert notify.head_recurring(now) == 1
    txt = sent[0][1]
    assert "Аренда студии, Астана — 300 000 ₸" in txt and "Списано автоматически" in txt and "Claude — 50 000 ₸" in txt
    assert notify.head_recurring(now) == 0                                          # раз в день
    with db.pool.connection() as c:
        auto = c.execute("SELECT * FROM fin_ledger WHERE note LIKE 'Автосписание%%'").fetchall()
        assert len(auto) == 2 and {float(a["amount"]) for a in auto} == {50000} and auto[-1]["article_code"] == "sub_claude"   # октябрь и ноябрь
        assert [x["title"] for x in recurring.due_now(c, now.date())] == ["Аренда студии, Астана"]   # автосписание — не к оплате
        c.execute("UPDATE fin_ledger SET status='cancelled' WHERE id=%s", (auto[-1]["id"],))       # не та сумма — HEAD отменил
        recurring.auto_book(c, now.date())
        assert c.execute("SELECT count(*) n FROM fin_ledger WHERE note LIKE 'Автосписание%%'").fetchone()["n"] == 2   # не повторяет
        assert {x["title"] for x in recurring.due_now(c, now.date())} == {"Аренда студии, Астана", "Claude"}
    p = client.get("/api/head/pulse", headers=hdr(1000)).json()
    assert p["bills"] and all(b["status"] in ("today", "overdue") for b in p["bills"])
