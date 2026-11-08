"""Общие зависимости: человек по подписи Telegram или по сессии входа с компьютера."""
from fastapi import Depends, Header, HTTPException

from . import db
from .config import settings
from .telegram import InitDataError, verify_init_data
from .viewas import VIEW, resolve


def load_person(conn, tg_id: int, by: str = "tg_id"):
    p = conn.execute(f"SELECT * FROM people WHERE {'id' if by == 'id' else 'tg_id'} = %s", (tg_id,)).fetchone()
    if p:
        p["zones"] = [r["zone_code"] for r in conn.execute(
            "SELECT zone_code FROM person_zones WHERE person_id = %s ORDER BY zone_code", (p["id"],))]
    return p


def tg_user(x_telegram_init_data: str = Header(default="")) -> dict:
    try:
        return verify_init_data(x_telegram_init_data, settings.bot_token, settings.initdata_max_age)
    except InitDataError as e:
        raise HTTPException(401, f"telegram: {e}")


def roles_of(p: dict) -> list[str]:
    """Основная роль и дополнительные (HEAD 08.11: у одного человека бывает две роли)."""
    main = p.get("role_main") or p.get("role_code")
    return [r for r in [main, *(p.get("extra_roles") or [])] if r]


def act_as(p: dict, role: str) -> dict:
    """«Я сейчас: …» — дальше всё (меню, права, учёба) считается от выбранной роли; основная — в role_main."""
    if not role or role == p.get("role_code") or role not in (p.get("extra_roles") or []) or role == "head":
        return p
    return {**p, "role_main": p["role_code"], "role_code": role}


def current_person(x_telegram_init_data: str = Header(default=""), authorization: str = Header(default=""),
                   x_act_role: str = Header(default="")) -> dict:
    """В Telegram — подпись initData; с компьютера — сессия по коду от бота (weblogin)."""
    if not x_telegram_init_data and authorization:
        from .weblogin import person_id
        pid = person_id(authorization)
        if not pid:
            raise HTTPException(401, "session expired")
        with db.pool.connection() as conn:
            p = load_person(conn, pid, by="id")
    else:
        user = tg_user(x_telegram_init_data)
        with db.pool.connection() as conn:
            p = load_person(conn, int(user["id"]))
    if not p:
        raise HTTPException(403, "not registered")
    if p["status"] == "blocked":
        raise HTTPException(403, "blocked")
    d = VIEW.get()
    if d and d.get("as"):   # HEAD смотрит как сотрудник: дальше всё считается от лица этого человека, запись закрыта
        with db.pool.connection() as conn:
            p = resolve(conn, p, d["as"], load_person)
        return {**p, "roles": roles_of(p)}
    p = act_as(p, x_act_role)
    return {**p, "roles": roles_of(p)}


def require_head(p: dict = Depends(current_person)) -> dict:
    if p["role_code"] != "head" or p["status"] != "active":
        raise HTTPException(403, "head only")
    return p
