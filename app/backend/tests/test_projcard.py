"""HEAD 14.11: карточка проекта — кто встречает на объекте (телефон ГИП/МОП/HEAD) и деньги проекта (HEAD и МОП)."""
from artgame import db
from conftest import hdr
from test_cabinets import dz  # noqa: F401


def test_contact_and_money(client, dz, monkeypatch):  # noqa: F811
    ids, _ = dz
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1810, 'Кафе карточка', 'Астана', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
    body = {"name": "Айгуль, администратор", "phone": "+7 701 000 00 00"}
    assert client.post("/api/objects/1810/contact", json=body, headers=hdr(2000)).status_code == 403
    assert client.post("/api/objects/1810/contact", json=body, headers=hdr(1000)).json()["phone"] == body["phone"]
    from artgame import projcard
    assert projcard.can_phone({"role_code": "artist", "id": ids[2000]}, None) is False
    assert projcard.can_phone({"role_code": "artist", "id": ids[2000]}, ids[2000]) is True
    with db.pool.connection() as c:
        assert c.execute("SELECT site_phone FROM objects WHERE id=1810").fetchone()["site_phone"] == body["phone"]
    # деньги: художнику нельзя, HEAD — сумма, долг, затраты, маржа
    assert client.get("/api/objects/1810/money", headers=hdr(2000)).status_code == 403
    from artgame import bx
    monkeypatch.setattr(bx, "_deal", lambda p, i, fresh=False: {"ID": str(i), "OPPORTUNITY": "1160000", "TITLE": "1810 · КАФЕ"})
    m = client.get("/api/objects/1810/money", headers=hdr(1000)).json()
    assert m["sum"] == 1160000 and m["costs_total"] == 0 and m["profit"] == m["net"] and m["debt"] >= 0


def test_materials_and_promo(client, dz):  # noqa: F811
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1811, 'Кафе материалы', 'Астана', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
    assert client.get("/api/objects/1811/materials", headers=hdr(2000)).status_code == 403
    m = client.get("/api/objects/1811/materials", headers=hdr(1000)).json()
    assert m == {"kits": [], "buys": [], "buys_total": 0}
    pr = client.get("/api/objects/1811/promo", headers=hdr(2000)).json()
    assert pr["publish"] is None and pr["can_set"] is False and pr["photo"] == 0
    assert client.post("/api/objects/1811/publish", json={"ok": True}, headers=hdr(2000)).status_code == 403
    assert client.post("/api/objects/1811/publish", json={"ok": True}, headers=hdr(1000)).json()["publish"] is True
    assert client.get("/api/objects/1811/promo", headers=hdr(1000)).json()["publish"] is True
