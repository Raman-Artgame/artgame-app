"""Бот: ответ на «Старт» и приведение профиля (HEAD 08.11)."""
from fastapi.testclient import TestClient

from artgame import tgbot
from artgame.main import app


def test_hook_replies_only_with_secret(monkeypatch):
    sent = []
    monkeypatch.setattr(tgbot, "CALL", lambda m, **p: sent.append((m, p)))
    c = TestClient(app)
    upd = {"message": {"chat": {"id": 42, "type": "private"}, "from": {"first_name": "Аня"}, "text": "/start"}}
    assert c.post("/api/tg/hook", json=upd).json() == {"ok": False}
    assert c.post("/api/tg/hook", json=upd, headers={"X-Telegram-Bot-Api-Secret-Token": "x"}).json() == {"ok": False}
    assert not sent
    r = c.post("/api/tg/hook", json=upd, headers={"X-Telegram-Bot-Api-Secret-Token": tgbot.hook_secret()})
    assert r.json() == {"ok": True}
    m, p = sent[0]
    assert m == "sendPhoto" and p["chat_id"] == 42 and "Аня" in p["caption"] and p["photo"].endswith("/bot-welcome.jpg")
    assert p["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"].endswith("/")
    # группы бот молча пропускает
    upd["message"]["chat"]["type"] = "group"
    c.post("/api/tg/hook", json=upd, headers={"X-Telegram-Bot-Api-Secret-Token": tgbot.hook_secret()})
    assert len(sent) == 1


def test_setup_changes_only_diff(monkeypatch):
    state = {"getMyName": {"name": "artgame team"}, "getMyDescription": {"description": ""},
             "getMyShortDescription": {"short_description": tgbot.SHORT}, "getMyCommands": [{"command": "x"}],
             "getChatMenuButton": {"type": "web_app", "text": "ARTGAME", "web_app": {"url": tgbot.app_url()}},
             "getWebhookInfo": {"url": "https://script.google.com/old"}}
    calls = []

    def fake(m, **p):
        calls.append((m, p))
        return state.get(m)
    monkeypatch.setattr(tgbot, "CALL", fake)
    done = tgbot.setup()
    names = [m for m, _ in calls if not m.startswith("get")]
    assert names == ["setMyName", "setMyDescription", "deleteMyCommands", "setWebhook"]
    wh = dict(calls)["setWebhook"]
    assert wh["url"].endswith("/api/tg/hook") and wh["secret_token"] == tgbot.hook_secret() and wh["drop_pending_updates"]
    assert "webhook (был: script.google.com)" in done


def test_hook_falls_back_to_text(monkeypatch):
    sent = []

    def fake(m, **p):
        if m == "sendPhoto":
            raise RuntimeError("sendPhoto: wrong file")
        sent.append((m, p))
    monkeypatch.setattr(tgbot, "CALL", fake)
    upd = {"message": {"chat": {"id": 7, "type": "private"}, "from": {}, "text": "/start"}}
    TestClient(app).post("/api/tg/hook", json=upd, headers={"X-Telegram-Bot-Api-Secret-Token": tgbot.hook_secret()})
    assert sent[0][0] == "sendMessage" and sent[0][1]["text"].startswith("Привет!")
