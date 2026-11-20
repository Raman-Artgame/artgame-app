"""12.11 (Владимир, «drive: TransportError»): сбой связи с Google — сервер повторяет сам, токен не берёт на каждый файл;
не вышло — понятный текст и retry для телефона, смена не создаётся наполовину."""
import uuid
from datetime import timedelta

import httpx
from google.auth.exceptions import TransportError

from artgame import db, drive
from artgame.config import settings
from conftest import hdr
from test_backfill import _today
from test_files import JPEG
from test_production import team  # noqa: F401


def test_retry_then_ok(monkeypatch):
    monkeypatch.setattr(drive.time, "sleep", lambda s: None)
    n = {"k": 0}

    def flaky():
        n["k"] += 1
        if n["k"] < 3:
            raise TransportError("oauth2.googleapis.com unreachable")
        return "ok"
    assert drive._retry(flaky) == "ok" and n["k"] == 3
    n["k"] = -10
    try:
        drive._retry(flaky)
        raise AssertionError
    except TransportError:
        assert n["k"] == -7                                  # 3 попытки и сдаёмся
    bad = httpx.Response(403, request=httpx.Request("GET", "https://x"))
    calls = []
    def http_error():  # noqa: E306
        calls.append(1)
        bad.raise_for_status()
    try:
        drive._retry(http_error)
    except httpx.HTTPStatusError:
        assert len(calls) == 1                               # ответ Google с ошибкой не повторяем


def test_past_shift_drive_down_clear_message(client, team, monkeypatch):  # noqa: F811
    y = _today() - timedelta(days=1)
    monkeypatch.setattr(settings, "backfill_from", (y - timedelta(days=5)).isoformat())
    monkeypatch.setattr(settings, "backfill_until", _today().isoformat())

    def down(*a, **k):
        raise TransportError("timed out")
    monkeypatch.setattr(drive, "save_photo", down)
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "day": y.isoformat(), "start_time": "10:00",
            "hours": 7, "work_done": "Граффити надпись", "photo_after": JPEG}
    r = client.post("/api/shifts/past", json=body, headers=hdr(5000))
    assert r.status_code == 502
    d = r.json()["detail"]
    assert d["retry"] and "Google Диск" in d["message"] and "TransportError" not in d["message"]
    with db.pool.connection() as c:
        assert not c.execute("SELECT 1 FROM shifts WHERE client_uid=%s", (body["client_uid"],)).fetchone()   # не наполовину
