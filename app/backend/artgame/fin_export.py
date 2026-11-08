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
PROFIT = 12   # колонка «Прибыль до ИПН» в «Сводке»
ORDER = ["Сводка", "Проекты", "Движение денег", "ФОТ", "Закупки"]
# Оформление (HEAD 08.11: «красиво, в нашем стиле, поудобнее»): цвета приложения (tokens.css) — светлый фон, чёрная шапка,
# красный акцент. Для каждого листа: колонки денег, колонки дат, ширины. Применяется при каждой выгрузке, руками не держим.
LAYOUT = {
    "Сводка": {"money": range(1, 17), "date": (), "w": [110] + [125] * 16 + [360], "freeze_col": 1},
    "Проекты": {"money": (10, 11, 12), "date": (9,), "w": [90, 70, 260, 110, 60, 110, 140, 120, 110, 100, 125, 125, 115], "freeze_col": 3},
    "Движение денег": {"money": (3,), "date": (0,), "w": [95, 150, 95, 115, 190, 75, 70, 170, 280, 80, 85], "freeze_col": 1},
    "ФОТ": {"money": (3, 4, 5), "date": (6,), "w": [90, 200, 120, 115, 115, 115, 110, 420], "freeze_col": 2},
    "Закупки": {"money": (5,), "date": (0,), "w": [95, 170, 150, 170, 200, 110, 90, 110, 95], "freeze_col": 1},
}
C = {"dark": "#0B0B0D", "light": "#F1F0EC", "alt": "#F7F6F3", "white": "#FFFFFF", "line": "#DCDBD6", "accent": "#E60041",
     "ok": "#1F7A45", "okbg": "#E5F3EA", "hotbg": "#FBE4E8", "muted": "#6B6B70"}


def _rgb(h: str) -> dict:
    return {"red": int(h[1:3], 16) / 255, "green": int(h[3:5], 16) / 255, "blue": int(h[5:7], 16) / 255}


def _d(x):
    """Дата → число дней Google Таблиц (чтобы сортировалась и фильтровалась как дата)."""
    if not x:
        return ""
    if isinstance(x, str):
        x = date.fromisoformat(x[:10])
    return (x - date(1899, 12, 30)).days


def build(conn, year: int, head: dict) -> dict[str, list[list]]:
    """Строки листов за год. Месяцы до запуска (ноябрь 2026) остаются пустыми — история в старой таблице."""
    last = date.today().month if date.today().year == year else 12
    sv = [["Месяц", "Выручка с НДС", "НДС", "Без НДС", "На объекты (чеки)", "Склад", "Мастерская холстов", "Отдел продаж",
           "Материалы и транспорт (оценка, до ноября)", "ФОТ", "Постоянные", "Переменные", "Прибыль до ИПН", "ИПН (оценка)",
           "Приход денег", "Расход денег", "Остаток на конец", "Примечание"]]
    pay = [["Месяц", "Получатель", "Группа", "Начислено", "Выплачено", "Осталось", "Последняя выплата", "Из чего"]]
    for m in range(1, last + 1):
        ym = f"{year}-{m:02d}"
        s = finance.summary(ym, head)
        c, r = s["costs"], s["revenue"]
        sv.append([MONTHS[m - 1], r["gross"], r["vat"], r["net"], c["project"], c["stock"], c["canvas"], c["sales"], c.get("materials", 0),
                   c["payroll"], c["fixed"], c["variable"], s["profit"], s["ipn"], s["cash"]["in"], s["cash"]["out"],
                   sum(float(b["balance"]) for b in s["cash"]["closing"]),
                   "история: материалы — оценка старой таблицы, аренда/подписки/реклама — по нынешним ставкам «Значений»" if date(year, m, 1) < finance.HIST_CUT else ""])
        for x in (r for r in finance.payroll(ym, head)["rows"] if r["accrued"] or r["paid"]):   # без пустых строк
            pay.append([MONTHS[m - 1], x["name"], x["group"], x["accrued"], x["paid"], x["left"], _d(x["last_paid"]),
                        "; ".join(f"{a['detail'] or a['kind']}: {float(a['amount']):.0f}" for a in x["lines"])])
    if len(sv) > 1:   # итог года: суммы по колонкам, остаток — на конец последнего месяца
        tot = [sum(float(r[i] or 0) for r in sv[1:]) for i in range(1, 16)]
        sv.append([f"Итого {year}", *tot, sv[-1][16], ""])
    led = [["Дата", "Счёт", "Приход/расход", "Сумма", "Статья", "За месяц", "Сделка", "Получатель", "Комментарий", "Источник", "Статус"]]
    for l in conn.execute(
            """SELECT l.*, a.title AS art, ac.title AS acc, py.name AS payee FROM fin_ledger l JOIN fin_articles a ON a.code=l.article_code
               JOIN fin_accounts ac ON ac.code=l.account_code LEFT JOIN fin_payees py ON py.id=l.payee_id
               WHERE l.op_date >= %s AND l.op_date < %s ORDER BY l.op_date, l.id""", (date(year, 1, 1), date(year + 1, 1, 1))).fetchall():
        led.append([_d(l["op_date"]), l["acc"], KIND[l["direction"]], float(l["amount"]), l["art"], l["period"], l["deal_id"] or "",
                    l["payee"] or "", l["note"] or "", l["source"], "отменено" if l["status"] == "cancelled" else ""])
    buy = [["Дата", "Кто", "Статья", "Категория", "Объект / сделка", "Сумма", "Чьи деньги", "Статус", "Выплата"]]
    art = {"project": "На объект", "stock": "Склад", "canvas": "Мастерская холстов", "sales": "Отдел продаж"}
    for e in conn.execute(
            """SELECT e.*, c.title AS cat, c.article, pe.full_name AS who, o.title AS obj FROM expenses e
               JOIN expense_categories c ON c.code=e.category JOIN people pe ON pe.id=e.person_id JOIN objects o ON o.id=e.object_id
               WHERE e.created_at >= %s AND e.created_at < %s AND e.status <> 'cancelled' ORDER BY e.created_at""",
            (date(year, 1, 1), date(year + 1, 1, 1))).fetchall():
        buy.append([_d(e["created_at"].date()), e["who"], art.get(e["article"], e["article"]), e["cat"],
                    f"№ {e['deal_id']}" if e["deal_id"] else (e["obj"] if e["object_id"] else ""), float(e["amount"]),
                    "свои" if e["paid_by"] == "own" else "компании",
                    {"submitted": "ждёт проверки", "approved": "принято", "rejected": "отказ"}.get(e["status"], e["status"]),
                    {"to_pay": "к выплате", "paid": "выплачено"}.get(e["payout_status"], "")])
    prj = [["Месяц", "Сделка", "Объект", "Город", "Модель", "Категория", "Услуга", "Источник", "ИП", "Конец работ", "Выручка с НДС",
            "Получено", "Долг"]]
    for r in conn.execute("SELECT * FROM fin_projects WHERE year=%s ORDER BY month, closed NULLS LAST, row_no", (year,)).fetchall():
        prj.append([MONTHS[r["month"] - 1], r["deal_id"] or "", r["title"], r["city"], r["model"], r["category"], r["service"], r["source"],
                    r["ip"], _d(r["closed"]), float(r["revenue"]), float(r["received"]), float(r["debt"])])
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
    meta = httpx.get(base, params={"fields": "sheets(properties(sheetId,title),bandedRanges(bandedRangeId),conditionalFormats)"},
                     headers=h, timeout=30)
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
    meta = httpx.get(base, params={"fields": "sheets(properties(sheetId,title,gridProperties),bandedRanges(bandedRangeId),conditionalFormats)"},
                     headers=h, timeout=30).json()
    httpx.post(f"{base}:batchUpdate", json={"requests": style(meta.get("sheets", []), tabs)}, headers=h, timeout=60).raise_for_status()


def style(sheets: list[dict], tabs: dict[str, list[list]]) -> list[dict]:
    """Запросы оформления: старые полосы и условные правила снимаем и ставим заново — повторная выгрузка не копит их."""
    req, ids = [], {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheets}
    grid = {s["properties"]["title"]: s["properties"].get("gridProperties", {}) for s in sheets}
    for s in sheets:
        sid, title = s["properties"]["sheetId"], s["properties"]["title"]
        if title not in tabs:   # «Лист1» и прочие пустые — прячем (не удаляем)
            if len(ids) > len(tabs):
                req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "hidden": True}, "fields": "hidden"}})
            continue
        req += [{"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}} for b in s.get("bandedRanges", [])]
        req += [{"deleteConditionalFormatRule": {"sheetId": sid, "index": 0}} for _ in s.get("conditionalFormats", [])]
    for pos, title in enumerate(ORDER):
        if title not in ids or title not in tabs:
            continue
        sid, lay, rows = ids[title], LAYOUT[title], tabs[title]
        n, cols = max(len(rows), 2), len(rows[0])
        R = grid[title].get("rowCount", 1000)   # формат — на всю сетку листа (запись значений сама её расширяет)
        rng = lambda r0, r1, c0=0, c1=cols: {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1,  # noqa: E731
                                             "startColumnIndex": c0, "endColumnIndex": c1}
        req.append({"updateSheetProperties": {"properties": {"sheetId": sid, "index": pos, "tabColor": _rgb(C["accent"] if pos == 0 else C["dark"]),
                                                             "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": lay["freeze_col"],
                                                                                "hideGridlines": True}},
                                              "fields": "index,tabColor,gridProperties.frozenRowCount,gridProperties.frozenColumnCount,gridProperties.hideGridlines"}})
        # весь лист: шрифт, обычные строки
        req.append({"repeatCell": {"range": rng(0, R, 0, grid[title].get("columnCount", 26)), "cell": {"userEnteredFormat": {
            "textFormat": {"fontFamily": "Inter", "fontSize": 10, "bold": False, "foregroundColor": _rgb(C["dark"])},
            "verticalAlignment": "MIDDLE", "wrapStrategy": "CLIP", "backgroundColor": _rgb(C["white"])}},
            "fields": "userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy,userEnteredFormat.backgroundColor,userEnteredFormat.numberFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.borders"}})
        # шапка: чёрная, светлый жирный текст
        req.append({"repeatCell": {"range": rng(0, 1), "cell": {"userEnteredFormat": {
            "backgroundColor": _rgb(C["dark"]), "textFormat": {"fontFamily": "Inter", "fontSize": 10, "bold": True, "foregroundColor": _rgb(C["light"])},
            "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP", "horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy,userEnteredFormat.horizontalAlignment"}})
        req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                                                  "properties": {"pixelSize": 40}, "fields": "pixelSize"}})
        req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 1, "endIndex": R},
                                                  "properties": {"pixelSize": 26}, "fields": "pixelSize"}})
        for i, w in enumerate(lay["w"]):
            req.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                                      "properties": {"pixelSize": w}, "fields": "pixelSize"}})
        for c in lay["money"]:
            req.append({"repeatCell": {"range": rng(1, R, c, c + 1), "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "NUMBER", "pattern": '#,##0" ₸";[Red]-#,##0" ₸";"–"'}, "horizontalAlignment": "RIGHT"}},
                "fields": "userEnteredFormat.numberFormat,userEnteredFormat.horizontalAlignment"}})
        for c in lay["date"]:
            req.append({"repeatCell": {"range": rng(1, R, c, c + 1), "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "DATE", "pattern": "dd.mm.yyyy"}, "horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.numberFormat,userEnteredFormat.horizontalAlignment"}})
        # полосы через строку и тонкая линия снизу шапки
        body = n - 1 if title == "Сводка" else n   # строку «Итого» не красим полосами
        req.append({"addBanding": {"bandedRange": {"range": rng(1, body), "rowProperties": {
            "firstBandColorStyle": {"rgbColor": _rgb(C["white"])}, "secondBandColorStyle": {"rgbColor": _rgb(C["alt"])}}}}})
        req.append({"updateBorders": {"range": rng(1, n), "bottom": {"style": "SOLID", "colorStyle": {"rgbColor": _rgb(C["line"])}},
                                      "innerHorizontal": {"style": "SOLID", "colorStyle": {"rgbColor": _rgb(C["line"])}}}})
        req.append({"setBasicFilter": {"filter": {"range": rng(0, body)}}})
        if title == "Сводка":   # итог года — тёмная строка; прибыль: зелёная/красная
            req.append({"repeatCell": {"range": rng(n - 1, n), "cell": {"userEnteredFormat": {
                "backgroundColor": _rgb(C["dark"]), "textFormat": {"fontFamily": "Inter", "bold": True, "foregroundColor": _rgb(C["light"])}}},
                "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat"}})
            for kind, fg, bg in (("NUMBER_GREATER", C["ok"], C["okbg"]), ("NUMBER_LESS", C["accent"], C["hotbg"])):
                req.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(1, n - 1, PROFIT, PROFIT + 1)], "booleanRule": {
                    "condition": {"type": kind, "values": [{"userEnteredValue": "0"}]},
                    "format": {"backgroundColor": _rgb(bg), "textFormat": {"bold": True, "foregroundColor": _rgb(fg)}}}}}})
        if title == "Движение денег":   # расход — красным, отменённые — серым зачёркнутым
            req.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(1, n, 2, 4)], "booleanRule": {
                "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$C2="расход"'}]},
                "format": {"textFormat": {"foregroundColor": _rgb(C["accent"])}}}}}})
            req.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(1, n)], "booleanRule": {
                "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$K2="отменено"'}]},
                "format": {"textFormat": {"strikethrough": True, "foregroundColor": _rgb(C["muted"])}}}}}})
        if title in ("ФОТ", "Проекты"):   # долг / «осталось» больше нуля — красным
            c = 5 if title == "ФОТ" else 12
            req.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [rng(1, n, c, c + 1)], "booleanRule": {
                "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0"}]},
                "format": {"textFormat": {"bold": True, "foregroundColor": _rgb(C["accent"])}}}}}})
    return req


def run(year: int | None = None) -> dict:
    if not settings.fin_sheet_id:
        return {"ok": False, "detail": "таблица витрины ещё не задана (ARTGAME_FIN_SHEET_ID)"}
    year = year or settings.fin_sheet_year   # одна витрина — один год; в 2027 будет свой файл, 2026-й не затираем
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
