"""Вход с компьютера без Telegram (HEAD 06.11): человек вводит телефон или @ник, бот присылает код в Telegram,
браузер получает сессию на 30 дней (заголовок Authorization: Bearer). Входит только тот, кто уже есть в команде
и активен; ответ на запрос кода одинаковый, есть человек или нет, — по нему нельзя перебрать список команды."""
import hashlib
import re
import secrets

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from . import db, notify
from .config import settings

router = APIRouter()
CODE_MIN, SESSION_DAYS, MAX_TRIES, RESEND_SEC = 10, 30, 5, 60


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def find(conn, who: str):
    who = (who or "").strip()
    if who.startswith("@") or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", who):
        return conn.execute("SELECT * FROM people WHERE lower(tg_username) = lower(%s) AND status = 'active'", (who.lstrip("@"),)).fetchone()
    digits = re.sub(r"\D", "", who)[-10:]
    if len(digits) < 10:
        return None
    return conn.execute("SELECT * FROM people WHERE right(regexp_replace(coalesce(phone, ''), '\\D', '', 'g'), 10) = %s AND status = 'active' "
                        "ORDER BY id LIMIT 1", (digits,)).fetchone()


class CodeIn(BaseModel):
    who: str


class VerifyIn(BaseModel):
    who: str
    code: str


@router.post("/api/login/code")
def send_code(body: CodeIn):
    with db.pool.connection() as conn:
        p = find(conn, body.who)
        if p:
            recent = conn.execute("SELECT 1 FROM login_codes WHERE person_id = %s AND created_at > now() - make_interval(secs => %s)",
                                  (p["id"], RESEND_SEC)).fetchone()
            if not recent:
                code = f"{secrets.randbelow(10 ** 6):06d}"
                conn.execute("UPDATE login_codes SET used = true WHERE person_id = %s AND NOT used", (p["id"],))
                conn.execute("INSERT INTO login_codes (person_id, code_hash, expires_at) VALUES (%s, %s, now() + make_interval(mins => %s))",
                             (p["id"], _h(f"{p['id']}:{code}"), CODE_MIN))
                db.audit(conn, p["id"], "login_code", "people", p["id"])
                try:
                    notify.SEND(p["tg_id"], f"Код для входа в ARTGAME с компьютера: {code}\nДействует {CODE_MIN} минут. "
                                            "Если вход не вы — никому не сообщайте код.")
                except Exception as e:  # noqa: BLE001
                    print("login code send:", e)
    return {"ok": True, "text": "Если вы в команде ARTGAME, код уже в Telegram, в чате с ботом."}


@router.post("/api/login/verify")
def verify(body: VerifyIn, request: Request):
    code = re.sub(r"\D", "", body.code)
    with db.pool.connection() as conn:
        p = find(conn, body.who)
        row = p and conn.execute("SELECT * FROM login_codes WHERE person_id = %s AND NOT used AND expires_at > now() ORDER BY id DESC LIMIT 1",
                                 (p["id"],)).fetchone()
        if not row or row["tries"] >= MAX_TRIES:
            raise HTTPException(400, "Код устарел. Запросите новый.")
        ok = secrets.compare_digest(row["code_hash"], _h(f"{p['id']}:{code}"))
        if not ok:   # попытку записываем до ответа: исключение внутри соединения откатило бы её
            conn.execute("UPDATE login_codes SET tries = tries + 1 WHERE id = %s", (row["id"],))
            conn.commit()
            raise HTTPException(400, "Код не подошёл.")
        conn.execute("UPDATE login_codes SET used = true WHERE id = %s", (row["id"],))
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO web_sessions (token_hash, person_id, expires_at, agent) VALUES (%s, %s, now() + make_interval(days => %s), %s)",
                     (_h(token), p["id"], SESSION_DAYS, (request.headers.get("user-agent") or "")[:200]))
        db.audit(conn, p["id"], "login_web", "people", p["id"])
    return {"token": token}


def person_id(authorization: str) -> int | None:
    """Bearer-токен → id человека; просроченный или чужой — None."""
    if not authorization.lower().startswith("bearer "):
        return None
    with db.pool.connection() as conn:
        r = conn.execute("UPDATE web_sessions SET last_seen = now() WHERE token_hash = %s AND expires_at > now() RETURNING person_id",
                         (_h(authorization[7:].strip()),)).fetchone()
    return r["person_id"] if r else None


@router.post("/api/logout")
def logout(authorization: str = Header(default="")):
    if authorization.lower().startswith("bearer "):
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM web_sessions WHERE token_hash = %s", (_h(authorization[7:].strip()),))
    return {"ok": True}
