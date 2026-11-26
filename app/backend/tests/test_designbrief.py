"""HEAD 26.11 «ТЗ дизайнеру»: срок и лёгкий бриф в задаче, вопрос дизайнера → «Сегодня» МОП, бриф клиента по ссылке без входа."""
from artgame import bx, db, drive
from conftest import hdr
from test_cabinets import dz  # noqa: F401

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def test_tz_and_brief(client, dz, monkeypatch):  # noqa: F811
    ids, calls = dz
    monkeypatch.setattr(drive, "save_photo", lambda *a, **k: "drv-brief")
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"], "bitrix_user_id": 4565}, headers=hdr(1000))
    bx._cache.clear()
    # МОП: одна форма — название, срок, старт работ, бриф кнопками (лишнее отбрасывается), текст
    t = client.post("/api/bx/deals/1601/design-tasks", json={
        "title": "Школа, 2 этаж", "deadline": "2026-12-05", "start_on": "2026-12-15", "note": "12 стен, развёртки приложил",
        "brief": {"who": ["Дети", "Марсиане"], "style": ["Графика"], "junk": ["x"]}}, headers=hdr(6000)).json()
    assert t["deadline"] == "2026-12-05" and t["start_on"] == "2026-12-15" and t["brief"] == {"who": ["Дети"], "style": ["Графика"]}
    assert not t["ask_open"] and not t["brief_sent"] and t["rounds"] == 0
    # МОП своей сделки открывает папку под материалы (фото стен, развёртки)
    assert client.post("/api/design/deal/1601/object", headers=hdr(6000)).json() == {"id": 1601}
    with db.pool.connection() as c:
        c.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, uploaded_by, drive_id)
                     VALUES (gen_random_uuid(), 1601, 'brief', 'razvertka.pdf', 'application/pdf', 10, 'ready', %s, 'drv-1')""", (mop,))
    assert client.get("/api/objects/1601/files?kind=brief", headers=hdr(7100)).json()[0]["name"] == "razvertka.pdf"
    assert client.get("/api/design/tasks", headers=hdr(7100)).json()["items"][0]["materials"] == 1

    # дизайнер дополняет ТЗ из переписки — видно, кто дописал; круг правок считается при входе в «Правки»
    r = client.post(f"/api/design/tasks/{t['id']}", json={"note": "12 стен. Клиент просит без красного"}, headers=hdr(7100)).json()
    assert r["tz_by"] == "Малика" or r["tz_by"]
    client.post(f"/api/design/tasks/{t['id']}", json={"stage": "work"}, headers=hdr(7100))
    assert client.post(f"/api/design/tasks/{t['id']}", json={"stage": "fix"}, headers=hdr(7100)).json()["rounds"] == 1
    n = len(calls)

    # «Вопрос МОП»: задача в «Сбор информации», у МОП строка в «Сегодня»; чужой МОП не отвечает
    assert client.post(f"/api/design/tasks/{t['id']}/ask", json={"text": "Какая высота потолка?"}, headers=hdr(6000)).status_code == 403
    r = client.post(f"/api/design/tasks/{t['id']}/ask", json={"text": "Какая высота потолка?"}, headers=hdr(7100)).json()
    assert r["stage"] == "info" and r["ask_open"] and r["msgs"][-1]["text"] == "Какая высота потолка?"
    today = client.get("/api/bx/today", headers=hdr(6000)).json()
    row = [x for x in today["queue"]["today"] if x["id"] == 1601 and x.get("action") == "design_q"]
    assert len(row) == 1 and "Какая высота потолка?" in row[0]["why"]
    assert client.post(f"/api/bx/deals/1601/design-tasks/{t['id']}/answer", json={"text": "3,2 м"}, headers=hdr(7100)).status_code == 403
    r = client.post(f"/api/bx/deals/1601/design-tasks/{t['id']}/answer", json={"text": "3,2 м"}, headers=hdr(6000)).json()
    assert r["stage"] == "work" and not r["ask_open"] and [m["kind"] for m in r["msgs"]] == ["ask", "answer"]
    bx._cache.clear()
    today = client.get("/api/bx/today", headers=hdr(6000)).json()
    assert not [x for x in today["queue"]["today"] if x.get("action") == "design_q"]
    assert len(calls) == n       # вопросы и ответы в Битрикс не пишут

    # бриф клиенту: ссылку делает и МОП, и дизайнер — одна и та же
    u1 = client.post(f"/api/design/tasks/{t['id']}/brief-link", headers=hdr(6000)).json()["url"]
    u2 = client.post(f"/api/design/tasks/{t['id']}/brief-link", headers=hdr(7100)).json()["url"]
    assert u1 == u2 and "/?brief=" in u1
    token = u1.split("brief=")[1]
    # клиент без входа: видит только название задачи
    g = client.get(f"/api/brief/{token}").json()
    assert g == {"title": "Школа, 2 этаж", "answers": {}, "done": False}
    assert client.get("/api/brief/" + "x" * 24).status_code == 404
    assert client.post(f"/api/brief/{token}", json={"answers": {"junk": "1"}}).status_code == 400
    ok = client.post(f"/api/brief/{token}", json={"lang": "kk", "answers": {
        "place": "Мектеп", "who": ["Балалар", "Қонақтар", "a", "b"], "idea": "Ғарыш " * 300, "junk": "x"}}).json()
    assert ok["ok"]
    assert client.post(f"/api/brief/{token}/photo", json={"data": "data:text/html;base64,AAAA"}).status_code == 400
    assert client.post(f"/api/brief/{token}/photo", json={"data": PNG}).json()["n"] == 1
    r = client.get("/api/design/tasks", headers=hdr(7100)).json()["items"][0]
    cb = r["client_brief"]
    assert cb["place"] == ["Мектеп"] and len(cb["who"]) == 3 and len(cb["idea"]) == 600 and cb["lang"] == "kk" and "junk" not in cb
    assert r["client_brief_at"] and r["brief_sent"] and r["materials"] == 2
    assert client.get(f"/api/brief/{token}").json()["done"]
