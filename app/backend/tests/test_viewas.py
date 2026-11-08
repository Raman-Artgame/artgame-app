"""«Смотреть как сотрудник» и «Пульт» HEAD (08.11)."""
import uuid

from artgame import db
from conftest import hdr
from test_places import placed  # noqa: F401  (фикстура мест)
from test_work import T0, T1, setup_people


def va(tg, target):
    return {**hdr(tg), "X-View-As": str(target)}


def test_view_as_person_read_only_and_journal(client):
    ids = setup_people(client)
    art = ids[2000]
    # только HEAD
    assert client.get("/api/me", headers=va(3000, art)).status_code == 403
    assert client.post("/api/view-as/start", json={"target": str(art)}, headers=hdr(2000)).status_code == 403
    assert client.get("/api/view-as/options", headers=hdr(2000)).status_code == 403
    opts = client.get("/api/view-as/options", headers=hdr(1000)).json()
    assert {p["id"] for p in opts["people"]} == set(ids.values()) and "head" not in {r["code"] for r in opts["roles"]}
    assert client.post("/api/view-as/start", json={"target": str(art)}, headers=hdr(1000)).json()["role_code"] == "artist"
    me = client.get("/api/me", headers=va(1000, art)).json()
    assert me["id"] == art and me["role_code"] == "artist" and me["_view_as"]["viewer_name"] == "HEAD"
    # видит как художник: разделы HEAD закрыты
    assert client.get("/api/people", headers=va(1000, art)).status_code == 403
    assert client.get("/api/work/dict", headers=va(1000, art)).status_code == 200
    # запись закрыта до обработчика
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "started_at": T0, "ended_at": T1, "area_m2": 5}
    r = client.post("/api/shifts", json=body, headers=va(1000, art))
    assert r.status_code == 403 and r.json()["view_as"] is True
    with db.pool.connection() as c:
        assert c.execute("SELECT count(*) AS n FROM shifts").fetchone()["n"] == 0
    client.post("/api/view-as/stop", json={"target": str(art)}, headers=hdr(1000))
    with db.pool.connection() as c:
        head = c.execute("SELECT id FROM people WHERE tg_id=1000").fetchone()["id"]
        acts = c.execute("SELECT person_id, action FROM audit_log WHERE action LIKE 'view_as%%' ORDER BY id").fetchall()
        # журнал, который сервер пишет во время просмотра, — на HEAD с пометкой
        db.audit(c, art, "deal_open", "deal", 1)   # вне просмотра — на самого человека
        assert c.execute("SELECT person_id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()["person_id"] == art
    assert [(a["person_id"], a["action"]) for a in acts] == [(head, "view_as_start"), (head, "view_as_stop")]
    # журнал HEAD показывает просмотр
    j = client.get("/api/journal", headers=hdr(1000)).json()
    assert {"view_as_start", "view_as_stop"} <= {i["action"] for i in j["items"]}


def test_view_as_role_and_audit_owner(client):
    ids = setup_people(client)
    me = client.get("/api/me", headers=va(1000, "role:mop")).json()
    assert me["role_code"] == "mop" and me["zones"] == ["sales"] and me["full_name"].startswith("Пример")
    assert client.get("/api/me", headers=va(1000, "role:head")).status_code == 400
    assert client.get("/api/me", headers=va(1000, "role:nope")).status_code == 400
    assert client.get("/api/me", headers=va(1000, 99999)).status_code == 404
    # чужой журнал не пополняется, пока HEAD смотрит: запись уходит на HEAD с пометкой
    from artgame import viewas
    tok = viewas.VIEW.set({"as": str(ids[2000]), "viewer": 1, "target": {"kind": "person", "id": ids[2000]}})
    try:
        with db.pool.connection() as c:
            head = c.execute("SELECT id FROM people WHERE tg_id=1000").fetchone()["id"]
            viewas.VIEW.get()["viewer"] = head
            db.audit(c, ids[2000], "deal_open", "deal", 5)
            r = c.execute("SELECT person_id, data FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        viewas.VIEW.reset(tok)
    assert r["person_id"] == head and r["data"]["view_as"]["id"] == ids[2000] and r["data"]["for"] == ids[2000]


def test_place_link_read_only(placed):  # noqa: F811
    ids = setup_people(placed)
    head_url = {p["code"]: p["url"] for p in placed.get("/api/places", headers=hdr(1000)).json()}["dz"].removesuffix("/index.html")
    assert placed.put(head_url + "/_db/projects/p1", json={"a": 1}).status_code == 200
    # HEAD как роль «Главный дизайнер»: место открывается, но писать нельзя
    lst = placed.get("/api/places", headers=va(1000, "role:lead_designer")).json()
    url = lst[0]["url"].removesuffix("/index.html")
    assert url.count(".") == 3 and placed.get(url + "/index.html").status_code == 200
    assert placed.get(url + "/_db/projects").json()["docs"][0]["id"] == "p1"
    assert placed.put(url + "/_db/projects/p1", json={"a": 2}).status_code == 403
    # подделка пометки — ссылка не проходит
    bad = url.rsplit(".", 1)[0] + "/_db/projects"
    assert placed.get(bad).status_code == 403
    # художник глазами HEAD: место художников видно, запись закрыта
    art = placed.get("/api/places", headers=va(1000, ids[2000])).json()
    assert [p["code"] for p in art] == ["art"]


def test_pulse(client):
    ids = setup_people(client)
    client.post("/api/register", json={"full_name": "Новый"}, headers=hdr(7000))
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "started_at": T0, "ended_at": T1, "area_m2": 5}
    client.post("/api/shifts", json=body, headers=hdr(2000))
    assert client.get("/api/head/pulse", headers=hdr(2000)).status_code == 403
    assert client.get("/api/head/pulse", headers=va(1000, ids[2000])).status_code == 403   # глазами художника пульта нет
    p = client.get("/api/head/pulse", headers=hdr(1000)).json()
    assert [x["full_name"] for x in p["pending"]] == ["Новый"]
    assert p["review"]["shifts"] == 1 and p["review"]["expenses"] == 0
    assert any(t["code"] == "artist" and t["active"] == 2 for t in p["team"])
    assert p["feed"][0]["action"] in ("shift_add", "register")
