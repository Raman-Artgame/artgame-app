"""Константы: лист «Значения» таблицы «КОНСТАНТЫ ARTGAME KZ» — главный источник.

Колонки: A Ключ | B Блок | C Название | D Значение | E Ед. | F Кто видит | G Статус | H Строка | I Изменено.
Сервер забирает лист каждые 5 мин и по кнопке, хранит версию, если что-то поменялось.
В приложение попадают только ключи со статусом «Утверждено» и подходящим «Кто видит».
"""
import hashlib
import json

from psycopg.types.json import Jsonb

from .config import settings

SPREADSHEET_ID = "1Az0OYkdmv1eJZv43xoB0y3HhYvBQPHR0LEHFprJsEt4"
RANGE = "Значения!A2:I"

# Роль → какие значения «Кто видит» ей доступны. head видит всё.
ROLE_AUDIENCE = {
    "mop": {"все", "моп"}, "mop_vip": {"все", "моп"},
    "lead_designer": {"все", "дизайн"}, "designer_asst": {"все", "дизайн"},
    "marketer": {"все", "маркетинг"},
}
PRODUCTION = {"все", "производство"}


def audience(role_code: str | None) -> set[str] | None:
    if role_code == "head":
        return None  # всё
    if role_code is None:
        return set()
    return ROLE_AUDIENCE.get(role_code, PRODUCTION)


def parse_rows(rows: list[list[str]]) -> dict:
    out = {}
    for r in rows:
        r = r + [""] * (9 - len(r))
        key = r[0].strip()
        if not key:
            continue
        out[key] = {"block": r[1], "title": r[2], "value": r[3], "unit": r[4],
                    "who": r[5].strip().lower(), "status": r[6].strip(), "changed": r[8]}
    return out


def who_set(who: str) -> set[str]:
    """«Кто видит» бывает списком: «производство, моп»."""
    return {w.strip() for w in who.split(",") if w.strip()}


def visible(values: dict, role_code: str | None) -> dict:
    aud = audience(role_code)
    return {k: v for k, v in values.items()
            if v["status"] == "Утверждено" and (aud is None or who_set(v["who"]) & aud)}


def num(v):
    """Значение ячейки числом («17 000», «0,8»); не число — строка."""
    s = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        x = float(s)
    except ValueError:
        return str(v).strip()
    return int(x) if x.is_integer() else x


def latest(conn) -> dict:
    """Все утверждённые значения последнего снимка: ключ → число. Только для расчётов на сервере."""
    row = conn.execute("SELECT values FROM constants_versions ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {}
    return {k: num(v["value"]) for k, v in row["values"].items() if v["status"] == "Утверждено"}


def fetch_rows() -> list[list[str]]:
    """Чтение через сервисный аккаунт Google (тот же доступ, что у DRIVE01)."""
    import httpx
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        settings.google_sa_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    creds.refresh(Request())
    r = httpx.get(f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{RANGE}",
                  headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
    r.raise_for_status()
    return r.json().get("values", [])


def store_if_changed(conn, values: dict) -> bool:
    checksum = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    last = conn.execute("SELECT checksum FROM constants_versions ORDER BY id DESC LIMIT 1").fetchone()
    if last and last["checksum"] == checksum:
        return False
    conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (%s, %s)", (checksum, Jsonb(values)))
    return True
