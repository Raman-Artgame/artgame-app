"""История 2026 года в базе приложения (HEAD 06.11.2026): январь–октябрь из старых таблиц, дальше — само.

- Проекты: лист «Проекты <год>» таблицы «Финансовый учёт 2026 (единый)» → fin_projects (копия, обновляется каждый запуск).
- Оплаты клиентов: поступления 1–4 сделок из листа → журнал денег на счёт «История (до ноября)».
- ФОТ: «ФОТ 2026» (лист на месяц, блок на человека: объекты, «Премия», «Оклад», «Аванс») → начисления и выплаты истории.
  Выплата: аванс — 15-го, остаток — 5-го следующего месяца (так платим); счёт «История».
Повторный запуск ничего не задваивает: всё по source_ref / ref. Пересчёт ФОТ в приложении историю не трогает.
"""
import re
import uuid
from datetime import date

from . import fin, fin_bx

FOT_ID = "1Ff_jEaYSl25PvIlgRNqw5wejCsVFCqonPBQVba2FJgw"
CUT = fin_bx.START                   # с ноября — живой учёт
YEAR = 2026
MONTHS = [m.capitalize() for m in fin.MONTHS]


def _num(v) -> float:
    return fin._num(v)


def import_projects(conn, year: int = YEAR) -> int:
    rows = fin.sheet_values(fin.SHEET_ID, f"Проекты {year}!A2:Q")
    n, seen = 0, []
    for i, r in enumerate(rows, start=2):
        r = list(r) + [""] * (17 - len(r))
        mon_name = str(r[1]).strip().lower()
        closed = fin._date(r[13])
        mon = int(closed[5:7]) if closed else (fin.MONTHS.index(mon_name) + 1 if mon_name in fin.MONTHS else 0)
        if not mon or not (str(r[0]).strip().isdigit() or str(r[2]).strip()):
            continue
        conn.execute(
            """INSERT INTO fin_projects (year, row_no, deal_id, month, closed, title, city, model, category, service, source, ip,
                                         revenue, received, debt, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (year, row_no) DO UPDATE SET deal_id=EXCLUDED.deal_id, month=EXCLUDED.month, closed=EXCLUDED.closed,
                 title=EXCLUDED.title, city=EXCLUDED.city, model=EXCLUDED.model, category=EXCLUDED.category, service=EXCLUDED.service,
                 source=EXCLUDED.source, ip=EXCLUDED.ip, revenue=EXCLUDED.revenue, received=EXCLUDED.received, debt=EXCLUDED.debt,
                 synced_at=now()""",
            (year, i, int(r[0]) if str(r[0]).strip().isdigit() else None, mon, closed or None, str(r[2]).strip(), str(r[3]).strip(),
             r[4] or None, r[5] or None, r[7] or None, r[8] or None, r[10] or None, _num(r[14]), _num(r[15]), _num(r[16])))
        n += 1
        seen.append(i)
    # строки, которых больше нет в листе, — убираем из копии (это зеркало листа, не учётные записи)
    conn.execute("DELETE FROM fin_projects WHERE year=%s AND NOT (row_no = ANY(%s))", (year, seen))
    return n


def import_client_payments(conn, year: int = YEAR) -> dict:
    ids = sorted({r["deal_id"] for r in conn.execute("SELECT deal_id FROM fin_projects WHERE year=%s AND deal_id IS NOT NULL",
                                                     (year,)).fetchall()})
    out = fin_bx.import_payments(conn, since=date(year, 1, 1), until=CUT, ids=ids, account="hist")
    return out


# ---------- ФОТ 2026 ----------

def _clean_name(s: str) -> str:
    """«Асель 15т» → «Асель», «Вова М 15т/20т» → «Вова М»."""
    return " ".join(w for w in str(s or "").split() if not re.search(r"\d", w)).strip()


def parse_fot(values: list[list]) -> list[dict]:
    """Блоки людей справа: шапка — имя в строке города (колонки G, K, O, …), ниже объекты, «Премия», «Оклад», «Аванс», «Итог»."""
    grid = [list(r) for r in values]
    width = max((len(r) for r in grid), default=0)
    cell = lambda i, j: str(grid[i][j]).strip() if i < len(grid) and j < len(grid[i]) and grid[i][j] is not None else ""  # noqa: E731
    people = []
    for i in range(len(grid)):
        if cell(i, 1).lower().startswith("аванс") and cell(i, 2).upper().startswith("ЗП"):   # строка города: «АСТАНА | Аванс | ЗП 1-5 …»
            city = cell(i, 0).capitalize()
            for j in range(6, width, 4):
                name = _clean_name(cell(i, j))
                if not name:
                    continue
                p = {"city": city, "name": name, "objects": [], "piece": 0.0, "bonus": 0.0, "salary": 0.0, "advance": 0.0}
                for k in range(i + 1, min(i + 25, len(grid))):
                    label, amt = cell(k, j), _num(cell(k, j + 1))
                    low = label.lower()
                    if low.startswith("итог") or low.startswith("остаток"):
                        break
                    if low.startswith("премия") or low.startswith("бонус"):
                        p["bonus"] += amt
                    elif low.startswith("аванс"):
                        p["advance"] += amt
                    elif low.startswith("оклад"):
                        p["salary"] += amt
                    elif label and amt:
                        p["piece"] += amt
                        p["objects"].append(f"{label} {amt:,.0f}".replace(",", " "))
                if p["piece"] or p["bonus"] or p["salary"] or p["advance"]:
                    people.append(p)
    return people


def _payee(conn, name: str, city: str) -> int:
    """Получатель по имени: точное совпадение, затем по первому слову имени человека в приложении, иначе — новый (ручной)."""
    row = conn.execute("SELECT id FROM fin_payees WHERE lower(name)=lower(%s) ORDER BY id LIMIT 1", (name,)).fetchone()
    if row:
        return row["id"]
    first = name.split()[0]
    cand = conn.execute("""SELECT f.id FROM fin_payees f WHERE f.person_id IS NOT NULL
                           AND (lower(split_part(f.name, ' ', 1)) = lower(%s) OR lower(f.name) LIKE lower(%s))""",
                        (first, name + "%")).fetchall()
    if len(cand) == 1:
        return cand[0]["id"]
    return conn.execute("""INSERT INTO fin_payees (name, grp, scheme, status, note) VALUES (%s, 'core', 'manual', 'archived', %s)
                           RETURNING id""",
                        (name, f"из «ФОТ 2026», {city}")).fetchone()["id"]


def import_payroll(conn, year: int = YEAR, by: int | None = None) -> dict:
    added, people = 0, 0
    for m, title in enumerate(MONTHS, start=1):
        ym = f"{year}-{m:02d}"
        if date(year, m, 1) >= CUT:
            break
        try:
            values = fin.sheet_values(FOT_ID, f"'{title}'!A1:AZ80")
        except RuntimeError:
            try:
                values = fin.sheet_values(FOT_ID, f"'{title} '!A1:AZ80")   # «Январь » с пробелом в конце
            except RuntimeError:
                continue
        for p in parse_fot(values):
            people += 1
            pid = _payee(conn, p["name"], p["city"])
            for kind, amount, detail in (("piece", p["piece"], "; ".join(p["objects"])[:500]), ("bonus", p["bonus"], "премия"),
                                         ("salary", p["salary"], "оклад")):
                ref = f"hist:{ym}:{p['city']}:{p['name']}:{kind}"
                if not amount or conn.execute("SELECT 1 FROM fin_accruals WHERE ref=%s AND status='active'", (ref,)).fetchone():
                    continue
                conn.execute("""INSERT INTO fin_accruals (period, payee_id, kind, amount, detail, ref, created_by)
                                VALUES (%s,%s,%s,%s,%s,%s,%s)""", (ym, pid, kind, amount, f"ФОТ 2026: {detail}", ref, by))
                added += 1
            total = p["piece"] + p["bonus"] + p["salary"]
            nxt = date(year + (m == 12), m % 12 + 1, 5)
            for n, amount, day in (("avans", min(p["advance"], total) if total else p["advance"], date(year, m, 15)),
                                   ("rest", max(total - p["advance"], 0), nxt)):
                ref = f"hist:{ym}:{p['city']}:{p['name']}:{n}"
                if amount <= 0 or conn.execute("SELECT 1 FROM fin_ledger WHERE source='import' AND source_ref=%s", (ref,)).fetchone():
                    continue
                conn.execute("""INSERT INTO fin_ledger (client_uid, op_date, account_code, direction, amount, article_code, period,
                                                        payee_id, note, source, source_ref, created_by)
                                VALUES (%s,%s,'hist','out',%s,'payroll',%s,%s,%s,'import',%s,%s)""",
                             (uuid.uuid4(), day, amount, ym, pid, "ФОТ 2026: " + ("аванс" if n == "avans" else "расчёт"), ref, by))
    return {"people_months": people, "added": added}


def run(conn, by: int | None = None) -> dict:
    out = {}
    for name, fn in (("projects", lambda: import_projects(conn)), ("payments", lambda: import_client_payments(conn)),
                     ("payroll", lambda: import_payroll(conn, by=by))):
        try:
            with conn.transaction():
                out[name] = fn()
        except Exception as ex:  # noqa: BLE001 — один источник недоступен: остальные всё равно грузим
            out[name] = {"error": str(ex)[:200]}
    return out
