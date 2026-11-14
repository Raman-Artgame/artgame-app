"""И.о. Главного художника (HEAD 09.11): права и меню Главного, ставка и ФОТ — художника; повышение снимает «и.о.»."""
from artgame import db
from conftest import hdr
from test_dual_role import _shift
from test_production import VALS, Copying, team  # noqa: F401


def test_acting_lead(client, team):  # noqa: F811
    pid = client.post("/api/register", json={"full_name": "Ангелина Тест"}, headers=hdr(6200)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "artist", "zones": ["mural"]}, headers=hdr(1000))
    assert client.post(f"/api/people/{pid}", json={"acting_role": "head"}, headers=hdr(1000)).status_code == 400
    r = client.post(f"/api/people/{pid}", json={"acting_role": "lead_artist", "acting_promo": "2026-12-15",
                                                "acting_note": "День рождения команды"}, headers=hdr(1000)).json()
    assert r["acting_role"] == "lead_artist" and str(r["acting_promo"]) == "2026-12-15" and r["acting_since"]
    me = client.get("/api/me", headers=hdr(6200)).json()
    assert me["role_code"] == "lead_artist" and me["acting"] and me["roles"] == ["artist"] and me["role_main"] == "artist"
    # смена — по ставке художника
    assert _shift(client, 6200, "mural", 6)["role_code"] == "artist"
    # повышение: HEAD ставит роль «Главный художник» — «и.о.» снимается
    r = client.post(f"/api/people/{pid}", json={"role_code": "lead_artist"}, headers=hdr(1000)).json()
    assert r["acting_role"] is None and r["acting_promo"] is None
    me = client.get("/api/me", headers=hdr(6200)).json()
    assert me["role_code"] == "lead_artist" and not me.get("acting")
    # снять «и.о.» пустой строкой
    client.post(f"/api/people/{pid}", json={"role_code": "artist"}, headers=hdr(1000))
    client.post(f"/api/people/{pid}", json={"acting_role": "lead_artist"}, headers=hdr(1000))
    assert client.post(f"/api/people/{pid}", json={"acting_role": ""}, headers=hdr(1000)).json()["acting_role"] is None
    with db.pool.connection() as c:
        assert c.execute("SELECT acting_since FROM people WHERE id=%s", (pid,)).fetchone()["acting_since"] is None
