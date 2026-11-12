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
        "pay.carpenter.month": 200000, "fin.fixed.bitrix_year": 120000, "fin.var.ads_target_day": 1000}


def uid():
    return str(uuid.uuid4())


def setup(client, monkeypatch):
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                     ("t", Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "head"} for k, v in VALS.items()})))
        conn.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (731, 'Кафе', 'Астана', 'UC_AV00QK')")
    monkeypatch.setattr(drive, "save_receipt", lambda conn, dept, name, data, deal_id=None: f"drv-{dept}")
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
    assert client.post(f"/api/shift/{s['id']}/review", json={"approve": True, "stars": 5}, headers=hdr(1000)).json()["status"] == "approved"


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
    # коммуналка — отдельная постоянная статья (HEAD 10.11)
    assert any(x["code"] == "utilities" and x["title"] == "Коммунальные услуги" for x in client.get("/api/fin/dict", headers=hdr(1000)).json()["articles"])
    assert led(account="kaspi", amount=1_160_000, article="client_payment", deal_id=1601, op_date="2026-11-03").json()["direction"] == "in"
    assert led(account="kaspi", amount=200_000, article="transfer", to_account="cash").status_code == 200
    assert led(account="kaspi", amount=200_000, article="transfer").status_code == 400     # без счёта «куда»
    assert led(account="kaspi", amount=10, article="payroll").status_code == 400            # выплаты — только через ФОТ
    bal = {b["code"]: float(b["balance"]) for b in client.get("/api/fin/summary", params={"ym": YM}, headers=hdr(1000)).json()["cash"]["closing"]}
    assert bal == {"kaspi": 5_000_000 - 300_000 + 1_160_000 - 200_000, "cash": 500_000, "head": 0, "artamonov": 0, "hist": 0}
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
    assert next(b for b in s["budget"] if b["code"] == "ads_target")["plan"] == 30000   # 1000 ₸ в день × 30 дней ноября
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
    ids = setup(client, monkeypatch)
    with db.pool.connection() as conn:   # трата художника на объект 731 — и в «Траты» (отдел), и в строку проекта
        cat = conn.execute("SELECT code FROM expense_categories WHERE article='project' AND active ORDER BY sort LIMIT 1").fetchone()["code"]
        conn.execute("""INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, status)
                        VALUES (gen_random_uuid(), %s, 731, 'mural', %s, 5000, 'approved')""", (ids[2000], cat))
        conn.execute("""INSERT INTO fin_projects (year, row_no, deal_id, month, closed, title, revenue, origin)
                        VALUES (2026, 1000731, 731, 11, '2026-11-05', 'Кафе', 100000, 'bitrix')""")
    client.post("/api/fin/ledger", json={"client_uid": uid(), "op_date": "2026-11-01", "account": "kaspi", "amount": 1000,
                                         "article": "opening"}, headers=hdr(1000))
    monkeypatch.setattr(settings, "fin_sheet_id", "")
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
    assert r["ok"] and set(written) == {"Сводка", "Модель", "Проекты", "Движение денег", "ФОТ", "Траты"}
    tr = written["Траты"]
    assert tr[1][0] == "02 РОСПИСЬ · 1 трата" and tr[2][5] == 731 and tr[2][7] == 5000.0 and tr[-1][7] == 5000.0
    pr = next(r for r in written["Проекты"] if r[1] == 731)
    assert pr[13] == 5000.0 and pr[14] == 95000.0 and pr[15] == "Битрикс"
    sub = next(r for r in written["Проекты"] if r[0] == "Итого: Ноябрь")
    assert sub[13] == 5000.0 and sub[14] == 95000.0   # подытог считает и траты
    md = {row[0]: row for row in written["Модель"] if row}
    assert md["Показатель"][-1] == "Итого 2026" and md["ВЫРУЧКА"][1] == "" and "Прибыль до ИПН" in md
    assert written["Сводка"][11][0] == "Ноябрь" and written["Движение денег"][1][3] == 1000.0


def test_bitrix_payments(client, monkeypatch):
    """Оплаты клиентов из Битрикса: поступления сделки → приходы журнала, без задвоения; правка суммы — замена; отмена HEAD держится."""
    from artgame import bx, fin_bx
    setup(client, monkeypatch)
    deals = [{"ID": "831", "TITLE": "Кафе", "CATEGORY_ID": "0", "UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT": "500000|KZT",
              "UF_CRM_ARTGAME_FIN03_PAY1_DATE": "2026-11-03T03:00:00+05:00", "UF_CRM_ARTGAME_FIN03_PAY2_AMOUNT": "300000|KZT",
              "UF_CRM_ARTGAME_FIN03_PAY2_DATE": "2026-10-20T03:00:00+05:00"},   # октябрь — до запуска учёта, не берём
             {"ID": "900", "TITLE": "Дизайн квартиры", "CATEGORY_ID": "13", "UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT": "90000|KZT",
              "UF_CRM_ARTGAME_FIN03_PAY1_DATE": "2026-11-04"}]
    monkeypatch.setattr(bx, "read_all", lambda m, p, fresh=False: deals)
    run = lambda: fin_bx_run(fin_bx)  # noqa: E731
    assert run()["added"] == 2 and run()["added"] == 0
    led = lambda: [x for x in client.get("/api/fin/ledger", params={"ym": YM}, headers=hdr(1000)).json() if x["source"] == "bitrix"]  # noqa: E731
    rows = {x["deal_id"]: x for x in led()}
    assert rows[831]["article_code"] == "client_payment" and float(rows[831]["amount"]) == 500000 and rows[831]["account_code"] == "kaspi"
    assert rows[900]["article_code"] == "design_prepay"
    # HEAD меняет счёт, МОП исправляет сумму в сделке: новая строка, счёт сохраняется
    assert client.post(f"/api/fin/ledger/{rows[831]['id']}/account", json={"account": "cash"}, headers=hdr(1000)).json()["ok"]
    deals[0]["UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT"] = "550000|KZT"
    assert run()["changed"] == 1
    act = [x for x in led() if x["status"] == "active"]
    assert sorted(float(x["amount"]) for x in act) == [90000, 550000] and {x["account_code"] for x in act if x["deal_id"] == 831} == {"cash"}
    # HEAD отменил строку — следующий импорт её не возвращает
    d900 = next(x for x in act if x["deal_id"] == 900)
    client.post(f"/api/fin/ledger/{d900['id']}/cancel", headers=hdr(1000))
    assert run() == {"deals": 2, "added": 0, "changed": 0}


def fin_bx_run(fin_bx):
    with db.pool.connection() as conn, conn.transaction():
        return fin_bx.import_payments(conn)


FOT_OCT = [[None] * 12,
           ["АСТАНА", "Аванс", "ЗП 1-5", "Премия|%", "Итог", None, "Владимир", None, None, None, "Асель 15т"],
           ["Владимир", None, None, None, "=", None, "Мурал Павлодар", "360000", "13 дней", None, "Gala One", "130 000"],
           ["Асель", None, None, None, "=", None, "Школа", "34000", "1 день", None, "Картины", "105000"],
           [None] * 6 + ["Премия", "212000", None, None, "Премия", "20000"],
           [None] * 6 + ["Аванс", "200000", None, None, "Аванс", "0"],
           [None] * 6 + ["Итог", "=SUM", None, None, "Итог", "=SUM"],
           ["ШЫМКЕНТ", "Аванс ", "ЗП 1-5", "Премия|%", "Итог", None, "Анна"],
           [None] * 6 + ["Оклад", "200000"],
           [None] * 6 + ["Аванс", "124500", "80т заказчик"],
           [None] * 6 + ["Итог", "=SUM"]]


def test_history_import(client, monkeypatch):
    """История 2026: проекты из листа, ФОТ из «ФОТ 2026» — начисления и выплаты на счёт «История», без задвоения."""
    from artgame import fin, fin_history
    ids = setup(client, monkeypatch)
    people = fin_history.parse_fot(FOT_OCT)
    by = {p["name"]: p for p in people}
    assert by["Владимир"]["piece"] == 394000 and by["Владимир"]["bonus"] == 212000 and by["Владимир"]["advance"] == 200000
    assert by["Асель"]["piece"] == 235000 and by["Анна"]["salary"] == 200000 and by["Анна"]["city"] == "Шымкент"
    projects = [["171", "Октябрь", "ЦУМ", "Караганда", "B2B", "Спорт", "", "Роспись", "Instagram", "", "Яковлев", "", "", "20.10.2026",
                 "1 160 000", "1 000 000", "160 000", "174 000", "40 000", "", "", "", "", "", "", "", "6 000"], ["", "Октябрь", ""]]

    def sheet(sid, rng):
        if sid == fin.SHEET_ID:
            return projects
        return FOT_OCT if rng.startswith("'Октябрь'") else []
    monkeypatch.setattr(fin, "sheet_values", sheet)
    monkeypatch.setattr(fin_history, "import_client_payments", lambda conn, year=2026: {"deals": 0})
    client.get("/api/fin/payees", headers=hdr(1000))                         # получатели команды
    with db.pool.connection() as conn:
        conn.execute("UPDATE fin_payees SET name='Асель Нурланова' WHERE person_id=%s", (ids[2000],))
        r1 = fin_history.run(conn)
        r2 = fin_history.run(conn)
        assert r1["projects"] == 1 and r1["payroll"]["added"] == 5 and r2["payroll"]["added"] == 0
        pr = conn.execute("SELECT * FROM fin_projects").fetchall()
        assert len(pr) == 1 and pr[0]["month"] == 10 and float(pr[0]["revenue"]) == 1160000
        out = conn.execute("SELECT sum(amount) AS s FROM fin_ledger WHERE account_code='hist' AND article_code='payroll'").fetchone()["s"]
        assert float(out) == 394000 + 212000 + 235000 + 20000 + 200000
    p = client.get("/api/fin/payroll/2026-10", headers=hdr(1000)).json()
    rows = {x["name"]: x for x in p["rows"]}
    assert rows["Асель Нурланова"]["accrued"] == 255000                     # нашёлся человек приложения по имени
    assert rows["Владимир"]["accrued"] == 606000 and rows["Владимир"]["left"] == 0
    assert client.post("/api/fin/payroll/2026-10/compute", headers=hdr(1000)).status_code == 400
    s = client.get("/api/fin/summary", params={"ym": "2026-11"}, headers=hdr(1000)).json()
    assert all(b["code"] != "hist" or float(b["balance"]) <= 0 for b in s["cash"]["closing"])
    assert s["costs"]["materials"] == 0                                       # с ноября — живой учёт, без оценок
    s = client.get("/api/fin/summary", params={"ym": "2026-10"}, headers=hdr(1000)).json()
    assert s["costs"]["materials"] == 174000 + 40000 + 6000 and any("история" in w for w in s["warn"])
    # до ноября постоянные/переменные — оценка по ставкам «Значений»: студия 300к + Битрикс 120к/12; таргет 1000 ₸ × 31 день
    assert s["costs"]["fixed"] == 300000 + 10000 and s["costs"]["variable"] == 31000
    assert next(b for b in s["budget"] if b["code"] == "rent_studio")["estimate"] is True


def test_export_style():
    """Оформление витрины: старые полосы/правила снимаются, «Лист1» прячется, итог года в «Сводке» — тёмная строка."""
    from artgame.fin_export import style
    sheets = [{"properties": {"sheetId": 0, "title": "Лист1"}},
              {"properties": {"sheetId": 5, "title": "Сводка", "gridProperties": {"rowCount": 1000, "columnCount": 26}},
               "bandedRanges": [{"bandedRangeId": 77}], "conditionalFormats": [{}, {}]}]
    r = style(sheets, {"Сводка": [["Месяц"] + [""] * 15, ["Ноябрь"] + [0] * 15, ["Итого 2026"] + [0] * 15]})
    kinds = [next(iter(x)) for x in r]
    assert r[0] == {"updateSheetProperties": {"properties": {"sheetId": 0, "hidden": True}, "fields": "hidden"}}
    assert {"deleteBanding": {"bandedRangeId": 77}} in r and kinds.count("deleteConditionalFormatRule") == 2
    assert kinds.count("addBanding") == 1 and kinds.count("addConditionalFormatRule") == 2
    assert all("(" not in x[k].get("fields", "") for x in r for k in x)   # маски полей — через точку, скобки API не принимает


def test_sections():
    """«Проекты» и «ФОТ» разделами по месяцам: шапка месяца, подытог, итог года; группы строк сворачиваются, старый фильтр снимается."""
    from artgame.fin_export import _kind, sectioned, style
    h = ["Месяц", "Кто", "Сумма"]
    rows = sectioned(h, {10: [["Октябрь", "А", 100], ["Октябрь", "Б", 50]], 11: [["Ноябрь", "В", 10]],
                         9: [["Сентябрь", "Г", 1]]}, (2,), 2026, ("проект", "проекта", "проектов"))
    assert rows[1][0] == "СЕНТЯБРЬ · 1 проект" and rows[4][0] == "ОКТЯБРЬ · 2 проекта" and rows[7] == ["Итого: Октябрь", "", 150.0]
    assert rows[-1] == ["Итого 2026", "", 161.0] and [_kind(r) for r in rows][:4] == ["", "section", "", "sub"]
    sheets = [{"properties": {"sheetId": 3, "title": "ФОТ", "gridProperties": {"rowCount": 50}}, "basicFilter": {"range": {}},
               "rowGroups": [{"range": {"sheetId": 3, "dimension": "ROWS", "startIndex": 2, "endIndex": 4}, "depth": 1}]}]
    r = style(sheets, {"ФОТ": [r + [""] * 5 for r in rows]})
    kinds = [next(iter(x)) for x in r]
    assert kinds.count("addDimensionGroup") == 3 and kinds.count("deleteDimensionGroup") == 1 and "clearBasicFilter" in kinds
    assert "setBasicFilter" not in kinds and "addBanding" not in kinds
    coll = [x["updateDimensionGroup"]["dimensionGroup"]["range"]["startIndex"] for x in r if "updateDimensionGroup" in x]
    assert coll == [2]   # свёрнут только сентябрь, два последних месяца открыты
    assert all("(" not in x[k].get("fields", "") for x in r for k in x)


def test_bitrix_projects(client, monkeypatch):
    """С ноября проекты — сданные сделки Битрикса: «Оплата+закрывающие» по дню перевода, «Оплата получена» — по «Окончание факт»;
    сделки из листа не задваиваются; выручка месяца в «Сводке» их видит."""
    from artgame import bx, fin, fin_bx
    setup(client, monkeypatch)
    with db.pool.connection() as conn:
        conn.execute("""INSERT INTO fin_projects (year, row_no, deal_id, month, closed, title, revenue) VALUES (2026, 5, 943, 10, '2026-10-14', 'ФОК', 100)""")
    deals = [{"ID": "1579", "TITLE": "1579 · ДЕТСКАЯ ПЛОЩАДКА — АСТАНА", "STAGE_ID": "UC_BMKDS4", "OPPORTUNITY": "300000.00",
              "MOVED_TIME": "2026-11-04T13:13:22+03:00", fin_bx.F_END: "", bx.OBJECT: "Детская площадка", bx.CITY: "1",
              "UF_CRM_ARTGAME_FIN03_RECEIVED": "0|KZT", "UF_CRM_ARTGAME_FIN03_DEBT": "300000|KZT"},
             {"ID": "1611", "TITLE": "1611 · УЙДОМДОНЕР — АСТАНА", "STAGE_ID": "WON", "OPPORTUNITY": "110000",
              "MOVED_TIME": "2026-11-06T10:00:00+03:00", fin_bx.F_END: "2026-11-05T03:00:00+03:00", bx.OBJECT: "", bx.CITY: "1"},
             {"ID": "943", "TITLE": "943 · ФОК", "STAGE_ID": "UC_BMKDS4", "OPPORTUNITY": "9787500", "MOVED_TIME": "2026-11-02T10:00:00+03:00"},
             {"ID": "1700", "TITLE": "1700 · СТАРАЯ", "STAGE_ID": "WON", "OPPORTUNITY": "50000", "MOVED_TIME": "2026-11-03T10:00:00+03:00",
              fin_bx.F_END: ""}]
    monkeypatch.setattr(bx, "read_all", lambda m, p, fresh=False: deals)
    monkeypatch.setattr(bx, "read", lambda m, p, fresh=False, **k: {"result": {"items": [{"CREATED_TIME": "2026-09-30T10:00:00+03:00"}]}})
    monkeypatch.setattr(bx, "city_name", lambda v: "Астана")
    monkeypatch.setattr(bx, "enum_map", lambda code: {"43243": "B2B — бизнес"})
    deals[0][fin_bx.F_MODEL] = "43243"
    with db.pool.connection() as conn, conn.transaction():
        r = fin_bx.import_projects(conn)
        got = {x["deal_id"]: x for x in conn.execute("SELECT * FROM fin_projects WHERE origin='bitrix'").fetchall()}
    assert r["projects"] == 2 and set(got) == {1579, 1611}                       # 943 есть в листе, 1700 сдана в сентябре
    assert str(got[1579]["closed"]) == "2026-11-04" and got[1579]["title"] == "Детская площадка" and float(got[1579]["debt"]) == 300000
    assert str(got[1611]["closed"]) == "2026-11-05" and got[1611]["title"] == "УЙДОМДОНЕР"
    assert got[1579]["model"] == "B2B"
    monkeypatch.setattr(fin, "sheet_values", lambda sid, rng: [])
    monkeypatch.setattr(fin, "month_rows", lambda y, m, fresh=False: [r for r in fin.rows(y, fresh) if r["month"] == m])
    fin._cache.clear()
    s = client.get("/api/fin/summary", params={"ym": "2026-11"}, headers=hdr(1000)).json()
    assert s["revenue"]["gross"] == 410000


def test_bitrix_payment_without_date(client, monkeypatch):
    """HEAD 09.11 («почему 0»): в сделке сумма поступления есть, даты нет — приход днём импорта; закрытые сделки не трогаем."""
    from artgame import bx, fin_bx
    setup(client, monkeypatch)
    deals = [{"ID": "525", "TITLE": "Вок", "CATEGORY_ID": "0", "STAGE_ID": "UC_AV00QK", "UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT": "289000|KZT",
              "UF_CRM_ARTGAME_FIN03_PAY1_DATE": ""},
             {"ID": "9", "TITLE": "Старая", "CATEGORY_ID": "0", "STAGE_ID": "WON", "UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT": "200000|KZT"}]
    monkeypatch.setattr(bx, "read_all", lambda m, p, fresh=False: deals)
    assert fin_bx_run(fin_bx)["added"] == 1 and fin_bx_run(fin_bx) == {"deals": 2, "added": 0, "changed": 0}
    with db.pool.connection() as c:
        r = c.execute("SELECT * FROM fin_ledger WHERE source='bitrix'").fetchall()
    assert len(r) == 1 and r[0]["deal_id"] == 525 and "дата не указана" in r[0]["note"]
    deals[0]["UF_CRM_ARTGAME_FIN03_PAY1_DATE"] = "2026-11-05T03:00:00+05:00"   # МОП поставил дату — строка переезжает
    assert fin_bx_run(fin_bx)["changed"] == 1
    with db.pool.connection() as c:
        act = c.execute("SELECT op_date FROM fin_ledger WHERE source='bitrix' AND status='active'").fetchall()
    assert [str(x["op_date"]) for x in act] == ["2026-11-05"]
