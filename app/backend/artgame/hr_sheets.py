"""Связь кандидатов с таблицами Диска (HEAD 26.11 «эти 2 таблицы надо связать»).

- «БАЗА КАНДИДАТОВ И ПОДРЯДЧИКОВ»: строка кандидата на листе направления (ИМЯ · ТЕЛЕФОН · ГОРОД · СТАТУС · КОММЕНТАРИЙ ·
  ПОРТФОЛИО / РЕЗЮМЕ · ВОЗРАСТ · ПОСЛЕДНИЙ КОНТАКТ). Новый — первая пустая строка (формулы «Повтор?» и «№ подбора» уже
  протянуты вниз, их не трогаем); дальше строка ищется по телефону и правится: статус и комментарий по шагу в приложении.
- «СОТРУДНИКИ И СУППОРТЫ»: после «Принять» — строка внизу, стаж и возраст — теми же формулами, что у остальных.
Главное место — приложение; таблицы только повторяют (Диск — для выгрузки). Сбой Google не ломает анкету: строка
дописывается при следующем изменении кандидата.
"""
import logging
import re
from datetime import date, datetime

import httpx

from .config import settings

log = logging.getLogger("artgame.hr")

BASE_ID = "13OcHCO2zeiZmBdyIc_V1QGN6Veun4j6drpJJgM6eC2I"    # БАЗА КАНДИДАТОВ И ПОДРЯДЧИКОВ
STAFF_ID = "1DE-3hLqm4eN37xEODSKt1IJnO1BMMZS51XK3srtxSbk"   # СОТРУДНИКИ И СУППОРТЫ
STAFF_SHEET = "Сотрудники и суппорты"
BASE_SHEETS = ("Художники", "Дизайнеры", "Видеографы", "Продажи", "Помощник принтера")
API = "https://sheets.googleapis.com/v4/spreadsheets"
MON = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
# шаг в приложении → статус базы (лист «Настройки»): в работе — «Пригласить», принят — «В команде»
STATUS = {"new": "Пригласить", "talk": "Пригласить", "interview": "Пригласить", "trial": "Пригласить", "hired": "В команде",
          "reserve": "Резерв"}
STAGE_RU = {"new": "Новый", "talk": "Связались", "interview": "Собеседование", "trial": "Пробная смена", "hired": "Принят",
            "reserve": "Резерв", "rejected": "Отказ"}
_TOK: dict = {}


def status_of(c: dict) -> str:
    if c["stage"] == "rejected":
        return "Не актуален" if c.get("self_refused") else "Не приглашать"
    return STATUS[c["stage"]]


def _token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    c = _TOK.get("c")
    if c and c.valid and c.expiry and (c.expiry - datetime.utcnow()).total_seconds() > 300:
        return c.token
    c = service_account.Credentials.from_service_account_file(settings.google_sa_file, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    c.refresh(Request())
    _TOK["c"] = c
    return c.token


def _h() -> dict:
    return {"Authorization": f"Bearer {_token()}"}


def get(sid: str, rng: str) -> list[list[str]]:
    r = httpx.get(f"{API}/{sid}/values/{rng}", headers=_h(), timeout=30)
    r.raise_for_status()
    return r.json().get("values", [])


def batch_get(sid: str, ranges: list[str]) -> list[list[list[str]]]:
    r = httpx.get(f"{API}/{sid}/values:batchGet", headers=_h(), timeout=30, params=[("ranges", x) for x in ranges])
    r.raise_for_status()
    return [v.get("values", []) for v in r.json().get("valueRanges", [])]


def put(sid: str, rng: str, rows: list[list]) -> None:
    r = httpx.put(f"{API}/{sid}/values/{rng}", headers=_h(), timeout=30, params={"valueInputOption": "USER_ENTERED"},
                  json={"range": rng, "majorDimension": "ROWS", "values": rows})
    r.raise_for_status()


def phone(s: str | None) -> str:
    """Телефон как в базе: 11 цифр с 8 (87771234567). +7 / 7 / 10 цифр приводятся к нему."""
    d = re.sub(r"\D", "", s or "")
    if len(d) == 10:
        d = "8" + d
    if len(d) == 11 and d[0] == "7":
        d = "8" + d[1:]
    return d


def _q(sheet: str) -> str:
    return "'" + sheet.replace("'", "''") + "'"


def find_prior(ph: str) -> dict | None:
    """Был ли телефон в базе раньше (на любом листе): лист, имя, статус, комментарий, последний контакт."""
    vals = batch_get(BASE_ID, [f"{_q(s)}!A2:H" for s in BASE_SHEETS])
    for s, rows in zip(BASE_SHEETS, vals):
        for r in rows:
            r = r + [""] * (8 - len(r))
            if phone(r[1]) == ph:
                return {"sheet": s, "name": r[0], "status": r[3], "comment": r[4][:300], "contact": r[7]}
    return None


def age(birth: str | None) -> str:
    try:
        d = datetime.strptime((birth or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        return ""
    t = date.today()
    return str(t.year - d.year - ((t.month, t.day) < (d.month, d.day)))


def comment(c: dict, level_title: str | None) -> str:
    a = c.get("answers") or {}
    bits = [f"Анкета из приложения ({c['created_at']:%d.%m})", f"этап: {STAGE_RU[c['stage']]}"]
    if level_title:
        bits.append(f"хочет: {level_title}")
    for k in ("style", "years"):
        v = a.get(k)
        if v:
            bits.append(", ".join(v) if isinstance(v, list) else str(v))
    if c.get("stars"):
        bits.append("★" * c["stars"])
    if c.get("reason"):
        bits.append(f"причина: {c['reason']}")
    if c.get("note"):
        bits.append(c["note"])
    return "; ".join(bits)[:500]


def base_row(c: dict, level_title: str | None, folder_url: str) -> list:
    t = datetime.now()
    return [c["full_name"], c["phone"], c.get("city") or "", status_of(c), comment(c, level_title), folder_url,
            age((c.get("answers") or {}).get("birth")), f"{MON[t.month - 1]} {t.year}"]


def base_upsert(sheet: str, c: dict, level_title: str | None, folder_url: str) -> int:
    """Строка кандидата на листе направления: есть телефон — правим её, нет — первая пустая строка. Возвращает номер строки."""
    rows = get(BASE_ID, f"{_q(sheet)}!A1:B")
    n = None
    for i, r in enumerate(rows[1:], start=2):
        if len(r) > 1 and phone(r[1]) == c["phone"]:
            n = i
            break
    if n is None:
        n = next((i for i, r in enumerate(rows[1:], start=2) if not (r and r[0].strip())), len(rows) + 1)
    put(BASE_ID, f"{_q(sheet)}!A{n}:H{n}", [base_row(c, level_title, folder_url)])
    return n


def base_clear(sheet: str, ph: str) -> int | None:
    """Удалённая анкета (HEAD 28.11): строку этого телефона на листе очищаем (A:H — формулы правее не трогаем)."""
    rows = get(BASE_ID, f"{_q(sheet)}!A1:B")
    for i, r in enumerate(rows[1:], start=2):
        if len(r) > 1 and phone(r[1]) == ph:
            r2 = httpx.post(f"{API}/{BASE_ID}/values/{_q(sheet)}!A{i}:H{i}:clear", headers=_h(), timeout=30)
            r2.raise_for_status()
            return i
    return None


def staff_append(c: dict, role_title: str, support: bool) -> int:
    """Принят: строка внизу «Сотрудников и суппортов», если такого телефона там ещё нет."""
    rows = get(STAFF_ID, f"{_q(STAFF_SHEET)}!A1:F")
    for i, r in enumerate(rows, start=1):
        if len(r) > 5 and phone(r[5]) == c["phone"]:
            return i
    n = len(rows) + 1
    a = c.get("answers") or {}
    put(STAFF_ID, f"{_q(STAFF_SHEET)}!A{n}:L{n}", [[
        "СУППОРТ" if support else "ОСНОВНОЙ СОСТАВ", c.get("city") or "", c["full_name"], role_title, "", c["phone"],
        date.today().strftime("%d.%m.%Y"),
        f'=IF(G{n}="";"";DATEDIF(G{n};TODAY();"Y")&" г. "&DATEDIF(G{n};TODAY();"YM")&" мес.")',
        (a.get("birth") or "").strip(), f'=IF(I{n}="";"";DATEDIF(I{n};TODAY();"Y"))', "Работает", "Из анкеты приложения"]])
    return n
