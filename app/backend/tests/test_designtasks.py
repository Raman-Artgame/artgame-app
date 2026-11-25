"""HEAD 25.11: задачи на дизайн при сделке — МОП просит из карточки, дизайнер ведёт на доске, сделка не уезжает."""
from artgame import db
from conftest import hdr
from test_cabinets import dz  # noqa: F401


def test_design_tasks(client, dz):  # noqa: F811
    ids, calls = dz
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"], "bitrix_user_id": 4565}, headers=hdr(1000))
    # дизайнер сам задачу не ставит; МОП — на свою сделку, сколько угодно раз
    assert client.post("/api/bx/deals/1601/design-tasks", json={"title": "Холл"}, headers=hdr(7100)).status_code == 403
    a = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Столовая", "note": "Стена 6×3"}, headers=hdr(6000)).json()
    b = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Спортзал", "urgent": True}, headers=hdr(6000)).json()
    assert a["stage"] == "new" and b["stage"] == "urgent" and a["deal_title"] == "Продажа"
    r = client.get("/api/bx/deals/1601/design-tasks", headers=hdr(6000)).json()
    assert [x["title"] for x in r["items"]] == ["Столовая", "Спортзал"] and r["can_add"]
    assert not client.get("/api/bx/deals/1601/design-tasks", headers=hdr(7100)).json()["can_add"]
    assert not calls        # в Битрикс ничего не пишем, сделка стоит на месте
    # доска: дизайнер видит неразобранные; взял в работу — задача его
    d = client.get("/api/design/tasks", headers=hdr(7100)).json()
    assert len(d["items"]) == 2 and d["stages"][0]["name"] == "Свежие заказы" and not d["all"]
    t = client.post(f"/api/design/tasks/{a['id']}", json={"stage": "work", "size": "l"}, headers=hdr(7100)).json()
    assert t["designer_id"] == ids[7100] and t["stage_name"] == "Взято в работу" and t["size"] == "l"
    # чужую задачу второй дизайнер не трогает; назначает Главный
    assert client.post(f"/api/design/tasks/{b['id']}", json={"designer_id": ids[7000]}, headers=hdr(7100)).status_code == 403
    assert client.post(f"/api/design/tasks/{b['id']}", json={"designer_id": ids[7000]}, headers=hdr(7000)).json()["designer_id"] == ids[7000]
    assert client.post(f"/api/design/tasks/{b['id']}", json={"stage": "fix"}, headers=hdr(7100)).status_code == 403
    assert len(client.get("/api/design/tasks", headers=hdr(7100)).json()["items"]) == 1
    assert len(client.get("/api/design/tasks", headers=hdr(1000)).json()["items"]) == 2
    # «Утверждено» — только с эскизом; файл должен лежать в ДИЗАЙН этой сделки
    assert client.post(f"/api/design/tasks/{a['id']}", json={"stage": "done"}, headers=hdr(7100)).status_code == 400
    assert client.post(f"/api/design/tasks/{a['id']}", json={"file_id": 999999}, headers=hdr(7100)).status_code == 400
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1601, 'Продажа', 'Астана', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
        fid = c.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, uploaded_by, drive_id)
                           VALUES (gen_random_uuid(), 1601, 'design', 'stolovaya.png', 'image/png', 10, 'ready', %s, 'drive-file-0001')
                           RETURNING id""", (ids[7100],)).fetchone()["id"]
    t = client.post(f"/api/design/tasks/{a['id']}", json={"file_id": fid, "stage": "done"}, headers=hdr(7100)).json()
    assert t["stage"] == "done" and t["approved"] and t["file_name"] == "stolovaya.png"
    m = client.get("/api/bx/deals/1601/design-tasks", headers=hdr(6000)).json()["items"][0]
    assert m["stage_name"] == "УТВЕРЖДЕНО" and m["file_id"] == fid
    # единиц задачи не дают
    with db.pool.connection() as c:
        assert c.execute("SELECT count(*) AS n FROM design_units").fetchone()["n"] == 0
    # убрать: утверждённую нельзя, свою неутверждённую МОП убирает
    assert client.post(f"/api/design/tasks/{a['id']}/cancel", headers=hdr(6000)).status_code == 400
    assert client.post(f"/api/design/tasks/{b['id']}/cancel", headers=hdr(7100)).status_code == 403
    assert client.post(f"/api/design/tasks/{b['id']}/cancel", headers=hdr(6000)).json()["ok"]
    assert len(client.get("/api/bx/deals/1601/design-tasks", headers=hdr(6000)).json()["items"]) == 1
