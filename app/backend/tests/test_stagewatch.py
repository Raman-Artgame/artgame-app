"""Стадии двигаются только из приложения (HEAD 25.11): переход в Битриксе мимо приложения — МОП сводкой за проход,
HEAD одной сводкой за день; первый проход только запоминает старые смены."""
from datetime import datetime
from zoneinfo import ZoneInfo

from artgame import bx, db, notify
from artgame.config import settings
from conftest import hdr
from test_bx import bxc  # noqa: F401

TZ = ZoneInfo("Asia/Almaty")


def mv(i, by, stage="UC_VCP4VO"):
    return {"ID": str(i), "TITLE": f"{i} · ОБЪЕКТ", "STAGE_ID": stage, "MOVED_TIME": f"2026-11-25T10:{i % 60:02d}:00+05:00",
            "MOVED_BY_ID": str(by), "ASSIGNED_BY_ID": "4565"}


def test_stage_outside(bxc, monkeypatch):
    c, ids = bxc
    c.post(f"/api/people/{ids[6000]}", json={"bitrix_user_id": 4565}, headers=hdr(1000))
    rows = [mv(977, 4565), mv(1661, 4565), mv(1602, 1)]
    monkeypatch.setattr(bx, "read_all", lambda m, p, fresh=False: rows)
    monkeypatch.setattr(bx, "users", lambda: [{"id": 4565, "name": "Ануар"}])
    monkeypatch.setattr(bx, "stages", lambda: {"UC_VCP4VO": {"name": "Отложено"}})
    sent = []
    monkeypatch.setattr(notify, "SEND", lambda tg, text: sent.append((tg, text)))
    noon = datetime(2026, 11, 25, 12, 0, tzinfo=TZ)
    assert notify.stage_outside(noon) == 0                          # без вебхука не знаем, кто «приложение»
    monkeypatch.setattr(settings, "bitrix_webhook", "https://x.bitrix24.kz/rest/1/key/")
    assert notify.app_bx_user() == 1
    assert notify.stage_outside(noon) == 0 and sent == []           # первый проход: старые смены только запоминаем
    assert notify.stage_outside(noon) == 0 and sent == []           # ничего нового
    rows += [mv(1385, 4565), mv(1425, 4565), mv(1700, 1)]
    assert notify.stage_outside(noon) == 1                          # МОП — одно сообщение на обе сделки, HEAD днём молчит
    assert sent[0][0] == 6000 and "№ 1385" in sent[0][1] and "№ 1425" in sent[0][1] and "977" not in sent[0][1] and "1700" not in sent[0][1]
    assert "Ануар → «Отложено»" in sent[0][1]
    assert notify.stage_outside(noon) == 0                          # повторно не шлём
    ev = datetime(2026, 11, 25, 20, 5, tzinfo=TZ)
    with db.pool.connection() as conn:                               # журнал пишет текущую дату — подгоняем под «день» теста
        conn.execute("UPDATE audit_log SET at = %s WHERE action='stage_outside'", (ev,))
    sent.clear()
    assert notify.stage_outside(ev) == 1                            # вечером HEAD — одна сводка только по новым
    assert sent[0][0] == 1000 and "За день 2 смен" in sent[0][1] and "977" not in sent[0][1]
    assert notify.stage_outside(datetime(2026, 11, 25, 20, 30, tzinfo=TZ)) == 0   # раз в день
