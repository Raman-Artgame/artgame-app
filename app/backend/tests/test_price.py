"""Единое рабочее место МОП (HEAD 06.11): объединённый расчёт, причины отказа, квалификация, скрипты, проекты."""
import json

import pytest

from artgame import bx, db, price
from conftest import hdr
from test_bx import DEALS, bxc, fake  # noqa: F401


def test_compute_defaults():
    v = {}
    r = price.compute(price.PriceIn(service="mural", area=60, level="medium"), v)
    # ставка плавно 22 000 → 17 000 между 30 и 100 м²: 60 м² → 19 857 ₸/м², итог округлён до 1 000
    assert r["total"] == 1191000 and r["design"] == "M" and r["dprice"] == 36000 and not r["no_vat"]
    assert r["pay"]["prepay"] == 596000 and r["pay"]["rest"] == 595000 and r["pay"]["vat_included"]
    assert r["norm"]["shifts"] == 6 and r["norm"]["crew"] == 3 and r["norm"]["client"] == 4
    assert "Ориентир" in r["ladder"] and "1 191 000 ₸" in r["client_text"]
    r = price.compute(price.PriceIn(service="print", area=25, extras=["lacquer"], cash=10), v)
    assert r["lines"][0][2] == 589000 and r["total"] == 583000 and r["norm"]["ink"] == 375   # +10% лак, −10% наличные, округление
    r = price.compute(price.PriceIn(service="fix", level="hard", qty=2), v)
    assert r["total"] == 398000 and r["no_vat"] and r["pay"]["vat"] == round(398000 * 1.16)
    r = price.compute(price.PriceIn(service="mural", area=5, level="easy"), v)
    assert r["total"] == 120000 and any("минимальн" in f[1].lower() for f in r["flags"])   # минимальный заказ
    r = price.compute(price.PriceIn(service="mural", area=10, level="easy", place="near"), v)
    assert r["total"] == 350000   # выезд: не меньше минимума
    with pytest.raises(bx.HTTPException):
        price.compute(price.PriceIn(service="canvas", area=1), v)


def test_compute_from_values():
    v = {"mural.medium.a": 30000, "mural.medium.b": 30000, "mural.start": 30, "mural.round": 1000, "vat": 16, "prepay.work": 30}
    r = price.compute(price.PriceIn(service="mural", area=20, level="medium"), v)
    assert r["total"] == 600000 and r["pay"]["prepay_pct"] == 30 and r["pay"]["prepay"] == 180000


def test_price_save_and_reasons(bxc, monkeypatch):
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
    body = {"service": "mural", "area": 60, "level": "medium", "extras": ["height"]}
    r = c.post("/api/bx/deals/1601/price", json=body, headers=hdr(6000)).json()
    assert r["total"] == 1310000 and r["norm"]["shifts"] == 7.5   # высота +10% к цене и ×0.8 к норме
    assert c.post("/api/bx/deals/1651/price", json=body, headers=hdr(6000)).status_code == 403   # чужая сделка
    r = c.post("/api/bx/deals/1601/price/save", json=body, headers=hdr(6000)).json()
    f = calls[0][1]["fields"]
    assert r["bx"] == "ok" and f["OPPORTUNITY"] == 1310000 and f["UF_CRM_ARTGAME_AREA_M2"] == 60 and f["UF_CRM_ARTGAME_NORM_SHIFTS"] == 7.5
    assert f["UF_CRM_ARTGAME_COMPLEXITY"] == "902" and f["UF_CRM_ARTGAME_TERM_DAYS"] == 5 and r["norm_fields"]
    assert "расчёт: Художественная роспись — 1 310 000 ₸ с НДС, 60 м², по норме 7.5 смен, 3 чел., 5 раб. дн. клиенту, дизайн M" in calls[1][1]["fields"]["COMMENT"]
    g = c.get("/api/bx/deals/1601/calc", headers=hdr(6000)).json()
    assert g["out"]["total"] == 1310000 and g["in"]["area"] == 60 and g["by"] == "P6000"
    assert g["kp"] == {"name": "Художественная роспись стен", "sub": "уровень «Средний», по утверждённому эскизу; дизайн M 36 000 ₸ засчитывается в работы при договоре в течение 30 дней",
                       "qty": "60", "price": "21833.33", "service": "Художественная роспись стен", "vat": True}
    assert c.get("/api/bx/deals/1601/calc", headers=hdr(1000)).json()["out"]["total"] == 1310000   # HEAD видит
    DEALS["1601"]["OPPORTUNITY"] = "589250.00"
    # причины отказа: только из списка, текст = причина + комментарий
    assert len(c.get("/api/bx/reasons", headers=hdr(6000)).json()) == 8
    assert c.post("/api/bx/deals/1601/stage", json={"stage": "LOSE", "reason": "дорого"}, headers=hdr(6000)).status_code == 400
    calls.clear()
    r = c.post("/api/bx/deals/1601/stage", json={"stage": "LOSE", "reason_code": "price", "reason": "бюджет 300 тыс."}, headers=hdr(6000)).json()
    assert r["bx"] == "ok" and calls[0][1]["fields"][bxw.F_REASON] == "Дорого: бюджет клиента ниже. бюджет 300 тыс."
    assert "перевёл в «Высокая стоимость»: Дорого: бюджет клиента ниже. бюджет 300 тыс." in calls[1][1]["fields"]["COMMENT"]
    DEALS["1601"]["STAGE_ID"] = "PREPARATION"
    # квалификация: город, услуга, площадь, адрес
    calls.clear()
    r = c.post("/api/bx/deals/1601/fields", json={"city": "12077", "area": 40, "address": "ул. Абая 1"}, headers=hdr(6000)).json()
    f = calls[0][1]["fields"]
    assert r["bx"] == "ok" and f[bx.CITY] == "12077" and f[bx.AREA] == 40 and f[bx.ADDR] == "ул. Абая 1"
    assert "уточнил: 40 м², Астана, ул. Абая 1" in calls[1][1]["fields"]["COMMENT"]
    assert c.post("/api/bx/deals/1601/fields", json={}, headers=hdr(6000)).status_code == 400
    d = c.get("/api/bx/dict", headers=hdr(6000)).json()
    assert d["cities"] == [{"id": "12077", "name": "Астана"}] and d["services"] == [{"id": "19285", "name": "Художественная роспись стен"}]
    DEALS["1601"] = old


def test_scripts(bxc, monkeypatch, tmp_path):
    from artgame import places
    from artgame.config import settings
    c, ids = bxc
    key = "11" * 32
    monkeypatch.setattr(settings, "content_key", key)
    monkeypatch.setattr(places, "ROOT", tmp_path)
    (tmp_path / "mop").mkdir()
    data = {"scr": {"p1": [["1. Первое касание", [{"c": "С1", "s": "Первый ответ", "ru": "Здравствуйте!"}]]], "p2": []}, "algo": {"steps": [{"n": "01", "title": "Лид"}]}}
    (tmp_path / "mop" / "scripts.json.enc").write_bytes(places.encrypt(json.dumps(data).encode(), "mop/scripts.json", key))
    assert c.get("/api/bx/scripts", headers=hdr(2000)).status_code == 403   # художник
    r = c.get("/api/bx/scripts", headers=hdr(6000)).json()
    assert r["scr"]["p1"][0][1][0]["c"] == "С1" and r["algo"]["steps"][0]["n"] == "01"


def test_projects(bxc):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    old = dict(DEALS["1601"])
    DEALS["1601"].update({"STAGE_ID": "UC_AV00QK", "UF_CRM_ARTGAME_TERM_DAYS": "4", "UF_CRM_ARTGAME_NORM_SHIFTS": "6", "UF_CRM_ARTGAME_NORM_CREW": None, "OPPORTUNITY": "589250.00", "DATE_MODIFY": "2026-11-01T13:51:28+03:00"})
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO objects (id, title, status) VALUES (1601, 'Кафе', 'active')")
        conn.execute("""INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, area_m2, status)
                        VALUES (gen_random_uuid(), %s, 1601, 'mural', now() - interval '1 day', now() - interval '14 hours', 12, 'approved'),
                               (gen_random_uuid(), %s, 1601, 'mural', now() - interval '2 day', now() - interval '38 hours', 10, 'submitted')""",
                     (ids[2000], ids[2000]))
    bx._cache.clear()
    try:
        r = c.get("/api/bx/projects", headers=hdr(6000)).json()
        assert r["counts"] == {"work": 1, "soon": 0, "closing": 0, "late": 1}
        p = r["projects"][0]
        # старт 01.11 (вс), 4 рабочих дня → сдача 05.11; сегодня 06.11 и позже → просрочен
        assert p["id"] == 1601 and p["working"] and p["start"] == "2026-11-01" and p["due"] == "2026-11-05" and p["left"] < 0 and p["state"] == "late"
        assert p["done"] == {"shifts": 2, "m2": 22.0, "last": p["done"]["last"]} and p["progress"] == 33 and p["people"] == ["P2000"]
        # «Старт факт» из сделки важнее истории стадий; «Оплата+закрывающие» — отдельно, не «в работе»
        DEALS["1601"]["UF_CRM_ARTGAME_PROJECT_START_ACTUAL"] = "2026-11-03T03:00:00+03:00"
        DEALS["1651"]["STAGE_ID"] = "UC_BMKDS4"
        bx._cache.clear()
        r = c.get("/api/bx/projects", headers=hdr(6000)).json()
        assert r["counts"]["work"] == 1 and r["counts"]["closing"] == 1
        p = next(x for x in r["projects"] if x["id"] == 1601)
        assert p["start"] == "2026-11-03" and p["due"] == "2026-11-09"
        q = next(x for x in r["projects"] if x["id"] == 1651)
        assert q["closing"] and not q["working"] and q["state"] == "closing" and q["left"] is None
        assert p["sum"] == 589250 and p["manager"] == "Ануар Минкеев" and p["norm"] == {"shifts": 6, "crew": 0, "term": 4}
        r2 = c.get("/api/bx/projects", headers=hdr(2000)).json()   # художник видит проект, но не сумму
        assert r2["projects"][0]["sum"] is None
    finally:
        DEALS["1601"] = old
        DEALS["1651"]["STAGE_ID"] = "NEW"
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM shifts WHERE object_id=1601"); conn.execute("DELETE FROM objects WHERE id=1601")
