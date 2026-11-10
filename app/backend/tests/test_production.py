"""Правки HEAD 08.11: смена по шагам (фото до/после, «что сделал»), условия объекта из сделки, траты саппорта,
«Продакшн» (Отчёты → утверждение HEAD → Продакшн), рилс в ФОТ по pay.reels / pay.reels.max."""
import uuid
from datetime import date

import pytest
from psycopg.types.json import Jsonb

from artgame import db, drive
from conftest import hdr
from test_files import JPEG, FakeDrive

T0, T1 = "2026-11-04T09:00:00+05:00", "2026-11-04T19:00:00+05:00"
VALS = {"pay.support.shift": 10000, "pay.chief.shift": 20000, "shift.hours": 10, "norm.mural.medium": 10, "norm.k.height": "0,8",
        "norm.k.outdoor": "0,9", "norm.k.surface": "0,85", "norm.role.support": "0,5", "pay.reels": 5000, "pay.reels.max": 2}


class Copying(FakeDrive):
    def copy(self, fid, parent, name=None):
        i = self._id()
        FakeDrive.store[i] = {**FakeDrive.store[fid], "parents": [parent]}
        return i


@pytest.fixture
def team(client, monkeypatch):
    FakeDrive.store = {}
    monkeypatch.setattr(drive, "Drive", Copying)
    with db.pool.connection() as c:
        c.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)",
                  ("t", Jsonb({k: {"value": str(v), "status": "Утверждено", "who": "head"} for k, v in VALS.items()})))
        # МОП заполнил сделку: сложность «Средний», в расчёте — высота и сложная поверхность
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address) "
                  "VALUES (731, 'Кафе', 'Астана', 'UC_AV00QK', 'medium', 60, 'Мангилик Ел 1')")
        c.execute("INSERT INTO deal_calc (deal_id, data) VALUES (731, %s)",
                  (Jsonb({"in": {"service": "mural", "level": "medium", "extras": ["height"], "outdoor": False, "surface": True}}),))
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    ids = {}
    for tg, role, zones in [(2000, "support", ["mural"]), (3000, "lead_artist", ["mural"]), (5000, "artist", ["mural"])]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": zones}, headers=hdr(1000))
        ids[tg] = pid
    return ids


def test_shift_in_steps_with_deal_conditions(client, team):
    promo = client.get("/api/work/object/731", headers=hdr(2000)).json()
    assert promo["complexity"] == "medium" and promo["at_height"] and promo["hard_surface"] and not promo["outdoor"]
    assert promo["address"] == "Мангилик Ел 1" and promo["area"] == 60
    assert promo["plan_m2"] == round(10 * 0.8 * 0.85 * 0.5, 2)        # норма саппорта на смену по условиям сделки
    uid = str(uuid.uuid4())
    start = {"client_uid": uid, "object_id": 731, "zone_code": "mural", "started_at": T0, "photo_before": JPEG}
    s = client.post("/api/shifts/start", json=start, headers=hdr(2000)).json()
    assert s["status"] == "open" and s["photo_before"] and s["photo_before_url"]
    assert client.post("/api/shifts/start", json=start, headers=hdr(2000)).json()["id"] == s["id"]   # повтор очереди
    again = {**start, "client_uid": str(uuid.uuid4())}
    assert client.post("/api/shifts/start", json=again, headers=hdr(2000)).status_code == 409       # уже идёт
    assert client.get("/api/shifts/open", headers=hdr(2000)).json()["shift"]["id"] == s["id"]
    assert client.get("/api/work/object/731", headers=hdr(5000)).json()["now"] == ["P2000"]
    assert client.get("/api/review", headers=hdr(3000)).json()["shifts"] == []                      # открытая — не на проверке
    fin = {"client_uid": uid, "ended_at": T1, "area_m2": 3.4, "work_done": "Загрунтовал и разметил стену", "photo_after": JPEG}
    assert client.post("/api/shifts/finish", json={**fin, "work_done": ""}, headers=hdr(2000)).status_code == 422
    f = client.post("/api/shifts/finish", json=fin, headers=hdr(2000)).json()
    assert f["status"] == "submitted" and f["complexity"] == "medium" and f["at_height"] and f["hard_surface"]
    assert float(f["plan_m2"]) == 3.4 and float(f["kpd"]) == 1.0
    assert client.post("/api/shifts/finish", json=fin, headers=hdr(2000)).json()["id"] == s["id"]  # повтор — без изменений
    r = client.get("/api/review", headers=hdr(3000)).json()["shifts"]
    assert r[0]["work_done"] == "Загрунтовал и разметил стену" and r[0]["photo_after_url"]
    # фото легли в МЕДИА / Отчёты сделки
    assert {v["parents"][0] for v in FakeDrive.store.values()} == {"deal-731/МЕДИА/Отчёты"}
    # старый способ: сложность с телефона перекрывается сделкой
    old = client.post("/api/shifts", json={"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "started_at": T0,
                                           "ended_at": T1, "complexity": "easy"}, headers=hdr(5000)).json()
    assert old["complexity"] == "medium" and old["at_height"]


def test_support_expense_categories(client, team):
    cats = {c["code"] for c in client.get("/api/work/dict", headers=hdr(2000)).json()["categories"]}
    assert cats == {"transport", "purchase"}
    assert "paint" in {c["code"] for c in client.get("/api/work/dict", headers=hdr(5000)).json()["categories"]}
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "category": "paint", "amount": 1000}
    assert client.post("/api/expenses", json=body, headers=hdr(2000)).status_code == 400
    assert client.post("/api/expenses", json={**body, "category": "purchase"}, headers=hdr(2000)).status_code == 200


def upload(client, tg, mt, name="a.mp4"):
    r = client.post("/api/objects/731/uploads", json={"client_uid": str(uuid.uuid4()), "kind": "media", "media_type": mt, "name": name,
                                                      "mime": "video/mp4", "size": 5}, headers=hdr(tg))
    if r.status_code != 200:
        return r
    fid = f"drvM{uuid.uuid4().hex[:8]}"
    FakeDrive.store[fid] = {"parents": [FakeDrive.pending[0]], "size": "5", "mimeType": "video/mp4", "data": b"12345"}
    return client.post(f"/api/files/{r.json()['file_id']}/done", json={"drive_id": fid}, headers=hdr(tg))


def test_production_review_and_reels_pay(client, team):
    assert upload(client, 5000, "reels").status_code == 403                 # художник — без «Продакшна»
    assert upload(client, 3000, "bad").status_code == 400
    got = [upload(client, 3000, "reels").json() for _ in range(3)] + [upload(client, 3000, "video").json()]
    assert all(g["review"] == "pending" for g in got) and FakeDrive.pending[0] == "deal-731/МЕДИА/Отчёты"   # последнее — видео
    assert sum(v["parents"] == ["deal-731/МЕДИА/Рилс"] for v in FakeDrive.store.values()) == 3          # рилс — в «МЕДИА / Рилс» (HEAD 10.11)
    assert client.get("/api/media?scope=review", headers=hdr(3000)).status_code == 403
    assert len(client.get("/api/media?scope=review", headers=hdr(1000)).json()["items"]) == 4
    assert client.get("/api/media?scope=object&object_id=731", headers=hdr(2000)).json()["items"] == []   # саппорт видит только утверждённое
    assert client.post(f"/api/media/{got[0]['id']}/review", json={"approve": True}, headers=hdr(3000)).status_code == 403
    assert client.post(f"/api/media/{got[3]['id']}/review", json={"approve": False}, headers=hdr(1000)).status_code == 400
    for g in got[:3]:
        assert client.post(f"/api/media/{g['id']}/review", json={"approve": True}, headers=hdr(1000)).json()["ok"]
    client.post(f"/api/media/{got[3]['id']}/review", json={"approve": False, "note": "темно"}, headers=hdr(1000))
    assert sum(v["parents"] == ["deal-731/МЕДИА/Продакшн"] for v in FakeDrive.store.values()) == 3
    mine = client.get("/api/media?scope=mine", headers=hdr(3000)).json()
    assert mine["reels"] == {"rate": 5000, "max": 2} and {x["review"] for x in mine["items"]} == {"approved", "rejected"}
    assert len(client.get("/api/media?scope=object&object_id=731", headers=hdr(2000)).json()["items"]) == 3
    # ФОТ месяца: 3 утверждённых рилс, в месяц оплачиваются до 2
    ym = date.today().strftime("%Y-%m")
    out = client.post(f"/api/fin/payroll/{ym}/compute", headers=hdr(1000)).json()
    lines = {r["name"]: {(l["kind"], float(l["amount"])) for l in r["lines"]} for r in out["rows"]}
    assert ("reels", 10000.0) in lines["P3000"]
    assert {"label": "Рилс после утверждения HEAD (до 2 в месяц)", "amount": 5000} in client.get("/api/fin/my", headers=hdr(3000)).json()["rate"]
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["media"] == 0


def test_reels_flag_any_person(client, team):
    """HEAD 09.11: «Оплачиваемые рилс» любому человеку (напр. Глебу) — «Продакшн» и рилс в оплату."""
    assert upload(client, 5000, "reels").status_code == 403
    assert client.post(f"/api/people/{team[5000]}", json={"reels": True}, headers=hdr(1000)).json()["reels"] is True
    assert client.get("/api/me", headers=hdr(5000)).json()["reels"] is True
    assert upload(client, 5000, "reels").json()["review"] == "pending"
    assert client.get("/api/media?scope=mine", headers=hdr(5000)).json()["reels"] == {"rate": 5000, "max": 2}
    assert any(x["label"].startswith("Рилс") for x in client.get("/api/fin/my", headers=hdr(5000)).json()["rate"])
    client.post(f"/api/people/{team[5000]}", json={"reels": False}, headers=hdr(1000))
    assert upload(client, 5000, "reels").status_code == 403


def test_designer_media_library(client, team):
    """HEAD 10.11: Главный дизайнер видит в «Продакшн → Медиа» видео всех объектов (кроме возвращённых) и сдаёт рилс HEAD."""
    pid = client.post("/api/register", json={"full_name": "Дизайнер"}, headers=hdr(7000)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "lead_designer", "zones": ["design"]}, headers=hdr(1000))
    v1, v2 = upload(client, 3000, "video").json(), upload(client, 3000, "video").json()
    upload(client, 3000, "photo")
    client.post(f"/api/media/{v2['id']}/review", json={"approve": False, "note": "темно"}, headers=hdr(1000))
    lib = client.get("/api/media?scope=library&type=video", headers=hdr(7000)).json()["items"]
    assert [x["id"] for x in lib] == [v1["id"]] and lib[0]["url"]
    assert client.get("/api/media?scope=library", headers=hdr(5000)).status_code == 403   # художнику — нет
    r = upload(client, 7000, "reels").json()
    assert r["review"] == "pending"
    assert r["id"] in {x["id"] for x in client.get("/api/media?scope=review", headers=hdr(1000)).json()["items"]}
