"""Кабинеты команды (HEAD 07.11): проверка по лестнице, сбор на объект, воронка дизайна, единицы, каталог, ставка в «Мои»."""
import uuid

import pytest
from psycopg.types.json import Jsonb

from artgame import bx, bxw, db
from artgame.config import settings
from conftest import hdr

T0, T1 = "2026-11-04T09:00:00+05:00", "2026-11-04T19:00:00+05:00"
VALS = {"pay.artist.shift": 15000, "pay.artist.hour": 1500, "pay.chief.shift": 20000, "shift.hours": 10,
        "pay.design.lead.month": 300000, "pay.design.unit_over": 10000, "pay.design.catalog": 5000,
        "design.unit.xs": "0,5", "design.unit.s": 1, "design.unit.m": 2, "design.unit.l": 4, "design.unit.xl": 8}


def people(client, roles):
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                     ("t", Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "head"} for k, v in VALS.items()})))
        conn.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (731, 'Кафе', 'Астана', 'UC_AV00QK')")
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    ids = {}
    for tg, role, zones in roles:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": zones}, headers=hdr(1000))
        ids[tg] = pid
    return ids


def shift(client, tg):
    return client.post("/api/shifts", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural",
                                            "started_at": T0, "ended_at": T1}, headers=hdr(tg)).json()["id"]


def test_review_by_rank(client):
    people(client, [(2000, "artist", ["mural"]), (3000, "lead_artist", ["mural"]), (3100, "lead_artist", ["mural"]),
                    (4000, "artist_pro", ["mural"])])
    a, l2, pro = shift(client, 2000), shift(client, 3100), shift(client, 4000)
    seen = lambda tg: {x["id"] for x in client.get("/api/review", headers=hdr(tg)).json()["shifts"]}  # noqa: E731
    assert seen(3000) == {a}                 # Главный: художника да, Главного и Про — нет
    assert seen(4000) == {a, l2}             # Про выше Главного — проверяет его, себя нет
    assert client.post(f"/api/shift/{pro}/review", json={"approve": True}, headers=hdr(3000)).status_code == 403
    assert client.post(f"/api/shift/{l2}/review", json={"approve": True}, headers=hdr(4000)).json()["status"] == "approved"
    assert seen(1000) >= {a, pro}


def test_kit_flow(client):
    people(client, [(2000, "artist", ["mural"]), (3000, "lead_artist", ["mural"]), (4500, "print_master", ["print"])])
    d = client.get("/api/kit/dict", headers=hdr(3000)).json()
    assert list(d["zones"]) == ["mural"] and d["zones"]["mural"]["facade"] and d["can_edit_role"]
    assert not client.get("/api/kit/dict", headers=hdr(2000)).json()["can_edit_role"]
    items = {"aerosol": [{"color": "RAL 3020", "taken": 6}, {"color": "", "taken": 3}], "facade": {"taken": "12,5"},
             "mat": {"МАТ-03": {"taken": 1}, "МАТ-06": {"taken": 2}}, "obr": {"ОБР-02": {"took": True, "state_out": "исправно"}},
             "ras": {"РАС-03": True}, "pre": [True, True, True]}
    # художник не собирает, печать — не его зона
    assert client.post("/api/kit/731/mural", json={"items": items}, headers=hdr(2000)).status_code == 403
    assert client.post("/api/kit/731/mural", json={"items": items}, headers=hdr(4500)).status_code == 403
    k = client.post("/api/kit/731/mural", json={"items": items}, headers=hdr(3000)).json()
    assert [r["color"] for r in k["items"]["aerosol"]] == ["RAL 3020"] and k["items"]["facade"]["taken"] == 12.5
    assert "МАТ-03" not in k["items"]["mat"]           # неизвестный код отброшен
    # художник видит список, но не правит
    g = client.get("/api/kit/731/mural", headers=hdr(2000)).json()
    assert g["list"]["id"] == k["id"] and not g["can_edit"]
    # сдать нельзя, пока не вернули и не отметили состояние
    r = client.post("/api/kit/731/mural/close", headers=hdr(3000))
    assert r.status_code == 409 and "ОБР-02" in r.json()["detail"] and "RAL 3020" in r.json()["detail"]
    items.update({"aerosol": [{"color": "RAL 3020", "taken": 6, "returned": 2}], "facade": {"taken": 12.5, "returned": 2.5},
                  "mat": {"МАТ-06": {"taken": 2, "returned": 0}},
                  "obr": {"ОБР-02": {"took": True, "state_out": "исправно", "back": True, "state_in": "есть замечание"}}})
    client.post("/api/kit/731/mural", json={"items": items}, headers=hdr(3000))
    u = client.post("/api/kit/731/mural/close", headers=hdr(3000)).json()["usage"]
    assert u["aerosol"] == [{"color": "RAL 3020", "used": 4.0}] and u["facade_l"] == 10.0 and u["mat"] == {"МАТ-06": 2.0} and u["lost"] == []
    assert client.post("/api/kit/731/mural", json={"items": items}, headers=hdr(3000)).status_code == 409
    lst = client.get("/api/kit", headers=hdr(3000)).json()
    assert lst["objects"][0]["lists"]["mural"]["status"] == "closed"


DEALS = {}
STAGES = [("C13:NEW", "Свежие заказы", 10, None), ("C13:PREPARATION", "Взято в работу", 20, None),
          ("C13:EXECUTING", "Правки", 30, None), ("C13:WON", "УТВЕРЖДЕНО", 40, "success"), ("C13:LOSE", "Отказ", 50, "failure")]


def fake(method, params):
    if method == "crm.deal.list":
        f = params["filter"]
        sem = lambda d: "S" if d["STAGE_ID"].endswith("WON") else "F" if d["STAGE_ID"].endswith("LOSE") else "P"  # noqa: E731
        rows = [d for d in DEALS.values() if sem(d) == f["STAGE_SEMANTIC_ID"] and int(d["CATEGORY_ID"]) in f["CATEGORY_ID"]]
        if ">=CLOSEDATE" in f:
            rows = [d for d in rows if f[">=CLOSEDATE"] <= (d.get("CLOSEDATE") or "")[:10] < f["<CLOSEDATE"]]
        return {"result": rows, "total": len(rows)}
    if method == "crm.deal.get":
        return {"result": DEALS.get(str(params["id"]))}
    if method == "crm.status.list":
        if params["filter"]["ENTITY_ID"] != "DEAL_STAGE_13":
            return {"result": []}
        return {"result": [{"STATUS_ID": s, "NAME": n, "SORT": str(o), **({"EXTRA": {"SEMANTICS": e}} if e else {})} for s, n, o, e in STAGES]}
    if method == "crm.deal.fields":
        return {"result": {}}
    raise AssertionError(method)


@pytest.fixture
def dz(client, monkeypatch):
    DEALS.clear()
    DEALS.update({
        "1647": {"ID": "1647", "TITLE": "Дизайн кафе", "STAGE_ID": "C13:NEW", "CATEGORY_ID": "13", "ASSIGNED_BY_ID": "4565"},
        "1648": {"ID": "1648", "TITLE": "Дизайн школы", "STAGE_ID": "C13:PREPARATION", "CATEGORY_ID": "13", "ASSIGNED_BY_ID": "4565",
                 "UF_CRM_ARTGAME_DESIGNER": "7001"},
        "1601": {"ID": "1601", "TITLE": "Продажа", "STAGE_ID": "NEW", "CATEGORY_ID": "0", "ASSIGNED_BY_ID": "4565"}})
    monkeypatch.setattr(bx, "READ", fake)
    bx._cache.clear()
    ids = people(client, [(7000, "lead_designer", []), (7100, "designer_asst", []), (2000, "artist", ["mural"])])
    client.post(f"/api/people/{ids[7000]}", json={"bitrix_user_id": 7000}, headers=hdr(1000))
    client.post(f"/api/people/{ids[7100]}", json={"bitrix_user_id": 7001}, headers=hdr(1000))
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    calls = []

    def fake_call(method, params):
        calls.append((method, params))
        if method == "crm.deal.update":
            DEALS[str(params["id"])].update(params["fields"])
        return {"result": True}
    monkeypatch.setattr(bxw, "CALL", fake_call)
    return ids, calls


def test_design_funnel_units(client, dz):
    ids, calls = dz
    assert client.get("/api/design/deals", headers=hdr(2000)).status_code == 403
    lead = client.get("/api/design/deals", headers=hdr(7000)).json()
    assert {d["id"] for d in lead["deals"]} == {1647, 1648} and lead["can_assign"]
    assert [s["id"] for s in lead["stages"]] == ["C13:NEW", "C13:PREPARATION", "C13:EXECUTING", "C13:WON"]
    assert [s["units"] for s in lead["sizes"]] == [0.5, 1, 2, 4, 8]
    asst = client.get("/api/design/deals", headers=hdr(7100)).json()
    assert [d["id"] for d in asst["deals"]] == [1648] and not asst["can_assign"]
    # помощник не назначает размер и не трогает чужую сделку
    assert client.post("/api/design/deals/1648", json={"size": "m"}, headers=hdr(7100)).status_code == 403
    assert client.post("/api/design/deals/1647", json={"stage": "C13:PREPARATION"}, headers=hdr(7100)).status_code == 403
    assert client.post("/api/design/deals/1601", json={"stage": "C13:NEW"}, headers=hdr(7000)).status_code == 404
    # Главный назначает XS (в Битриксе нет — хранится в приложении)
    r = client.post("/api/design/deals/1648", json={"size": "xs", "deadline": "2026-11-12"}, headers=hdr(7000)).json()
    assert r["bx"] == "ok" and "UF_CRM_ARTGAME_DESIGN_COMPLEXITY" not in calls[0][1]["fields"]
    # круги правок: каждый переход в «Правки» — новый круг
    for n in (1, 2):
        assert client.post("/api/design/deals/1648", json={"stage": "C13:EXECUTING"}, headers=hdr(7100)).json()["round"] == n
        client.post("/api/design/deals/1648", json={"stage": "C13:PREPARATION"}, headers=hdr(7100))
    # «УТВЕРЖДЕНО» без эскиза — нельзя
    r = client.post("/api/design/deals/1648", json={"stage": "C13:WON"}, headers=hdr(7100))
    assert r.status_code == 409 and "эскиз" in r.json()["detail"]
    assert client.post("/api/design/deals/1648", json={"stage": "C13:WON", "layout": "https://drive/x"}, headers=hdr(7100)).json()["bx"] == "ok"
    u = client.get("/api/design/units", headers=hdr(7100)).json()
    assert u["mine"] == 0.5 and u["rows"][0]["rounds"] == 2 and not u["can_cancel"]
    # повторное чтение воронки единицу не дублирует
    client.get("/api/design/deals", headers=hdr(7000))
    assert len(client.get("/api/design/units", headers=hdr(7000)).json()["rows"]) == 1
    # проект в работу не пошёл — HEAD снимает с причиной
    assert client.post("/api/design/units/1648/cancel", json={"reason": "клиент отказался"}, headers=hdr(7000)).status_code == 403
    assert client.post("/api/design/units/1648/cancel", json={"reason": "клиент отказался"}, headers=hdr(1000)).json()["ok"]
    assert client.get("/api/design/units", headers=hdr(7100)).json()["mine"] == 0


def test_catalog_and_pay(client, dz):
    ids, _ = dz
    b = {"title": "Лофт", "style": "лофт", "authors": [ids[7000], ids[7100]]}
    assert client.post("/api/design/catalogs", json={**b, "authors": [ids[2000]]}, headers=hdr(7000)).status_code == 400
    c = client.post("/api/design/catalogs", json=b, headers=hdr(7000)).json()
    assert client.post(f"/api/design/catalogs/{c['id']}/send", headers=hdr(7000)).status_code == 409   # без ссылки
    client.post(f"/api/design/catalogs/{c['id']}", json={**b, "url": "https://pin/x"}, headers=hdr(7100))
    assert client.post(f"/api/design/catalogs/{c['id']}/send", headers=hdr(7100)).json()["ok"]
    assert client.post(f"/api/design/catalogs/{c['id']}/decide", json={"approve": True}, headers=hdr(7000)).status_code == 403
    assert client.post(f"/api/design/catalogs/{c['id']}/decide", json={"approve": False}, headers=hdr(1000)).status_code == 400
    assert client.post(f"/api/design/catalogs/{c['id']}/decide", json={"approve": True}, headers=hdr(1000)).json()["ok"]
    # ФОТ месяца: оклад Главного дизайнера, каталог пополам; норма единиц ждёт решения — предупреждение
    client.post("/api/design/deals/1647", json={"size": "l", "designer_bx": 7000, "layout": "https://d/1", "stage": "C13:WON"}, headers=hdr(7000))
    ym = __import__("datetime").date.today().strftime("%Y-%m")
    out = client.post(f"/api/fin/payroll/{ym}/compute", headers=hdr(1000)).json()
    assert any("норма pay.design.norm_units" in w for w in out["warn"])
    lines = {r["name"]: {(l["kind"], float(l["amount"])) for l in r["lines"]} for r in out["rows"]}
    assert lines["P7000"] == {("salary", 300000.0), ("catalog", 2500.0)} and ("catalog", 2500.0) in lines["P7100"]
    my = client.get("/api/fin/my", headers=hdr(7000)).json()
    assert {"label": "Оклад в месяц", "amount": 300000} in my["rate"] and my["accrued"] == 302500
    art = client.get("/api/fin/my", headers=hdr(2000)).json()["rate"]
    assert art[0] == {"label": "Смена 10 ч", "amount": 15000}


def test_design_team_from_bitrix_and_expense_cats(client, dz, monkeypatch):
    """HEAD 09.11: дизайнер из Битрикса (Малика), которого нет в приложении, — в выборе; у дизайнеров в «Расходе» — такси и «Другое»."""
    monkeypatch.setattr(bx, "users", lambda: [{"id": 4341, "name": "Малика Жұмаділдина", "position": "Дизайнер", "phone": ""},
                                              {"id": 7000, "name": "Алия", "position": "Главный дизайнер", "phone": ""},
                                              {"id": 4565, "name": "Ануар Минкеев", "position": "МОП", "phone": ""}])
    t = client.get("/api/design/team", headers=hdr(7000)).json()
    assert [x["bitrix_user_id"] for x in t if x.get("bx_only")] == [4341]
    DEALS["1647"]["UF_CRM_ARTGAME_DESIGNER"] = "4341"
    bx._cache.clear()
    d = {x["id"]: x for x in client.get("/api/design/deals?fresh=1", headers=hdr(7000)).json()["deals"]}
    assert d[1647]["designer"] == "Малика Жұмаділдина"
    cats = [c["code"] for c in client.get("/api/work/dict", headers=hdr(7100)).json()["categories"]]
    assert cats == ["transport", "other"]
