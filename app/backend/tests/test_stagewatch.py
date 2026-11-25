"""Стадии двигаются только из приложения (HEAD 25.11): переход, сделанный в Битриксе мимо приложения, — сообщение МОП и HEAD."""
from datetime import datetime
from zoneinfo import ZoneInfo

from artgame import bx, db, notify
from artgame.config import settings
from conftest import hdr
from test_bx import bxc  # noqa: F401

TZ = ZoneInfo("Asia/Almaty")


def test_stage_outside(bxc, monkeypatch):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    rows = [{"ID": "1601", "TITLE": "1601 · КАФЕ", "STAGE_ID": "UC_AV00QK", "MOVED_TIME": "2026-11-25T10:00:00+05:00", "MOVED_BY_ID": "4565", "ASSIGNED_BY_ID": "4565"},
            {"ID": "1602", "TITLE": "1602 · ШКОЛА", "STAGE_ID": "PREPARATION", "MOVED_TIME": "2026-11-25T10:05:00+05:00", "MOVED_BY_ID": "1", "ASSIGNED_BY_ID": "4565"}]
    monkeypatch.setattr(bx, "read_all", lambda m, p, fresh=False: rows)
    monkeypatch.setattr(bx, "users", lambda: [{"id": 4565, "name": "Ануар"}])
    monkeypatch.setattr(bx, "stages", lambda: {"UC_AV00QK": {"name": "Договор подписан"}})
    sent = []
    monkeypatch.setattr(notify, "SEND", lambda tg, text: sent.append((tg, text)))
    noon = datetime(2026, 11, 25, 12, 0, tzinfo=TZ)
    assert notify.stage_outside(noon) == 0                         # без вебхука не знаем, кто «приложение»
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    assert notify.app_bx_user() == 1
    assert notify.stage_outside(datetime(2026, 11, 25, 23, 0, tzinfo=TZ)) == 0   # ночью молчим
    assert notify.stage_outside(noon) == 2                          # 1601 руками: МОП и HEAD; 1602 — из приложения, молчим
    assert {tg for tg, _ in sent} == {6000, 1000}
    assert "№ 1601" in sent[0][1] and "Ануар → «Договор подписан»" in sent[0][1] and "1602" not in sent[0][1]
    assert notify.stage_outside(noon) == 0                          # один раз
    with db.pool.connection() as conn:
        a = conn.execute("SELECT * FROM audit_log WHERE action='stage_outside'").fetchall()
    assert len(a) == 1 and str(a[0]["entity_id"]) == "1601"
