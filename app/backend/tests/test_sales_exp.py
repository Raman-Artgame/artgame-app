"""Траты отдела продаж (HEAD 05.11): чек обязателен, лимит МОП из «Значений», сверх — к HEAD, привязка к сделке по желанию."""
import uuid

from psycopg.types.json import Jsonb

from artgame import db, drive
from conftest import hdr
from test_bx import bxc  # noqa: F401  — фикстура: HEAD, МОП 6000/6100, художник 2000

JPG = "data:image/jpeg;base64,/9j/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def body(amount, **kw):
    return {"client_uid": str(uuid.uuid4()), "category": "sales_trip", "amount": amount, "receipt": JPG, **kw}


def limit(v):
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                     (str(uuid.uuid4()), Jsonb({"mop.expense.limit_month": {"value": str(v), "status": "Утверждено"}} if v else {})))


def test_sales_expenses(bxc, monkeypatch):  # noqa: F811
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    saved = []
    monkeypatch.setattr(drive, "save_receipt", lambda conn, dept, name, data, deal_id=None: saved.append(name) or f"drv-{len(saved)}")
    # без чека — нельзя; чужая статья (проектная) — нельзя; художнику — нельзя
    assert c.post("/api/sales/expenses", json={**body(1000), "receipt": ""}, headers=hdr(6000)).status_code == 422
    assert c.post("/api/sales/expenses", json=body(1000, category="paint"), headers=hdr(6000)).status_code == 400
    assert c.post("/api/sales/expenses", json=body(1000), headers=hdr(2000)).status_code == 403
    # лимит не задан — всё к HEAD
    limit(0)
    r = c.post("/api/sales/expenses", json=body(3000), headers=hdr(6000)).json()
    assert r["status"] == "submitted" and r["over_limit"] and not r["auto"]
    # лимит 20 000: в пределах — одобрено само, «к выплате»; сверх — к HEAD
    limit(20000)
    b = body(12000, deal_id=1601, note="такси на замер", category="sales_trip")
    r1 = c.post("/api/sales/expenses", json=b, headers=hdr(6000)).json()
    assert r1["status"] == "approved" and r1["payout_status"] == "to_pay" and r1["deal_id"] == 1601 and r1["receipt_url"]
    assert c.post("/api/sales/expenses", json=b, headers=hdr(6000)).json()["id"] == r1["id"] and len(saved) == 2   # повтор из очереди
    r2 = c.post("/api/sales/expenses", json=body(6000, category="sales_office", paid_by="company"), headers=hdr(6000)).json()
    assert r2["status"] == "submitted" and r2["over_limit"]   # 3000 + 12000 + 6000 > 20000
    assert c.post("/api/sales/expenses", json=body(4000), headers=hdr(6100)).json()["status"] == "approved"   # лимит у каждого свой
    m = c.get("/api/sales/expenses", headers=hdr(6000)).json()
    assert m["limit"] == 20000 and m["spent"] == 21000 and m["left"] == 0 and m["waiting"] == 2 and len(m["items"]) == 3
    assert m["by_category"]["sales_trip"] == 15000 and m["by_category"]["sales_office"] == 6000 and not m["all"]
    # HEAD видит отдел и одобряет сверх лимита во «Проверке»
    h = c.get("/api/sales/expenses", headers=hdr(1000)).json()
    assert h["all"] and h["total"] == 25000 and [p["total"] for p in h["people"]] == [21000, 4000]
    rv = c.get("/api/review", headers=hdr(1000)).json()["expenses"]
    x2 = next(x for x in rv if x["id"] == r2["id"])
    assert x2["object_title"] == "Отдел продаж · Канцелярия и материалы · сверх лимита"
    assert c.post(f"/api/expense/{r2['id']}/review", json={"approve": True}, headers=hdr(1000)).json()["status"] == "approved"
    # проектная форма «Расход» не видит статей отдела продаж
    assert not any(x["code"].startswith("sales_") for x in c.get("/api/work/dict", headers=hdr(6000)).json()["categories"])
    # карточка сделки: стоимость привлечения
    assert c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()["acq"] == {"sum": 12000.0, "count": 1}
    # Диск недоступен — 502, трата не записана (телефон повторит)
    monkeypatch.setattr(drive, "save_receipt", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert c.post("/api/sales/expenses", json=body(100), headers=hdr(6100)).status_code == 502
