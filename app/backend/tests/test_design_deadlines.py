"""HEAD 28.11: сроки заданий дизайнеров — срок обязателен, бот напоминает каждое утро, просрочка видна на Пульте."""
from datetime import datetime
from zoneinfo import ZoneInfo

from artgame import db, notify
from conftest import hdr
from test_cabinets import dz  # noqa: F401

TZ = ZoneInfo("Asia/Almaty")


def test_design_deadlines(client, dz, monkeypatch):  # noqa: F811
    ids, _ = dz
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"], "bitrix_user_id": 4565}, headers=hdr(1000))
    a = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Столовая", "deadline": "2026-12-04"}, headers=hdr(6000)).json()
    b = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Спортзал", "deadline": "2026-12-06"}, headers=hdr(6000)).json()
    client.post(f"/api/design/tasks/{a['id']}", json={"stage": "work"}, headers=hdr(7100))
    # срок убрать нельзя, поменять можно
    assert client.post(f"/api/design/tasks/{a['id']}", json={"deadline": None}, headers=hdr(7100)).status_code == 400
    sent = []
    monkeypatch.setattr(notify, "SEND", lambda tg, text: sent.append((tg, text)))
    at = lambda d, h: datetime(2026, 12, d, h, 0, tzinfo=TZ)  # noqa: E731
    assert notify.design_deadlines(at(3, 8)) == 0            # до 9:00 молчим
    assert notify.design_deadlines(at(2, 10)) == 0           # до срока два дня — рано
    assert notify.design_deadlines(at(3, 10)) == 1 and sent[-1][0] == 7100 and "Срок завтра" in sent[-1][1] and "Столовая" in sent[-1][1]
    assert notify.design_deadlines(at(3, 12)) == 0           # раз в день
    assert notify.design_deadlines(at(4, 10)) == 1 and "Срок сегодня" in sent[-1][1]
    # просрочено: своё — дизайнеру, неразобранное — Главному дизайнеру
    sent.clear()
    assert notify.design_deadlines(at(7, 10)) == 2
    txt = dict(sent)
    assert "Просрочено" in txt[7100] and "3 дн." in txt[7100] and "Спортзал" in txt[7000] and "1 дн." in txt[7000]
    # «ждём клиента» дизайнеру не горит; МОП — раз в 3 дня
    client.post(f"/api/design/tasks/{a['id']}", json={"stage": "wait"}, headers=hdr(7100))
    with db.pool.connection() as c:
        c.execute("UPDATE design_tasks SET updated_at = %s WHERE id=%s", (at(4, 10), a["id"]))
    sent.clear()
    assert notify.design_deadlines(at(8, 10)) == 2           # Главному про «Спортзал» и МОП про ожидание
    txt = dict(sent)
    assert "ждёт клиента" in txt[6000] and "Столовая" in txt[6000] and 7100 not in txt
    assert notify.design_deadlines(at(8, 11)) == 0
    assert notify.design_deadlines(at(10, 10)) == 2          # 6 дней ожидания — второе напоминание МОП
    # Пульт HEAD: просроченные списком
    with db.pool.connection() as c:
        c.execute("UPDATE design_tasks SET deadline = current_date - 2 WHERE id=%s", (b["id"],))
    late = client.get("/api/head/pulse", headers=hdr(1000)).json()["design_late"]
    assert [x["id"] for x in late] == [1601] and "Спортзал" in late[0]["title"] and "без дизайнера" in late[0]["title"]
