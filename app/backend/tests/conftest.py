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
        yield tc
    db.pool.close()
    db.pool = None


def hdr(tg_id: int, **extra):
    return {"X-Telegram-Init-Data": make_init_data({"id": tg_id, "first_name": "T", **extra})}


@pytest.fixture(autouse=True)
def no_telegram(monkeypatch):
    """Бот в тестах никуда не пишет (регистрация, траты сверх лимита); test_notify подменяет SEND сам."""
    from artgame import notify
    monkeypatch.setattr(notify, "SEND", lambda tg, text: None)
    from artgame import dm
    monkeypatch.setattr(dm, "SEND", lambda tg, text: None)
