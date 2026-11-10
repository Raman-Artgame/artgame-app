"""Задним числом с 1.11 (HEAD 09.11): «Прошлая смена» и расход с датой — на проверку, с пометкой; окно — из настроек."""
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def _today() -> date:   # дата по Алматы, как у сервера (после 19:00 UTC в Алматы уже завтра)
    return datetime.now(ZoneInfo("Asia/Almaty")).date()

from artgame import db
from artgame.config import settings
from conftest import hdr
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401


def test_past_shift_and_expense(client, team, monkeypatch):  # noqa: F811
    y = _today() - timedelta(days=1)
    monkeypatch.setattr(settings, "backfill_from", (y - timedelta(days=5)).isoformat())
    monkeypatch.setattr(settings, "backfill_until", _today().isoformat())
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage, status) VALUES (732, 'Сдан', 'Астана', 'WON', 'done')")
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage, status) VALUES (733, 'Снова в работе', 'Астана', 'UC_AV00QK', 'active')")
    d = client.get("/api/work/dict", headers=hdr(5000)).json()["backfill"]
    assert d["open"] and {o["id"] for o in d["objects"]} == {731, 733}   # только «Выполнение проекта»
    # HEAD 10.11: сделку по ошибке перенесли с «Выполнения» — задним числом её видно, пока открыт срок
    from artgame import sync_objects
    with db.pool.connection() as c:
        sync_objects.upsert(c, [{"ID": "733", "TITLE": "733 · Снова в работе — Астана", "STAGE_ID": "WON", "CATEGORY_ID": "0"}])
    d = client.get("/api/work/dict", headers=hdr(5000)).json()
    assert 733 in {o["id"] for o in d["backfill"]["objects"]} and 733 not in {o["id"] for o in d["objects"]}
    with db.pool.connection() as c:
        sync_objects.upsert(c, [{"ID": "733", "TITLE": "733 · Снова в работе — Астана", "STAGE_ID": "UC_AV00QK", "CATEGORY_ID": "0"}])
    body = {"client_uid": str(uuid.uuid4()), "object_id": 732, "zone_code": "mural", "day": y.isoformat(), "hours": 8,
            "area_m2": 6.5, "work_done": "Фон и контур"}
    s = client.post("/api/shifts/past", json={**body, "photo_after": JPEG}, headers=hdr(5000)).json()
    assert s["status"] == "submitted" and s["backfill"] and s["role_code"] == "artist" and s["photo_after"]
    # сколько угодно фото — по одному (HEAD 09.11)
    for _ in range(3):
        r = client.post(f"/api/shifts/{s['id']}/photos", json={"client_uid": str(uuid.uuid4()), "photo": JPEG}, headers=hdr(5000)).json()
    assert r["count"] == 3
    assert client.post(f"/api/shifts/{s['id']}/photos", json={"client_uid": str(uuid.uuid4()), "photo": JPEG}, headers=hdr(2000)).status_code == 404
    mine = next(x for x in client.get("/api/my", headers=hdr(5000)).json()["shifts"] if x["id"] == s["id"])
    assert len(mine["photos"]) == 3
    assert client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4())}, headers=hdr(5000)).status_code == 409
    # сегодня (HEAD 10.11): ещё идущую смену — нельзя, с понятным текстом; уже закончившуюся — можно
    r = client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4()), "day": _today().isoformat(), "start_time": "23:59"},
                    headers=hdr(5000))
    assert r.status_code == 400 and "ещё не закончилась" in r.json()["detail"]
    from datetime import datetime as _dt
    from artgame.work import TZ as _TZ
    if _dt.now(_TZ).hour >= 1:   # тест в первый час после полуночи пропускает этот шаг
        ok = client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4()), "day": _today().isoformat(), "start_time": "00:00",
                                                   "hours": 0.5}, headers=hdr(5000))
        assert ok.status_code == 200 and ok.json()["backfill"]
    assert client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4()), "day": (y - timedelta(days=9)).isoformat()},
                       headers=hdr(5000)).status_code == 400
    # проверка видит её у Главного
    rows = client.get("/api/review", headers=hdr(3000)).json()["shifts"]
    assert any(r["id"] == s["id"] and r["backfill"] for r in rows)
    e = client.post("/api/expenses", json={"client_uid": str(uuid.uuid4()), "object_id": 732, "zone_code": "mural", "category": "transport",
                                           "amount": 1500, "receipt": JPEG, "day": y.isoformat()}, headers=hdr(5000)).json()
    assert e["backfill"] and e["created_at"].startswith(y.isoformat())
    # окно закрыто — нельзя
    monkeypatch.setattr(settings, "backfill_until", y.isoformat())
    assert client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4()), "day": (y - timedelta(days=1)).isoformat()},
                       headers=hdr(5000)).status_code == 400


def test_past_shift_long_night(client, team, monkeypatch):  # noqa: F811
    """HEAD 09.11: ночные проекты и смены дольше 16 ч — одной записью до 48 ч, с временем начала (ночь считает ФОТ)."""
    y = _today() - timedelta(days=3)   # 18:00 + 34 ч должно закончиться раньше «сейчас» в любое время суток
    monkeypatch.setattr(settings, "backfill_from", (y - timedelta(days=5)).isoformat())
    monkeypatch.setattr(settings, "backfill_until", _today().isoformat())
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "day": y.isoformat(), "hours": 34,
            "start_time": "18:00", "area_m2": 22, "work_done": "Ночной проект", "photo_after": JPEG}
    s = client.post("/api/shifts/past", json=body, headers=hdr(5000)).json()
    assert s["status"] == "submitted" and s["started_at"].startswith(y.isoformat() + "T13:00")   # 18:00 Алматы = 13:00 UTC
    assert client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4()), "hours": 49}, headers=hdr(5000)).status_code == 422


def test_road_does_not_block_and_fix(client, team, monkeypatch):  # noqa: F811
    """HEAD 09.11 (Ажар): дорога в тот же день не мешает внести смену; проверяющий сам правит время и тип."""
    y = _today() - timedelta(days=2)   # 09:00 + 18 ч — уже закончилась и сразу после полуночи по Алматы
    monkeypatch.setattr(settings, "backfill_from", (y - timedelta(days=5)).isoformat())
    monkeypatch.setattr(settings, "backfill_until", _today().isoformat())
    with db.pool.connection() as c:
        pid = c.execute("SELECT id FROM people WHERE tg_id=5000").fetchone()["id"]
        road = c.execute("""INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, status, kind, trip, work_done)
                            VALUES (gen_random_uuid(), %s, 731, 'mural', %s::date + time '09:00', %s::date + time '19:00', 'submitted', 'road', true, 'Дорога на объект')
                            RETURNING id""", (pid, y, y)).fetchone()["id"]
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "day": y.isoformat(), "hours": 18,
            "start_time": "09:00", "work_done": "Роспись до ночи"}
    s = client.post("/api/shifts/past", json=body, headers=hdr(5000))
    assert s.status_code == 200, s.text
    assert client.post(f"/api/shift/{road}/fix", json={"start_time": "09:00", "hours": 18}, headers=hdr(5000)).status_code == 403   # сам себе — нет
    r = client.post(f"/api/shift/{road}/fix", json={"start_time": "10:30", "hours": 17.5, "kind": "work"}, headers=hdr(1000)).json()
    assert r["kind"] == "work" and "05:30" in r["started_at"]   # 10:30 Алматы

