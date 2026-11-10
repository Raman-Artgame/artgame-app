"""«Диалог с HEAD» (HEAD 09.11): личный диалог, рассылка всем / по ролям, ответ из Telegram.
HEAD 10.11: в бот уходит только рассылка, личные сообщения — только в приложении."""
from conftest import hdr
from test_production import VALS, Copying, team  # noqa: F401

from artgame import db, dm, tgbot


def test_dialog_and_broadcast(client, team, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)) or 900 + len(sent))
    # сотрудник пишет HEAD → в бот ничего (HEAD 10.11), у HEAD непрочитанное в приложении
    r = client.post("/api/dm", json={"text": "Когда аванс?"}, headers=hdr(2000))
    assert r.status_code == 200 and not r.json()["from_head"]
    assert sent == []
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 1}
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["dm"] == {"unread": 1, "people": 1}
    assert client.get("/api/dm/threads", headers=hdr(2000)).status_code == 403          # чужие диалоги — только HEAD
    th = client.get("/api/dm/threads", headers=hdr(1000)).json()
    assert th["items"][0]["id"] == team[2000] and th["items"][0]["unread"] == 1 and len(th["items"]) == 3
    # HEAD открыл и ответил → прочитано, у сотрудника непрочитанное в приложении, в бот ничего
    d = client.get(f"/api/dm/with/{team[2000]}", headers=hdr(1000)).json()
    assert [x["text"] for x in d["items"]] == ["Когда аванс?"]
    assert client.get("/api/dm/unread", headers=hdr(1000)).json() == {"n": 0}
    client.post(f"/api/dm/with/{team[2000]}", json={"text": "В пятницу"}, headers=hdr(1000))
    assert sent == []
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 1}
    my = client.get("/api/dm", headers=hdr(2000)).json()["items"]
    assert [(x["from_head"], x["text"]) for x in my] == [(False, "Когда аванс?"), (True, "В пятницу")]
    assert client.get("/api/dm/unread", headers=hdr(2000)).json() == {"n": 0}
    assert client.get("/api/dm", headers=hdr(3000)).json()["items"] == []                # чужой диалог не виден
    assert client.post("/api/dm", json={"text": ""}, headers=hdr(2000)).status_code == 422
    # рассылка по роли и всем
    b = client.post("/api/dm/broadcast", json={"text": "Собрание в 10", "roles": ["lead_artist"]}, headers=hdr(1000)).json()
    assert b["sent"] == 1 and [s[0] for s in sent] == [3000] and sent[-1][1].startswith("📣")   # рассылка — в бот
    assert client.post("/api/dm/broadcast", json={"text": "x", "roles": ["mop"]}, headers=hdr(1000)).status_code == 409
    b = client.post("/api/dm/broadcast", json={"text": "Всем привет"}, headers=hdr(1000)).json()
    assert b["sent"] == 3 and sorted(s[0] for s in sent[1:]) == [2000, 3000, 5000]
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
    client.post("/api/tg/hook", json=up(5000, "Краска закончилась"), headers=h)            # сотрудник пишет боту → в диалог, HEAD в бот ничего
    assert sent == [] and bot[-1][1]["text"].startswith("✓ Передал HEAD")
    client.post("/api/dm/broadcast", json={"text": "Сбор в 9"}, headers=hdr(1000))         # рассылка — в бот
    mid = 500 + len(sent)
    client.post("/api/tg/hook", json=up(5000, "Буду", reply=mid), headers=h)               # ответ свайпом на рассылку → в диалог
    items = client.get("/api/dm", headers=hdr(5000)).json()["items"]
    assert [(x["from_head"], x["text"], x["via"]) for x in items] == [(False, "Краска закончилась", "tg"), (True, "Сбор в 9", "app"), (False, "Буду", "tg")]
    with db.pool.connection() as c:                                                         # старое уведомление сотрудника (до 10.11)
        c.execute("UPDATE dm SET tg_msg_id=77 WHERE text='Буду'")
    n = len(sent)
    client.post("/api/tg/hook", json=up(1000, "Купи сам, чек в расход", reply=77), headers=h)   # HEAD свайпом по старому — в диалог, без бота
    assert len(sent) == n and bot[-1][1]["text"] == "✓ Отправлено: P5000"
    client.post("/api/tg/hook", json=up(1000, "просто так"), headers=h)                     # HEAD без ответа-свайпа — подсказка
    assert "в приложении" in bot[-1][1]["text"]
    client.post("/api/tg/hook", json=up(5000, "/start"), headers=h)                         # «Старт» — приветствие, не в диалог
    assert bot[-1][0] == "sendPhoto" and len(client.get("/api/dm", headers=hdr(5000)).json()["items"]) == 4
    client.post("/api/tg/hook", json=up(777, "кто я"), headers=h)                           # незнакомый — приветствие
    assert bot[-1][0] == "sendPhoto"


def test_one_notice_per_person(client, team, monkeypatch):  # noqa: F811
    """HEAD 10.11: о личных сообщениях — одно уведомление без текста письма; новое — старое удаляется; прочитал — удаляется."""
    bot, sent = [], []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)))
    monkeypatch.setattr(dm, "BOT", lambda m, **p: bot.append((m, p)) or {"message_id": 100 + len(bot)})
    client.post(f"/api/dm/with/{team[2000]}", json={"text": "Секретная сумма 500 000"}, headers=hdr(1000))
    m, p = bot[-1]
    assert m == "sendMessage" and p["chat_id"] == 2000 and p["text"].startswith("✉️ Новое сообщение от HEAD") and "500" not in p["text"]
    first = 100 + len(bot)
    client.post(f"/api/dm/with/{team[2000]}", json={"text": "Ещё одно"}, headers=hdr(1000))
    assert [b[0] for b in bot[-2:]] == ["deleteMessage", "sendMessage"] and bot[-2][1]["message_id"] == first
    assert "2" in bot[-1][1]["text"] and sent == []
    n = len(bot)
    client.get("/api/dm", headers=hdr(2000))                                                # прочитал → уведомление удалено
    assert bot[n:] == [("deleteMessage", {"chat_id": 2000, "message_id": 100 + n})]
    client.get("/api/dm", headers=hdr(2000))
    assert len(bot) == n + 1                                                                 # второй раз удалять нечего
    # HEAD: одно уведомление «от команды» с именами, без текста
    client.post("/api/dm", json={"text": "Вопрос по смене"}, headers=hdr(2000))
    client.post("/api/dm", json={"text": "Краска"}, headers=hdr(3000))
    m, p = bot[-1]
    assert m == "sendMessage" and p["chat_id"] == 1000 and "команды: 2" in p["text"] and "P3000, P2000" in p["text"] and "Краска" not in p["text"]
    client.get(f"/api/dm/with/{team[3000]}", headers=hdr(1000))                            # прочитал одного — счётчик молча
    assert bot[-1][0] == "editMessageText" and "команды: 1" in bot[-1][1]["text"]
    client.get(f"/api/dm/with/{team[2000]}", headers=hdr(1000))
    assert bot[-1][0] == "deleteMessage" and bot[-1][1]["chat_id"] == 1000
    # рассылка уведомление «Новое сообщение» не создаёт — она сама приходит текстом
    n = len(bot)
    client.post("/api/dm/broadcast", json={"text": "Сбор в 9"}, headers=hdr(1000))
    assert len(bot) == n and len(sent) == 3
