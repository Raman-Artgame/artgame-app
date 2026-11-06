"""Заполненность карточки сделки и ИИ-помощник (HEAD 06.11): что заполнено, что нужно сейчас, разбор переписки."""
from artgame import bx, db, fill
from conftest import hdr
from test_bx import DEALS, bxc, fake  # noqa: F401


def test_fill_state_and_fields(bxc, monkeypatch):
    from artgame import bxw
    from artgame.config import settings
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    calls = []

    def fake_call(method, params):
        calls.append((method, params))
        if method == "crm.deal.update":
            DEALS["1601"].update({k: v for k, v in params["fields"].items() if not isinstance(v, (dict, list))})
        return {"result": True}
    monkeypatch.setattr(bxw, "CALL", fake_call)
    old = dict(DEALS["1601"])
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM deal_calc WHERE deal_id=1601")   # расчёт мог остаться от других тестов
    try:
        DEALS["1601"].update({"STAGE_ID": "FINAL_INVOICE", bx.F_SHIFTS: None, fill.F_DAYS: None, fill.F_WARR: None, fill.F_START: None, fill.F_END: None})
        bx._cache.clear()
        f = c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()["fill"]
        by = {x["key"]: x for x in f["items"]}
        # на стадии «Отправка счёта/договора» нужно всё до шага «Договор»; оплата и работа — ещё нет
        assert by["city"]["ok"] and by["area"]["ok"] and by["address"]["ok"] and by["sum"]["ok"]
        assert by["adv"]["ok"] and by["adv"]["need"] and not by["days"]["ok"] and by["days"]["need"]
        assert not by["paid"]["need"] and not by["start"]["need"]
        assert "Срок по договору, дней" in f["missing"] and "Расчёт цены и срока" in f["missing"]
        r = c.post("/api/bx/deals/1601/fields", json={"days": 20, "warranty": 6, "start": "2026-11-10", "end": "2026-11-30"}, headers=hdr(6000)).json()
        w = calls[0][1]["fields"]
        assert r["bx"] == "ok" and w[fill.F_DAYS] == "20" and w[fill.F_WARR] == 6 and w[fill.F_START] == "2026-11-10" and w[fill.F_END] == "2026-11-30"
        assert "уточнил: срок 20 дн., гарантия 6 мес., старт 10.11.2026, сдача план 30.11.2026" in calls[1][1]["fields"]["COMMENT"]
        bx._cache.clear()
        f = c.get("/api/bx/deals/1601/full", headers=hdr(6000)).json()["fill"]
        assert "Срок по договору, дней" not in f["missing"]
    finally:
        DEALS["1601"] = old
        bx._cache.clear()


def test_extract_rules(bxc, monkeypatch):
    from artgame.config import settings
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "anthropic_key", "")
    text = ("Здравствуйте! Нужна роспись стены в детском саду, Астана, ул. Кенесары, 40. Площадь примерно 45 м2. "
            "Готовы внести аванс 50%, хотим уложиться за 14 дней. ТОО «Солнышко», БИН 123456789012, тел. +7 701 555 44 33")
    r = c.post("/api/bx/deals/1601/extract", json={"text": text}, headers=hdr(6000)).json()
    f, cl = r["fields"], r["client"]
    assert r["source"] == "rules"
    assert f["area"] == 45 and f["adv"] == 50 and f["days"] == 14 and f["city"] == "5501" and f["address"].startswith("ул. Кенесары")
    assert cl["bin"] == "123456789012" and cl["company"] == "ТОО «Солнышко»" and cl["phone"] == "+7 701 555 44 33"
    assert c.post("/api/bx/deals/1601/extract", json={"text": "привет"}, headers=hdr(6000)).status_code == 400
    assert c.post("/api/bx/deals/1651/extract", json={"text": text}, headers=hdr(6000)).status_code == 403   # чужая сделка


def test_extract_ai(bxc, monkeypatch):
    from artgame.config import settings
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "anthropic_key", "k")
    seen = {}

    def fake_ai(text, cities, services):
        seen.update(cities=cities, services=services)
        return {"city": "Астана", "service": "Художественная роспись стен", "area": 60, "address": "пр. Абая 10", "adv": 30, "days": 0,
                "start": "2026-11-20", "name": "Айгерим", "phone": "", "email": "", "bin": "", "company": "", "signer": "", "wishes": "космос"}
    monkeypatch.setattr(fill, "_ai", fake_ai)
    r = c.post("/api/bx/deals/1601/extract", json={"text": "длинная переписка с клиентом"}, headers=hdr(6000)).json()
    assert r["source"] == "ai" and seen["cities"] == ["Астана"]
    assert r["fields"] == {"city": "5501", "cityName": "Астана", "service": "19285", "serviceName": "Художественная роспись стен",
                           "area": 60, "address": "пр. Абая 10", "adv": 30, "days": None, "start": "2026-11-20"}
    monkeypatch.setattr(fill, "_ai", lambda *a: (_ for _ in ()).throw(RuntimeError("timeout")))
    r = c.post("/api/bx/deals/1601/extract", json={"text": "площадь 30 м2, аванс 50%"}, headers=hdr(6000)).json()
    assert r["source"] == "rules" and "ИИ не ответил" in r["note"] and r["fields"]["area"] == 30


def test_stage_lock(bxc, monkeypatch, tmp_path):
    """Замок (HEAD 06.11): вперёд по воронке — только с заполненной карточкой; назад, «Отложено», отказ — свободно; HEAD — может."""
    from artgame import bxw
    from artgame.config import settings
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    calls = []

    def fake_call(method, params):
        calls.append((method, params))
        if method == "crm.deal.update":
            DEALS["1601"].update({k: v for k, v in params["fields"].items() if not isinstance(v, (dict, list))})
        return {"result": True}
    monkeypatch.setattr(bxw, "CALL", fake_call)
    old = dict(DEALS["1601"])
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM deal_calc WHERE deal_id=1601")   # расчёт мог остаться от других тестов
    try:
        DEALS["1601"].update({"STAGE_ID": "NEW", bx.F_SHIFTS: None, fill.F_DAYS: None, fill.F_WARR: None})
        bx._cache.clear()
        r = c.post("/api/bx/deals/1601/stage", json={"stage": "PREPARATION"}, headers=hdr(6000))
        assert r.status_code == 409 and "Расчёт цены и срока" in r.json()["detail"] and not calls
        # без расчёта КП ложится в сделку, но стадия стоит
        r = bxw.doc_saved({"id": ids[6000], "role_code": "mop", "full_name": "Ануар", "status": "active"}, 1601,
                          "КП ARTGAME №1601.pdf", "", {"total": 589250, "area": 25})
        assert "STAGE_ID" not in calls[0][1]["fields"] and r["held"] == ["Расчёт цены и срока"]
        with db.pool.connection() as conn:
            conn.execute("INSERT INTO deal_calc (deal_id, data) VALUES (1601, '{}')")
        bx._cache.clear()
        assert c.post("/api/bx/deals/1601/stage", json={"stage": "PREPARATION"}, headers=hdr(6000)).json()["bx"] == "ok"
        # на «Отправку счёта/договора» нужны КП-файл, аванс, срок, гарантия
        r = c.post("/api/bx/deals/1601/stage", json={"stage": "FINAL_INVOICE"}, headers=hdr(6000))
        assert r.status_code == 409 and "Срок по договору, дней" in r.json()["detail"] and "Гарантия, мес." in r.json()["detail"]
        # скачанный договор сам приносит аванс, срок и гарантию — стадия двигается (КП уже в сделке)
        DEALS["1601"][bxw.F_KP] = [{"id": 1}]
        bx._cache.clear()
        calls.clear()
        r = bxw.doc_saved({"id": ids[6000], "role_code": "mop", "full_name": "Ануар", "status": "active"}, 1601,
                          "ARTGAME_Dogovor_1601.docx", "", {"total": 600000, "adv": 50, "days": 20, "warr": 6})
        assert calls[0][1]["fields"]["STAGE_ID"] == "FINAL_INVOICE" and not r["held"]
        # назад и в «Отложено» — без замка; в работу без оплаты — нельзя, HEAD — можно
        assert c.post("/api/bx/deals/1601/stage", json={"stage": "PREPARATION"}, headers=hdr(6000)).json()["bx"] == "ok"
        DEALS["1601"]["STAGE_ID"] = "FINAL_INVOICE"
        bx._cache.clear()
        r = c.post("/api/bx/deals/1601/stage", json={"stage": "UC_AV00QK"}, headers=hdr(6000))
        assert r.status_code == 409 and "Аванс поступил" in r.json()["detail"]
        assert c.post("/api/bx/deals/1601/stage", json={"stage": "UC_AV00QK"}, headers=hdr(1000)).json()["bx"] == "ok"
    finally:
        DEALS["1601"] = old
        bx._cache.clear()
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM deal_calc WHERE deal_id=1601")
