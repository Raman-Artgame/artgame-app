"""Закрытие сделки через HEAD (HEAD 12.11 «Да, по рекомендациям»): 11 пунктов проверяет приложение, «На закрытие» — только
когда всё выполнено; HEAD видит паспорт (прибыль и маржа — только у HEAD), «Вернуть» — сообщение МОП и ГИП, «Закрыть» —
сделка в «Оплата получена» и «Окончание факт» в Битрикс, паспорт снимком, PDF в «ДОКУМЕНТЫ», объект закрыт для смен и трат.
Сделку, перетащенную в «Оплата получена» прямо в Битриксе, Пульт показывает «мимо вас»; назад сама она не двигается."""
from psycopg.types.json import Jsonb

from artgame import bx, bxw, closing, db, dm, drive
from artgame.config import settings
from conftest import hdr
from test_bx import DEALS, fake
from test_finance import JPG, VALS, uid

F_CONTRACT, F_INV, F_ACTS = bxw.F_CONTRACT, bxw.F_INVOICES, bxw.F_ACTS
FILE = [{"id": 11, "downloadUrl": "https://bx.example/file"}]
STAGES = [{"STATUS_ID": "UC_AV00QK", "NAME": "Выполнение проекта", "SORT": "110"},
          {"STATUS_ID": "UC_BMKDS4", "NAME": "Оплата+закрывающие документы", "SORT": "120"},
          {"STATUS_ID": "WON", "NAME": "Оплата получена", "SORT": "200", "EXTRA": {"SEMANTICS": "success"}},
          {"STATUS_ID": "LOSE", "NAME": "Высокая стоимость", "SORT": "160", "EXTRA": {"SEMANTICS": "failure"}}]

COPIES: list = []   # копии фото «В Продакшн»: (откуда, куда)


def deal(i, stage="UC_BMKDS4", **f):
    return {"ID": str(i), "TITLE": f"{i} · ШКОЛА — ШЫМКЕНТ", "STAGE_ID": stage, "CATEGORY_ID": "0", "OPPORTUNITY": "1160000.00",
            "ASSIGNED_BY_ID": "4565", "CONTACT_ID": "0", "COMPANY_ID": "0", "MYCOMPANY_ID": "1103", "UF_CRM_6881101914D8D": None,
            F_CONTRACT: FILE, F_INV: FILE, F_ACTS: FILE, bxw.F_START: "2026-11-02T03:00:00+03:00", bxw.F_END: "2026-11-08T03:00:00+03:00",
            bx.F_SHIFTS: "2", **f}


def setup(client, monkeypatch):
    def read(method, params):
        if method == "crm.status.list" and params["filter"]["ENTITY_ID"] == "DEAL_STAGE":
            return {"result": STAGES}
        return fake(method, params)

    monkeypatch.setattr(bx, "READ", read)
    bx._cache.clear()
    monkeypatch.setitem(DEALS, "1700", deal(1700))
    calls = []

    def call(method, params):
        calls.append((method, params))
        if method == "crm.deal.update":
            DEALS[str(params["id"])].update(params["fields"])
        return {"result": True}

    monkeypatch.setattr(bxw, "CALL", call)
    monkeypatch.setattr(settings, "bitrix_webhook", "https://bx.example/rest/1/x/")
    sent = []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)))
    pdfs = []

    class FakeDrive:
        def pdf_from_html(self, parent, name, html):
            pdfs.append((parent, name, html))
            return "pdf-1"

        def copy(self, fid, parent, name=None):
            COPIES.append((fid, parent))
            return "prod-" + fid

    monkeypatch.setattr(drive, "Drive", FakeDrive)
    monkeypatch.setattr(drive, "ensure_folders", lambda conn, obj, d=None: {"doc": "doc-1700", "prod": "prod-1700"})
    monkeypatch.setattr(drive, "folder_of", lambda conn, obj, kind, d=None, media_type=None: drive.key_of(kind, media_type) + "-1700")
    COPIES.clear()
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    ids = {}
    for tg, role, zones in [(2000, "artist", ["mural"]), (3000, "lead_artist", ["mural"]), (6000, "mop", ["sales"])]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": zones}, headers=hdr(1000))
        ids[tg] = pid
    client.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                     ("t", Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "head"}
                                  for k, v in {**VALS, "pay.trip_food": 3000, closing.MODEL: 70}.items()})))
        conn.execute("""INSERT INTO objects (id, title, city, bitrix_stage, gip_person_id, drive_folder, design_synced_at)
                        VALUES (1700, 'Школа', 'Шымкент', 'UC_BMKDS4', %s, 'fold-1700', now())""", (ids[3000],))
    return ids, calls, sent, pdfs


def keys(r):
    return {x["key"] for x in r["checks"] if not x["ok"]}


def test_close_flow(client, monkeypatch):
    ids, calls, sent, pdfs = setup(client, monkeypatch)
    st = client.get("/api/bx/deals/1700/close", headers=hdr(6000)).json()
    assert st["ready"] and not st["ok"] and keys(st) == {"debt", "end", "photos"}
    assert next(x for x in st["checks"] if x["key"] == "design")["skip"]   # дизайна не было — пункт не нужен
    r = client.post("/api/bx/deals/1700/close", headers=hdr(6000))
    assert r.status_code == 409 and "Долг 0" in r.json()["detail"]
    assert client.get("/api/bx/deals/1700/close", headers=hdr(2000)).status_code == 403   # сделки видят МОП и HEAD

    # МОП внёс доплату с чеком (на сверке у HEAD), ГИП отметил сдачу, со смены есть фото, смена ждёт проверки
    monkeypatch.setattr(drive, "save_income_receipt", lambda conn, name, data, deal_id: "drv-income")
    pay = client.post("/api/bx/deals/1700/payment", json={"client_uid": uid(), "amount": 1160000, "op_date": "2026-11-10", "account": "kaspi",
                                                          "receipt": JPG}, headers=hdr(6000))
    assert pay.status_code == 200, pay.text
    assert client.post("/api/objects/1700/done", json={"day": "2026-11-10"}, headers=hdr(2000)).status_code == 403   # не ГИП
    done = client.post("/api/objects/1700/done", json={"day": "2026-11-10"}, headers=hdr(3000)).json()
    assert done["done_on"] == "2026-11-10" and done["done_by"] == "P3000"
    with db.pool.connection() as conn:
        conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, drive_id, status, uploaded_by)
                        VALUES (gen_random_uuid(), 1700, 'photo', 'после.jpg', 'image/jpeg', 'drv-ph', 'ready', %s)""", (ids[2000],))
    s = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 1700, "zone_code": "mural",
                                         "started_at": "2026-11-09T09:00:00+05:00", "ended_at": "2026-11-09T19:00:00+05:00"}, headers=hdr(2000)).json()
    st = client.get("/api/bx/deals/1700/close", headers=hdr(6000)).json()
    assert keys(st) == {"checked", "shifts"}
    assert next(x for x in st["checks"] if x["key"] == "shifts")["detail"] == "на проверке 1"
    assert "profit" not in str(st) and "margin" not in str(st)   # МОП прибыль и маржу не видит (решение 3)
    pid = client.get("/api/fin/payments/check", headers=hdr(1000)).json()
    lid = (pid.get("items") if isinstance(pid, dict) else pid)[0]["id"]
    assert client.post(f"/api/fin/ledger/{lid}/check", headers=hdr(1000)).status_code == 200
    assert client.post(f"/api/shift/{s['id']}/review", json={"approve": True}, headers=hdr(1000)).json()["status"] == "approved"
    assert client.get("/api/bx/deals/1700/close", headers=hdr(6000)).json()["ok"]

    # «На закрытие»: заявка — HEAD в бот и на Пульт; повтор не задваивает
    r = client.post("/api/bx/deals/1700/close", headers=hdr(6000))
    assert r.status_code == 200, r.text
    assert r.json()["request"]["status"] == "sent" and len(sent) == 1 and sent[0][0] == 1000 and "№ 1700" in sent[0][1]
    assert client.post("/api/bx/deals/1700/close", headers=hdr(6000)).json()["again"]
    assert client.get("/api/head/closing", headers=hdr(6000)).status_code == 403
    lst = client.get("/api/head/closing", headers=hdr(1000)).json()
    assert [x["deal_id"] for x in lst["sent"]] == [1700] and lst["bypass"] == []

    # паспорт: деньги, ФОТ, прибыль и маржа рядом с моделью, флаг «срок сорван»
    assert client.get("/api/head/closing/1700", headers=hdr(6000)).status_code == 403
    ps = client.get("/api/head/closing/1700", headers=hdr(1000)).json()
    assert ps["money"]["sum"] == 1160000 and ps["money"]["net"] == 1000000 and ps["money"]["debt"] == 0
    fot = next(g for g in ps["costs"] if g["key"] == "fot")
    assert fot["total"] == 15000 and fot["rows"][0]["name"] == "P2000" and fot["rows"][0]["hours"] == 10
    assert ps["result"] == {"net": 1000000, "costs": 15000, "profit": 985000, "margin": 98.5, "model": 70}
    assert ps["plan"]["shifts_plan"] == 2 and ps["plan"]["shifts_fact"] == 1 and ps["plan"]["days"] == 9
    assert any(f.startswith("Срок сорван: сдали 10.11.2026, по плану 08.11.2026") for f in ps["flags"])
    assert not any(f.startswith("Не выполнено") for f in ps["flags"])   # невыполненные пункты — в «Пунктах закрытия»
    assert [x["short"] for x in ps["checks"]][:3] == ["Долг 0", "Оплаты сверены", "Переплата"]
    assert ps["deal"]["myco"] == "ИП Яковлев" and ps["deal"]["gip"] == "P3000" and ps["photos"][0]["thumb"]
    # лучшее фото — «В Продакшн»: копия в «МЕДИА / Продакшн / Фото», оригинал на месте
    assert client.post(f"/api/head/closing/1700/prod/{ps['photos'][0]['id']}", headers=hdr(1000)).json()["prod"]
    assert COPIES == [("drv-ph", "prod_photo-1700")]
    assert client.get("/api/head/closing/1700", headers=hdr(1000)).json()["photos"][0]["prod"]

    # «Вернуть»: без причины нельзя; с пунктом — МОП и ГИП получают сообщение в чате «HEAD», стадия та же
    assert client.post("/api/head/closing/1700/return", json={}, headers=hdr(1000)).status_code == 400
    r = client.post("/api/head/closing/1700/return", json={"reason": "Нужны фото фасада", "points": ["photos", "xxx"]}, headers=hdr(1000)).json()
    assert r["told"] == 2 and not calls
    with db.pool.connection() as conn:
        got = {x["person_id"]: x["text"] for x in conn.execute("SELECT person_id, text FROM dm WHERE from_head").fetchall()}
    assert set(got) == {ids[6000], ids[3000]} and "Доделать: Фото объекта" in got[ids[6000]] and "Нужны фото фасада" in got[ids[3000]]
    st = client.get("/api/bx/deals/1700/close", headers=hdr(6000)).json()
    assert st["request"]["status"] == "returned" and st["request"]["points"] == [{"key": "photos", "title": "Фото объекта"}]

    # снова «На закрытие» → HEAD «Закрыть»: стадия и «Окончание факт» в Битрикс, без денег в ленте; паспорт и PDF
    assert client.post("/api/bx/deals/1700/close", headers=hdr(6000)).status_code == 200
    r = client.post("/api/head/closing/1700/close", headers=hdr(1000))
    assert r.status_code == 200, r.text
    assert r.json()["bx"] == "ok" and r.json()["via"] == "app"
    upd = [p for m, p in calls if m == "crm.deal.update"]
    assert upd == [{"id": 1700, "fields": {"STAGE_ID": "WON", bxw.F_END_FACT: "2026-11-10"}, "params": {"REGISTER_SONET_EVENT": "Y"}}]
    note = [p for m, p in calls if m == "crm.timeline.comment.add"][0]["fields"]["COMMENT"]
    assert "паспорт" in note and "985" not in note and "₸" not in note   # прибыль в Битрикс не пишем
    assert pdfs and pdfs[0][0] == "doc-1700" and "Паспорт сделки № 1700" in pdfs[0][2] and "985 000 ₸" in pdfs[0][2] and "<h2>Пункты закрытия</h2>" in pdfs[0][2]
    with db.pool.connection() as conn:
        row = conn.execute("SELECT * FROM deal_close WHERE deal_id=1700 AND status='closed'").fetchone()
        assert row["pdf_drive_id"] == "pdf-1" and row["passport"]["result"]["profit"] == 985000 and row["bx"] == "ok"
        assert conn.execute("SELECT closed_at FROM objects WHERE id=1700").fetchone()["closed_at"]
        assert conn.execute("SELECT count(*) AS n FROM dm WHERE text LIKE '%%закрыта. Паспорт сохранён%%'").fetchone()["n"] == 2
    ps = client.get("/api/head/closing/1700", headers=hdr(1000)).json()
    assert ps["frozen"] and ps["closed"]["by"] == "HEAD" and ps["request"]["pdf"].endswith("/pdf-1/view")
    assert client.post("/api/head/closing/1700/close", headers=hdr(1000)).status_code == 409
    lst = client.get("/api/head/closing", headers=hdr(1000)).json()
    assert lst["sent"] == [] and lst["closed"][0]["deal_id"] == 1700 and lst["closed"][0]["result"]["margin"] == 98.5

    # закрытый объект: ни смены, ни расхода, ни командировки, ни сдачи — даже задним числом
    sh = client.post("/api/shifts", json={"client_uid": uid(), "object_id": 1700, "zone_code": "mural",
                                          "started_at": "2026-11-11T09:00:00+05:00", "ended_at": "2026-11-11T19:00:00+05:00"}, headers=hdr(2000))
    assert sh.status_code == 400 and "закрыта HEAD" in sh.json()["detail"]
    ex = client.post("/api/expenses", json={"client_uid": uid(), "object_id": 1700, "zone_code": "mural", "category": "transport",
                                            "amount": 1000, "receipt": JPG}, headers=hdr(2000))
    assert ex.status_code == 400
    assert client.post("/api/objects/1700/trip-costs", json={"client_uid": uid(), "item": "lodging", "amount": 5000}, headers=hdr(1000)).status_code == 400
    assert client.post("/api/objects/1700/done", json={"day": "2026-11-09"}, headers=hdr(3000)).status_code == 409
    with db.pool.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM shifts WHERE object_id=1700").fetchone()["n"] == 1


def test_stage_won_only_through_passport(client, monkeypatch):
    setup(client, monkeypatch)
    for tg in (6000, 1000):
        r = client.post("/api/bx/deals/1700/stage", json={"stage": "WON"}, headers=hdr(tg))
        assert r.status_code == 409 and "шаг «Закрытие»" in r.json()["detail"]


def test_bypass_no_docs_and_test_deal(client, monkeypatch):
    ids, calls, sent, pdfs = setup(client, monkeypatch)
    # перетащили в «Оплата получена» прямо в Битриксе 12.11 — у HEAD «мимо вас»; старые выигранные (1590) — нет
    monkeypatch.setitem(DEALS, "1800", deal(1800, stage="WON", MOVED_TIME="2026-11-12T10:00:00+05:00", MOVED_BY_ID="4693"))
    monkeypatch.setitem(DEALS, "1801", deal(1801, stage="WON", MOVED_TIME="2026-11-05T10:00:00+05:00"))
    by = client.get("/api/head/closing", headers=hdr(1000)).json()["bypass"]
    assert [(x["deal_id"], x["moved_by"]) for x in by] == [(1800, "Тимур Жандосов")]
    ps = client.get("/api/head/closing/1800", headers=hdr(1000)).json()
    assert ps["bypass"] and not ps["frozen"]
    # HEAD принял закрытие мимо паспорта: в Битрикс ничего не пишем, паспорт сохраняем
    r = client.post("/api/head/closing/1800/close", headers=hdr(1000)).json()
    assert r["via"] == "bitrix" and r["bx"] == "skip" and not calls
    assert client.get("/api/head/closing", headers=hdr(1000)).json()["bypass"] == []
    # ещё одна такая — HEAD вернул: сделка назад на «Оплата+закрывающие документы»
    monkeypatch.setitem(DEALS, "1802", deal(1802, stage="WON", MOVED_TIME="2026-11-12T11:00:00+05:00"))
    client.post("/api/head/closing/1802/return", json={"reason": "закрытие — через паспорт"}, headers=hdr(1000))
    assert [p["fields"] for m, p in calls if m == "crm.deal.update"] == [{"STAGE_ID": "UC_BMKDS4"}]

    # «Без документов»: договор, счёт и АВР не нужны
    monkeypatch.setitem(DEALS, "1900", deal(1900, MYCOMPANY_ID="2071", **{F_CONTRACT: None, F_INV: None, F_ACTS: None}))
    st = client.get("/api/bx/deals/1900/close", headers=hdr(6000)).json()
    docs = {x["key"]: x for x in st["checks"] if x["key"] in ("contract", "invoice", "act")}
    assert all(x["ok"] and x["skip"] for x in docs.values()) and st["myco"].startswith("Без документов")
    monkeypatch.setitem(DEALS, "1901", deal(1901, **{F_CONTRACT: None}))
    assert "contract" in keys(client.get("/api/bx/deals/1901/close", headers=hdr(6000)).json())
    # тестовая сделка — не закрываем
    monkeypatch.setitem(DEALS, "1409", deal(1409, TITLE="ТЕСТ ARTGAME — ДОКУМЕНТЫ — НЕ КЛИЕНТ"))
    assert client.post("/api/bx/deals/1409/close", headers=hdr(6000)).status_code == 400
    assert client.post("/api/head/closing/1409/close", headers=hdr(1000)).status_code == 400
