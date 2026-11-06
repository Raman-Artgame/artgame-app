"""Витрина финансов в Google Таблице (HEAD 05.11: база главная, Таблица — для просмотра, руками не правим).

Сервер переписывает листы «Сводка», «Движение денег», «ФОТ», «Закупки» таблицы ARTGAME_FIN_SHEET_ID
сервисным аккаунтом (нужен доступ «Редактор» к этой таблице). Запуск: кнопка HEAD и таймер artgame-finexport.
Пока таблица не задана — ничего не пишет и говорит об этом.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from . import db, fin_bx, fin_history, finance
from .config import settings
from .deps import require_head

router = APIRouter(prefix="/api")
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
KIND = {"in": "приход", "out": "расход"}


def build(conn, year: int, head: dict) -> dict[str, list[list]]:
    """Строки листов за год. Месяцы до запуска (ноябрь 2026) остаются пустыми — история в старой таблице."""
    last = date.today().month if date.today().year == year else 12
    sv = [["Месяц", "Выручка с НДС", "НДС", "Без НДС", "На объекты (чеки)", "Склад", "Мастерская холстов", "Отдел продаж",
           "ФОТ", "Постоянные", "Переменные", "Прибыль", "ИПН (оценка)", "Приход денег", "Расход денег", "Остаток на конец"]]
    pay = [["Месяц", "Получатель", "Группа", "Начислено", "Выплачено", "Осталось", "Последняя выплата", "Из чего"]]
    for m in range(1, last + 1):
        ym = f"{year}-{m:02d}"
        s = finance.summary(ym, head)
        c, r = s["costs"], s["revenue"]
        sv.append([MONTHS[m - 1], r["gross"], r["vat"], r["net"], c["project"], c["stock"], c["canvas"], c["sales"], c["payroll"],
                   c["fixed"], c["variable"], s["profit"], s["ipn"], s["cash"]["in"], s["cash"]["out"],
                   sum(float(b["balance"]) for b in s["cash"]["closing"])])
        for x in finance.payroll(ym, head)["rows"]:
            pay.append([MONTHS[m - 1], x["name"], x["group"], x["accrued"], x["paid"], x["left"], str(x["last_paid"] or ""),
                        "; ".join(f"{a['detail'] or a['kind']}: {float(a['amount']):.0f}" for a in x["lines"])])
    led = [["Дата", "Счёт", "Приход/расход", "Сумма", "Статья", "За месяц", "Сделка", "Получатель", "Комментарий", "Источник", "Статус"]]
    for l in conn.execute(
            """SELECT l.*, a.title AS art, ac.title AS acc, py.name AS payee FROM fin_ledger l JOIN fin_articles a ON a.code=l.article_code
               JOIN fin_accounts ac ON ac.code=l.account_code LEFT JOIN fin_payees py ON py.id=l.payee_id
               WHERE l.op_date >= %s AND l.op_date < %s ORDER BY l.op_date, l.id""", (date(year, 1, 1), date(year + 1, 1, 1))).fetchall():
        led.append([str(l["op_date"]), l["acc"], KIND[l["direction"]], float(l["amount"]), l["art"], l["period"], l["deal_id"] or "",
                    l["payee"] or "", l["note"] or "", l["source"], "отменено" if l["status"] == "cancelled" else ""])
    buy = [["Дата", "Кто", "Статья", "Категория", "Объект / сделка", "Сумма", "Чьи деньги", "Статус", "Выплата"]]
    art = {"project": "На объект", "stock": "Склад", "canvas": "Мастерская холстов", "sales": "Отдел продаж"}
    for e in conn.execute(
            """SELECT e.*, c.title AS cat, c.article, pe.full_name AS who, o.title AS obj FROM expenses e
               JOIN expense_categories c ON c.code=e.category JOIN people pe ON pe.id=e.person_id JOIN objects o ON o.id=e.object_id
               WHERE e.created_at >= %s AND e.created_at < %s AND e.status <> 'cancelled' ORDER BY e.created_at""",
            (date(year, 1, 1), date(year + 1, 1, 1))).fetchall():
        buy.append([e["created_at"].strftime("%Y-%m-%d"), e["who"], art.get(e["article"], e["article"]), e["cat"],
                    f"№ {e['deal_id']}" if e["deal_id"] else (e["obj"] if e["object_id"] else ""), float(e["amount"]),
                    "свои" if e["paid_by"] == "own" else "компании",
                    {"submitted": "ждёт проверки", "approved": "принято", "rejected": "отказ"}.get(e["status"], e["status"]),
                    {"to_pay": "к выплате", "paid": "выплачено"}.get(e["payout_status"], "")])
    prj = [["Месяц", "Сделка", "Объект", "Город", "Модель", "Категория", "Услуга", "Источник", "ИП", "Конец работ", "Выручка с НДС",
            "Получено", "Долг"]]
    for r in conn.execute("SELECT * FROM fin_projects WHERE year=%s ORDER BY month, closed NULLS LAST, row_no", (year,)).fetchall():
        prj.append([MONTHS[r["month"] - 1], r["deal_id"] or "", r["title"], r["city"], r["model"], r["category"], r["service"], r["source"],
                    r["ip"], str(r["closed"] or ""), float(r["revenue"]), float(r["received"]), float(r["debt"])])
    return {"Сводка": sv, "Проекты": prj, "Движение денег": led, "ФОТ": pay, "Закупки": buy}


def write(sheet_id: str, tabs: dict[str, list[list]]):
    import httpx
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(settings.google_sa_file,
                                                                  scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(Request())
    h = {"Authorization": f"Bearer {creds.token}"}
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    meta = httpx.get(base, params={"fields": "sheets.properties.title"}, headers=h, timeout=30)
    if meta.status_code == 403:
        raise RuntimeError("таблица витрины не открыта сервисному аккаунту на редактирование")
    meta.raise_for_status()
    have = {s["properties"]["title"] for s in meta.json().get("sheets", [])}
    add = [{"addSheet": {"properties": {"title": t}}} for t in tabs if t not in have]
    if add:
        httpx.post(f"{base}:batchUpdate", json={"requests": add}, headers=h, timeout=30).raise_for_status()
    httpx.post(f"{base}/values:batchClear", json={"ranges": [f"'{t}'!A:Z" for t in tabs]}, headers=h, timeout=30).raise_for_status()
    data = [{"range": f"'{t}'!A1", "values": [["" if v is None else v for v in row] for row in rows]} for t, rows in tabs.items()]
    httpx.post(f"{base}/values:batchUpdate", json={"valueInputOption": "RAW", "data": data}, headers=h, timeout=60).raise_for_status()


def run(year: int | None = None) -> dict:
    if not settings.fin_sheet_id:
        return {"ok": False, "detail": "таблица витрины ещё не задана (ARTGAME_FIN_SHEET_ID)"}
    year = year or date.today().year
    pays = None
    try:   # сначала оплаты клиентов из Битрикса — витрина видит их сразу
        with db.pool.connection() as conn, conn.transaction():
            pays = fin_bx.import_payments(conn)
    except Exception as ex:  # noqa: BLE001 — Битрикс недоступен: витрину всё равно обновляем
        pays = {"error": str(ex)[:200]}
    with db.pool.connection() as conn:
        hist = fin_history.run(conn)
    with db.pool.connection() as conn:
        head = conn.execute("SELECT * FROM people WHERE role_code='head' ORDER BY id LIMIT 1").fetchone() or {"id": None}
        tabs = build(conn, year, head)
    write(settings.fin_sheet_id, tabs)
    return {"ok": True, "rows": {t: len(r) - 1 for t, r in tabs.items()}, "bitrix": pays, "history": hist}


@router.post("/fin/export")
def export(p: dict = Depends(require_head)):
    try:
        return run()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"витрина не обновлена: {e}")


if __name__ == "__main__":   # таймер artgame-finexport@.service
    db.open_pool()
    print(run())
