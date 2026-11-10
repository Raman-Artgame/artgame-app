import pytest
from datetime import date as _date

from artgame import bx, db
from conftest import hdr

DEALS = {
    "1601": {"ID": "1601", "TITLE": "1601 · КАФЕ — АСТАНА", "STAGE_ID": "PREPARATION", "CATEGORY_ID": "0", "OPPORTUNITY": "589250.00",
             "ASSIGNED_BY_ID": "4565", "CONTACT_ID": "2223", "COMPANY_ID": "77", "DATE_MODIFY": "2026-11-01T13:51:28+03:00",
             "UF_CRM_6881101914D8D": "12077", "UF_CRM_ARTGAME_AREA_M2": "25", "UF_CRM_1755520919823": "ул. Достык 5|51.1;71.4|1947",
             "UF_CRM_1753294730602": "19285", "UF_CRM_ARTGAME_ADVANCE_PERCENT": 50},
    "1651": {"ID": "1651", "TITLE": "Школа", "STAGE_ID": "NEW", "CATEGORY_ID": "0", "OPPORTUNITY": "0", "ASSIGNED_BY_ID": "4693",
             "CONTACT_ID": "2215", "COMPANY_ID": "0", "DATE_MODIFY": "2026-11-04T11:00:00+03:00", "UF_CRM_6881101914D8D": None},
    "1647": {"ID": "1647", "TITLE": "Дизайн кафе", "STAGE_ID": "C13:NEW", "CATEGORY_ID": "13", "OPPORTUNITY": "0", "ASSIGNED_BY_ID": "4565",
             "CONTACT_ID": "0", "COMPANY_ID": "0", "DATE_MODIFY": "2026-10-20T11:00:00+03:00", "DATE_CREATE": "2026-10-20T11:00:00+03:00"},
    "1590": {"ID": "1590", "TITLE": "1590 · ОФИС — ШЫМКЕНТ", "STAGE_ID": "WON", "CATEGORY_ID": "0", "OPPORTUNITY": "2900000.00",
             "ASSIGNED_BY_ID": "4565", "CONTACT_ID": "0", "COMPANY_ID": "0", "DATE_MODIFY": "2026-11-03T10:00:00+03:00",
             "CLOSEDATE": "2026-11-03T10:00:00+03:00", "UF_CRM_6881101914D8D": None},
}
SEMANTIC = {"WON": "S", "LOSE": "F"}
LEADS = {
    "3001": {"ID": "3001", "TITLE": "Заявка с сайта", "NAME": "Дана", "LAST_NAME": "", "STATUS_ID": "UC_93GBZP", "ASSIGNED_BY_ID": "4565",
             "DATE_CREATE": "2026-11-01T09:00:00+05:00", "DATE_MODIFY": "2026-11-01T09:00:00+05:00", "OPPORTUNITY": "0",
             "PHONE": [{"VALUE": "+7 701 555 44 33"}], "CONTACT_ID": None, "COMPANY_ID": None, "SOURCE_ID": "WEB",
             "UF_CRM_1753202309": None},
    "3002": {"ID": "3002", "TITLE": "Чужой лид", "STATUS_ID": "UC_93GBZP", "ASSIGNED_BY_ID": "4693",
             "DATE_CREATE": "2026-11-04T09:00:00+05:00", "DATE_MODIFY": "2026-11-04T09:00:00+05:00", "PHONE": []},
}
CALLS = []
PHONE_CALLS = []   # звонки за двое суток для calls.missed (новые сверху)
DIALOGS, HISTORY = [], {}   # открытые диалоги WhatsApp и их переписка (chats.waiting)


def fake(method, params):
    CALLS.append(method)
    if method == "crm.deal.list":
        f = params["filter"]
        rows = [d for d in DEALS.values() if "ASSIGNED_BY_ID" not in f or int(d["ASSIGNED_BY_ID"]) == f["ASSIGNED_BY_ID"]]
        rows = [d for d in rows if "ID" in f or SEMANTIC.get(d["STAGE_ID"].split(":")[-1], "P") == f.get("STAGE_SEMANTIC_ID", "P")]
        rows = [d for d in rows if "CATEGORY_ID" not in f or int(d["CATEGORY_ID"]) in f["CATEGORY_ID"]]
        rows = [d for d in rows if "ID" not in f or int(d["ID"]) in f["ID"]]
        rows = [d for d in rows if "STAGE_ID" not in f or d["STAGE_ID"] in f["STAGE_ID"]]
        rows = [d for d in rows if "%TITLE" not in f or f["%TITLE"].lower() in (d.get("TITLE") or "").lower()]   # поиск «Оплат»
        if ">=CLOSEDATE" in f:
            rows = [d for d in rows if f[">=CLOSEDATE"] <= d.get("CLOSEDATE", "")[:10] < f["<CLOSEDATE"]]
        return {"result": rows, "total": len(rows)}
    if method == "crm.deal.get":
        return {"result": DEALS.get(str(params["id"]))}
    if method == "crm.status.list" and params["filter"]["ENTITY_ID"] == "STATUS":
        return {"result": [{"STATUS_ID": "UC_93GBZP", "NAME": "Новый лид", "SORT": "10"},
                           {"STATUS_ID": "IN_PROCESS", "NAME": "В работе", "SORT": "20"},
                           {"STATUS_ID": "CONVERTED", "NAME": "Сделка", "SORT": "30", "EXTRA": {"SEMANTICS": "success"}},
                           {"STATUS_ID": "UC_MARGO5", "NAME": "Дорого", "SORT": "40", "EXTRA": {"SEMANTICS": "failure"}},
                           {"STATUS_ID": "UC_YHM21B", "NAME": "Вакансии Астана", "SORT": "50"},
                           {"STATUS_ID": "UC_F2Y3S1", "NAME": "Вакансии", "SORT": "60", "EXTRA": {"SEMANTICS": "failure"}}]}
    if method == "crm.lead.list":
        f = params["filter"]
        rows = [l for l in LEADS.values() if l["STATUS_ID"] not in ("CONVERTED", "UC_MARGO5", "UC_F2Y3S1")
                and ("ASSIGNED_BY_ID" not in f or int(l["ASSIGNED_BY_ID"]) == f["ASSIGNED_BY_ID"])]
        return {"result": rows, "total": len(rows)}
    if method == "crm.lead.get":
        return {"result": LEADS.get(str(params["id"]))}
    if method == "crm.lead.fields":
        return {"result": {"UF_CRM_1753202309": {"type": "enumeration", "items": [{"ID": "5501", "VALUE": "Казахстан, Астана"}]},
                           "UF_CRM_ARTGAME_LEAD_AREA": {"type": "double"}}}
    if method == "crm.status.list" and params["filter"]["ENTITY_ID"] == "DEAL_STAGE_13":
        return {"result": [{"STATUS_ID": "C13:NEW", "NAME": "Новая задача", "SORT": "10"}, {"STATUS_ID": "C13:EXECUTING", "NAME": "В работе", "SORT": "20"}]}
    if method == "crm.status.list":
        return {"result": [{"STATUS_ID": "NEW", "NAME": "Взаимное информирование", "SORT": "10"},
                           {"STATUS_ID": "PREPARATION", "NAME": "Встреча/Отправка КП", "SORT": "60"},
                           {"STATUS_ID": "FINAL_INVOICE", "NAME": "Отправка счета/договора", "SORT": "100"},
                           {"STATUS_ID": "UC_AV00QK", "NAME": "Выполнение проекта", "SORT": "110"},
                           {"STATUS_ID": "UC_VCP4VO", "NAME": "Отложено", "SORT": "130"},
                           {"STATUS_ID": "LOSE", "NAME": "Высокая стоимость", "SORT": "160", "EXTRA": {"SEMANTICS": "failure"}}]}
    if method == "crm.deal.fields":
        return {"result": {"UF_CRM_6881101914D8D": {"type": "enumeration", "items": [{"ID": "12077", "VALUE": "Казахстан, Астана"}]},
                           "UF_CRM_1753294730602": {"items": [{"ID": "19285", "VALUE": "Художественная роспись стен"}]},
                           "UF_CRM_ARTGAME_COMPLEXITY": {"type": "enumeration", "items": [{"ID": "901", "VALUE": "Лёгкий"}, {"ID": "902", "VALUE": "Средний"},
                                                                                           {"ID": "903", "VALUE": "Сложный"}, {"ID": "904", "VALUE": "Авторский"}]},
                           "UF_CRM_ARTGAME_NORM_SHIFTS": {"type": "double"}, "UF_CRM_ARTGAME_NORM_CREW": {"type": "integer"},
                           "UF_CRM_ARTGAME_TERM_DAYS": {"type": "integer"}, "UF_CRM_ARTGAME_AREA_M2": {"type": "double"}, "OPPORTUNITY": {"title": "Сумма"},
                           "UF_CRM_ARTGAME_OBJECT": {"type": "string"},
                           "UF_CRM_ARTGAME_PROJECT_MODEL": {"type": "enumeration", "listLabel": "Модель", "items": [{"ID": "31", "VALUE": "B2B"}, {"ID": "32", "VALUE": "B2C"}]},
                           "UF_CRM_ARTGAME_PROJECT_VIP": {"type": "boolean", "listLabel": "VIP"},
                           "UF_CRM_1753381517": {"type": "employee", "listLabel": "Художники", "isMultiple": True}}}
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
    if method == "crm.activity.list" and params["filter"].get("PROVIDER_ID") == "IMOPENLINES_SESSION":
        return {"result": DIALOGS}
    if method == "imopenlines.session.history.get":
        h = HISTORY.get(params["SESSION_ID"])
        if h is None:
            raise bx.HTTPException(502, "Битрикс: insufficient_scope")
        return {"result": h}
    if method == "crm.activity.list" and ">=CREATED" in params["filter"]:
        return {"result": PHONE_CALLS}
    if method == "crm.activity.list":
        return {"result": [{"ID": "7", "SUBJECT": "Звонок клиенту", "TYPE_ID": "2", "COMPLETED": "Y", "CREATED": "2026-11-04T12:00:00+03:00", "RESPONSIBLE_ID": "4565"}]}
    if method == "tasks.task.list":
        return {"result": {"tasks": [{"id": "501", "title": "Перезвонить по КП", "deadline": f"{_date.today()}T10:00:00+03:00", "ufCrmTask": ["D_1601"]}]}}
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
    assert [d["id"] for d in r["deals"]] == [1601, 1647] and not r["all"]   # продажи и дизайн, воронку выбирает экран
    d = r["deals"][0]
    assert d["stage_name"] == "Встреча/Отправка КП" and d["city"] == "Астана" and d["sum"] == 589250 and d["area"] == 25
    # HEAD видит всех и имя менеджера; художник — нет доступа
    h = c.get("/api/bx/deals", headers=hdr(1000)).json()
    assert {x["id"] for x in h["deals"]} == {1601, 1651, 1647} and h["all"]
    assert h["funnels"] == {"0": "Продажи", "13": "Дизайн"} and [n for _, n in h["managers"]] == ["Ануар Минкеев", "Тимур Жандосов"]
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
    assert card["client"] == {"type": "ТОО", "name": "ТОО «Ромашка»", "phone": "+77001112233", "email": "a@x.kz", "no_contact": False}
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
    assert [x["id"] for x in c.post(base + "/_bx/my_deals", json={}).json()["deals"]] == [1601, 1647]
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
    # документ скачан на странице: КП → сумма, площадь, файл, стадия NEW → PREPARATION (расчёт сохранён — замок открыт)
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO deal_calc (deal_id, data) VALUES (1601, '{\"out\": {\"total\": 589250}}') ON CONFLICT DO NOTHING")
    (tmp_path / "abc1.bin").write_bytes(b"%PDF")
    calls.clear()
    bx._cache.clear()
    url = c.get("/api/places", headers=hdr(6000)).json()
    r = bxw.doc_saved({"id": ids[6000], "role_code": "mop", "full_name": "Ануар", "status": "active"}, 1601,
                      "КП ARTGAME №1601 Ромашка 05.11.2026.pdf", "abc1", {"total": 589250, "area": 25})
    f = calls[0][1]["fields"]
    assert r["bx"] == "ok" and f["OPPORTUNITY"] == 589250 and f["UF_CRM_ARTGAME_AREA_M2"] == 25 and f["STAGE_ID"] == "PREPARATION"
    assert f[bxw.F_KP][0]["fileData"][0].startswith("КП ARTGAME") and r["stage"] == "PREPARATION"
    # расчёт из карточки: площадь + сложность → смены, люди, срок по нормам → в сделку (МОП руками не вводит)
    calls.clear()
    r = c.post("/api/bx/deals/1601/calc", json={"area": 60, "level": "medium"}, headers=hdr(6000)).json()
    assert r["calc"] == {"shifts": 6, "crew": 3, "prep": 1, "work": 2, "days": 3, "client": 4, "ink": 0, "level": "medium", "service": "mural"}
    f = calls[0][1]["fields"]
    assert f[bx.F_SHIFTS] == 6 and f[bx.F_CREW] == 3 and f[bx.F_TERM] == 4 and f[bx.F_LEVEL] == "902" and f[bx.AREA] == 60 and r["norm_fields"]
    assert "расчёт: 60 м² Средний: 6 смен, 3 чел., 4 раб. дн." in calls[1][1]["fields"]["COMMENT"]
    full = c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()
    assert full["level"] == "medium" and full["norm"] == {"shifts": 6, "crew": 3, "term": 4} and full["norm_fields"]
    assert c.post("/api/bx/deals/1601/calc", json={"area": 120, "service": "print"}, headers=hdr(6000)).json()["calc"]["crew"] == 6
    # договор из «Выполнения проекта» стадию назад не двигает
    DEALS["1601"]["STAGE_ID"] = "UC_AV00QK"
    bx._cache.clear()
    r = bxw.doc_saved({"id": ids[6000], "role_code": "mop", "full_name": "Ануар", "status": "active"}, 1601,
                      "ARTGAME_Dogovor_1601.docx", "", {"total": 600000, "adv": 50, "days": 20, "warr": 6})
    assert "STAGE_ID" not in calls[-2][1]["fields"] and calls[-2][1]["fields"][bxw.F_ADV] == 50
    j = c.get("/api/journal", headers=hdr(6000)).json()
    assert [x["data"]["bx"] for x in j["items"] if x["action"] == "bx_write"][:2] == ["ok", "ok"]
    DEALS["1601"]["STAGE_ID"] = "PREPARATION"
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM deal_calc WHERE deal_id=1601")


def test_full_and_today(bxc):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    d = c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()
    assert d["manager"] == "Ануар Минкеев" and [h["stage"] for h in d["history"]] == ["Встреча/Отправка КП", "Взаимное информирование"]
    assert {f["kind"] for f in d["feed"]} == {"comment", "call"} and d["feed"][0]["who"] == "Ануар Минкеев"
    t = c.get("/api/bx/today", headers=hdr(6000)).json()
    assert t["tasks"] == [{"id": 501, "title": "Перезвонить по КП", "deadline": f"{_date.today()}T10:00:00+03:00", "deal": 1601}]
    assert [x["id"] for x in t["kp"]] == [1601] and t["limits"]["kp_days"] == 2   # сделка на КП с 04.11 — без ответа
    # дизайн-сделка в C13:NEW — не «новая заявка», а «без движения» в «позже»
    assert [x["id"] for x in t["new"]] == [] and any(x["id"] == 1647 and x["why"].startswith("дизайн: без движения") for x in t["queue"]["later"])


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
    assert co["earn"] == 275000 and m["mine"]["share"] == 100 and m["bonus_plan"] == 100000
    import calendar
    from datetime import date
    t = date.today()
    if (t.year, t.month) == (2026, 11):   # план месяца: темп — выручка на сегодня, растянутая на месяц
        f = 2500000 / t.day * 30
        assert co["pace"]["day"] == t.day and co["pace"]["days"] == 30 and co["pace"]["net"] == round(f)
        st = 3 if f > 15e6 else 2 if f > 7e6 else 1
        assert co["pace"]["step"] == st and co["pace"]["earn"] == round(200000 + f * (3, 4, 5)[st - 1] / 100 + (100000 if st == 3 else 0))
    h = c.get("/api/bx/month?ym=2026-11", headers=hdr(1000)).json()
    assert h["all"] and h["managers"][0]["name"] == "Ануар Минкеев" and h["managers"][0]["net"] == 2500000
    assert c.get("/api/bx/month?ym=2026-10", headers=hdr(6000)).json()["company"]["count"] == 0
    assert m["source"] == "bitrix" and not m["warn"] and "ARTGAME_GOOGLE_SA_FILE" in h["warn"]   # без листа — по Битриксу, HEAD видит почему


def test_month_from_sheet(bxc, monkeypatch):
    """HEAD 05.11: выручка месяца — по листу «Проекты <год>» (дата завершения работ), менеджер — из Битрикса по номеру."""
    from psycopg.types.json import Jsonb
    from artgame import fin
    c, ids = bxc
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES ('t2', %s)", (Jsonb({"vat": {"value": "16", "status": "Утверждено"}}),))
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    seen = {}
    rows = [["1590", "Ноябрь", "Офис", "Шымкент"] + [""] * 9 + ["03.11.2026", "1 160 000"],
            ["1601", "Ноябрь", "Школа", "Астана"] + [""] * 9 + ["", "580 000"],          # без даты — по колонке «Месяц»
            ["999", "Октябрь", "Старое", ""] + [""] * 9 + ["20.10.2026", "100"],          # другой месяц
            ["Итого", "", "", ""] + [""] * 9 + ["", "9 999 999"]]                          # не сделка
    monkeypatch.setattr(fin, "sheet_values", lambda sid, rng: seen.update(rng=rng) or rows)
    fin._cache.clear()
    m = c.get("/api/bx/month?ym=2026-11", headers=hdr(6000)).json()
    assert seen["rng"] == "Проекты 2026!A2:O" and m["source"] == "sheet"
    assert m["company"]["count"] == 2 and m["company"]["gross"] == 1740000 and m["company"]["net"] == 1500000
    assert [(d["id"], d["closed"], d["city"], d["manager"]) for d in m["mine"]["deals"]] == [(1590, "2026-11-03", "Шымкент", "Ануар Минкеев"), (1601, "2026-11-01", "Астана", "Ануар Минкеев")]
    assert c.get("/api/bx/month?ym=2026-10", headers=hdr(1000)).json()["company"]["gross"] == 100
    d = c.get("/api/bx/month?ym=2026-12", headers=hdr(1000)).json()   # месяца в листе нет — по Битриксу, без тревоги
    assert d["source"] == "bitrix" and not d["warn"]
    monkeypatch.setattr(fin, "sheet_values", lambda sid, rng: (_ for _ in ()).throw(RuntimeError("таблица не открыта сервисному аккаунту приложения")))
    fin._cache.clear()
    h = c.get("/api/bx/month?ym=2026-11&fresh=1", headers=hdr(1000)).json()
    assert h["source"] == "bitrix" and "не открыта сервисному аккаунту" in h["warn"] and h["company"]["gross"] == 2900000


def test_notify(bxc, monkeypatch):
    from datetime import datetime, time
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
    assert notify.run(datetime.combine(_date.today(), time(3, 0), tzinfo=ZoneInfo("Asia/Almaty"))) == 0   # ночью молчим
    assert notify.run(datetime.combine(_date.today(), time(8, 30), tzinfo=ZoneInfo("Asia/Almaty"))) == 2   # до сводки — только «горит»: вернуться + лид
    assert "Пора вернуться" in sent[0][1] and "Лид Дана" in sent[0][1] and "Задача" not in sent[0][1]
    sent.clear()
    n = notify.run(datetime.combine(_date.today(), time(10, 0), tzinfo=ZoneInfo("Asia/Almaty")))   # сводка: остальное одним сообщением
    assert n == 1 and sent[0][0] == 6000 and sent[0][1].startswith("☀️ На сегодня: 2 горит, 1 сделать.") and "Пора вернуться" not in sent[0][1]
    assert "Задача на сегодня: Перезвонить по КП" in sent[0][1]
    assert notify.run(datetime.combine(_date.today(), time(10, 30), tzinfo=ZoneInfo("Asia/Almaty"))) == 0 and len(sent) == 1   # повторно не шлём
    with db.pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM bx_reminders WHERE sent_at IS NULL").fetchone()["n"] == 0


def test_read_falls_back_to_webhook(monkeypatch):
    """Без адреса шлюза чтение идёт вебхуком (05.11: шлюз на сервере только под OAuth)."""
    from artgame import bx
    from artgame.config import settings
    monkeypatch.setattr(settings, "gateway_url", "")
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"result": [{"ID": "1"}], "total": 1}

    def fake_post(url, json, timeout):
        seen["url"] = url
        return R()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    assert bx._gateway_read("crm.deal.list", {"filter": {}}) == {"result": [{"ID": "1"}], "total": 1}
    assert seen["url"] == "https://x.bitrix24.kz/rest/1/key/crm.deal.list"
    monkeypatch.setattr(settings, "bitrix_webhook", "")
    import pytest
    with pytest.raises(Exception) as ex:
        bx._gateway_read("crm.deal.list", {})
    assert "не подключён" in str(ex.value.detail)


def test_leads(bxc, monkeypatch):
    from artgame import bxw
    from artgame.config import settings
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    r = c.get("/api/bx/leads", headers=hdr(6000)).json()
    assert [l["id"] for l in r["leads"]] == [3001]
    l = r["leads"][0]
    assert l["new"] and l["name"] == "Дана" and l["phone"] == "+7 701 555 44 33"
    assert l["missing"] == ["город", "услуга"]   # услуги у лида в Битриксе нет — спросим при переводе; площадь — перед КП
    assert c.get("/api/bx/leads/3002", headers=hdr(6000)).status_code == 403
    full = c.get("/api/bx/leads/3001", headers=hdr(6000)).json()
    assert full["has"] == {"service": False, "area": True} and full["fail"] == [{"id": "UC_MARGO5", "name": "Дорого"}]
    assert c.get("/api/bx/leads/cities", headers=hdr(6000)).json() == [{"id": "5501", "name": "Астана"}]
    # «Сегодня»: новый лид старше 4 ч — в «Горит»
    t = c.get("/api/bx/today", headers=hdr(6000)).json()["queue"]
    assert any(x["entity"] == "lead" and x["id"] == 3001 for x in t["hot"])
    # запись
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x/rest/1/k/")
    calls = []

    def fake_call(method, params):
        calls.append((method, params))
        if method == "crm.lead.update":
            LEADS[str(params["id"])].update(params["fields"])
        return {"result": {"task": {"id": "778"}}} if method == "tasks.task.add" else {"result": 9100 if method.endswith(".add") else True}
    monkeypatch.setattr(bxw, "CALL", fake_call)
    assert c.post("/api/bx/leads/3001/convert", headers=hdr(6000)).status_code == 400   # не заполнены город и площадь
    assert c.post("/api/bx/leads/3001", json={"city": "999"}, headers=hdr(6000)).status_code == 400
    assert c.post("/api/bx/leads/3001", json={"city": "5501", "area": 40, "service": "1"}, headers=hdr(6000)).json()["bx"] == "ok"
    upd = next(p for m, p in calls if m == "crm.lead.update")
    assert upd["fields"] == {"UF_CRM_1753202309": "5501", "UF_CRM_ARTGAME_LEAD_AREA": 40}   # услуги нет в Битриксе — не пишем
    # итог звонка с датой перезвона → комментарий, задача, напоминание
    from datetime import date, timedelta
    nxt = (date.today() + timedelta(days=1)).isoformat()
    r = c.post("/api/bx/leads/3001/call", json={"result": "callback", "text": "в пятницу", "next": nxt}, headers=hdr(6000)).json()
    assert r["task"] == 778
    assert any(m == "crm.timeline.comment.add" and "просил перезвонить: в пятницу" in p["fields"]["COMMENT"] for m, p in calls)
    with db.pool.connection() as conn:
        assert conn.execute("SELECT entity FROM bx_reminders WHERE deal_id=3001").fetchone()["entity"] == "lead"
    # отказ — только с причиной
    assert c.post("/api/bx/leads/3001/status", json={"status": "UC_MARGO5"}, headers=hdr(6000)).status_code == 400
    # в сделку: контакт → сделка (город по названию) → лид сконвертирован
    calls.clear()
    assert c.post("/api/bx/leads/3001/convert", headers=hdr(6000)).status_code == 400          # услуга обязательна
    assert c.post("/api/bx/leads/3001/convert", json={"service": "1"}, headers=hdr(6000)).status_code == 400
    assert not calls
    # объект обязателен: из него и города — название сделки (HEAD 06.11)
    assert "объект" in c.post("/api/bx/leads/3001/convert", json={"service": "19285"}, headers=hdr(6000)).json()["detail"]
    assert not calls
    r = c.post("/api/bx/leads/3001/convert", json={"service": "19285", "address": "Астана, Кенесары 40", "object": "Школа №12"},
               headers=hdr(6000)).json()
    assert r == {"bx": "ok", "deal": 9100}
    assert [m for m, _ in calls] == ["crm.contact.add", "crm.deal.add", "crm.deal.update", "crm.item.update", "crm.activity.binding.add",
                                     "crm.lead.update", "crm.timeline.comment.add"]
    deal = calls[1][1]["fields"]
    assert deal["UF_CRM_6881101914D8D"] == "12077" and deal["UF_CRM_ARTGAME_AREA_M2"] == 40 and deal["LEAD_ID"] == 3001
    assert deal["CONTACT_ID"] == 9100 and deal["ASSIGNED_BY_ID"] == 4565 and deal["TITLE"] == "ШКОЛА №12 — АСТАНА"
    assert deal["UF_CRM_1753294730602"] == "19285" and deal["UF_CRM_1755520919823"] == "Астана, Кенесары 40"
    assert calls[2][1] == {"id": 9100, "fields": {"TITLE": "9100 · ШКОЛА №12 — АСТАНА"}}
    assert calls[3][1] == {"entityTypeId": 2, "id": 9100, "fields": {"leadId": 3001}}   # поле «Лид» у сделки
    assert calls[4][1] == {"activityId": 7, "entityTypeId": 2, "entityId": 9100}        # звонок лида — и в сделке
    assert calls[5][1]["fields"] == {"STATUS_ID": "CONVERTED"}
    LEADS["3001"].update({"STATUS_ID": "UC_93GBZP", "UF_CRM_1753202309": None})
    LEADS["3001"].pop("UF_CRM_ARTGAME_LEAD_AREA", None)


def test_rows_shapes():
    assert bx._rows({"result": {"items": [{"ID": 1}]}}) == [{"ID": 1}]
    assert bx._rows({"result": [{"ID": 2}]}) == [{"ID": 2}]
    assert bx._rows([{"ID": 3}]) == [{"ID": 3}]
    assert bx._rows({"result": {"something": 1}}) == []


def test_missed_calls(bxc):
    """Пропущенный входящий без перезвона — наверх «Горит»; после перезвона — пропадает. Чужие — не видно."""
    from datetime import datetime, timezone
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    miss = lambda oid, tid="2": {"ID": "9", "OWNER_TYPE_ID": tid, "OWNER_ID": oid, "DIRECTION": "1", "SETTINGS": {"MISSED_CALL": True},  # noqa: E731
                                 "CREATED": now, "START_TIME": now, "END_TIME": now, "SUBJECT": "Входящий от +7 700", "RESPONSIBLE_ID": "4693"}
    PHONE_CALLS[:] = [miss("1601"), miss("1651"), miss("3001", "1")]
    try:
        t = c.get("/api/bx/today?fresh=1", headers=hdr(6000)).json()["queue"]
        hot = [(x["entity"], x["id"]) for x in t["hot"] if x["why"].startswith("пропущенный звонок")]
        assert hot == [("deal", 1601), ("lead", 3001)]          # 1651 — чужая сделка
        assert sum((x["entity"], x["id"]) == ("deal", 1601) for b in t.values() for x in b) == 1   # без дублей
        # перезвонили (последний звонок исходящий) — пропал
        PHONE_CALLS.insert(0, {**miss("1601"), "ID": "10", "DIRECTION": "2", "SETTINGS": {}})
        t = c.get("/api/bx/today?fresh=1", headers=hdr(6000)).json()["queue"]
        assert not any(x["why"].startswith("пропущенный") and x["id"] == 1601 for x in t["hot"])
        # HEAD видит все
        t = c.get("/api/bx/today?fresh=1", headers=hdr(1000)).json()["queue"]
        assert {x["id"] for x in t["hot"] if x["why"].startswith("пропущенный")} == {1651, 3001}
    finally:
        PHONE_CALLS.clear()


def test_call_label():
    from artgame import calls
    a = {"SUBJECT": "Исходящий на +7 701", "DIRECTION": "2", "START_TIME": "2026-11-05T11:29:01+03:00", "END_TIME": "2026-11-05T11:31:55+03:00"}
    assert calls.label(a) == "Исходящий на +7 701 · 2:54"
    assert calls.label({**a, "END_TIME": a["START_TIME"]}) == "Исходящий на +7 701 · не соединился"
    assert calls.label({"SUBJECT": "Входящий", "DIRECTION": "1", "SETTINGS": {"MISSED_CALL": True}}) == "Входящий · пропущен"


def test_chat_waiting(bxc):
    """Клиент написал последним в WhatsApp дольше 30 мин назад — «Горит», кнопка «Ответить»; ответили — пропало."""
    from datetime import datetime, timedelta, timezone
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    t0 = lambda m: (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat(timespec="seconds")  # noqa: E731
    users = {"15": {"id": "15", "connector": False, "type": "user"}, "4995": {"id": "4995", "connector": True, "type": "extranet"}}
    msg = lambda i, sid, text, m: {"id": str(i), "senderid": sid, "date": t0(m), "text": text}  # noqa: E731
    DIALOGS[:] = [{"ID": "1", "OWNER_TYPE_ID": "2", "OWNER_ID": "1601", "ASSOCIATED_ENTITY_ID": "71", "LAST_UPDATED": t0(5)},
                  {"ID": "2", "OWNER_TYPE_ID": "1", "OWNER_ID": "3001", "ASSOCIATED_ENTITY_ID": "72", "LAST_UPDATED": t0(5)},
                  {"ID": "3", "OWNER_TYPE_ID": "2", "OWNER_ID": "1647", "ASSOCIATED_ENTITY_ID": "73", "LAST_UPDATED": t0(5)}]
    HISTORY.clear()
    HISTORY.update({
        # сделка 1601: клиент спросил 2 ч назад, потом ещё раз; системное сообщение не в счёт
        71: {"users": users, "message": {"1": msg(1, "15", "Здравствуйте", 200), "2": msg(2, "4995", "Сколько стоит?", 120),
                                         "3": msg(3, "4995", "Ау", 60), "4": msg(4, "0", "Анна начала работу с диалогом", 50)}},
        # лид 3001: менеджер ответил с телефона через Wazzup — от имени клиента, но с пометкой
        72: {"users": users, "message": {"1": msg(1, "4995", "Привет", 120), "2": msg(2, "4995", "=== Исходящее сообщение, автор: Тимур ===\nДобрый день", 100)}},
        # сделка 1647: клиент написал 10 мин назад — ещё в норме
        73: {"users": users, "message": {"1": msg(1, "4995", "Ок", 10)}},
    })
    try:
        t = c.get("/api/bx/today?fresh=1", headers=hdr(6000)).json()
        hot = [(x["entity"], x["id"], x["action"]) for x in t["queue"]["hot"] if x["why"].startswith("клиент ждёт")]
        assert hot == [("deal", 1601, "chat")] and t["warn"] == ""
        assert "2 ч" in next(x["why"] for x in t["queue"]["hot"] if x["id"] == 1601)
        # без права «Открытые линии» — предупреждение, «Сегодня» работает
        HISTORY.clear()
        t = c.get("/api/bx/today?fresh=1", headers=hdr(6000)).json()
        assert "Открытые линии" in t["warn"] and t["queue"]["hot"] is not None
    finally:
        DIALOGS.clear()
        HISTORY.clear()


def test_chat_history_shapes_and_batch(monkeypatch):
    """Переписка: пустые наборы списком, наивные даты — без падения; через вебхук — одна пачка batch, чужие диалоги не читаем."""
    from datetime import datetime, timedelta, timezone
    from artgame import chats
    from artgame.config import settings
    assert chats.last_client_wait({"message": [], "users": []}) is None
    assert chats.last_client_wait(None) is None
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None).isoformat(timespec="seconds")
    w = chats.last_client_wait({"users": [{"id": "9", "connector": True}], "message": [{"id": "1", "senderid": "9", "date": old}]})
    assert w is not None and w.tzinfo is not None
    t0 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
    acts = [{"OWNER_TYPE_ID": "2", "OWNER_ID": "1601", "ASSOCIATED_ENTITY_ID": "71", "LAST_UPDATED": t0},
            {"OWNER_TYPE_ID": "2", "OWNER_ID": "9999", "ASSOCIATED_ENTITY_ID": "79", "LAST_UPDATED": t0}]
    sent = []

    def webhook(method, params):
        sent.append((method, params))
        if method == "crm.activity.list":
            return {"result": acts}
        assert method == "batch"
        return {"result": {"result": {k: {"users": {"9": {"connector": True}}, "message": {"1": {"id": "1", "senderid": "9", "date": old}}}
                                      for k in params["cmd"]}, "result_error": []}}
    monkeypatch.setattr(bx, "READ", bx._gateway_read)
    monkeypatch.setattr(bx, "_webhook_read", webhook)
    monkeypatch.setattr(settings, "gateway_url", "")
    monkeypatch.setattr(settings, "bitrix_webhook", "https://example.invalid/rest/1/x/")
    out, err = chats.waiting(True, {("deal", 1601)})
    assert err == "" and [(o["entity"], o["id"]) for o in out] == [("deal", 1601)]
    batches = [p for m, p in sent if m == "batch"]
    assert len(batches) == 1 and list(batches[0]["cmd"]) == ["s71"]
    assert batches[0]["cmd"]["s71"] == "imopenlines.session.history.get?SESSION_ID=71"


def test_today_survives_broken_source(bxc, monkeypatch):
    """Упали звонки — «Сегодня» открывается со сделками и пометкой, а не ошибкой 500."""
    from artgame import calls
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))

    def boom(fresh=False):
        raise RuntimeError("timeout")
    monkeypatch.setattr(calls, "missed", boom)
    r = c.get("/api/bx/today?fresh=1", headers=hdr(6000))
    assert r.status_code == 200
    t = r.json()
    assert "звонки не загрузились" in t["warn"] and (t["queue"]["hot"] or t["queue"]["today"] or t["queue"]["later"])


def test_anna_fixes(bxc, monkeypatch):
    """Замечания Анны 06.11: «Жду ответа», вакансии, название, контакт сделки, поля проекта, города сделки."""
    from datetime import date, timedelta
    from artgame import bxw
    from artgame.config import settings
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x/rest/1/k/")
    calls = []

    def fake_call(method, params):
        calls.append((method, params))
        if method == "crm.lead.update":
            LEADS[str(params["id"])].update(params["fields"])
        if method == "crm.deal.update":
            DEALS[str(params["id"])].update(params["fields"])
        return {"result": {"task": {"id": "779"}}} if method == "tasks.task.add" else {"result": 9200 if method.endswith(".add") else True}
    monkeypatch.setattr(bxw, "CALL", fake_call)
    # города в карточке сделки — из списка СДЕЛКИ (у лида свои ID)
    dct = c.get("/api/bx/dict", headers=hdr(6000)).json()
    assert dct["cities"] == [{"id": "12077", "name": "Астана"}]
    assert dct["project"]["model"] == [{"id": "31", "name": "B2B"}, {"id": "32", "name": "B2C"}] and "artists" in dct["project"]["have"]
    # «Жду ответа»: без даты нельзя; с датой — лид не горит, а ждёт в «позже»
    assert any(x["id"] == 3001 for x in c.get("/api/bx/today", headers=hdr(6000)).json()["queue"]["hot"])
    assert c.post("/api/bx/leads/3001/call", json={"result": "wait"}, headers=hdr(6000)).status_code == 400
    nxt = date.today() + timedelta(days=2)
    assert c.post("/api/bx/leads/3001/call", json={"result": "wait", "text": "думает", "next": nxt.isoformat()}, headers=hdr(6000)).json()["bx"] == "ok"
    q = c.get("/api/bx/today?fresh=1", headers=hdr(6000)).json()["queue"]
    assert not any(x["entity"] == "lead" and x["id"] == 3001 for x in q["hot"] + q["today"])
    w = next(x for x in q["later"] if x["entity"] == "lead" and x["id"] == 3001)
    assert w["why"].startswith(f"ждём до {nxt:%d.%m}") and "думает" in w["why"] and w["wait"] == nxt.isoformat()
    # название лида
    calls.clear()
    assert c.post("/api/bx/leads/3001", json={"title": "Школа №12 — Астана"}, headers=hdr(6000)).json()["bx"] == "ok"
    assert calls[0][0] == "crm.lead.update" and calls[0][1]["fields"] == {"TITLE": "Школа №12 — Астана"}
    # вакансия: без причины, из списка лидов уходит
    full = c.get("/api/bx/leads/3001?fresh=1", headers=hdr(6000)).json()
    assert full["vacancy"] == [{"id": "UC_YHM21B", "name": "Вакансии Астана", "keep": True}, {"id": "UC_F2Y3S1", "name": "Вакансии", "keep": False}]
    assert all(f["id"] != "UC_F2Y3S1" for f in full["fail"])
    assert c.post("/api/bx/leads/3001/status", json={"status": "UC_YHM21B"}, headers=hdr(6000)).json()["bx"] == "ok"
    assert [l["id"] for l in c.get("/api/bx/leads?fresh=1", headers=hdr(6000)).json()["leads"]] == []
    LEADS["3001"]["STATUS_ID"] = "UC_93GBZP"
    # название сделки = «№ · ОБЪЕКТ — ГОРОД»; объект пишется в своё поле
    calls.clear()
    assert c.post("/api/bx/deals/1601/fields", json={"object": "Кафе Daily"}, headers=hdr(6000)).json()["bx"] == "ok"
    upd = next(p for m, p in calls if m == "crm.deal.update")["fields"]
    assert upd["TITLE"] == "1601 · КАФЕ DAILY — АСТАНА" and upd["UF_CRM_ARTGAME_OBJECT"] == "Кафе Daily"
    # поля проекта: только известные значения; VIP — Y/N, художники — списком
    calls.clear()
    r = c.post("/api/bx/deals/1601/fields", json={"project": {"model": "31", "vip": True, "artists": ["4565", "999"], "size": "x"}}, headers=hdr(6000))
    assert r.json()["bx"] == "ok"
    upd = next(p for m, p in calls if m == "crm.deal.update")["fields"]
    assert upd == {"UF_CRM_ARTGAME_PROJECT_MODEL": "31", "UF_CRM_ARTGAME_PROJECT_VIP": "Y", "UF_CRM_1753381517": [4565]}
    card = c.get("/api/bx/deals/1601?fresh=1", headers=hdr(6000)).json()
    assert card["project"]["model"] == "31" and card["project"]["vip"] is True and card["project"]["artists"] == ["4565"]
    # контакт: у сделки уже есть — 409; без контакта и без телефона — 400; с телефоном — создаём и привязываем
    assert c.post("/api/bx/deals/1601/contact", json={}, headers=hdr(6000)).status_code == 409
    DEALS["1590"]["STAGE_ID"] = "PREPARATION"
    try:
        assert c.get("/api/bx/deals/1590", headers=hdr(6000)).json()["client"]["no_contact"] is True
        assert c.post("/api/bx/deals/1590/contact", json={}, headers=hdr(6000)).status_code == 400
        calls.clear()
        assert c.post("/api/bx/deals/1590/contact", json={"name": "Ерлан", "phone": "+77015550000"}, headers=hdr(6000)).json()["bx"] == "ok"
        assert [m for m, _ in calls] == ["crm.contact.add", "crm.deal.update", "crm.timeline.comment.add"]
        assert calls[0][1]["fields"]["PHONE"] == [{"VALUE": "+77015550000", "VALUE_TYPE": "WORK"}] and calls[1][1]["fields"] == {"CONTACT_ID": 9200}
    finally:
        DEALS["1590"].update({"STAGE_ID": "WON", "CONTACT_ID": "0"})
        DEALS["1601"].update({"TITLE": "1601 · КАФЕ — АСТАНА"})
        for k in ("UF_CRM_ARTGAME_OBJECT", "UF_CRM_ARTGAME_PROJECT_MODEL", "UF_CRM_ARTGAME_PROJECT_VIP", "UF_CRM_1753381517"):
            DEALS["1601"].pop(k, None)
