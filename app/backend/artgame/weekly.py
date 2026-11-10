"""Выплаты по понедельникам (HEAD 10.11): «расходы всех и оплату суппортам мы делаем каждый понедельник».

Каждый понедельник HEAD открывает «Финансы → ФОТ → К выплате в понедельник» и видит:
- Саппорты (получатель с графиком «weekly»): начислено по принятым сменам месяца (тот же расчёт, что «Мои выплаты»,
  онлайн), минус уже выплаченное. Прошлый месяц тоже, пока не закрыт.
- Все остальные: одобренные чеки «свои деньги», ещё не возмещённые («к выплате»).
«Выплачено» — строка ФОТ в журнале денег (статья payroll, за месяц начисления) и чеки → «выплачено».
Сотрудник видит статус у своих расходов и в «Мои выплаты». Месячный ФОТ это учитывает: выплаченное вычитается из «Осталось».
"""
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .deps import require_head
from .work import with_receipt
from .finance import TZ, _f, _receipt, add_ledger, compute, now_ym, sync_payees

router = APIRouter(prefix="/api")


def _prev(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _periods() -> list[str]:
    from .fin_bx import START
    cur = now_ym()
    return [x for x in (_prev(cur), cur) if x >= f"{START:%Y-%m}"]


def due(conn, by: dict, payee_id: int | None = None) -> list[dict]:
    """К выплате сейчас: по каждому получателю — строки по месяцам {ym, amount, what, expense_ids}."""
    sync_payees(conn)
    out = []
    payees = conn.execute("""SELECT f.*, pe.role_code FROM fin_payees f JOIN people pe ON pe.id=f.person_id
                             WHERE f.status='active' AND (%s::bigint IS NULL OR f.id=%s) ORDER BY f.name""", (payee_id, payee_id)).fetchall()
    for f in payees:
        lines = []
        if f["pay_rule"] == "weekly":
            for ym in _periods():
                with conn.transaction(force_rollback=True):
                    compute(conn, ym, by, only_person=f["person_id"])
                    acc = conn.execute("""SELECT kind, amount, ref FROM fin_accruals WHERE period=%s AND payee_id=%s AND status='active'""",
                                       (ym, f["id"])).fetchall()
                accrued = sum(_f(a["amount"]) for a in acc)
                paid = _f(conn.execute("""SELECT coalesce(sum(amount),0) AS s FROM fin_ledger WHERE period=%s AND payee_id=%s
                                          AND article_code='payroll' AND status='active'""", (ym, f["id"])).fetchone()["s"])
                left = round(accrued - paid, 2)
                if left >= 1:
                    exp = [int(a["ref"]) for a in acc if a["kind"] == "reimburse" and a["ref"]]
                    lines.append({"ym": ym, "amount": left, "what": "смены" + (" и чеки" if exp else ""), "expense_ids": exp})
        else:
            rows = conn.execute("""SELECT id, amount, to_char(created_at AT TIME ZONE 'Asia/Almaty', 'YYYY-MM') AS ym FROM expenses
                                   WHERE person_id=%s AND paid_by='own' AND status='approved' AND payout_status='to_pay'
                                   ORDER BY created_at""", (f["person_id"],)).fetchall()
            by_ym = {}
            for r in rows:
                x = by_ym.setdefault(r["ym"], {"ym": r["ym"], "amount": 0.0, "what": "чеки", "expense_ids": []})
                x["amount"] = round(x["amount"] + _f(r["amount"]), 2)
                x["expense_ids"].append(r["id"])
            lines = list(by_ym.values())
        if lines:
            out.append({"payee_id": f["id"], "person_id": f["person_id"], "name": f["name"], "role_code": f["role_code"],
                        "weekly": f["pay_rule"] == "weekly", "lines": lines, "total": round(sum(x["amount"] for x in lines), 2),
                        "checks": sum(len(x["expense_ids"]) for x in lines)})
    return out


def next_monday(d: date | None = None) -> date:
    d = d or datetime.now(TZ).date()
    return d + timedelta(days=(7 - d.weekday()) % 7)


@router.get("/fin/weekly")
def weekly(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        rows = due(conn, p)
        # что уже выплатили (HEAD 10.11: «как отслеживать, что уже оплатили»): последние выплаты с датой и чеком перевода
        paid = [with_receipt(x) for x in conn.execute(
            """SELECT l.id, l.op_date, l.amount, l.period, l.note, l.receipt_file_id, l.account_code, l.ack_at, f.name, a.title AS account
               FROM fin_ledger l JOIN fin_payees f ON f.id=l.payee_id JOIN fin_accounts a ON a.code=l.account_code
               WHERE l.article_code='payroll' AND l.status='active' AND l.op_date >= current_date - 45
               ORDER BY l.op_date DESC, l.id DESC LIMIT 60""").fetchall()]
    return {"monday": next_monday(), "rows": rows, "total": round(sum(r["total"] for r in rows), 2), "paid": paid}


class WeeklyPayIn(BaseModel):
    client_uid: uuid.UUID
    payee_id: int
    account: str
    op_date: date
    amount: float = Field(gt=0)    # сколько HEAD видел на экране — сверяем, чтобы не заплатить «не то»
    receipt: str | None = Field(default=None, max_length=8_000_000)   # чек перевода (скриншот из галереи), HEAD 10.11


@router.post("/fin/weekly/pay")
def weekly_pay(b: WeeklyPayIn, p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM fin_ledger WHERE client_uid=%s", (b.client_uid,)).fetchone():
            return {"ok": True, "repeat": True}
        if not conn.execute("SELECT 1 FROM fin_accounts WHERE code=%s AND active", (b.account,)).fetchone():
            raise HTTPException(400, "нет такого счёта")
        rows = due(conn, p, b.payee_id)
        if not rows:
            raise HTTPException(409, "к выплате ничего нет — уже выплачено?")
        r = rows[0]
        if abs(r["total"] - b.amount) >= 1:
            raise HTTPException(409, f"сумма изменилась: сейчас к выплате {r['total']:,.0f} ₸ — обновите экран".replace(",", " "))
        with conn.transaction():
            fid = _receipt(conn, p, f"Выплата {b.op_date} {r['name']} {r['total']:.0f}", b.receipt) if b.receipt else None
            ids = []
            for i, x in enumerate(r["lines"]):
                uid = b.client_uid if i == 0 else uuid.uuid5(b.client_uid, x["ym"])
                row = add_ledger(conn, p, client_uid=uid, op_date=b.op_date, account=b.account, direction="out", amount=x["amount"],
                                 article="payroll", period=x["ym"], payee_id=r["payee_id"],
                                 note=f"Понедельник: {r['name']}, {x['what']} за {x['ym']}", source="app", receipt_file_id=fid)
                ids.append(row["id"])
                if x["expense_ids"]:
                    conn.execute("UPDATE expenses SET payout_status='paid' WHERE payout_status='to_pay' AND id = ANY(%s)", (x["expense_ids"],))
            db.audit(conn, p["id"], "fin_weekly_pay", "fin_payees", r["payee_id"], {"amount": r["total"], "ledger": ids})
    return {"ok": True, "paid": r["total"], "ledger": ids}
