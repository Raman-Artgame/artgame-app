"""Задним числом с 1.11 (HEAD 09.11): «Прошлая смена» и расход с датой — на проверку, с пометкой; окно — из настроек."""
import uuid
from datetime import date, timedelta

from artgame import db
from artgame.config import settings
from conftest import hdr
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401


def test_past_shift_and_expense(client, team, monkeypatch):  # noqa: F811
    y = date.today() - timedelta(days=1)
    monkeypatch.setattr(settings, "backfill_from", (y - timedelta(days=5)).isoformat())
    monkeypatch.setattr(settings, "backfill_until", date.today().isoformat())
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage, status) VALUES (732, 'Сдан', 'Астана', 'WON', 'done')")
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage, status) VALUES (733, 'Снова в работе', 'Астана', 'UC_AV00QK', 'active')")
    d = client.get("/api/work/dict", headers=hdr(5000)).json()["backfill"]
    assert d["open"] and {o["id"] for o in d["objects"]} == {731, 733}   # только «Выполнение проекта»
    body = {"client_uid": str(uuid.uuid4()), "object_id": 732, "zone_code": "mural", "day": y.isoformat(), "hours": 8,
            "area_m2": 6.5, "work_done": "Фон и контур"}
    s = client.post("/api/shifts/past", json={**body, "photo_after": JPEG}, headers=hdr(5000)).json()
    assert s["status"] == "submitted" and s["backfill"] and s["role_code"] == "artist" and s["photo_after"]
    assert client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4())}, headers=hdr(5000)).status_code == 409
    assert client.post("/api/shifts/past", json={**body, "client_uid": str(uuid.uuid4()), "day": date.today().isoformat()},
                       headers=hdr(5000)).status_code == 400
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
