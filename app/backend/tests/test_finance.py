"""Финансы (HEAD 06.11): журнал денег и остатки по счетам, получатели ФОТ, начисление из смен / окладов / % МОП / чеков,
выплату отмечает только HEAD, закупки на склад и в мастерскую холстов — из бюджета, сводка месяца."""
import uuid

from psycopg.types.json import Jsonb

from artgame import db, drive, fin
from conftest import hdr

JPG = "data:image/jpeg;base64,/9j/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
YM = "2026-11"
VALS = {"pay.artist.shift": 15000, "pay.artist.hour": 1500, "pay.chief.shift": 20000, "pay.chief.min_month": 150000,
        "shift.hours": 10, "pay.mop.salary": 200000, "vat": 16, "pay.mop.step1.from": 2000000, "pay.mop.step1.pct": 3,
        "pay.mop.step2.from": 7000000, "pay.mop.step2.pct": 4, "pay.mop.step3.from": 15000000, "pay.mop.step3.pct": 5,
        "pay.mop.bonus_plan": 100000, "pay.accountant.month": 120000, "fin.stock.limit_month": 50000,
        "fin.fixed.rent_studio_ast": 300000, "fin.tax.ipn": 10,
        "pay.carpenter.month": 200000, "fin.fixed.bitrix_year": 120000}


def uid():
    return str(uuid.uuid4())


def setup(client, monkeypatch):
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                     ("t", Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "head"} for k, v in VALS.items()})))
        conn.execute("INSERT INTO objects (id, title, city) VALUES (731, 'Кафе', 'Астана')")
    monkeypatch.setattr(drive, "save_office_receipt", lambda folder, name, data: f"drv-{folder}")
    monkeypatch.setattr(drive, "save_photo", lambda *a, **k: "drv-obj")
    # выручка ноября по листу «Проекты 2026»: 11 600 000 с НДС → 10 000 000 без НДС → ступень 2 (4 %)
    monkeypatch.setattr(fin, "month_rows", lambda y, m, fresh=False: [{"id": 1, "sum": 11_600_000.0}])
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    ids = {}
    for tg, role, zones in [(2000, "artist", ["mural"]), (3000, "lead_artist", ["mural"]), (6000, "mop", ["sales"]),
                            (8000, "carpenter", [])]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": zones}, headers=hdr(1000))
        ids[tg] = pid
    return ids


def shift(client, tg, start, end):
    s = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 731, "zone_code": "mural",
                                          "started_at": start, "ended_at": end}, headers=hdr(tg)).json()
    assert client.post(f"/api/shift/{s['id']}/review", json={"approve": True}, headers=hdr(1000)).json()["status"] == "approved"


def test_finance_flow(client, monkeypatch):
    ids = setup(client, monkeypatch)
    # только HEAD
    assert client.get("/api/fin/summary", headers=hdr(2000)).status_code == 403
    # остаток на начало и операции по счетам; перевод — две строки, в остаток компании не влияет
    led = lambda **kw: client.post("/api/fin/ledger", json={"client_uid": uid(), "op_date": "2026-11-01", **kw}, headers=hdr(1000))  # noqa: E731
    assert led(account="kaspi", amount=5_000_000, article="opening").status_code == 200
    assert led(account="cash", amount=300_000, article="opening").status_code == 200
    rent = led(account="kaspi", amount=300_000, article="rent_studio", note="аренда ноябрь").json()
    assert rent["direction"] == "out" and rent["period"] == YM
    assert led(account="kaspi", amount=1_160_000, article="client_payment", deal_id=1601, op_date="2026-11-03").json()["direction"] == "in"
    assert led(account="kaspi", amount=200_000, article="transfer", to_account="cash").status_code == 200
    assert led(account="kaspi", amount=200_000, article="transfer").status_code == 400     # без счёта «куда»
    assert led(account="kaspi", amount=10, article="payroll").status_code == 400            # выплаты — только через ФОТ
    bal = {b["code"]: float(b["balance"]) for b in client.get("/api/fin/summary", params={"ym": YM}, headers=hdr(1000)).json()["cash"]["closing"]}
    assert bal == {"kaspi": 5_000_000 - 300_000 + 1_160_000 - 200_000, "cash": 500_000, "head": 0}
    # смены: художник 2 полные + 1 короткая (4 ч по часу), главный художник 1 смена → доплата до минимума
    shift(client, 2000, "2026-11-04T09:00:00+05:00", "2026-11-04T19:00:00+05:00")
    shift(client, 2000, "2026-11-05T09:00:00+05:00", "2026-11-05T19:00:00+05:00")
    shift(client, 2000, "2026-11-06T09:00:00+05:00", "2026-11-06T13:00:00+05:00")
    shift(client, 3000, "2026-11-04T09:00:00+05:00", "2026-11-04T19:00:00+05:00")
    shift(client, 2000, "2026-10-30T09:00:00+05:00", "2026-10-30T19:00:00+05:00")   # октябрь — не в ноябре
    # чек художника своими на объект (к возмещению) и закупка на склад главным художником
    e = client.post("/api/expenses", json={"client_uid": uid(), "object_id": 731, "zone_code": "mural", "category": "paint",
                                            "amount": 7000, "paid_by": "own"}, headers=hdr(2000)).json()
    client.post(f"/api/expense/{e['id']}/review", json={"approve": True}, headers=hdr(1000))
    # склад: художнику нельзя, плотнику — только мастерская, главный художник в пределах лимита — само
    assert client.post("/api/stock/expenses", json={"client_uid": uid(), "category": "stock_paint", "amount": 1000, "receipt": JPG},
                       headers=hdr(2000)).status_code == 403
    assert client.post("/api/stock/expenses", json={"client_uid": uid(), "category": "stock_paint", "amount": 1000, "receipt": JPG},
                       headers=hdr(8000)).status_code == 400
    s1 = client.post("/api/stock/expenses", json={"client_uid": uid(), "category": "stock_paint", "amount": 40000, "receipt": JPG},
                     headers=hdr(3000)).json()
    assert s1["status"] == "approved" and s1["payout_status"] == "to_pay" and s1["zone_code"] is None
    s2 = client.post("/api/stock/expenses", json={"client_uid": uid(), "category": "stock_tape", "amount": 20000, "receipt": JPG,
                                                  "paid_by": "company"}, headers=hdr(3000)).json()
    assert s2["status"] == "submitted" and s2["over_limit"]
    c1 = client.post("/api/stock/expenses", json={"client_uid": uid(), "category": "canvas_wood", "amount": 25000, "receipt": JPG},
                     headers=hdr(8000)).json()
    assert c1["status"] == "submitted"   # лимита мастерской в «Значениях» нет — к HEAD
    rv = {x["id"]: x for x in client.get("/api/review", headers=hdr(1000)).json()["expenses"]}
    assert rv[s2["id"]]["object_title"] == "Склад · Скотч, плёнка, укрывка · сверх лимита"
    assert rv[c1["id"]]["object_title"] == "Мастерская холстов · Брус и подрамники"
    assert client.get("/api/review", headers=hdr(3000)).json()["expenses"] == []   # склад проверяет только HEAD
    client.post(f"/api/expense/{c1['id']}/review", json={"approve": True}, headers=hdr(1000))
    mine = client.get("/api/stock/expenses", headers=hdr(3000)).json()
    assert mine["limits"]["stock"]["spent"] == 60000 and mine["limits"]["stock"]["left"] == 0 and not mine["all"]
    # получатель без приложения: бухгалтер с окладом из «Значений»
    pl = {x["name"]: x for x in client.get("/api/fin/payees", headers=hdr(1000)).json()}
    acc = pl["Бухгалтер"]                                                    # заведён миграцией 013, оклад из «Значений»
    assert pl["SMM"]["amount_key"] == "pay.smm.month" and pl["P8000"]["scheme"] == "salary"
    # оклад сверх смен (как у Анны): засчитывается в гарантированный минимум
    p3 = pl["P3000"]
    client.post(f"/api/fin/payees/{p3['id']}", json={"name": "P3000", "grp": "core", "scheme": "shifts", "amount": 50000}, headers=hdr(1000))
    assert client.post("/api/fin/payees", json={"name": "Иван", "grp": "nope", "scheme": "salary"}, headers=hdr(1000)).status_code == 400
    # начисление
    r = client.post(f"/api/fin/payroll/{YM}/compute", headers=hdr(1000)).json()
    by = {x["name"]: x for x in r["rows"]}
    assert by["P2000"]["accrued"] == 15000 * 2 + 4 * 1500 + 7000           # 2 смены + 4 ч + возмещение чека
    assert by["P3000"]["accrued"] == 150000 + 40000                         # 20 000 + оклад 50 000 + доплата 80 000 + склад своими
    assert {a["kind"]: float(a["amount"]) for a in by["P3000"]["lines"]}["topup"] == 80000
    assert by["P6000"]["accrued"] == 200000 + 400000                        # оклад + 4 % от 10 млн
    assert by["P8000"]["accrued"] == 200000 + 25000 and any("pay.carpenter.shift" in w for w in r["warn"]) is False
    assert by["Бухгалтер"]["accrued"] == 120000 and by["Бухгалтер"]["group"] == "Офис"
    # повторный пересчёт не удваивает; ручная премия остаётся
    client.post(f"/api/fin/payroll/{YM}/accrual", json={"payee_id": acc["id"], "amount": 10000, "detail": "премия"}, headers=hdr(1000))
    r = client.post(f"/api/fin/payroll/{YM}/compute", headers=hdr(1000)).json()
    assert {x["name"]: x["accrued"] for x in r["rows"]}["Бухгалтер"] == 130000
    assert {x["name"]: x["accrued"] for x in r["rows"]}["P2000"] == 43000
    # выплата: частично, потом остаток → чеки «выплачено»
    pid = by["P2000"]["id"]
    pay = lambda amt: client.post(f"/api/fin/payroll/{YM}/pay", json={"client_uid": uid(), "payee_id": pid, "amount": amt,  # noqa: E731
                                                                    "account": "kaspi", "op_date": "2026-11-15"}, headers=hdr(1000)).json()
    assert pay(20000)["left"] == 23000
    with db.pool.connection() as conn:
        assert conn.execute("SELECT payout_status FROM expenses WHERE id=%s", (e["id"],)).fetchone()["payout_status"] == "to_pay"
    assert pay(23000)["left"] == 0
    with db.pool.connection() as conn:
        assert conn.execute("SELECT payout_status FROM expenses WHERE id=%s", (e["id"],)).fetchone()["payout_status"] == "paid"
    assert client.post(f"/api/fin/payroll/{YM}/pay", json={"client_uid": uid(), "payee_id": pid, "amount": 1, "account": "kaspi",
                                                          "op_date": "2026-11-15"}, headers=hdr(2000)).status_code == 403
    # каждый видит своё
    my = client.get("/api/fin/my", params={"ym": YM}, headers=hdr(2000)).json()
    assert my["accrued"] == 43000 and my["paid"] == 43000 and my["left"] == 0
    # сводка месяца
    s = client.get("/api/fin/summary", params={"ym": YM}, headers=hdr(1000)).json()
    assert s["revenue"]["net"] == 10_000_000 and s["revenue"]["vat"] == 1_600_000
    c = s["costs"]
    assert c["project"] == 7000 and c["stock"] == 40000 and c["canvas"] == 25000 and c["fixed"] == 300000
    assert c["payroll"] == r["accrued"] - 7000 - 40000 - 25000                # возмещения не считаются второй раз
    assert s["profit"] == 10_000_000 - sum(c.values()) and s["ipn"] == round(s["profit"] * 0.10)
    studio = next(b for b in s["budget"] if b["code"] == "rent_studio")
    assert next(b for b in s["budget"] if b["code"] == "bitrix")["plan"] == 10000   # годовая сумма / 12
    assert studio["plan"] == 300000 and studio["fact"] == 300000
    assert s["cash"]["in"] == 1_160_000 and s["cash"]["out"] == 300_000 + 43000
    # отмена выплаты возвращает чек в «к выплате»
    last = [x for x in client.get("/api/fin/ledger", params={"ym": YM}, headers=hdr(1000)).json() if x["article_code"] == "payroll"][0]
    assert client.post(f"/api/fin/ledger/{last['id']}/cancel", headers=hdr(1000)).json()["ok"]
    with db.pool.connection() as conn:
        assert conn.execute("SELECT payout_status FROM expenses WHERE id=%s", (e["id"],)).fetchone()["payout_status"] == "to_pay"


def test_export_rows(client, monkeypatch):
    """Витрина: строки листов собираются из базы; без ARTGAME_FIN_SHEET_ID ничего не пишется."""
    from artgame import fin_export
    from artgame.config import settings
    setup(client, monkeypatch)
    client.post("/api/fin/ledger", json={"client_uid": uid(), "op_date": "2026-11-01", "account": "kaspi", "amount": 1000,
                                         "article": "opening"}, headers=hdr(1000))
    assert client.post("/api/fin/export", headers=hdr(1000)).json()["ok"] is False
    written = {}
    monkeypatch.setattr(settings, "fin_sheet_id", "sheet-x")
    monkeypatch.setattr(fin_export, "write", lambda sid, tabs: written.update(tabs))
    import datetime as dt

    class D(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 20)
    monkeypatch.setattr(fin_export, "date", D)
    r = client.post("/api/fin/export", headers=hdr(1000)).json()
    assert r["ok"] and set(written) == {"Сводка", "Движение денег", "ФОТ", "Закупки"}
    assert written["Сводка"][11][0] == "Ноябрь" and written["Движение денег"][1][3] == 1000.0
