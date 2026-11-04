"""Общие зависимости: человек по подписи Telegram."""
from fastapi import Depends, Header, HTTPException

from . import db
from .config import settings
from .telegram import InitDataError, verify_init_data


def load_person(conn, tg_id: int):
    p = conn.execute("SELECT * FROM people WHERE tg_id = %s", (tg_id,)).fetchone()
    if p:
        p["zones"] = [r["zone_code"] for r in conn.execute(
            "SELECT zone_code FROM person_zones WHERE person_id = %s ORDER BY zone_code", (p["id"],))]
    return p


def tg_user(x_telegram_init_data: str = Header(default="")) -> dict:
    try:
        return verify_init_data(x_telegram_init_data, settings.bot_token, settings.initdata_max_age)
    except InitDataError as e:
        raise HTTPException(401, f"telegram: {e}")


def current_person(user: dict = Depends(tg_user)) -> dict:
    with db.pool.connection() as conn:
        p = load_person(conn, int(user["id"]))
    if not p:
        raise HTTPException(403, "not registered")
    if p["status"] == "blocked":
        raise HTTPException(403, "blocked")
    return p


def require_head(p: dict = Depends(current_person)) -> dict:
    if p["role_code"] != "head" or p["status"] != "active":
        raise HTTPException(403, "head only")
    return p
