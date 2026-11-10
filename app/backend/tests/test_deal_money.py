"""Итоги оплат сделки считает приложение (HEAD 10.11): «Поступило», «Долг», «Упущено» — по журналу денег, а не роботом FIN03.
Формулы сверены с тем, что FIN03 записал в 321 сделку (10.11): поступило = сумма поступлений, долг = сумма − поступило,
у проигранных долг 0 и остаток в «Упущено», без НДС = сумма / 1,16."""
from artgame import bx, bxw, db, deal_money as dm, fin_bx
from artgame.config import settings
from conftest import hdr
from test_finance import YM, setup, uid

A1, D1 = "UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT", "UF_CRM_ARTGAME_FIN03_PAY1_DATE"
A2, D2 = "UF_CRM_ARTGAME_FIN03_PAY2_AMOUNT", "UF_CRM_ARTGAME_FIN03_PAY2_DATE"
REC, DEBT, LOST, NET, VAT = (dm.F[k] for k in ("received", "debt", "lost", "net", "vat"))


def deal(i, stage="UC_AV00QK", sem="P", opp=0, created="2026-11-02T10:00:00+03:00", moved="2026-11-02T10:00:00+03:00", **f):
    return {"ID": str(i), "TITLE": f"Сделка {i}", "CATEGORY_ID": "0", "STAGE_ID": stage, "STAGE_SEMANTIC_ID": sem,
            "OPPORTUNITY": f"{opp:.2f}", "CURRENCY_ID": "KZT", "DATE_CREATE": created, "MOVED_TIME": moved, **f}


def test_formulas_like_fin03():
    # Айболит 10.11: 800 000 внесено без даты, FIN03 стоял — «Поступило» пустое, долг старый
    d = deal(1347, opp=1_600_000, **{A1: "800000|KZT", D1: "", DEBT: "800000|KZT"})
    t = dm.target(d, None, 16)
    assert t["received"] == 800_000 and t["debt"] == 800_000 and t["lost"] == 0 and t["overpaid"] == 0
    assert t["net"] == 1379310.34 and t["vat"] == 220689.66          # как у FIN03: round(сумма / 1,16, 2)
    assert dm.managed(d, None) and dm.changes(d, t) == {"received": 800_000, "net": 1379310.34, "vat": 220689.66}
    # проиграна 09.11 без оплат: долг 0, остаток — «Упущено»
    d = deal(1305, stage="APOLOGY", sem="F", opp=480_000, moved="2026-11-09T12:45:00+03:00")
    assert dm.managed(d, None) and dm.changes(d, dm.target(d, None, 16)) == {"lost": 480_000, "net": 413793.1, "vat": 66206.9}
    # старая выигранная сделка без поступлений, которую FIN03 не вёл: не трогаем — иначе ложный долг
    old = deal(181, stage="WON", sem="S", opp=952_000, created="2025-10-23T10:00:00+03:00", moved="2025-11-07T10:00:00+03:00")
    assert not dm.managed(old, None)
    # FIN03 уже вёл сделку: ведём и мы; «без НДС» у старой сделки без этого поля не заводим
    old[REC], old[DEBT] = "0|KZT", "952000|KZT"
    assert dm.managed(old, None) and dm.changes(old, dm.target(old, None, 16)) == {}
    # «Поступило» вбито руками без поступления — возвращается к журналу, долг снова виден
    d = deal(1611, stage="WON", sem="S", opp=110_000, **{REC: "110000|KZT", DEBT: "0|KZT", NET: "94827.59|KZT", VAT: "15172.41|KZT"})
    assert dm.changes(d, dm.target(d, None, 16)) == {"received": 0, "debt": 110_000}
    # переплата и два поступления
    d = deal(963, stage="WON", sem="S", opp=150_000, **{A1: "150000|KZT", D1: "2026-03-01", A2: "130000|KZT", D2: "2026-04-01"})
    t = dm.target(d, None, 16)
    assert t["received"] == 280_000 and t["debt"] == 0 and t["overpaid"] == 130_000
    assert dm._money_str(1379310.34, "KZT") == "1379310.34|KZT" and dm._money_str(150000.0, "") == "150000|KZT"


def test_ledger_is_the_source(client, monkeypatch):
    """Журнал — источник: поступление из сделки + наличные HEAD; отмена HEAD сразу убирает деньги из итога; запись только
    изменённых полей и только при ARTGAME_PAY_PUSH; повторный проход ничего не пишет."""
    setup(client, monkeypatch)
    deals = {831: deal(831, opp=1_000_000, **{A1: "300000|KZT", D1: "2026-11-03T03:00:00+05:00", REC: "300000|KZT", DEBT: "700000|KZT"}),
             900: deal(900, stage="LOSE", sem="F", opp=200_000, moved="2026-11-05T10:00:00+03:00")}

    def read(method, params, fresh=False, **k):
        assert method == "crm.deal.list"
        return {"result": [dict(d) for d in deals.values()]}

    def read_all(method, params, fresh=False, **k):
        ids = (params.get("filter") or {}).get("ID")
        return [dict(d) for i, d in deals.items() if ids is None or i in [int(x) for x in ids]]

    monkeypatch.setattr(bx, "read", read)
    monkeypatch.setattr(bx, "read_all", read_all)
    wrote = []

    def call(method, params):
        assert method == "crm.deal.update"
        wrote.append((params["id"], params["fields"]))
        deals[params["id"]].update(params["fields"])   # Битрикс принял
        return {"result": True}

    monkeypatch.setattr(bxw, "CALL", call)
    monkeypatch.setattr(settings, "bitrix_webhook", "https://bx.example/rest/1/x/")
    monkeypatch.setattr(dm, "PAUSE", 0)
    with db.pool.connection() as conn, conn.transaction():
        assert fin_bx.import_payments(conn)["added"] == 1   # поступление 1 сделки 831 — в журнал
    # HEAD принял наличными ещё 200 000 по сделке 831
    cash = client.post("/api/fin/ledger", json={"client_uid": uid(), "op_date": "2026-11-06", "account": "cash", "amount": 200000,
                                                "article": "client_payment", "deal_id": 831}, headers=hdr(1000)).json()
    assert cash["deal_id"] == 831

    # запись выключена: только сверка
    chk = client.get("/api/fin/deal-money", headers=hdr(1000)).json()
    assert chk["push"] is False and {r["id"] for r in chk["rows"]} == {831, 900}
    r831 = next(r for r in chk["rows"] if r["id"] == 831)["fields"]
    assert r831["Поступило"] == {"bitrix": 300000, "app": 500000} and r831["Долг"] == {"bitrix": 700000, "app": 500000}
    with db.pool.connection() as conn:
        assert dm.push(conn)["written"] == 0 and not wrote
    assert client.get("/api/fin/deal-money", headers=hdr(6000)).status_code == 403   # сверку видит только HEAD

    monkeypatch.setattr(settings, "pay_push", True)
    with db.pool.connection() as conn:
        out = dm.push(conn)
    assert out["written"] == 2 and not out["errors"]
    got = dict(wrote)
    assert got[831][REC] == "500000|KZT" and got[831][DEBT] == "500000|KZT"
    assert got[900][LOST] == "200000|KZT" and DEBT not in got[900]
    wrote.clear()
    with db.pool.connection() as conn:
        assert dm.push(conn)["diff"] == 0 and not wrote   # всё совпало — ничего не пишем
        log = conn.execute("SELECT data FROM audit_log WHERE action='deal_money_push' AND entity_id='831'").fetchone()["data"]
    assert log["bx"] == "ok" and log["fields"]["Поступило"] == [300000, 500000]

    # HEAD отменил наличные — итог сделки обновляется сразу (фоном после ответа), без таймера
    assert client.post(f"/api/fin/ledger/{cash['id']}/cancel", headers=hdr(1000)).json()["ok"]
    assert wrote == [(831, {REC: "300000|KZT", DEBT: "700000|KZT"})]
    # HEAD отменил и поступление из сделки: из поля сделки оно обратно не считается
    wrote.clear()
    with db.pool.connection() as conn:
        row = conn.execute("SELECT id FROM fin_ledger WHERE source='bitrix' AND deal_id=831 AND status='active'").fetchone()
    client.post(f"/api/fin/ledger/{row['id']}/cancel", headers=hdr(1000))
    assert wrote == [(831, {REC: "0|KZT", DEBT: "1000000|KZT"})]
    # ручная правка «Поступило» в Битриксе возвращается к журналу на следующем проходе
    wrote.clear()
    deals[831][REC] = "1000000|KZT"
    with db.pool.connection() as conn:
        assert dm.push(conn)["written"] == 1
    assert wrote == [(831, {REC: "0|KZT"})]


def test_card_and_lock_follow_ledger(client, monkeypatch):
    """Карточка и замок «Аванс поступил» видят оплату из журнала, даже когда поле FIN03 в сделке пустое."""
    setup(client, monkeypatch)
    d = deal(1347, opp=1_600_000, **{DEBT: "800000|KZT"})
    assert dm.card(d)["received"] == 0
    client.post("/api/fin/ledger", json={"client_uid": uid(), "op_date": "2026-11-10", "account": "kaspi", "amount": 800000,
                                         "article": "client_payment", "deal_id": 1347}, headers=hdr(1000))
    c = dm.card(d)
    assert c["received"] == 800_000 and c["debt"] == 800_000
    led = [x for x in client.get("/api/fin/ledger", params={"ym": YM}, headers=hdr(1000)).json() if x["deal_id"] == 1347]
    assert len(led) == 1


def test_mop_enters_payment_with_receipt(client, monkeypatch):
    """«Внести оплату» (HEAD 10.11): МОП в своей сделке — сумма, дата, счёт, фото чека; чек — в «Приходы чеки» сделки,
    оплата сразу в «Поступило» со статусом «на сверке»; HEAD ✓ сверяет, ✕ отменяет; повтор из офлайн-очереди не задваивает."""
    from datetime import date, timedelta

    from artgame import drive
    from test_finance import JPG
    ids = setup(client, monkeypatch)
    client.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    deals = {"1347": {**deal(1347, opp=1_600_000), "ASSIGNED_BY_ID": "4565"},
             "1400": {**deal(1400, opp=500_000), "ASSIGNED_BY_ID": "4693"},
             "1647": {**deal(1647, stage="C13:PREPARATION", opp=90_000), "CATEGORY_ID": "13", "ASSIGNED_BY_ID": "4565"}}
    monkeypatch.setattr(bx, "READ", lambda m, p: {"result": deals.get(str(p["id"]))} if m == "crm.deal.get" else {"result": []})
    saved = []
    monkeypatch.setattr(drive, "save_income_receipt", lambda conn, name, data, deal_id: saved.append((deal_id, name)) or "drv-income")
    today = str(dm.datetime.now(dm.TZ).date())   # дата по Алматы, как у сервера
    pay = {"client_uid": uid(), "amount": 800000, "op_date": today, "account": "kaspi", "receipt": JPG, "note": "аванс 50%"}
    r = client.post("/api/bx/deals/1347/payment", json=pay, headers=hdr(6000))
    assert r.status_code == 200, r.text
    row = r.json()["row"]
    assert row["source"] == "app" and row["article_code"] == "client_payment" and row["checked_at"] is None and row["receipt_url"]
    assert r.json()["pay"]["received"] == 800_000 and r.json()["pay"]["debt"] == 800_000 and r.json()["pay"]["on_check"] == 800_000
    assert saved == [(1347, f"{today} приход 800000 Сделка 1347")]
    assert client.post("/api/bx/deals/1347/payment", json=pay, headers=hdr(6000)).json()["row"]["id"] == row["id"]   # повтор очереди
    # чужая сделка, будущая дата, счёт «История», без чека — нельзя
    assert client.post("/api/bx/deals/1400/payment", json={**pay, "client_uid": uid()}, headers=hdr(6000)).status_code == 403
    tomorrow = str(dm.datetime.now(dm.TZ).date() + timedelta(days=1))
    assert client.post("/api/bx/deals/1347/payment", json={**pay, "client_uid": uid(), "op_date": tomorrow}, headers=hdr(6000)).status_code == 400
    assert client.post("/api/bx/deals/1347/payment", json={**pay, "client_uid": uid(), "account": "hist"}, headers=hdr(6000)).status_code == 400
    assert client.post("/api/bx/deals/1347/payment", json={**pay, "client_uid": uid(), "receipt": ""}, headers=hdr(6000)).status_code == 422
    # дизайн — «Предоплата за дизайн»
    r = client.post("/api/bx/deals/1647/payment", json={**pay, "client_uid": uid(), "amount": 90000}, headers=hdr(6000))
    assert r.json()["row"]["article_code"] == "design_prepay"
    # замок «Аванс поступил» открыт по журналу
    from artgame import fill
    st = fill.state(deals["1347"], {"stage": "UC_AV00QK", "pay": dm.card(deals["1347"])}, None)
    assert next(x for x in st["items"] if x["key"] == "paid")["ok"]

    # HEAD: две оплаты на сверке, в Пульте тоже
    chk = client.get("/api/fin/payments/check", headers=hdr(1000)).json()
    assert [x["deal_id"] for x in chk] == [1347, 1647] and chk[0]["author"] == "P6000" and chk[0]["receipt_url"]
    pulse = client.get("/api/head/pulse", headers=hdr(1000)).json()["review"]
    assert pulse["payments"] == 2 and pulse["payments_sum"] == 890_000
    assert client.get("/api/fin/payments/check", headers=hdr(6000)).status_code == 403
    assert client.post(f"/api/fin/ledger/{row['id']}/check", headers=hdr(1000)).json()["ok"]
    assert client.post(f"/api/fin/ledger/{row['id']}/check", headers=hdr(1000)).status_code == 409
    second = chk[1]["id"]
    assert client.post(f"/api/fin/ledger/{second}/cancel", headers=hdr(1000)).json()["ok"]   # ✕ — ошибочная
    assert client.get("/api/fin/payments/check", headers=hdr(1000)).json() == []
    assert dm.card(deals["1647"])["received"] == 0
    # оплату, которую внёс сам HEAD, сверять не нужно
    r = client.post("/api/bx/deals/1400/payment", json={**pay, "client_uid": uid(), "amount": 250000}, headers=hdr(1000)).json()
    assert r["row"]["checked_at"] and client.get("/api/fin/payments/check", headers=hdr(1000)).json() == []
    items = dm.card(deals["1347"])["items"]
    assert len(items) == 1 and items[0]["on_check"] is False and items[0]["account_title"]


def test_count_only_after_check(client, monkeypatch):
    """Если HEAD выберет «считать после ✓»: оплата МОП не входит в «Поступило», пока HEAD её не сверил."""
    ids = setup(client, monkeypatch)
    from artgame import drive
    from test_finance import JPG
    from datetime import date
    client.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    d = {**deal(1347, opp=1_600_000), "ASSIGNED_BY_ID": "4565"}
    monkeypatch.setattr(bx, "READ", lambda m, p: {"result": d})
    monkeypatch.setattr(drive, "save_income_receipt", lambda *a: "drv")
    monkeypatch.setattr(dm, "COUNT_UNCHECKED", False)
    row = client.post("/api/bx/deals/1347/payment", json={"client_uid": uid(), "amount": 800000, "op_date": str(date.today()),
                                                          "account": "cash", "receipt": JPG}, headers=hdr(6000)).json()["row"]
    assert dm.card(d)["received"] == 0 and dm.card(d)["on_check"] == 800_000
    client.post(f"/api/fin/ledger/{row['id']}/check", headers=hdr(1000))
    assert dm.card(d)["received"] == 800_000


def test_payments_desk_and_history(client, monkeypatch):
    """«Вносит оплаты клиентов» (HEAD 10.11, Анна): галочка в «Команде» → вкладка «Оплаты», любая сделка по номеру или
    названию, с фото чека; без галочки нельзя. Оплата до 01.11.2026 — в счёт «История»: долг сделки уменьшает, деньги ноября нет."""
    from datetime import date

    from artgame import drive
    from test_finance import JPG
    ids = setup(client, monkeypatch)
    deals = {"1579": {**deal(1579, stage="WON", sem="S", opp=300_000), "TITLE": "1579 · ДЕТСКАЯ ПЛОЩАДКА — АСТАНА", "ASSIGNED_BY_ID": "4565"},
             "1611": {**deal(1611, stage="WON", sem="S", opp=110_000), "TITLE": "1611 · УЙДОМДОНЕР — АСТАНА", "ASSIGNED_BY_ID": "4565"}}

    def read(m, p):
        if m == "crm.deal.get":
            return {"result": deals.get(str(p["id"]))}
        if m == "crm.deal.list":
            f = p["filter"]
            return {"result": [d for d in deals.values() if ("ID" not in f or int(d["ID"]) in f["ID"])
                               and ("%TITLE" not in f or f["%TITLE"].lower() in d["TITLE"].lower())]}
        return {"result": []}
    monkeypatch.setattr(bx, "READ", read)
    monkeypatch.setattr(bx, "stages", lambda: {"WON": {"name": "Сделка успешна", "semantic": "success"}})
    monkeypatch.setattr(bx, "users", lambda: [{"id": 4565, "name": "Ануар Минкеев"}])
    monkeypatch.setattr(drive, "save_income_receipt", lambda *a: "drv")
    anna = ids[3000]   # Главный художник, вносит оплаты по всем сделкам
    pay = {"client_uid": uid(), "amount": 300000, "op_date": "2026-10-20", "account": "kaspi", "receipt": JPG}
    # без галочки — ни поиска, ни оплаты
    assert client.get("/api/pay/deals?q=1579", headers=hdr(3000)).status_code == 403
    assert client.post("/api/bx/deals/1579/payment", json=pay, headers=hdr(3000)).status_code == 403
    assert client.post(f"/api/people/{anna}", json={"pays": True}, headers=hdr(1000)).json()["pays"] is True
    assert [x["pays"] for x in client.get("/api/people", headers=hdr(1000)).json() if x["id"] == anna] == [True]
    found = client.get("/api/pay/deals?q=площадка", headers=hdr(3000)).json()
    assert [(x["id"], x["stage_name"], x["sum"], x["manager"]) for x in found] == [(1579, "Сделка успешна", 300000, "Ануар Минкеев")]
    assert [x["id"] for x in client.get("/api/pay/deals?q=1611", headers=hdr(3000)).json()] == [1611]
    assert client.get("/api/pay/deals?q=а", headers=hdr(3000)).json() == []   # одна буква — не ищем
    d = client.get("/api/pay/deals/1579", headers=hdr(3000)).json()
    assert d["title"].startswith("1579") and d["pay"]["received"] == 0 and d["pay"]["debt"] == 300_000
    # октябрьская оплата (нашли задним числом): счёт «История», долг сделки закрыт, HEAD сверяет
    r = client.post("/api/bx/deals/1579/payment", json=pay, headers=hdr(3000)).json()
    assert r["row"]["account_code"] == "hist" and r["row"]["period"] == "2026-10" and "до ноября" in r["row"]["note"]
    assert r["pay"]["received"] == 300_000 and r["pay"]["debt"] == 0
    assert [x["deal_id"] for x in client.get("/api/fin/payments/check", headers=hdr(1000)).json()] == [1579]
    # ноябрьская — на выбранный счёт; «История» на ноябрь не выбрать; раньше 2025 года — нельзя
    r = client.post("/api/bx/deals/1611/payment", json={**pay, "client_uid": uid(), "amount": 110000, "op_date": str(date.today()),
                                                        "account": "cash"}, headers=hdr(3000)).json()
    assert r["row"]["account_code"] == "cash" and r["pay"]["debt"] == 0
    assert client.post("/api/bx/deals/1611/payment", json={**pay, "client_uid": uid(), "op_date": str(date.today()), "account": "hist"},
                       headers=hdr(3000)).status_code == 400
    assert client.post("/api/bx/deals/1611/payment", json={**pay, "client_uid": uid(), "op_date": "2024-12-31"}, headers=hdr(3000)).status_code == 400
    # галочку сняли — снова нельзя; у МОП без галочки поиска «Оплаты» нет (свои сделки — в «Сделках»)
    client.post(f"/api/people/{anna}", json={"pays": False}, headers=hdr(1000))
    assert client.get("/api/pay/deals/1611", headers=hdr(3000)).status_code == 403
    assert client.get("/api/pay/deals?q=1611", headers=hdr(6000)).status_code == 403


def test_undated_slot_gets_date_and_receipt(client, monkeypatch):
    """«Дата и чек» (HEAD 10.11): Анна вносила оплаты в «Поступление 1» без даты (525, 1317, 1329, 1587). В приложении к такой
    оплате указывают дату и фото чека: она заменяет поле сделки, «Поступило» не задваивается, импорт поле больше не читает."""
    from artgame import drive
    from test_finance import JPG
    ids = setup(client, monkeypatch)
    deals = {"1317": {**deal(1317, opp=160_000, **{A1: "80000|KZT", D1: "", REC: "0|KZT", DEBT: "160000|KZT"}),
                      "TITLE": "1317 · КИБЕРКЛУБ CYBORG — ШЫМКЕНТ", "ASSIGNED_BY_ID": "4565"},
             "1329": {**deal(1329, stage="WON", sem="S", opp=250_000, **{A1: "250000|KZT", D1: ""}),
                      "TITLE": "1329 · КОРЕЙСКИЙ МАГАЗИН РАМИ — АСТАНА", "ASSIGNED_BY_ID": "4565"},
             "1277": {**deal(1277, opp=300_000, **{A1: "150000|KZT", D1: "2026-10-20"}), "ASSIGNED_BY_ID": "4565"}}
    monkeypatch.setattr(bx, "READ", lambda m, p: {"result": deals.get(str(p["id"]))} if m == "crm.deal.get" else {"result": []})
    monkeypatch.setattr(bx, "read_all", lambda m, p, fresh=False, **k: [dict(d) for d in deals.values()])
    monkeypatch.setattr(drive, "save_income_receipt", lambda *a: "drv")
    client.post(f"/api/people/{ids[3000]}", json={"pays": True}, headers=hdr(1000))
    with db.pool.connection() as conn, conn.transaction():
        assert fin_bx.import_payments(conn)["added"] == 1   # открытая 1317: без даты — днём, когда импорт увидел; закрытая 1329 — нет
    c = dm.card(deals["1317"])
    assert c["received"] == 80_000 and [(x["source"], x["slot"]) for x in c["items"]] == [("bitrix", 1)] and c["history"] == []
    c = dm.card(deals["1329"])
    assert c["received"] == 250_000 and c["debt"] == 0 and c["history"] == [{"n": 1, "slot": 1, "date": "", "amount": 250_000}]
    assert dm.card(deals["1277"])["history"][0]["slot"] is None   # с датой — «Дата и чек» не нужна

    pay = {"client_uid": uid(), "amount": 80000, "op_date": "2026-11-04", "account": "kaspi", "receipt": JPG, "slot": 1}
    r = client.post("/api/bx/deals/1317/payment", json=pay, headers=hdr(3000))
    assert r.status_code == 200, r.text
    row = r.json()["row"]
    assert row["source"] == "app" and row["source_ref"] == "deal:1317:pay1" and "вместо «Поступление 1» без даты" in row["note"]
    c = r.json()["pay"]
    assert c["received"] == 80_000 and c["debt"] == 80_000 and c["on_check"] == 80_000   # не 160 000
    assert [(x["source"], x["status"], x["slot"]) for x in c["items"]] == [("app", "active", None)]   # строка импорта заменена
    assert client.post("/api/bx/deals/1317/payment", json=pay, headers=hdr(3000)).json()["row"]["id"] == row["id"]   # повтор очереди
    with db.pool.connection() as conn, conn.transaction():
        assert fin_bx.import_payments(conn) == {"deals": 3, "added": 0, "changed": 0}   # поле больше не читаем
    assert dm.card(deals["1317"])["received"] == 80_000

    # закрытая сделка, оплата в октябре: «История», «Поступило» 250 000, а не 500 000
    r = client.post("/api/bx/deals/1329/payment", json={**pay, "client_uid": uid(), "amount": 250000, "op_date": "2026-10-15"},
                    headers=hdr(3000)).json()
    assert r["row"]["account_code"] == "hist" and r["pay"]["received"] == 250_000 and r["pay"]["debt"] == 0 and r["pay"]["history"] == []
    # второй раз к той же оплате, к оплате с датой, к пустому полю — нельзя
    assert client.post("/api/bx/deals/1329/payment", json={**pay, "client_uid": uid()}, headers=hdr(3000)).status_code == 409
    assert client.post("/api/bx/deals/1277/payment", json={**pay, "client_uid": uid()}, headers=hdr(3000)).status_code == 400
    assert client.post("/api/bx/deals/1317/payment", json={**pay, "client_uid": uid(), "slot": 2}, headers=hdr(3000)).status_code == 400
    # HEAD ✕: оплаты нет — и поле сделки обратно не считается
    assert client.post(f"/api/fin/ledger/{row['id']}/cancel", headers=hdr(1000)).json()["ok"]
    c = dm.card(deals["1317"])
    assert c["received"] == 0 and c["debt"] == 160_000 and not any(x["slot"] for x in c["items"]) and c["history"] == []


def test_cash_without_photo(client, monkeypatch):
    """Наличные (HEAD 10.11): оплату наличными вносят без фото чека, HEAD сверяет сам; безналичную без фото внести нельзя.
    До ноября счёт — «История», наличные — отметкой в комментарии."""
    from datetime import date

    from artgame import drive
    ids = setup(client, monkeypatch)
    client.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    d = {**deal(1611, opp=110_000), "ASSIGNED_BY_ID": "4565"}
    monkeypatch.setattr(bx, "READ", lambda m, p: {"result": d})
    saved = []
    monkeypatch.setattr(drive, "save_income_receipt", lambda *a: saved.append(a) or "drv")
    pay = {"client_uid": uid(), "amount": 110000, "op_date": str(date.today()), "account": "kaspi"}
    assert client.post("/api/bx/deals/1611/payment", json=pay, headers=hdr(6000)).status_code == 400   # Kaspi без фото — нельзя
    r = client.post("/api/bx/deals/1611/payment", json={**pay, "account": "cash"}, headers=hdr(6000))
    assert r.status_code == 200, r.text
    row = r.json()["row"]
    assert row["account_code"] == "cash" and row["receipt_file_id"] is None and row["receipt_url"] is None and not saved
    assert r.json()["pay"]["received"] == 110_000 and r.json()["pay"]["debt"] == 0
    assert [(x["deal_id"], x["receipt_url"]) for x in client.get("/api/fin/payments/check", headers=hdr(1000)).json()] == [(1611, None)]
    # до ноября: «История», наличные — отметкой; без отметки «наличные» и без фото — нельзя
    r = client.post("/api/bx/deals/1611/payment", json={**pay, "client_uid": uid(), "amount": 5000, "op_date": "2026-10-20", "account": "hist",
                                                        "cash": True}, headers=hdr(6000)).json()
    assert r["row"]["account_code"] == "hist" and "до ноября · наличными" in r["row"]["note"]
    assert client.post("/api/bx/deals/1611/payment", json={**pay, "client_uid": uid(), "op_date": "2026-10-20", "account": "hist"},
                       headers=hdr(6000)).status_code == 400
