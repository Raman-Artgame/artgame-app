import pytest

from artgame import bx, db
from conftest import hdr

DEALS = {
    "1601": {"ID": "1601", "TITLE": "1601 · КАФЕ — АСТАНА", "STAGE_ID": "PREPARATION", "CATEGORY_ID": "0", "OPPORTUNITY": "589250.00",
             "ASSIGNED_BY_ID": "4565", "CONTACT_ID": "2223", "COMPANY_ID": "77", "DATE_MODIFY": "2026-11-01T13:51:28+03:00",
             "UF_CRM_6881101914D8D": "12077", "UF_CRM_ARTGAME_AREA_M2": "25", "UF_CRM_1755520919823": "ул. Достык 5|51.1;71.4|1947",
             "UF_CRM_1753294730602": "19285", "UF_CRM_ARTGAME_ADVANCE_PERCENT": 50},
    "1651": {"ID": "1651", "TITLE": "Школа", "STAGE_ID": "NEW", "CATEGORY_ID": "0", "OPPORTUNITY": "0", "ASSIGNED_BY_ID": "4693",
             "CONTACT_ID": "2215", "COMPANY_ID": "0", "DATE_MODIFY": "2026-11-04T11:00:00+03:00", "UF_CRM_6881101914D8D": None},
    "1590": {"ID": "1590", "TITLE": "1590 · ОФИС — ШЫМКЕНТ", "STAGE_ID": "WON", "CATEGORY_ID": "0", "OPPORTUNITY": "2900000.00",
             "ASSIGNED_BY_ID": "4565", "CONTACT_ID": "0", "COMPANY_ID": "0", "DATE_MODIFY": "2026-11-03T10:00:00+03:00",
             "CLOSEDATE": "2026-11-03T10:00:00+03:00", "UF_CRM_6881101914D8D": None},
}
SEMANTIC = {"WON": "S", "LOSE": "F"}
CALLS = []


def fake(method, params):
    CALLS.append(method)
    if method == "crm.deal.list":
        f = params["filter"]
        rows = [d for d in DEALS.values() if "ASSIGNED_BY_ID" not in f or int(d["ASSIGNED_BY_ID"]) == f["ASSIGNED_BY_ID"]]
        rows = [d for d in rows if SEMANTIC.get(d["STAGE_ID"].split(":")[-1], "P") == f.get("STAGE_SEMANTIC_ID", "P")]
        if ">=CLOSEDATE" in f:
            rows = [d for d in rows if f[">=CLOSEDATE"] <= d.get("CLOSEDATE", "")[:10] < f["<CLOSEDATE"]]
        return {"result": rows, "total": len(rows)}
    if method == "crm.deal.get":
        return {"result": DEALS.get(str(params["id"]))}
    if method == "crm.status.list":
        return {"result": [{"STATUS_ID": "NEW", "NAME": "Взаимное информирование", "SORT": "10"},
                           {"STATUS_ID": "PREPARATION", "NAME": "Встреча/Отправка КП", "SORT": "60"},
                           {"STATUS_ID": "UC_VCP4VO", "NAME": "Отложено", "SORT": "130"},
                           {"STATUS_ID": "LOSE", "NAME": "Высокая стоимость", "SORT": "160", "EXTRA": {"SEMANTICS": "failure"}}]}
    if method == "crm.deal.fields":
        return {"result": {"UF_CRM_6881101914D8D": {"type": "enumeration", "items": [{"ID": "12077", "VALUE": "Казахстан, Астана"}]},
                           "UF_CRM_1753294730602": {"items": [{"ID": "19285", "VALUE": "Художественная роспись стен"}]},
                           "OPPORTUNITY": {"title": "Сумма"}}}
    if method == "user.get":
        return {"result": [{"ID": "4565", "NAME": "Ануар", "LAST_NAME": "Минкеев", "USER_TYPE": "employee"},
                           {"ID": "4693", "NAME": "Тимур", "LAST_NAME": "Жандосов", "USER_TYPE": "employee"}]}
    if method == "crm.company.get":
        return {"result": {"ID": "77", "TITLE": "ТОО «Ромашка»", "PHONE": [{"VALUE": "+77001112233"}]}}
    if method == "crm.contact.get":
        return {"result": {"ID": params["id"], "NAME": "Айгерим", "LAST_NAME": "Сеитова", "EMAIL": [{"VALUE": "a@x.kz"}]}}
    if method == "crm.stagehistory.list":
        return {"result": {"items": []}} if False else {"result": [{"STAGE_ID": "PREPARATION", "CREATED_TIME": "2026-11-04T13:51:28+03:00"},
                                                                  {"STAGE_ID": "NEW", "CREATED_TIME": "2026-11-04T10:00:00+03:00"}]}
    if method == "crm.timeline.comment.list":
        return {"result": [{"ID": "1", "AUTHOR_ID": "4565", "CREATED": "2026-11-04T14:00:00+03:00", "COMMENT": "Отправил КП"}]}
    if method == "crm.activity.list":
        return {"result": [{"ID": "7", "SUBJECT": "Звонок клиенту", "TYPE_ID": "2", "COMPLETED": "Y", "CREATED": "2026-11-04T12:00:00+03:00", "RESPONSIBLE_ID": "4565"}]}
    if method == "tasks.task.list":
        return {"result": {"tasks": [{"id": "501", "title": "Перезвонить по КП", "deadline": "2026-11-06T10:00:00+03:00", "ufCrmTask": ["D_1601"]}]}}
    if method == "crm.requisite.list":
        raise bx.HTTPException(502, "method not allowed")
    raise AssertionError(method)


@pytest.fixture
def bxc(client, monkeypatch):
    monkeypatch.setattr(bx, "READ", fake)
    bx._cache.clear()
    bx._allowed.clear()
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    ids = {}
    for tg, role in [(6000, "mop"), (6100, "mop"), (2000, "artist")]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": ["sales"]}, headers=hdr(1000))
        ids[tg] = pid
    return client, ids


def test_link_and_my_deals(bxc):
    c, ids = bxc
    # не связан — понятная ошибка
    assert c.get("/api/bx/deals", headers=hdr(6000)).status_code == 409
    # связывает только HEAD; один пользователь Битрикса — один человек
    assert c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(6000)).status_code == 403
    assert c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000)).status_code == 200
    assert c.post(f"/api/people/{ids[6100]}", json={"bitrix_user_id": 4565}, headers=hdr(1000)).status_code == 409
    assert [u["name"] for u in c.get("/api/bx/users", headers=hdr(1000)).json()] == ["Ануар Минкеев", "Тимур Жандосов"]
    assert c.get("/api/bx/users", headers=hdr(6000)).status_code == 403
    r = c.get("/api/bx/deals", headers=hdr(6000)).json()
    assert [d["id"] for d in r["deals"]] == [1601] and not r["all"]
    d = r["deals"][0]
    assert d["stage_name"] == "Встреча/Отправка КП" and d["city"] == "Астана" and d["sum"] == 589250 and d["area"] == 25
    # HEAD видит всех и имя менеджера; художник — нет доступа
    h = c.get("/api/bx/deals", headers=hdr(1000)).json()
    assert {x["id"] for x in h["deals"]} == {1601, 1651} and h["all"]
    assert {x["manager"] for x in h["deals"]} == {"Ануар Минкеев", "Тимур Жандосов"}
    assert c.get("/api/bx/deals", headers=hdr(2000)).status_code == 403
    # снять связку
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 0}, headers=hdr(1000))
    with db.pool.connection() as conn:
        assert conn.execute("SELECT bitrix_user_id FROM people WHERE id=%s", (ids[6000],)).fetchone()["bitrix_user_id"] is None


def test_card_and_foreign_deal(bxc):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    card = c.get("/api/bx/deals/1601", headers=hdr(6000)).json()
    assert card["client"] == {"type": "ТОО", "name": "ТОО «Ромашка»", "phone": "+77001112233", "email": "a@x.kz"}
    assert card["address"] == "ул. Достык 5" and card["service"] == "Художественная роспись стен"
    assert card["requisites"] is None   # шлюз реквизиты не отдаёт — вводят вручную
    assert c.get("/api/bx/deals/1651", headers=hdr(6000)).status_code == 403
    assert c.get("/api/bx/deals/9999", headers=hdr(6000)).status_code == 404
    phys = c.get("/api/bx/deals/1651", headers=hdr(1000)).json()
    assert phys["client"]["type"] == "Физлицо" and phys["client"]["name"] == "Сеитова Айгерим"


def test_cache(bxc):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    CALLS.clear()
    c.get("/api/bx/deals", headers=hdr(6000))
    c.get("/api/bx/deals", headers=hdr(6000))
    assert CALLS.count("crm.deal.list") == 1
    c.get("/api/bx/deals?fresh=1", headers=hdr(6000))
    assert CALLS.count("crm.deal.list") == 2


def test_place_page_crm_get(bxc, tmp_path, monkeypatch):
    import secrets
    from artgame import pack_places, places
    from artgame.config import settings
    key = secrets.token_hex(32)
    monkeypatch.setattr(settings, "content_key", key)
    monkeypatch.setattr(places, "ROOT", tmp_path / "places")
    monkeypatch.setattr(pack_places, "ROOT", tmp_path / "places")
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.html").write_text("<html><head></head><body>МОП</body></html>")
    pack_places.pack(src, "mop", key)
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    url = c.get("/api/places", headers=hdr(6000)).json()[0]["url"]
    page = c.get(url).text
    assert "/api/p/_bx.js" in page and '"bx": true' in page
    base = url.rsplit("/", 1)[0]
    d = c.post(base + "/_bx/crm_get", json={"entity": "deal", "id": 1601}).json()
    assert d["id"] == 1601 and d["ufCrm_6881101914D8D"] == "12077" and d["ufCrmArtgameAdvancePercent"] == 50
    assert d["companyId"] == 77 and d["ufCrm_ARTGAME_AREA_M2"] == "25" and d["opportunity"] == "589250.00"
    assert c.post(base + "/_bx/crm_get", json={"entity": "company", "id": 77}).json()["title"] == "ТОО «Ромашка»"
    # чужая компания / чужая сделка — нельзя
    assert c.post(base + "/_bx/crm_get", json={"entity": "company", "id": 5}).status_code == 403
    assert c.post(base + "/_bx/crm_get", json={"entity": "deal", "id": 1651}).status_code == 403
    f = c.post(base + "/_bx/crm_fields", json={"entity": "deal"}).json()
    assert f["ufCrm_6881101914D8D"]["items"] == [{"id": "12077", "value": "Казахстан, Астана"}]
    assert [x["id"] for x in c.post(base + "/_bx/my_deals", json={}).json()["deals"]] == [1601]
    assert c.get("/api/p/_bx.js").status_code == 200


def test_journal(bxc):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    c.get("/api/bx/deals/1601", headers=hdr(6000))
    j = c.get("/api/journal", headers=hdr(6000)).json()
    assert [x["action"] for x in j["items"]] == ["deal_open"] and j["items"][0]["entity_id"] == "1601" and j["summary"] is None
    # чужой журнал — только HEAD
    assert c.get(f"/api/journal?person={ids[6000]}", headers=hdr(6100)).status_code == 403
    h = c.get(f"/api/journal?person={ids[6000]}", headers=hdr(1000)).json()
    assert len(h["items"]) == 1 and [s["deals_today"] for s in h["summary"] if s["id"] == ids[6000]] == [1]
    # у художника свой журнал тоже есть (вкладка только у МОП, данные — у всех)
    assert c.get("/api/journal", headers=hdr(2000)).json()["items"] == []


def test_write_off_and_on(bxc, monkeypatch, tmp_path):
    from artgame import bxw, places
    from artgame.config import settings
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    # ключа нет — действие в журнале, статус off, Битрикс не трогаем
    r = c.post("/api/bx/deals/1601/note", json={"text": "позвонить завтра"}, headers=hdr(6000)).json()
    assert r["bx"] == "off"
    # ключ есть — пишем и сверяем
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    monkeypatch.setattr(places, "DL_DIR", tmp_path)
    calls = []

    def fake_call(method, params):
        calls.append((method, params))
        if method == "crm.deal.update":
            DEALS["1601"].update({k: v for k, v in params["fields"].items() if not isinstance(v, (dict, list))})
        if method == "tasks.task.add":
            return {"result": {"task": {"id": "777"}}}
        return {"result": True}
    monkeypatch.setattr(bxw, "CALL", fake_call)
    # чужая сделка — нельзя даже с ключом
    assert c.post("/api/bx/deals/1651/note", json={"text": "x"}, headers=hdr(6000)).status_code == 403
    # стадия: проигрыш без причины — нельзя
    assert c.post("/api/bx/deals/1601/stage", json={"stage": "LOSE"}, headers=hdr(6000)).status_code == 400
    r = c.post("/api/bx/deals/1601/stage", json={"stage": "NEW"}, headers=hdr(6000)).json()
    assert r["bx"] == "ok" and DEALS["1601"]["STAGE_ID"] == "NEW" and calls[0][0] == "crm.deal.update" and calls[1][0] == "crm.timeline.comment.add"
    assert "P6000 (приложение)" in calls[1][1]["fields"]["COMMENT"]
    # «Отложено» — только с датой возврата: задача в Битриксе + напоминание
    assert c.post("/api/bx/deals/1601/stage", json={"stage": "UC_VCP4VO"}, headers=hdr(6000)).status_code == 400
    calls.clear()
    r = c.post("/api/bx/deals/1601/stage", json={"stage": "UC_VCP4VO", "until": "2027-01-15", "reason": "ждут бюджет"}, headers=hdr(6000)).json()
    assert r["bx"] == "ok" and r["task"] == 777 and "отложил до 15.01.2027: ждут бюджет" in calls[1][1]["fields"]["COMMENT"]
    tk = calls[2][1]["fields"]
    assert calls[2][0] == "tasks.task.add" and tk["RESPONSIBLE_ID"] == 4565 and tk["UF_CRM_TASK"] == ["D_1601"] and tk["DEADLINE"].startswith("2027-01-15")
    with db.pool.connection() as conn:
        assert conn.execute("SELECT due::text, note FROM bx_reminders WHERE deal_id=1601").fetchone() == {"due": "2027-01-15", "note": "ждут бюджет"}
    DEALS["1601"]["STAGE_ID"] = "NEW"
    # документ скачан на странице: КП → сумма, площадь, файл, стадия NEW → PREPARATION
    (tmp_path / "abc1.bin").write_bytes(b"%PDF")
    calls.clear()
    bx._cache.clear()
    url = c.get("/api/places", headers=hdr(6000)).json()
    r = bxw.doc_saved({"id": ids[6000], "role_code": "mop", "full_name": "Ануар", "status": "active"}, 1601,
                      "КП ARTGAME №1601 Ромашка 05.11.2026.pdf", "abc1", {"total": 589250, "area": 25})
    f = calls[0][1]["fields"]
    assert r["bx"] == "ok" and f["OPPORTUNITY"] == 589250 and f["UF_CRM_ARTGAME_AREA_M2"] == 25 and f["STAGE_ID"] == "PREPARATION"
    assert f[bxw.F_KP][0]["fileData"][0].startswith("КП ARTGAME") and r["stage"] == "PREPARATION"
    # договор из «Выполнения проекта» стадию назад не двигает
    DEALS["1601"]["STAGE_ID"] = "UC_AV00QK"
    bx._cache.clear()
    r = bxw.doc_saved({"id": ids[6000], "role_code": "mop", "full_name": "Ануар", "status": "active"}, 1601,
                      "ARTGAME_Dogovor_1601.docx", "", {"total": 600000, "adv": 50, "days": 20, "warr": 6})
    assert "STAGE_ID" not in calls[-2][1]["fields"] and calls[-2][1]["fields"][bxw.F_ADV] == 50
    j = c.get("/api/journal", headers=hdr(6000)).json()
    assert [x["data"]["bx"] for x in j["items"] if x["action"] == "bx_write"][:2] == ["ok", "ok"]
    DEALS["1601"]["STAGE_ID"] = "PREPARATION"


def test_full_and_today(bxc):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    d = c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()
    assert d["manager"] == "Ануар Минкеев" and [h["stage"] for h in d["history"]] == ["Встреча/Отправка КП", "Взаимное информирование"]
    assert {f["kind"] for f in d["feed"]} == {"comment", "звонок"} and d["feed"][0]["who"] == "Ануар Минкеев"
    t = c.get("/api/bx/today", headers=hdr(6000)).json()
    assert t["tasks"] == [{"id": 501, "title": "Перезвонить по КП", "deadline": "2026-11-06T10:00:00+03:00", "deal": 1601}]
    assert [x["id"] for x in t["kp"]] == [1601] and t["limits"]["kp_days"] == 2   # сделка на КП с 04.11 — без ответа


def test_month(bxc):
    from psycopg.types.json import Jsonb
    c, ids = bxc
    vals = {k: {"value": v, "status": "Утверждено"} for k, v in {"vat": "16", "pay.mop.salary": "200 000", "pay.mop.bonus_plan": "100 000",
            "pay.mop.step1.from": "2 000 000", "pay.mop.step1.pct": "3", "pay.mop.step2.from": "7 000 000", "pay.mop.step2.pct": "4",
            "pay.mop.step3.from": "15 000 000", "pay.mop.step3.pct": "5"}.items()}
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES ('t', %s)", (Jsonb(vals),))
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    m = c.get("/api/bx/month?ym=2026-11", headers=hdr(6000)).json()
    assert [d["id"] for d in m["mine"]["deals"]] == [1590] and m["mine"]["gross"] == 2900000 and m["mine"]["net"] == 2500000   # / 1,16
    co = m["company"]   # ступень и % — по всей выручке компании (HEAD 03.11)
    assert co["net"] == 2500000 and co["step"] == 1 and co["pct"] == 3 and co["bonus"] == 75000
    assert co["next"] == {"step": 2, "from": 7000000, "left": 4500000} and m["salary"] == 200000
    h = c.get("/api/bx/month?ym=2026-11", headers=hdr(1000)).json()
    assert h["all"] and h["managers"][0]["name"] == "Ануар Минкеев" and h["managers"][0]["net"] == 2500000
    assert c.get("/api/bx/month?ym=2026-10", headers=hdr(6000)).json()["company"]["count"] == 0


def test_notify(bxc, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from artgame import notify
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    sent = []
    monkeypatch.setattr(notify, "SEND", lambda tg, text: sent.append((tg, text)))
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO bx_reminders (person_id, deal_id, due, note) VALUES (%s, 1601, current_date, 'ждут бюджет')", (ids[6000],))
    t = c.get("/api/bx/today", headers=hdr(6000)).json()
    assert [d["id"] for d in t["back"]] == [1601] and t["kp"] == []   # отложенная — в «пора вернуться», не в «КП без ответа»
    assert notify.run(datetime(2026, 11, 6, 3, 0, tzinfo=ZoneInfo("Asia/Almaty"))) == 0   # ночью молчим
    n = notify.run(datetime(2026, 11, 6, 10, 0, tzinfo=ZoneInfo("Asia/Almaty")))
    assert n == 2 and sent[0][0] == 6000 and "Пора вернуться к сделке № 1601" in sent[0][1] and "ждут бюджет" in sent[0][1]
    assert "Задача на сегодня: Перезвонить по КП" in sent[0][1]
    assert notify.run(datetime(2026, 11, 6, 10, 30, tzinfo=ZoneInfo("Asia/Almaty"))) == 0 and len(sent) == 1   # повторно не шлём
    with db.pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM bx_reminders WHERE sent_at IS NULL").fetchone()["n"] == 0
