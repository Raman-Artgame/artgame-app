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


def test_head_own_expense_no_review(client):
    """Трата самого HEAD сразу принята и не висит у него же в «Проверке»; трата художника — ждёт."""
    setup_people(client)
    body = {"object_id": 731, "zone_code": "mural", "category": "other", "amount": 250000, "paid_by": "company", "note": "планшет"}
    h = client.post("/api/expenses", json={**body, "client_uid": str(uuid.uuid4())}, headers=hdr(1000)).json()
    a = client.post("/api/expenses", json={**body, "client_uid": str(uuid.uuid4())}, headers=hdr(2000)).json()
    assert h["status"] == "approved" and a["status"] == "submitted"
    assert [x["id"] for x in client.get("/api/review", headers=hdr(1000)).json()["expenses"]] == [a["id"]]
    # глазами художника HEAD ничего не пишет вовсе
    assert client.post("/api/expenses", json={**body, "client_uid": str(uuid.uuid4())}, headers=va(1000, 2)).status_code == 403


def test_test_as_role_writes_for_test_person(client, monkeypatch):
    """«Пройти как сотрудник» (test): HEAD действует от «Тест · Саппорт» — смена по шагам доходит до проверки по-настоящему."""
    from test_files import JPEG, FakeDrive
    from artgame import drive, viewas
    FakeDrive.store = {}
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    monkeypatch.setattr(viewas.settings, "public_origin", "https://test.app.artgame.world")
    setup_people(client)
    with db.pool.connection() as c:
        c.execute("UPDATE objects SET bitrix_stage='UC_AV00QK' WHERE id=731")
    opts = client.get("/api/view-as/options", headers=hdr(1000)).json()
    assert opts["test"] is True
    me = client.get("/api/me", headers=va(1000, "test:support")).json()
    assert me["role_code"] == "support" and me["full_name"] == "Тест · Саппорт" and me["_view_as"]["kind"] == "test"
    assert me["zones"] == ["mural"]
    assert client.get("/api/me", headers=va(1000, "test:support")).json()["id"] == me["id"]   # один на роль
    assert client.get("/api/me", headers=va(2000, "test:support")).status_code == 403          # только HEAD
    uid = str(uuid.uuid4())
    s = client.post("/api/shifts/start", json={"client_uid": uid, "object_id": 731, "zone_code": "mural", "started_at": T0,
                                               "photo_before": JPEG}, headers=va(1000, "test:support"))
    assert s.status_code == 200, s.text
    f = client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": T1, "area_m2": 2, "work_done": "Грунт и разметка",
                                                "photo_after": JPEG}, headers=va(1000, "test:support")).json()
    assert f["status"] == "submitted" and f["person_id"] == me["id"]
    assert len(FakeDrive.store) == 2
    with db.pool.connection() as c:
        assert c.execute("SELECT person_id FROM audit_log WHERE action='shift_finish'").fetchone()["person_id"] == me["id"]
    # тестовые сотрудники не мешают списку «смотреть как»
    assert me["id"] not in {p["id"] for p in client.get("/api/view-as/options", headers=hdr(1000)).json()["people"]}
    # на prod режима нет — ни по ARTGAME_ENV_NAME, ни по адресу (если имя среды забыли)
    monkeypatch.setattr(viewas.settings, "public_origin", "https://app.artgame.world")
    monkeypatch.setattr(viewas.settings, "database_url", "postgresql://artgame@localhost/artgame_prod")
    assert client.get("/api/me", headers=va(1000, "test:support")).status_code == 403
    monkeypatch.setattr(viewas.settings, "database_url", "postgresql://artgame@localhost/artgame_test")   # адрес не задан, база test — можно
    assert client.get("/api/me", headers=va(1000, "test:support")).status_code == 200
    monkeypatch.setattr(viewas.settings, "public_origin", "https://test.app.artgame.world")
    monkeypatch.setattr(viewas.settings, "env_name", "prod")
    assert client.get("/api/me", headers=va(1000, "test:support")).status_code == 403
    r = client.post("/api/shifts/start", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural",
                                               "started_at": T0, "photo_before": JPEG}, headers=va(1000, "test:support"))
    assert r.status_code == 403


def test_purge_test_people(client, monkeypatch):
    """HEAD 09.11: «Тест · …» — убрать отовсюду, прямо удалить: смены, расходы, фото, журнал; настоящие люди не трогаются."""
    from test_files import JPEG, FakeDrive
    from artgame import drive, viewas
    FakeDrive.store = {}
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    monkeypatch.setattr(viewas.settings, "public_origin", "https://test.app.artgame.world")
    setup_people(client)
    with db.pool.connection() as c:
        c.execute("UPDATE objects SET bitrix_stage='UC_AV00QK' WHERE id=731")
        real = c.execute("SELECT count(*) AS n FROM people").fetchone()["n"]
    client.post("/api/view-as/start", json={"target": "test:support"}, headers=hdr(1000))
    uid = str(uuid.uuid4())
    client.post("/api/shifts/start", json={"client_uid": uid, "object_id": 731, "zone_code": "mural", "started_at": T0, "photo_before": JPEG},
                headers=va(1000, "test:support"))
    s = client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": T1, "area_m2": 2, "work_done": "Тест", "photo_after": JPEG},
                    headers=va(1000, "test:support")).json()
    client.post(f"/api/shift/{s['id']}/review", json={"approve": False, "reason": "Тест"}, headers=hdr(1000))
    assert client.post("/api/view-as/purge", headers=va(1000, "test:support")).status_code == 403   # только «у себя»
    assert client.post("/api/view-as/purge", headers=hdr(1000)).json()["people"] == 1
    with db.pool.connection() as c:
        assert c.execute("SELECT count(*) AS n FROM people").fetchone()["n"] == real
        assert c.execute("SELECT count(*) AS n FROM shifts").fetchone()["n"] == 0
        assert c.execute("SELECT count(*) AS n FROM files").fetchone()["n"] == 0
        assert c.execute("""SELECT count(*) AS n FROM audit_log WHERE entity='shifts' OR person_id IS NULL
                            OR (action LIKE 'view_as%%' AND data->>'target' LIKE 'test:%%')""").fetchone()["n"] == 0
    assert client.post("/api/view-as/purge", headers=hdr(1000)).json()["people"] == 0
