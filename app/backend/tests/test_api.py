from artgame import constants as consts
from artgame import db
from conftest import hdr


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_no_signature(client):
    assert client.get("/api/me").status_code == 401


def test_register_and_roles(client):
    # HEAD по ARTGAME_HEAD_TG_ID сразу активен
    h = client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000)).json()
    assert h["role_code"] == "head" and h["status"] == "active"
    assert h["zones"] == ["design", "mural", "print", "sales"]
    # художник регистрируется сам → ждёт роли
    a = client.post("/api/register", json={"full_name": "Художник"}, headers=hdr(2000)).json()
    assert a["status"] == "pending" and a["role_code"] is None
    # повторная регистрация не создаёт дубль
    assert client.post("/api/register", json={"full_name": "X"}, headers=hdr(2000)).json()["id"] == a["id"]
    # роли назначает только HEAD
    assert client.get("/api/people", headers=hdr(2000)).status_code == 403
    r = client.post(f"/api/people/{a['id']}", json={"role_code": "artist", "zones": ["mural", "print"]}, headers=hdr(1000))
    assert r.json()["status"] == "active"
    me = client.get("/api/me", headers=hdr(2000)).json()
    assert me["role_code"] == "artist" and me["zones"] == ["mural", "print"]
    # уход: вход закрыт, история остаётся
    client.post(f"/api/people/{a['id']}", json={"status": "blocked"}, headers=hdr(1000))
    assert client.get("/api/me", headers=hdr(2000)).status_code == 403
    assert len(client.get("/api/people", headers=hdr(1000)).json()) == 2
    with db.pool.connection() as c:
        acts = [r["action"] for r in c.execute("SELECT action FROM audit_log ORDER BY id")]
    assert acts == ["register", "register", "assign", "assign"]


def test_constants_visibility(client):
    rows = [["mural.rate.a", "Роспись", "Ставка", "17", "тыс", "все", "Утверждено"],
            ["pay.artist", "Оплата", "Оплата", "1", "", "head", "Утверждено"],
            ["mop.pct", "МОП", "%", "3", "%", "моп", "Утверждено"],
            ["draft.x", "", "", "1", "", "все", "Черновик"]]
    with db.pool.connection() as c:
        assert consts.store_if_changed(c, consts.parse_rows(rows)) is True
        assert consts.store_if_changed(c, consts.parse_rows(rows)) is False
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    a = client.post("/api/register", json={"full_name": "A"}, headers=hdr(2000)).json()
    client.post(f"/api/people/{a['id']}", json={"role_code": "artist"}, headers=hdr(1000))
    assert set(client.get("/api/constants", headers=hdr(2000)).json()["values"]) == {"mural.rate.a"}
    assert set(client.get("/api/constants", headers=hdr(1000)).json()["values"]) == {"mural.rate.a", "pay.artist", "mop.pct"}
