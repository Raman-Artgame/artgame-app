"""МОП вводит всё в приложении (HEAD 25.11): заявка по звонку, клиент и реквизиты, подписанный договор."""
import base64

from artgame import bx, bxw, db, mopcrm
from artgame.config import settings
from conftest import hdr
from test_bx import DEALS, LEADS, bxc, fake  # noqa: F401 — фикстура и подмена Битрикса

SOURCES = [{"STATUS_ID": "CALL", "NAME": "Звонок", "SORT": "10"}, {"STATUS_ID": "3|WZ_WHATSAPP_X", "NAME": "WhatsApp (Wazzup)", "SORT": "20"},
           {"STATUS_ID": "REPEAT_SALE", "NAME": "Сарафан", "SORT": "40"}]


def read(extra_leads=(), extra_contacts=()):
    def r(method, params):
        if method == "crm.status.list" and params["filter"]["ENTITY_ID"] == "SOURCE":
            return {"result": SOURCES}
        if method == "crm.lead.list" and "PHONE" in params["filter"]:
            return {"result": [l for l in extra_leads if params["filter"]["PHONE"] in (l["_p"], l["_p"][-10:])]}
        if method == "crm.contact.list":
            return {"result": [x for x in extra_contacts if params["filter"]["PHONE"] in (x["_p"], x["_p"][-10:])]}
        return fake(method, params)
    return r


def test_norm_phone_and_check():
    assert mopcrm.norm_phone("8 (701) 555-44-33") == "+77015554433"
    assert mopcrm.norm_phone("701 555 44 33") == "+77015554433"
    assert mopcrm.norm_phone("+7 701 555") == ""
    ok = mopcrm.ClientIn(type="ТОО", company="ТОО «Ромашка»", bin="123456789012", bik="caspkzka", iik="KZ12 3456 7890 1234 5678")
    assert mopcrm.check(ok) == []
    bad = mopcrm.ClientIn(type="ТОО", company="", bin="123", bik="X", iik="RU1", phone="12")
    assert mopcrm.check(bad) == ["название компании", "телефон: нужно 10–11 цифр", "БИН: 12 цифр", "БИК банка: 8 знаков", "ИИК: KZ и 18 знаков"]


def test_new_lead(bxc, monkeypatch):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(bx, "READ", read(extra_leads=[{"ID": "3001", "NAME": "Дана", "ASSIGNED_BY_ID": "4565", "_p": "+77015554433"}]))
    bx._cache.clear()
    d = c.get("/api/bx/leads-new/dict", headers=hdr(6000)).json()
    assert [s["id"] for s in d["sources"]] == ["CALL", "REPEAT_SALE"]   # WhatsApp заводит сам канал
    assert d["cities"] == [{"id": "5501", "name": "Астана"}]
    body = {"name": "Айгерим", "phone": "8 701 555 44 33", "city": "5501", "note": "кафе 40 м²"}
    assert c.post("/api/bx/leads-new", json=body, headers=hdr(6000)).status_code == 409   # вебхука нет — запись выключена
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x/rest/1/k/")
    calls = []
    monkeypatch.setattr(bxw, "CALL", lambda m, p: calls.append((m, p)) or {"result": 9200 if m.endswith(".add") else True})
    assert c.post("/api/bx/leads-new", json={**body, "phone": "12"}, headers=hdr(6000)).status_code == 400
    assert c.post("/api/bx/leads-new", json={**body, "source": "3|WZ_WHATSAPP_X"}, headers=hdr(6000)).status_code == 400
    r = c.post("/api/bx/leads-new", json=body, headers=hdr(6000))
    assert r.status_code == 409 and r.json()["detail"]["dups"][0]["id"] == 3001 and not calls   # тот же номер — сначала показать
    r = c.post("/api/bx/leads-new", json={**body, "force": True}, headers=hdr(6000)).json()
    assert r == {"bx": "ok", "lead": 9200}
    m, p = calls[0]
    assert m == "crm.lead.add" and p["fields"]["PHONE"] == [{"VALUE": "+77015554433", "VALUE_TYPE": "WORK"}]
    assert p["fields"]["ASSIGNED_BY_ID"] == 4565 and p["fields"]["SOURCE_ID"] == "CALL" and p["fields"]["UF_CRM_1753202309"] == "5501"
    assert p["fields"]["COMMENTS"] == "кафе 40 м²" and p["fields"]["TITLE"] == "Айгерим — звонок"
    assert calls[1][0] == "crm.timeline.comment.add"
    with db.pool.connection() as conn:
        a = conn.execute("SELECT data FROM audit_log WHERE action='bx_write' AND entity='lead' ORDER BY id DESC LIMIT 1").fetchone()
    assert a["data"]["lead"] == 9200 and a["data"]["bx"] == "ok"
    # в списке лидов — откуда клиент
    monkeypatch.setattr(bx, "READ", read())
    bx._cache.clear()
    LEADS["3001"]["SOURCE_ID"] = "CALL"
    assert c.get("/api/bx/leads", headers=hdr(6000)).json()["leads"][0]["source"] == "Звонок"
    LEADS["3001"]["SOURCE_ID"] = "WEB"


class Crm:
    """Контакт, компания, реквизиты и банк в памяти — как их пишет и читает вебхук."""

    def __init__(self):
        self.contacts = {"2223": {"ID": "2223", "NAME": "Иван", "LAST_NAME": "Петров", "PHONE": [{"ID": "51", "VALUE": "+77010000000"}]}}
        self.companies, self.req, self.bank, self.calls, self.n = {}, {}, {}, [], 700

    def __call__(self, m, p):
        self.calls.append((m, p))
        if m == "crm.contact.get":
            return {"result": self.contacts.get(str(p["id"]))}
        if m == "crm.company.get":
            return {"result": self.companies.get(str(p["id"]))}
        if m == "crm.requisite.list":
            f = p["filter"]
            return {"result": sorted([r for r in self.req.values() if r["ENTITY_TYPE_ID"] == f["ENTITY_TYPE_ID"] and r["ENTITY_ID"] == f["ENTITY_ID"]],
                                     key=lambda r: -int(r["ID"]))}
        if m == "crm.requisite.bankdetail.list":
            return {"result": [b for b in self.bank.values() if b["ENTITY_ID"] == p["filter"]["ENTITY_ID"]]}
        if m.endswith(".add") and m != "crm.timeline.comment.add" and m != "crm.company.contact.add":
            self.n += 1
            row = {"ID": str(self.n), **p["fields"]}
            if m == "crm.company.add":
                row["PHONE"] = [{"ID": "61", **x} for x in p["fields"].get("PHONE", [])]
                self.companies[row["ID"]] = row
            elif m == "crm.requisite.add":
                self.req[row["ID"]] = row
            elif m == "crm.requisite.bankdetail.add":
                self.bank[row["ID"]] = row
            return {"result": self.n}
        if m == "crm.requisite.update":
            self.req[str(p["id"])].update(p["fields"])
        if m == "crm.requisite.bankdetail.update":
            self.bank[str(p["id"])].update(p["fields"])
        if m == "crm.company.update":
            self.companies[str(p["id"])].update({k: v for k, v in p["fields"].items() if k != "PHONE"})
        if m == "crm.contact.update":
            self.contacts[str(p["id"])].update(p["fields"])
        if m == "crm.deal.update":
            DEALS[str(p["id"])].update({k: str(v) for k, v in p["fields"].items()})
        return {"result": True}


def test_client_and_requisites(bxc, monkeypatch):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x/rest/1/k/")
    crm = Crm()
    monkeypatch.setattr(bxw, "CALL", crm)
    keep = dict(DEALS["1651"])
    DEALS["1651"].update(ASSIGNED_BY_ID="4565", CONTACT_ID="2223", COMPANY_ID="0")
    try:
        cl = c.get("/api/bx/deals/1651/client", headers=hdr(6000)).json()
        assert cl["type"] == "Физлицо" and cl["name"] == "Петров Иван" and cl["phone"] == "+77010000000"
        assert c.get("/api/bx/deals/1601/client", headers=hdr(6100)).status_code in (403, 409)   # чужая сделка
        bad = c.post("/api/bx/deals/1651/client", json={"type": "ТОО", "company": "Ромашка", "bin": "12"}, headers=hdr(6000))
        assert bad.status_code == 400 and "БИН" in bad.json()["detail"] and len(crm.calls) == 2
        # физлицо → ТОО с реквизитами и банком: новая компания, привязка к сделке, реквизиты «Юр. лицо», банк
        body = {"type": "ТОО", "company": "ТОО «Ромашка»", "name": "Петров Иван", "phone": "+7 701 000 00 00", "bin": "123456789012",
                "signer": "Сидоров С.С.", "bank": "АО «Kaspi Bank»", "bik": "caspkzka", "iik": "KZ123456789012345678"}
        r = c.post("/api/bx/deals/1651/client", json=body, headers=hdr(6000)).json()
        assert r["done"] == ["новая компания", "новые реквизиты", "банк"], r
        assert DEALS["1651"]["COMPANY_ID"] == "701"
        req = crm.req["702"]
        assert req["PRESET_ID"] == 3 and req["RQ_BIN"] == "123456789012" and req["RQ_CEO_NAME"] == "Сидоров С.С." and req["RQ_CEO_WORK_POS"] == "Директор"
        b = crm.bank["703"]
        assert b["RQ_BIK"] == "CASPKZKA" and b["RQ_IIK"] == b["RQ_ACC_NUM"] == "KZ123456789012345678" and b["ENTITY_ID"] == 702
        assert r["client"]["type"] == "ТОО" and r["client"]["bin"] == "123456789012"
        # договор и счёт читают реквизиты: шлюз их не даёт — берёт вебхук, подписант из RQ_CEO_NAME, ИИК из RQ_IIK
        assert bx.requisites(701) == {"cname": "ТОО «Ромашка»", "cbin": "123456789012", "signer": "Сидоров С.С.",
                                      "cbank": "АО «Kaspi Bank»", "cbik": "CASPKZKA", "ciik": "KZ123456789012345678"}
        # правка: те же реквизиты обновляются, а не плодятся
        crm.calls.clear()
        r = c.post("/api/bx/deals/1651/client", json={**body, "bik": "HSBKKZKX"}, headers=hdr(6000)).json()
        assert "новые реквизиты" not in r["done"] and crm.bank["703"]["RQ_BIK"] == "HSBKKZKX" and len(crm.req) == 1
        assert not any(m == "crm.company.add" for m, _ in crm.calls)
        # ТОО → ИП: у ИП другой пресет — новые реквизиты, название с «ИП»
        r = c.post("/api/bx/deals/1651/client", json={"type": "ИП", "company": "Петров", "bin": "990101300123"}, headers=hdr(6000)).json()
        assert crm.companies["701"]["TITLE"] == "ИП Петров" and r["client"]["type"] == "ИП"
        assert any(x["PRESET_ID"] == 1 and x["RQ_IIN"] == "990101300123" for x in crm.req.values())
        with db.pool.connection() as conn:
            n = conn.execute("SELECT count(*) n FROM audit_log WHERE action='bx_write' AND entity_id='1651' AND data->>'what'='клиент и реквизиты'").fetchone()["n"]
        assert n == 3
    finally:
        DEALS["1651"].clear()
        DEALS["1651"].update(keep)
        bx._cache.clear()


def test_signed_contract(bxc, monkeypatch):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x/rest/1/k/")
    calls = []
    monkeypatch.setattr(bxw, "CALL", lambda m, p: calls.append((m, p)) or {"result": True})
    data = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 signed").decode()
    assert c.post("/api/bx/deals/1601/signed", json={"name": "x.doc", "data": "data:text/plain;base64,eA=="}, headers=hdr(6000)).status_code == 400
    assert c.post("/api/bx/deals/1651/signed", json={"name": "d.pdf", "data": data}, headers=hdr(6000)).status_code == 403   # чужая
    r = c.post("/api/bx/deals/1601/signed", json={"name": "скан договора.pdf", "data": data}, headers=hdr(6000)).json()
    assert r["bx"] == "ok" and r["name"] == "Договор подписанный 1601 скан договора.pdf" and r["drive"] is None   # объекта нет — только сделка
    upd = next(p for m, p in calls if m == "crm.deal.update")
    f = upd["fields"]["UF_CRM_1753202391"]
    assert f[-1]["fileData"][0] == "Договор подписанный 1601 скан договора.pdf"
    assert base64.b64decode(f[-1]["fileData"][1]) == b"%PDF-1.4 signed"
