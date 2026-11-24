import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import pytest

TOKEN = "123:test-token"
os.environ["ARTGAME_BOT_TOKEN"] = TOKEN
os.environ["ARTGAME_HEAD_TG_ID"] = "1000"


def make_init_data(user: dict, token: str = TOKEN, auth_date: int | None = None) -> str:
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "q1",
              "user": json.dumps(user, separators=(",", ":"))}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def client():
    """Нужна пустая тестовая база: ARTGAME_TEST_DATABASE_URL."""
    url = os.environ.get("ARTGAME_TEST_DATABASE_URL")
    if not url:
        pytest.skip("no ARTGAME_TEST_DATABASE_URL")
    import psycopg
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    from fastapi.testclient import TestClient
    from artgame import db
    from artgame.main import app
    db.open_pool(url)
    with TestClient(app) as tc:
        # HEAD 24.11: расход без чека и комментария не принимается. Старым тестам чек и комментарий подставляем,
        # если ключа нет вовсе; тест отказа передаёт "receipt": None / "note": "" сам.
        post = tc.post

        def post_filled(url, *a, **kw):
            j = kw.get("json")
            if isinstance(j, dict) and (url == "/api/expenses" or url.endswith("/trip-costs")
                                        or (url == "/api/appeals" and j.get("kind") == "expense_late")):
                kw["json"] = {"receipt": JPG, "note": "тестовый расход", **j}
            return post(url, *a, **kw)
        tc.post = post_filled
        yield tc
    db.pool.close()
    db.pool = None


JPG = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2Q=="


@pytest.fixture(autouse=True)
def no_drive_receipts(monkeypatch, request):
    """Чеки в тестах на Диск не уходят; тесты, которым важен отдел/папка, подменяют save_receipt сами,
    а тесты с поддельным Диском (fake) идут через настоящий save_receipt."""
    if "fake" in request.fixturenames or "client" not in request.fixturenames:
        return
    from artgame import drive
    monkeypatch.setattr(drive, "save_receipt", lambda conn, dept, name, data, deal_id=None: f"drv-{dept}")


def hdr(tg_id: int, **extra):
    return {"X-Telegram-Init-Data": make_init_data({"id": tg_id, "first_name": "T", **extra})}


@pytest.fixture(autouse=True)
def no_telegram(monkeypatch):
    """Бот в тестах никуда не пишет (регистрация, траты сверх лимита); test_notify подменяет SEND сам."""
    from artgame import notify
    monkeypatch.setattr(notify, "SEND", lambda tg, text: None)
    from artgame import dm
    monkeypatch.setattr(dm, "SEND", lambda tg, text: None)
    monkeypatch.setattr(dm, "BOT", lambda m, **p: {"message_id": 1})
