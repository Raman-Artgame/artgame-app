"""Закупки на склад для всех ролей (HEAD 06.11): каталог из журнала закупок, потолок = ориентир + допуск из «Значений»,
в пределах потолка — принято само, выше потолка или без ориентира — к HEAD; деньги — в финансы (статья stock / canvas)."""
import uuid

from psycopg.types.json import Jsonb

from artgame import db, drive
from conftest import hdr

JPG = "data:image/jpeg;base64,/9j/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def buy(client, tg, dept, lines, **kw):
    return client.post("/api/stock/purchase", json={"client_uid": str(uuid.uuid4()), "dept": dept, "lines": lines, "receipt": JPG, **kw},
                       headers=hdr(tg))


def test_stock_purchase(client, monkeypatch):
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                     ("t", Jsonb({"stock.price_tolerance_pct": {"value": "15", "status": "Утверждено", "who": "head"}})))
    monkeypatch.setattr(drive, "save_receipt", lambda conn, dept, name, data, deal_id=None: f"drv-{dept}")
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    for tg, role in [(2000, "artist"), (6000, "mop"), (8000, "carpenter")]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": []}, headers=hdr(1000))

    cat = client.get("/api/stock/catalog", headers=hdr(2000)).json()
    assert cat["home"] == "art" and cat["tolerance"] == 15 and not cat["head"]
    assert len(cat["depts"]) == 7 and len(cat["items"]) > 150
    val = next(i for i in cat["items"] if i["code"] == "ХУД-001")
    assert val["ref_price"] == 320 and val["cap_price"] == 368
    assert client.get("/api/stock/catalog", headers=hdr(6000)).json()["home"] == "household"

    # художник: валики по 350 (выше ориентира, в потолке) — принято само, к выплате
    a = buy(client, 2000, "art", [{"item_code": "ХУД-001", "qty": 10, "amount": 3500}]).json()
    assert a["status"] == "approved" and a["payout_status"] == "to_pay" and a["category"] == "stock_art" and a["auto"]
    assert a["lines"][0]["flag"] == "above_ref"
    # МОП: мешки выше потолка + своя позиция без ориентира — к HEAD
    b = buy(client, 6000, "household", [{"item_code": "ХОЗ-003", "qty": 2, "amount": 800}, {"name": "Чайник", "qty": 1, "amount": 9000}],
            paid_by="company").json()
    assert b["status"] == "submitted" and b["amount"] == "9800.00" or float(b["amount"]) == 9800
    assert [x["flag"] for x in b["lines"]] == ["over_cap", "no_ref"]
    # плотник: мастерская идёт в статью canvas
    c = buy(client, 8000, "workshop", [{"item_code": "МАС-001", "qty": 4, "amount": 3000}]).json()
    assert c["status"] == "approved" and c["category"] == "canvas_workshop"
    # ошибки
    assert buy(client, 2000, "nope", [{"item_code": "ХУД-001", "qty": 1, "amount": 1}]).status_code == 400
    assert buy(client, 2000, "art", [{"name": " ", "qty": 1, "amount": 1}]).status_code == 400
    assert buy(client, 2000, "art", [{"item_code": "ХУД-001", "qty": 1, "amount": 1}], receipt="x" * 40).status_code == 400
    # повтор того же client_uid не задваивает
    u = str(uuid.uuid4())
    body = {"client_uid": u, "dept": "art", "lines": [{"item_code": "ХУД-007", "qty": 1, "amount": 170}], "receipt": JPG}
    assert client.post("/api/stock/purchase", json=body, headers=hdr(2000)).json()["id"] == \
        client.post("/api/stock/purchase", json=body, headers=hdr(2000)).json()["id"]

    # проверка HEAD: видно, почему ждёт
    rv = {x["id"]: x for x in client.get("/api/review", headers=hdr(1000)).json()["expenses"]}
    assert rv[b["id"]]["object_title"] == "Склад · Хозтовары и офис · выше потолка цены, нет ориентира цены"
    assert "Чайник × 1 = 9 000 (нет ориентира)" in rv[b["id"]]["note"]
    assert client.post(f"/api/expense/{b['id']}/review", json={"approve": True}, headers=hdr(1000)).json()["status"] == "approved"

    # мои закупки видны всем ролям; HEAD видит все
    mine = client.get("/api/stock/expenses", headers=hdr(2000)).json()
    assert {x["id"] for x in mine["items"]} >= {a["id"]} and not mine["all"]
    assert len(client.get("/api/stock/expenses", headers=hdr(1000)).json()["items"]) == 4
    assert len(client.get(f"/api/stock/lines/{b['id']}", headers=hdr(1000)).json()) == 2
    assert client.get(f"/api/stock/lines/{b['id']}", headers=hdr(2000)).status_code == 404

    # средняя фактическая цена по принятым
    it = {i["code"]: i for i in client.get("/api/stock/catalog", headers=hdr(1000)).json()["items"]}
    assert it["ХУД-001"]["fact_price"] == 350 and it["ХОЗ-003"]["fact_price"] == 400

    # ошиблись разделом (Анна 06.11: такси в «Склад») — своя покупка отменяется, чужая — нет; из списка и «факта» уходит
    assert client.post(f"/api/stock/expenses/{a['id']}/cancel", headers=hdr(6000)).status_code == 409
    assert client.post(f"/api/stock/expenses/{a['id']}/cancel", headers=hdr(2000)).json() == {"ok": True}
    assert client.post(f"/api/stock/expenses/{a['id']}/cancel", headers=hdr(2000)).status_code == 409   # второй раз — нечего
    assert a["id"] not in {x["id"] for x in client.get("/api/stock/expenses", headers=hdr(2000)).json()["items"]}
    assert client.get("/api/stock/expenses", headers=hdr(2000)).json()["me"] > 0
    it = {i["code"]: i for i in client.get("/api/stock/catalog", headers=hdr(1000)).json()["items"]}
    assert it["ХУД-001"]["fact_price"] is None
    with db.pool.connection() as conn:
        assert conn.execute("SELECT status, payout_status FROM expenses WHERE id=%s", (a["id"],)).fetchone() == {"status": "cancelled", "payout_status": "none"}

    # каталог правит только HEAD
    e = {"dept": "art", "name": "Валик средний", "unit": "шт", "ref_price": 400}
    assert client.post("/api/stock/items/ХУД-001", json=e, headers=hdr(2000)).status_code == 403
    assert float(client.post("/api/stock/items/ХУД-001", json=e, headers=hdr(1000)).json()["ref_price"]) == 400
    n = client.post("/api/stock/items", json={"dept": "household", "name": "Чайник", "ref_price": 9000}, headers=hdr(1000)).json()
    assert n["code"] == "НОВ-001"

    # в финансах — бюджетный расход «на склад» / «мастерская»
    from datetime import date
    s = client.get("/api/fin/summary", params={"ym": f"{date.today():%Y-%m}"}, headers=hdr(1000)).json()
    assert s["costs"]["stock"] == 9800 + 170 and s["costs"]["canvas"] == 3000
