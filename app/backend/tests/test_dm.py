"""«Чат» (HEAD 11.11): «HEAD» — объявления + вопросы (все HEAD); личные — любой ↔ любой (видят двое); в бот — только объявления."""
from conftest import hdr
from test_production import VALS, Copying, team  # noqa: F401

from artgame import dm, tgbot


def _second_head(client):
    pid = client.post("/api/register", json={"full_name": "Алина"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "head"}, headers=hdr(1000))
    return pid


def test_chat_hq_and_pm(client, team, monkeypatch):  # noqa: F811
    """«HEAD» — объявления + вопросы (все HEAD, чужие сотрудники не видят); личные — любой ↔ любой, видят двое."""
    sent = []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)) or 900 + len(sent))
    alina = _second_head(client)
    raman = client.get("/api/me", headers=hdr(1000)).json()["id"]
    lst = client.get("/api/dm/list", headers=hdr(2000)).json()
    assert [x["full_name"] for x in lst["people"]][:2] == ["HEAD", "Алина"] and len(lst["people"]) == 4   # HEAD сверху, себя нет
    # вопрос в «HEAD» и личное другому сотруднику
    client.post("/api/dm/room/hq", json={"text": "Не грузится фото"}, headers=hdr(2000))
    client.post(f"/api/dm/pm/{team[3000]}", json={"text": "Привет, ты завтра на объекте?"}, headers=hdr(2000))
    assert client.post(f"/api/dm/pm/{team[2000]}", json={"text": "x"}, headers=hdr(2000)).status_code == 404      # сам себе нельзя
    assert sent == []
    # P3000 видит личное, не видит вопрос P2000; отвечает
    assert client.get("/api/dm/unread", headers=hdr(3000)).json() == {"n": 1}
    assert client.get("/api/dm/room/hq", headers=hdr(3000)).json()["items"] == []
    l3 = client.get("/api/dm/list", headers=hdr(3000)).json()["people"]
    assert l3[0]["id"] == team[2000] and l3[0]["unread"] == 1
    d = client.get(f"/api/dm/pm/{team[2000]}", headers=hdr(3000)).json()
    assert [(x["mine"], x["text"]) for x in d["items"]] == [(False, "Привет, ты завтра на объекте?")]
    client.post(f"/api/dm/pm/{team[2000]}", json={"text": "Да, с 9"}, headers=hdr(3000))
    # HEAD не видит личного чата сотрудников
    assert [x["text"] for x in client.get(f"/api/dm/pm/{team[2000]}", headers=hdr(1000)).json()["items"]] == []
    # оба HEAD видят вопрос, Алина отвечает — Раман видит подпись
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 1}
    assert client.get("/api/dm/unread", headers=hdr(6000)).json() == {"n": 1}
    assert [g["last_text"] for g in client.get("/api/dm/threads", headers=hdr(6000)).json()["group"]] == ["Не грузится фото"]
    client.post(f"/api/dm/with/{team[2000]}", json={"text": "Посмотрим"}, headers=hdr(6000))
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 0}
    g = client.get(f"/api/dm/with/{team[2000]}", headers=hdr(1000)).json()["items"]
    assert [(x["author"], x["text"]) for x in g] == [("P2000", "Не грузится фото"), ("Алина", "Посмотрим")]
    # личное Раман ↔ сотрудник, Алина не видит
    client.post(f"/api/dm/pm/{team[2000]}", json={"text": "Лично"}, headers=hdr(1000))
    assert client.get(f"/api/dm/pm/{team[2000]}", headers=hdr(6000)).json()["items"] == []
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 3}                   # ответ Алины + P3000 + Раман
    # объявление — в «HEAD» каждому и в бот
    b = client.post("/api/dm/broadcast", json={"text": "Сбор в 9"}, headers=hdr(6000)).json()
    assert b["sent"] == 3 and sorted(x[0] for x in sent) == [2000, 3000, 5000] and "Алина" in sent[0][1]
    hq = client.get("/api/dm/room/hq", headers=hdr(2000)).json()["items"]
    assert [(x["author"], x["text"], x["broadcast"]) for x in hq] == [
        ("P2000", "Не грузится фото", False), ("Алина", "Посмотрим", False), ("Алина", "Сбор в 9", True)]
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 2}                   # HEAD прочитан, личные — нет
    assert client.post("/api/dm/broadcast", json={"text": "x", "roles": ["mop"]}, headers=hdr(1000)).status_code == 409
    assert client.get("/api/dm/threads", headers=hdr(2000)).status_code == 403
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
    g = client.get("/api/dm/room/hq", headers=hdr(5000)).json()["items"]
    assert [(x["text"], x["via"]) for x in g] == [("Краска закончилась", "tg")]
    client.post("/api/tg/hook", json=up(1000, "просто так"), headers=h)                        # HEAD — подсказка
    assert "в приложении" in bot[-1][1]["text"]
    client.post("/api/tg/hook", json=up(5000, "/start"), headers=h)
    assert bot[-1][0] == "sendPhoto"
    client.post("/api/tg/hook", json=up(777, "кто я"), headers=h)
    assert bot[-1][0] == "sendPhoto"
