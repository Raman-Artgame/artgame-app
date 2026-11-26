"""HEAD 26.11 «Эстафета сделки»: «Утверждено» помечает эскиз «В работу», «В производство» — стадия + ГИП + сроки одной кнопкой,
закрытие считает дизайн по метке, полоска пути, строка в «Сегодня»."""
from artgame import bx, db
from conftest import hdr
from test_cabinets import DEALS, dz  # noqa: F401


def _file(ids, name="v1.png", deal=1601):
    with db.pool.connection() as c:
        return c.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, uploaded_by, drive_id)
                            VALUES (gen_random_uuid(), %s, 'design', %s, 'image/png', 10, 'ready', %s, gen_random_uuid()::text)
                            RETURNING id""", (deal, name, ids[7100])).fetchone()["id"]


def test_relay(client, dz, monkeypatch):  # noqa: F811
    ids, calls = dz
    sent = []
    monkeypatch.setattr("artgame.gip._send", lambda tg, text: sent.append((tg, text)))
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"], "bitrix_user_id": 4565}, headers=hdr(1000))
    gip = client.post("/api/register", json={"full_name": "Главный"}, headers=hdr(6100)).json()["id"]
    client.post(f"/api/people/{gip}", json={"role_code": "lead_artist", "zones": ["mural"]}, headers=hdr(1000))
    DEALS["1601"]["STAGE_ID"] = "FINAL_INVOICE"
    bx._cache.clear()

    # дизайна ещё не было: полоска начинается с «Дизайн»
    p = client.get("/api/deals/1601/path?stage=FINAL_INVOICE", headers=hdr(6000)).json()
    assert [s["key"] for s in p["steps"]] == ["design", "approved", "work", "handed", "closed"]
    assert p["steps"][0]["state"] == "now" and p["approved"] is None

    # задача → два варианта → «Утверждено» со вторым: метка «В работу» только на нём
    t = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Холл"}, headers=hdr(6000)).json()
    client.post("/api/design/deal/1601/object", headers=hdr(7100))
    f1, f2 = _file(ids, "v1.png"), _file(ids, "v2.png")
    assert client.get("/api/deals/1601/path", headers=hdr(6000)).json()["steps"][1]["state"] == "todo"
    client.post(f"/api/design/tasks/{t['id']}", json={"file_id": f2, "stage": "done"}, headers=hdr(7100))
    with db.pool.connection() as c:
        marks = {r["id"]: r["approved_at"] for r in c.execute("SELECT id, approved_at FROM files WHERE object_id=1601")}
    assert marks[f2] and not marks[f1]
    p = client.get("/api/deals/1601/path", headers=hdr(6000)).json()
    assert [s["state"] for s in p["steps"][:3]] == ["done", "done", "now"] and p["approved"]["id"] == f2
    # в списке эскизов утверждённый — первым
    assert client.get("/api/objects/1601/files?kind=design", headers=hdr(7100)).json()[0]["id"] == f2

    # метку вручную ставят только дизайнеры и HEAD
    assert client.post(f"/api/design/files/{f1}/approve", json={"on": True}, headers=hdr(6000)).status_code == 403
    assert client.post(f"/api/design/files/{f1}/approve", json={"on": False}, headers=hdr(7000)).json()["ok"]

    # «Сегодня» у МОП: эскиз утверждён, сделка ещё в продажах
    today = client.get("/api/bx/today", headers=hdr(6000)).json()
    row = [x for x in today["queue"]["today"] if x["id"] == 1601]
    assert row and row[0]["action"] == "production"

    # окно «В производство»: МОП видит, чего не хватает (замок карточки), и эскиз
    f = client.get("/api/bx/deals/1601/production", headers=hdr(6000)).json()
    assert f["sketch"]["id"] == f2 and f["missing"] and gip in [c["id"] for c in f["candidates"]]
    r = client.post("/api/bx/deals/1601/production", json={"gip_id": gip, "start": "2026-12-01", "end": "2026-12-10"}, headers=hdr(6000))
    assert r.status_code == 409
    assert client.post("/api/bx/deals/1601/production", json={"gip_id": gip, "start": "2026-12-10", "end": "2026-12-01"},
                       headers=hdr(1000)).status_code == 400
    assert client.post("/api/bx/deals/1601/production", json={"gip_id": ids[7100], "start": "2026-12-01", "end": "2026-12-10"},
                       headers=hdr(1000)).status_code == 400   # дизайнер ГИП не бывает
    # HEAD (замок карточки на него не действует): стадия, сроки и ГИП одной кнопкой
    n = len(calls)
    r = client.post("/api/bx/deals/1601/production", json={"gip_id": gip, "start": "2026-12-01", "end": "2026-12-10"}, headers=hdr(1000)).json()
    assert r["ok"] and r["stage_moved"]
    upd = [x for m, x in calls[n:] if m == "crm.deal.update"][0]["fields"]
    assert upd["STAGE_ID"] == "UC_AV00QK" and upd["UF_CRM_ARTGAME_PROJECT_START_ACTUAL"] == "2026-12-01"
    note = [x for m, x in calls[n:] if m == "crm.timeline.comment.add"][0]["fields"]["COMMENT"]
    assert "куратор ГИП Главный" in note and "v2.png" in note
    with db.pool.connection() as c:
        o = c.execute("SELECT status, gip_person_id, bitrix_stage FROM objects WHERE id=1601").fetchone()
    assert (o["status"], o["gip_person_id"], o["bitrix_stage"]) == ("active", gip, "UC_AV00QK")
    assert sent and "ГИП проекта № 1601" in sent[-1][1] and "Старт 01.12" in sent[-1][1]
    # теперь ГИП ставит людей на объект
    assert client.get("/api/objects/1601/crew", headers=hdr(6100)).json()["can_edit"]
    p = client.get("/api/deals/1601/path", headers=hdr(6100)).json()
    assert [s["state"] for s in p["steps"]] == ["done", "done", "done", "now", "todo"]
    # повторно: стадию не трогаем, только ГИП и сроки
    r = client.post("/api/bx/deals/1601/production", json={"gip_id": gip, "start": "2026-12-02", "end": "2026-12-11"}, headers=hdr(1000)).json()
    assert not r["stage_moved"]
    # из «Сегодня» строка ушла: сделка в работе
    bx._cache.clear()
    today = client.get("/api/bx/today", headers=hdr(6000)).json()
    assert not [x for x in today["queue"]["today"] if x["id"] == 1601 and x.get("action") == "production"]


def test_closing_design_by_mark(client, dz):  # noqa: F811
    """Закрытие: ссылка в «Эскизе» засчитывается только старым сделкам без задач; с задачей — нужен эскиз «В работу»."""
    from artgame import closing
    ids, _ = dz
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, bitrix_stage) VALUES (1601, 'Продажа', 'UC_BMKDS4') ON CONFLICT DO NOTHING")
    fid = _file(ids)
    with db.pool.connection() as c:
        c.execute("UPDATE files SET kind='photo' WHERE id=%s", (fid,))   # пока эскиза нет
        d = {"ID": "1601", "OPPORTUNITY": "0", "UF_CRM_ARTGAME_APPROVED_LAYOUT": "https://drive.google.com/drive/folders/x"}
        money = {"debt": 0, "received": 0, "items": [], "overpaid": 0}
        chk = lambda: next(x for x in closing.checks(c, d, money) if x["key"] == "design")  # noqa: E731
        assert chk()["ok"]                                    # старая сделка: ссылки хватает
        c.execute("""INSERT INTO design_tasks (deal_id, title, stage, created_by) VALUES (1601, 'Холл', 'work', %s)""", (ids[7000],))
        c.execute("UPDATE files SET kind='design' WHERE id=%s", (fid,))
        assert not chk()["ok"]                                # задача есть, файл не утверждён — ссылка не спасает
        c.execute("UPDATE files SET approved_at=now() WHERE id=%s", (fid,))
        assert chk()["ok"] and chk()["detail"] == "эскиз «В работу»"
