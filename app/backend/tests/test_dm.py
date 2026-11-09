"""«Диалог с HEAD» (HEAD 09.11): личный диалог, рассылка всем / по ролям, уведомления бота, ответ свайпом из Telegram."""
from conftest import hdr
from test_production import VALS, Copying, team  # noqa: F401

from artgame import dm, tgbot


def test_dialog_and_broadcast(client, team, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)) or 900 + len(sent))
    # сотрудник пишет HEAD → уведомление HEAD (tg 1000), у HEAD непрочитанное
    r = client.post("/api/dm", json={"text": "Когда аванс?"}, headers=hdr(2000))
    assert r.status_code == 200 and not r.json()["from_head"]
    assert sent[-1][0] == 1000 and "P2000" in sent[-1][1] and "Когда аванс?" in sent[-1][1]
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 1}
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["dm"] == {"unread": 1, "people": 1}
    assert client.get("/api/dm/threads", headers=hdr(2000)).status_code == 403          # чужие диалоги — только HEAD
    th = client.get("/api/dm/threads", headers=hdr(1000)).json()
    assert th["items"][0]["id"] == team[2000] and th["items"][0]["unread"] == 1 and len(th["items"]) == 3
    # HEAD открыл и ответил → прочитано, сотруднику уведомление и непрочитанное
    d = client.get(f"/api/dm/with/{team[2000]}", headers=hdr(1000)).json()
    assert [x["text"] for x in d["items"]] == ["Когда аванс?"]
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 0}
    client.post(f"/api/dm/with/{team[2000]}", json={"text": "В пятницу"}, headers=hdr(1000))
    assert sent[-1][0] == 2000 and "В пятницу" in sent[-1][1]
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 1}
    my = client.get("/api/dm", headers=hdr(2000)).json()["items"]
    assert [(x["from_head"], x["text"]) for x in my] == [(False, "Когда аванс?"), (True, "В пятницу")]
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 0}
    assert client.get("/api/dm", headers=hdr(3000)).json()["items"] == []                # чужой диалог не виден
    assert client.post("/api/dm", json={"text": ""}, headers=hdr(2000)).status_code == 422
    # рассылка по роли и всем
    n = len(sent)
    b = client.post("/api/dm/broadcast", json={"text": "Собрание в 10", "roles": ["lead_artist"]}, headers=hdr(1000)).json()
    assert b["sent"] == 1 and [s[0] for s in sent[n:]] == [3000] and sent[-1][1].startswith("📣")
    assert client.post("/api/dm/broadcast", json={"text": "x", "roles": ["mop"]}, headers=hdr(1000)).status_code == 409
    b = client.post("/api/dm/broadcast", json={"text": "Всем привет"}, headers=hdr(1000)).json()
    assert b["sent"] == 3
    assert client.post("/api/dm/broadcast", json={"text": "x"}, headers=hdr(2000)).status_code == 403
    assert client.get("/api/dm/unread", headers=hdr(3000)).json() == {"n": 2}
    assert client.get("/api/dm/threads", headers=hdr(1000)).json()["broadcasts"][0]["text"] == "Всем привет"


def test_reply_from_telegram(client, team, monkeypatch):  # noqa: F811
    sent, bot = [], []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)) or 500 + len(sent))
    monkeypatch.setattr(tgbot, "CALL", lambda m, **p: bot.append((m, p)))
    h = {"X-Telegram-Bot-Api-Secret-Token": tgbot.hook_secret()}
    up = lambda chat, text, reply=None: {"message": {"chat": {"id": chat, "type": "private"}, "from": {"first_name": "T"}, "text": text,  # noqa: E731
                                                     **({"reply_to_message": {"message_id": reply}} if reply else {})}}
    client.post("/api/tg/hook", json=up(5000, "Краска закончилась"), headers=h)            # сотрудник пишет боту
    assert sent[-1] == (1000, sent[-1][1]) and "Краска закончилась" in sent[-1][1]
    assert bot[-1][1]["text"].startswith("✓ Передал HEAD")
    mid = 500 + len(sent)
    client.post("/api/tg/hook", json=up(1000, "Купи сам, чек в расход", reply=mid), headers=h)   # HEAD свайпом
    assert sent[-1][0] == 5000 and "Купи сам" in sent[-1][1] and bot[-1][1]["text"] == "✓ Отправлено: P5000"
    items = client.get("/api/dm", headers=hdr(5000)).json()["items"]
    assert [(x["from_head"], x["via"]) for x in items] == [(False, "tg"), (True, "tg")]
    client.post("/api/tg/hook", json=up(1000, "просто так"), headers=h)                     # HEAD без ответа-свайпа — подсказка
    assert "свайпом" in bot[-1][1]["text"]
    client.post("/api/tg/hook", json=up(5000, "/start"), headers=h)                         # «Старт» — приветствие, не в диалог
    assert bot[-1][0] == "sendPhoto" and len(client.get("/api/dm", headers=hdr(5000)).json()["items"]) == 2
    client.post("/api/tg/hook", json=up(777, "кто я"), headers=h)                           # незнакомый — приветствие
    assert bot[-1][0] == "sendPhoto"
