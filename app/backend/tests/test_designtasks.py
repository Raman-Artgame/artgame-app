"""HEAD 25.11: задачи на дизайн при сделке — МОП просит из карточки, дизайнер ведёт на доске, сделка не уезжает."""
from artgame import db
from conftest import hdr
from test_cabinets import dz  # noqa: F401


def test_design_tasks(client, dz):  # noqa: F811
    ids, calls = dz
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"], "bitrix_user_id": 4565}, headers=hdr(1000))
    # дизайнер сам задачу не ставит; МОП — на свою сделку, сколько угодно раз
    assert client.post("/api/bx/deals/1601/design-tasks", json={"title": "Холл", "deadline": "2026-12-05"}, headers=hdr(7100)).status_code == 403
    # HEAD 28.11: без срока задание не поставить
    assert client.post("/api/bx/deals/1601/design-tasks", json={"title": "Без срока"}, headers=hdr(6000)).status_code == 422
    a = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Столовая", "note": "Стена 6×3", "deadline": "2026-12-04"}, headers=hdr(6000)).json()
    b = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Спортзал", "urgent": True, "deadline": "2026-12-06"}, headers=hdr(6000)).json()
    assert a["stage"] == "new" and b["stage"] == "urgent" and a["deal_title"] == "Продажа"
    r = client.get("/api/bx/deals/1601/design-tasks", headers=hdr(6000)).json()
    assert [x["title"] for x in r["items"]] == ["Столовая", "Спортзал"] and r["can_add"]
    assert not client.get("/api/bx/deals/1601/design-tasks", headers=hdr(7100)).json()["can_add"]
    assert not calls        # постановка задачи в Битрикс не пишет, сделка стоит на месте
    # доска: дизайнер видит неразобранные; взял в работу — задача его
    d = client.get("/api/design/tasks", headers=hdr(7100)).json()
    assert len(d["items"]) == 2 and d["stages"][0]["name"] == "Свежие заказы" and not d["all"]
    t = client.post(f"/api/design/tasks/{a['id']}", json={"stage": "work", "size": "l"}, headers=hdr(7100)).json()
    assert t["designer_id"] == ids[7100] and t["stage_name"] == "Взято в работу" and t["size"] == "l"
    # HEAD 26.11: дизайнер, сложность и срок дизайна идут в сделку из задачи (МОП руками не вводит); стадию не трогаем
    assert calls[-1] == ("crm.deal.update", {"id": 1601, "fields": {"UF_CRM_ARTGAME_DESIGNER": 7001, "UF_CRM_ARTGAME_DESIGN_COMPLEXITY": "83", "UF_CRM_ARTGAME_DESIGN_DEADLINE": "2026-12-04"}})
    client.post(f"/api/design/tasks/{a['id']}", json={"deadline": "2026-12-05"}, headers=hdr(7100))
    assert calls[-1][1]["fields"]["UF_CRM_ARTGAME_DESIGN_DEADLINE"] == "2026-12-05" and "STAGE_ID" not in calls[-1][1]["fields"]
    n = len(calls)
    client.post(f"/api/design/tasks/{a['id']}", json={"stage": "fix"}, headers=hdr(7100))
    assert len(calls) == n      # смена стадии задачи в Битрикс не пишет
    # чужую задачу второй дизайнер не трогает; назначает Главный
    assert client.post(f"/api/design/tasks/{b['id']}", json={"designer_id": ids[7000]}, headers=hdr(7100)).status_code == 403
    assert client.post(f"/api/design/tasks/{b['id']}", json={"designer_id": ids[7000]}, headers=hdr(7000)).json()["designer_id"] == ids[7000]
    assert client.post(f"/api/design/tasks/{b['id']}", json={"stage": "fix"}, headers=hdr(7100)).status_code == 403
    assert len(client.get("/api/design/tasks", headers=hdr(7100)).json()["items"]) == 1
    assert len(client.get("/api/design/tasks", headers=hdr(1000)).json()["items"]) == 2
    # «Утверждено» — только с эскизом; файл должен лежать в ДИЗАЙН этой сделки
    assert client.post(f"/api/design/tasks/{a['id']}", json={"stage": "done"}, headers=hdr(7100)).status_code == 400
    assert client.post(f"/api/design/tasks/{a['id']}", json={"file_id": 999999}, headers=hdr(7100)).status_code == 400
    # папку сделки заводит сервер сам: строка objects со статусом early, в списках объектов её нет
    # HEAD 26.11: МОП своей сделки тоже открывает папку — кладёт фото стен и развёртки в «Нужен дизайн»
    assert client.post("/api/design/deal/1601/object", headers=hdr(6000)).json() == {"id": 1601}
    assert client.post("/api/design/deal/1601/object", headers=hdr(7100)).json() == {"id": 1601}
    assert client.post("/api/design/deal/1601/object", headers=hdr(7100)).json() == {"id": 1601}
    assert client.post("/api/design/deal/999/object", headers=hdr(7100)).status_code == 404
    with db.pool.connection() as c:
        o = c.execute("SELECT status, title, bitrix_stage FROM objects WHERE id=1601").fetchone()
        assert (o["status"], o["title"], o["bitrix_stage"]) == ("early", "Продажа", "NEW")
        fid = c.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, uploaded_by, drive_id)
                           VALUES (gen_random_uuid(), 1601, 'design', 'stolovaya.png', 'image/png', 10, 'ready', %s, 'drive-file-0001')
                           RETURNING id""", (ids[7100],)).fetchone()["id"]
    assert 1601 not in [x["id"] for x in client.get("/api/objects", headers=hdr(7100)).json()]
    # файл уже лежит в ДИЗАЙН сделки — «Утверждено» проходит и без привязки файла к задаче
    assert client.post(f"/api/design/tasks/{b['id']}", json={"stage": "done"}, headers=hdr(7000)).json()["stage"] == "done"
    assert client.post(f"/api/design/tasks/{b['id']}", json={"stage": "new"}, headers=hdr(7000)).json()["approved"] == ""
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
