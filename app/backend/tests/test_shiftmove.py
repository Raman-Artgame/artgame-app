"""HEAD 14.11: смена «Прошлой смены» записана не на тот объект — HEAD переносит смену и её фото (база и Диск), ничего не удаляя."""
import uuid
from datetime import timedelta

from artgame import db
from artgame.config import settings
from conftest import hdr
from test_backfill import _today
from test_files import JPEG, FakeDrive
from test_production import Copying, team  # noqa: F401


class Moving(Copying):
    def move(self, fid, parent):
        FakeDrive.store[fid]["parents"] = [parent]


def test_move_shift(client, team, monkeypatch):  # noqa: F811
    from artgame import drive
    monkeypatch.setattr(drive, "Drive", Moving)
    y = _today() - timedelta(days=1)
    monkeypatch.setattr(settings, "backfill_from", (y - timedelta(days=5)).isoformat())
    monkeypatch.setattr(settings, "backfill_until", _today().isoformat())
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage, status) VALUES (733, 'Енот', 'Астана', 'UC_AV00QK', 'active')")
    body = {"client_uid": str(uuid.uuid4()), "object_id": 731, "zone_code": "mural", "day": y.isoformat(), "hours": 8, "work_done": "Енот"}
    s = client.post("/api/shifts/past", json={**body, "photo_after": JPEG}, headers=hdr(5000)).json()
    client.post(f"/api/shifts/{s['id']}/photos", json={"client_uid": str(uuid.uuid4()), "photo": JPEG}, headers=hdr(5000))
    assert client.post(f"/api/shifts/{s['id']}/move", json={"object_id": 733}, headers=hdr(5000)).status_code == 403
    assert client.post(f"/api/shifts/{s['id']}/move", json={"object_id": 731}, headers=hdr(1000)).status_code == 400
    r = client.post(f"/api/shifts/{s['id']}/move", json={"object_id": 733}, headers=hdr(1000)).json()
    assert r["ok"] and r["files"] == 2
    with db.pool.connection() as c:
        assert c.execute("SELECT object_id FROM shifts WHERE id=%s", (s["id"],)).fetchone()["object_id"] == 733
        fs = c.execute("SELECT object_id, drive_id FROM files WHERE kind='photo' AND object_id IN (731, 733)").fetchall()
        assert {f["object_id"] for f in fs} == {733}
        assert c.execute("SELECT count(*) AS n FROM audit_log WHERE action='shift_move'").fetchone()["n"] == 1
    assert all("deal-733" in FakeDrive.store[f["drive_id"]]["parents"][0] for f in fs)
    assert any(o["id"] == 733 for o in client.get("/api/head/move-targets", headers=hdr(1000)).json())


def test_move_loose_photos(client, team, monkeypatch):  # noqa: F811
    from artgame import drive
    monkeypatch.setattr(drive, "Drive", Moving)
    with db.pool.connection() as c:
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage, status) VALUES (734, 'Дастархан', 'Астана', 'UC_AV00QK', 'active')")
    ids = [client.post("/api/objects/731/photos", json={"client_uid": str(uuid.uuid4()), "data": JPEG}, headers=hdr(5000)).json()["id"] for _ in range(3)]
    assert client.post(f"/api/files/{ids[0]}/move", json={"object_id": 734}, headers=hdr(5000)).status_code == 403
    r = client.post(f"/api/files/{ids[0]}/move", json={"object_id": 734, "same_day": True}, headers=hdr(1000)).json()
    assert r["files"] == 3
    with db.pool.connection() as c:
        assert {x["object_id"] for x in c.execute("SELECT object_id FROM files WHERE id = ANY(%s)", (ids,)).fetchall()} == {734}
