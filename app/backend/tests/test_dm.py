"""«Чат» (HEAD 11.11): Объявления, «Руководство» (все HEAD), личный чат с каждым HEAD (видят двое); в бот — только объявления."""
from conftest import hdr
from test_production import VALS, Copying, team  # noqa: F401

from artgame import dm, tgbot


def _second_head(client):
    pid = client.post("/api/register", json={"full_name": "Алина"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "head"}, headers=hdr(1000))
    return pid


def test_rooms_and_privacy(client, team, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)) or 900 + len(sent))
    alina = _second_head(client)
    raman = client.get("/api/me", headers=hdr(1000)).json()["id"]
    rooms = client.get("/api/dm/rooms", headers=hdr(2000)).json()["rooms"]
    assert [r["key"] for r in rooms] == ["news", "group", f"head:{raman}", f"head:{alina}"]
    # сотрудник пишет лично Раману и в «Руководство»
    assert client.post(f"/api/dm/room/head:{raman}", json={"text": "Лично Раману"}, headers=hdr(2000)).status_code == 200
    client.post("/api/dm/room/group", json={"text": "Не грузится фото"}, headers=hdr(2000))
    assert client.post("/api/dm/room/news", json={"text": "x"}, headers=hdr(2000)).status_code == 400
    assert sent == []                                                                          # в бот ничего
    # Раман: личное + руководство; Алина: только руководство
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 2}
    assert client.get("/api/dm/unread", headers=hdr(6000)).json() == {"n": 1}
    ta = client.get("/api/dm/threads", headers=hdr(6000)).json()
    assert [g["last_text"] for g in ta["group"]] == ["Не грузится фото"]
    assert all(x["last_text"] is None for x in ta["items"])                                    # личное Рамана Алине не видно
    d = client.get(f"/api/dm/with/{team[2000]}?room=me", headers=hdr(6000)).json()
    assert d["items"] == []
    # Алина отвечает в «Руководстве» — Раман видит её ответ, руководство прочитано у обоих
    client.post(f"/api/dm/with/{team[2000]}?room=group", json={"text": "Посмотрим сегодня"}, headers=hdr(6000))
    g = client.get(f"/api/dm/with/{team[2000]}?room=group", headers=hdr(1000)).json()["items"]
    assert [(x["author"], x["text"]) for x in g] == [("P2000", "Не грузится фото"), ("Алина", "Посмотрим сегодня")]
    assert client.get("/api/dm/unread", headers=hdr(6000)).json() == {"n": 0}
    # Раман отвечает лично
    tr = client.get("/api/dm/threads", headers=hdr(1000)).json()
    assert tr["items"][0]["id"] == team[2000] and tr["items"][0]["unread"] == 1
    client.post(f"/api/dm/with/{team[2000]}", json={"text": "Лично в ответ"}, headers=hdr(1000))
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 0}
    # у сотрудника: 2 непрочитанных (руководство + лично), чтение по комнате
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 2}
    me = client.get(f"/api/dm/room/head:{raman}", headers=hdr(2000)).json()["items"]
    assert [x["text"] for x in me] == ["Лично Раману", "Лично в ответ"]
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 1}
    assert client.get(f"/api/dm/room/head:{alina}", headers=hdr(2000)).json()["items"] == []
    assert client.get("/api/dm/room/head:999999", headers=hdr(2000)).status_code == 404
    assert client.get("/api/dm/threads", headers=hdr(2000)).status_code == 403                 # чужое — только HEAD
    # Алина делает объявление — в бот и в «Объявления» всем, подпись автора
    b = client.post("/api/dm/broadcast", json={"text": "Сбор в 9"}, headers=hdr(6000)).json()
    assert b["sent"] == 3 and sorted(x[0] for x in sent) == [2000, 3000, 5000] and "Алина" in sent[0][1]
    news = client.get("/api/dm/room/news", headers=hdr(3000)).json()["items"]
    assert [(x["author"], x["text"], x["broadcast"]) for x in news] == [("Алина", "Сбор в 9", True)]
    assert client.get(f"/api/dm/room/head:{alina}", headers=hdr(3000)).json()["items"] == []   # объявление — не личный чат
    b = client.post("/api/dm/broadcast", json={"text": "Собрание", "roles": ["lead_artist"]}, headers=hdr(1000)).json()
    assert b["sent"] == 1
    assert client.post("/api/dm/broadcast", json={"text": "x", "roles": ["mop"]}, headers=hdr(1000)).status_code == 409
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["dm"]["unread"] == 0


def test_feedback_all_heads(client, team):  # noqa: F811
    _second_head(client)
    client.post("/api/feedback", json={"kind": "bug", "text": "Не грузится фото"}, headers=hdr(2000))
    for h in (1000, 6000):
        assert [f["text"] for f in client.get("/api/head/pulse", headers=hdr(h)).json()["feedback"]] == ["Не грузится фото"]
        assert client.get("/api/feedback", headers=hdr(h)).status_code == 200


def test_from_telegram(client, team, monkeypatch):  # noqa: F811
    bot = []
    monkeypatch.setattr(tgbot, "CALL", lambda m, **p: bot.append((m, p)))
    h = {"X-Telegram-Bot-Api-Secret-Token": tgbot.hook_secret()}
    up = lambda chat, text: {"message": {"chat": {"id": chat, "type": "private"}, "from": {"first_name": "T"}, "text": text}}  # noqa: E731
    client.post("/api/tg/hook", json=up(5000, "Краска закончилась"), headers=h)               # сотрудник → «Руководство»
    assert bot[-1][1]["text"].startswith("✓ Передал руководству")
    g = client.get("/api/dm/room/group", headers=hdr(5000)).json()["items"]
    assert [(x["text"], x["via"]) for x in g] == [("Краска закончилась", "tg")]
    client.post("/api/tg/hook", json=up(1000, "просто так"), headers=h)                        # HEAD — подсказка
    assert "в приложении" in bot[-1][1]["text"]
    client.post("/api/tg/hook", json=up(5000, "/start"), headers=h)
    assert bot[-1][0] == "sendPhoto"
    client.post("/api/tg/hook", json=up(777, "кто я"), headers=h)
    assert bot[-1][0] == "sendPhoto"
