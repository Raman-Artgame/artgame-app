"""HEAD 14.11: дизайн в карточке проекта на любой стадии — сложность, дизайн/правка/докидка, утверждение HEAD → единицы и ФОТ."""
from datetime import date

from artgame import db
from conftest import hdr
from test_cabinets import dz  # noqa: F401


def test_design_in_project(client, dz, monkeypatch):  # noqa: F811
    ids, _ = dz
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1800, 'Кафе дизайн', 'Астана', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
    from artgame import bx, bxw
    monkeypatch.setattr(bx, "read", lambda *a, **k: {"result": {}})
    calls = []
    monkeypatch.setattr(bxw, "enabled", lambda: True)
    monkeypatch.setattr(bxw, "CALL", lambda m, prm: calls.append((m, prm)) or {"result": True})
    # дизайнер (не главный) сложность не ставит; Главный — ставит, S–XL уходит в сделку
    assert client.post("/api/design/object/1800/size", json={"size": "m"}, headers=hdr(7100)).status_code == 403
    assert client.post("/api/design/object/1800/size", json={"size": "m"}, headers=hdr(7000)).json()["bx"] == "ok"
    assert calls[0][0] == "crm.deal.update" and calls[0][1]["id"] == 1800
    assert client.post("/api/design/object/1800/size", json={"size": "xs"}, headers=hdr(7000)).json()["bx"] == "local"
    assert client.get("/api/design/object/1800", headers=hdr(7000)).json()["size"] == "xs"
    # докидка от Главного → HEAD утверждает → единицы дизайнеру в месяце
    body = {"kind": "fix", "size": "xs", "person_id": ids[7100], "note": "Докинули птиц слева", "url": "https://drive/x"}
    assert client.post("/api/design/object/1800/extra", json={**body, "person_id": ids[2000]}, headers=hdr(7000)).status_code == 400
    x = client.post("/api/design/object/1800/extra", json=body, headers=hdr(7000)).json()["id"]
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["design_wait"] == 1
    assert client.post(f"/api/design/extra/{x}/decide", json={"approve": True}, headers=hdr(7000)).status_code == 403
    assert client.post(f"/api/design/extra/{x}/decide", json={"approve": False}, headers=hdr(1000)).status_code == 400
    assert client.post(f"/api/design/extra/{x}/decide", json={"approve": True}, headers=hdr(1000)).json()["ok"]
    ym = date.today().strftime("%Y-%m")
    u = client.get(f"/api/design/units?ym={ym}", headers=hdr(7100)).json()
    assert u["mine"] == 0.5 and u["extras"][0]["object_title"] == "Кафе дизайн"
    # HEAD вносит сам — сразу утверждено
    client.post("/api/design/object/1800/extra", json={**body, "kind": "design", "size": "s", "note": "Дизайн проекта"}, headers=hdr(1000))
    assert client.get(f"/api/design/units?ym={ym}", headers=hdr(7100)).json()["mine"] == 1.5
