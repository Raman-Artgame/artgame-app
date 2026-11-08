"""Оплаты клиентов из Битрикса → журнал денег (бывший FIN03 на ПК HEAD, 06.11.2026). Только чтение Битрикса.

МОП вносит поступления в сделку: «Поступление 1–4 — сумма / дата». Сервер раз в 15 минут (таймер витрины) переносит
каждое поступление с даты запуска учёта одной строкой прихода: source='bitrix', source_ref='deal:<ID>:pay<N>'.
Сумма или дата в сделке поменялась — старая строка отменяется, пишется новая. Счёт в Битриксе не указан:
по умолчанию Kaspi ИП Яковлев, HEAD меняет счёт в «Финансы → Деньги».
"""
import uuid
from datetime import date

from . import bx

START = date(2026, 11, 1)          # учёт в приложении ведётся с ноября 2026 (HEAD 06.11)
DESIGN = 13                        # воронка «Дизайн РК» — предоплата за дизайн
PAY = [(n, f"UF_CRM_ARTGAME_FIN03_PAY{n}_AMOUNT", f"UF_CRM_ARTGAME_FIN03_PAY{n}_DATE") for n in (1, 2, 3, 4)]


def _day(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


SELECT = ["ID", "TITLE", "CATEGORY_ID"] + [f for _, a, d in PAY for f in (a, d)]


def import_payments(conn, since: date = START, until: date | None = None, ids: list[int] | None = None,
                    account: str = "kaspi") -> dict:
    """Поступления сделок с датой в [since, until) → приходы журнала. ids — только эти сделки (история года по листу «Проекты»)."""
    if ids is not None:
        deals = []
        for i in range(0, len(ids), 50):
            deals += bx.read_all("crm.deal.list", {"filter": {"ID": ids[i:i + 50]}, "select": SELECT}, fresh=True)
    else:
        deals = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": list(bx.CATEGORIES), ">=DATE_MODIFY": since.isoformat()},
                                              "select": SELECT}, fresh=True)
    added = changed = 0
    for d in deals:
        did = int(d["ID"])
        for n, fa, fd in PAY:
            amount, day = bx._money(d.get(fa)), _day(d.get(fd))
            ref = f"deal:{did}:pay{n}"
            rows = conn.execute("SELECT * FROM fin_ledger WHERE source='bitrix' AND source_ref=%s ORDER BY id DESC", (ref,)).fetchall()
            old = next((r for r in rows if r["status"] == "active"), None)
            if (day and day < since) or (old and old["op_date"] < since) or (until and ((day and day >= until) or (old and old["op_date"] >= until))):
                continue   # чужой период: история не трогается текущим импортом и наоборот
            ok = amount > 0 and day is not None
            if ok and any(float(r["amount"]) == amount and r["op_date"] == day for r in rows) and (old is None or
                                                                                               (float(old["amount"]) == amount and old["op_date"] == day)):
                continue   # уже в журнале (или HEAD сам отменил эту строку — не возвращаем)
            acc = old["account_code"] if old else account
            if old:   # поменяли или убрали в сделке — старую строку отменяем
                conn.execute("UPDATE fin_ledger SET status='cancelled' WHERE id=%s", (old["id"],))
                changed += 1
            if not ok:
                continue
            conn.execute(
                """INSERT INTO fin_ledger (client_uid, op_date, account_code, direction, amount, article_code, period, deal_id, note, source, source_ref)
                   VALUES (%s,%s,%s,'in',%s,%s,%s,%s,%s,'bitrix',%s)""",
                (uuid.uuid4(), day, acc, amount, "design_prepay" if int(d.get("CATEGORY_ID") or 0) == DESIGN else "client_payment",
                 f"{day:%Y-%m}", did, f"{(d.get('TITLE') or '')[:120]} · поступление {n}", ref))
            added += 0 if old else 1
    return {"deals": len(deals), "added": added, "changed": changed}


# ── Проекты с ноября — из Битрикса (HEAD 08.11) ─────────────────────────────────────────────────────────────────────
DONE = ("UC_BMKDS4", "WON")        # «Оплата+закрывающие документы» (работы сданы) и «Оплата получена»
F_END = "UF_CRM_ARTGAME_PROJECT_END_ACTUAL"
P_SELECT = ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "MOVED_TIME", F_END, bx.CITY, bx.OBJECT,
            "UF_CRM_ARTGAME_FIN03_RECEIVED", "UF_CRM_ARTGAME_FIN03_DEBT"]
ROW0 = 1_000_000


def _entered(did: int, stage: str) -> date | None:
    """День, когда сделка попала на стадию (история стадий Битрикса)."""
    try:
        hist = bx._rows(bx.read("crm.stagehistory.list", {"entityTypeId": 2, "filter": {"OWNER_ID": did, "STAGE_ID": stage},
                                                         "order": {"ID": "ASC"}}, fresh=True))
    except Exception:  # noqa: BLE001
        return None
    return _day(hist[0].get("CREATED_TIME")) if hist else None


def end_of_works(d: dict) -> date | None:
    """Конец работ: «Окончание факт», иначе день перевода в «Оплата+закрывающие», иначе последнее движение по стадиям."""
    end = _day(d.get(F_END))
    if end:
        return end
    if d.get("STAGE_ID") == "WON":
        end = _entered(int(d["ID"]), "UC_BMKDS4")
    return end or _day(d.get("MOVED_TIME"))


def import_projects(conn, since: date = START) -> dict:
    """Сделки «1.1 Продажи РК», сданные с `since`, → fin_projects (origin='bitrix'). Сделки, что уже есть в листе, не берём."""
    in_sheet = {r["deal_id"] for r in conn.execute("SELECT DISTINCT deal_id FROM fin_projects WHERE origin='sheet' AND deal_id IS NOT NULL")}
    deals = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": [0], "STAGE_ID": list(DONE), ">=MOVED_TIME": since.isoformat()},
                                          "select": P_SELECT}, fresh=True)
    seen, added = [], 0
    for d in deals:
        did = int(d["ID"])
        end = end_of_works(d)
        if did in in_sheet or not end or end < since:
            continue
        row_no = ROW0 + did
        title = (d.get(bx.OBJECT) or "").strip() or str(d.get("TITLE") or "").split("·", 1)[-1].split("—")[0].strip()
        added += conn.execute(
            """INSERT INTO fin_projects (year, row_no, deal_id, month, closed, title, city, revenue, received, debt, origin, synced_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'bitrix', now())
               ON CONFLICT (year, row_no) DO UPDATE SET month=EXCLUDED.month, closed=EXCLUDED.closed, title=EXCLUDED.title,
                 city=EXCLUDED.city, revenue=EXCLUDED.revenue, received=EXCLUDED.received, debt=EXCLUDED.debt, synced_at=now()
               RETURNING (xmax = 0) AS ins""",
            (end.year, row_no, did, end.month, end, title, bx.city_name(d.get(bx.CITY)), bx._money(d.get("OPPORTUNITY")),
             bx._money(d.get("UF_CRM_ARTGAME_FIN03_RECEIVED")), bx._money(d.get("UF_CRM_ARTGAME_FIN03_DEBT")))).fetchone()["ins"]
        seen.append(row_no)
    # сделку вернули со стадии или перенесли в лист — убираем из копии
    conn.execute("DELETE FROM fin_projects WHERE origin='bitrix' AND closed >= %s AND NOT (row_no = ANY(%s))", (since, seen))
    return {"projects": len(seen), "added": added}
