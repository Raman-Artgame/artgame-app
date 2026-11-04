"""Проверка подписи Telegram Mini App (initData).

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    pass


def verify_init_data(init_data: str, bot_token: str, max_age: int, now: float | None = None) -> dict:
    if not bot_token:
        raise InitDataError("bot token not configured")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataError("no hash")
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataError("bad signature")
    auth_date = int(pairs.get("auth_date", "0"))
    if (now or time.time()) - auth_date > max_age:
        raise InitDataError("expired")
    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError as e:
        raise InitDataError("bad user") from e
    if not user.get("id"):
        raise InitDataError("no user")
    return user
