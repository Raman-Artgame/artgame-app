"""Выручка месяца — до октября 2026 из листа «Проекты <год>» (ведётся руками), с ноября — сданные сделки Битрикса.

HEAD ведёт её по дате завершения работ, и только там актуальные цифры (05.11). В Битриксе CLOSEDATE — день перевода
в «успех» (сделки закрывают пачками), а «Фактическая дата завершения проекта» заполнена у малой части сделок.
Читается тем же сервисным аккаунтом, что и константы. Если лист недоступен — month() считает по Битриксу и говорит об этом.
Колонки: A ID сделки | B Месяц | C Объект | D Город | … | N Дата завершения работ | O Выручка (с НДС).
"""
import threading
import time

from .config import settings

SHEET_ID = "1phxf1Y-dEcKOzVG4pgR1eFwSOIqgPGS1a95tgfvrCgo"
TTL = 300
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
_cache: dict = {}
_lock = threading.Lock()


def sheet_values(spreadsheet_id: str, rng: str) -> list[list[str]]:
    """Чтение листа сервисным аккаунтом Google (тот же, что у констант и DRIVE01)."""
    import httpx
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    if not settings.google_sa_file:
        raise RuntimeError("на сервере не задан ARTGAME_GOOGLE_SA_FILE")
    creds = service_account.Credentials.from_service_account_file(
        settings.google_sa_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    creds.refresh(Request())
    r = httpx.get(f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{rng}",
                  headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
    if r.status_code == 403:
        raise RuntimeError("таблица не открыта сервисному аккаунту приложения")
    if r.status_code == 400:
        raise RuntimeError(f"нет листа «{rng.split('!')[0]}»")
    r.raise_for_status()
    return r.json().get("values", [])


def _num(s) -> float:
    try:
        return float(str(s or "").replace("\xa0", "").replace(" ", "").replace(",", ".") or 0)
    except ValueError:
        return 0.0


def _date(s: str) -> str:
    """«10.01.2026» → «2026-01-10»; иначе ''."""
    p = str(s or "").strip().split(".")
    return f"{p[2]}-{int(p[1]):02d}-{int(p[0]):02d}" if len(p) == 3 and p[0].isdigit() and p[1].isdigit() and len(p[2]) == 4 else ""


def rows(year: int, fresh: bool = False) -> list[dict]:
    """Все проекты года: {id, title, city, closed, month(1–12), sum}. Бросает RuntimeError, если лист недоступен."""
    key, now = f"fin:{year}", time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and not fresh and now - hit[0] < TTL:
            return hit[1]
    out = []
    for r in sheet_values(SHEET_ID, f"Проекты {year}!A2:O"):
        r = list(r) + [""] * (15 - len(r))
        if not str(r[0]).strip().isdigit():
            continue
        closed = _date(r[13])
        mon = int(closed[5:7]) if closed else (MONTHS.index(r[1].strip().lower()) + 1 if r[1].strip().lower() in MONTHS else 0)
        if not mon:
            continue
        out.append({"id": int(r[0]), "title": r[2].strip(), "city": r[3].strip(), "closed": closed or f"{year}-{mon:02d}-01",
                    "month": mon, "sum": _num(r[14])})
    out += bitrix_rows(year)
    with _lock:
        _cache[key] = (now, out)
    return out


def bitrix_rows(year: int) -> list[dict]:
    """С ноября 2026 проекты — сданные сделки Битрикса (fin_bx.import_projects, раз в 15 минут), а не ручной лист."""
    from . import db
    try:
        with db.pool.connection() as conn:
            got = conn.execute("""SELECT deal_id, title, city, closed, month, revenue FROM fin_projects
                                  WHERE year=%s AND origin='bitrix' ORDER BY closed""", (year,)).fetchall()
    except Exception:  # noqa: BLE001 — базы нет (тесты листа) — только лист
        return []
    return [{"id": r["deal_id"], "title": r["title"], "city": r["city"], "closed": str(r["closed"]), "month": r["month"],
             "sum": float(r["revenue"])} for r in got]


def month_rows(y: int, m: int, fresh: bool = False) -> list[dict]:
    return [r for r in rows(y, fresh) if r["month"] == m]
