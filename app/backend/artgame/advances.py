"""Авансы с 15 по 20 число (HEAD 16.11: «Добавь возможность выплачивать авансы с 15-20 числа. Просто многим нужны авансы»;
выбор HEAD: «Без просьб, сам»).

С 15 по 20 в «Финансы → ФОТ» блок «Аванс»: каждый сотрудник приложения — сколько заработал за месяц на сегодня
(тот же онлайн-расчёт, что «Мои выплаты») и сколько уже выплачено. HEAD вписывает сумму (не больше «можно») и жмёт «Выплачено»:
переводом с чеком или наличными (сотрудник жмёт «Получил»). Выплата — строка ФОТ за этот месяц, поэтому в расчёте 5-го
и в «К выплате в понедельник» уже вычтена. Отдельной таблицы нет.
"""
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .deps import require_head
from .finance import GROUP_TITLE, TZ, _f, _receipt, add_ledger, compute, now_ym, sync_payees

router = APIRouter(prefix="/api")
DAY_FROM, DAY_TO = 15, 20   # окно аванса — слова HEAD 16.11


def today() -> date:
    return datetime.now(TZ).date()


def rows(conn, by: dict, ym: str, payee_id: int | None = None) -> list[dict]:
    """По каждому сотруднику: заработано за месяц на сегодня, выплачено, можно дать. Расчёт откатывается — ничего не пишет."""
    sync_payees(conn)
    pays = conn.execute("""SELECT f.* FROM fin_payees f JOIN people pe ON pe.id=f.person_id
                           WHERE f.status='active' AND pe.status='active' AND (%s::bigint IS NULL OR f.id=%s) ORDER BY f.grp, f.name""",
                        (payee_id, payee_id)).fetchall()
    if not pays:
        return []
    with conn.transaction(force_rollback=True):   # один пересчёт месяца на всех (как «К выплате в понедельник»)
        compute(conn, ym, by, only_person=[f["person_id"] for f in pays])
        acc = {r["payee_id"]: _f(r["s"]) for r in conn.execute(
            """SELECT payee_id, sum(amount) AS s FROM fin_accruals WHERE period=%s AND payee_id = ANY(%s) AND status='active'
               GROUP BY payee_id""", (ym, [f["id"] for f in pays])).fetchall()}
    paid = {r["payee_id"]: r for r in conn.execute(
        """SELECT payee_id, sum(amount) AS s, max(op_date) AS last FROM fin_ledger WHERE period=%s AND payee_id = ANY(%s)
           AND article_code='payroll' AND status='active' GROUP BY payee_id""", (ym, [f["id"] for f in pays])).fetchall()}
    out = []
    for f in pays:
        e, pd = acc.get(f["id"], 0.0), _f(paid.get(f["id"], {}).get("s"))
        if e <= 0 and pd <= 0:
            continue
        out.append({"payee_id": f["id"], "name": f["name"], "group": GROUP_TITLE[f["grp"]], "scheme": f["scheme"],
                    "weekly": f["pay_rule"] == "weekly", "earned": round(e, 2), "paid": round(pd, 2),
                    "max": max(0, int(e - pd)), "last_paid": paid.get(f["id"], {}).get("last")})
    return out


@router.get("/fin/advances")
def advances(p: dict = Depends(require_head)):
    d, ym = today(), now_ym()
    is_open = DAY_FROM <= d.day <= DAY_TO
    with db.pool.connection() as conn:
        r = rows(conn, p, ym) if is_open else []
    return {"open": is_open, "from": DAY_FROM, "to": DAY_TO, "month": ym, "rows": r, "max": sum(x["max"] for x in r)}


class PayIn(BaseModel):
    client_uid: UUID
    payee_id: int
    amount: float = Field(gt=0, le=100_000_000)
    account: str
    receipt: str | None = Field(default=None, max_length=8_000_000)


@router.post("/fin/advances/pay")
def pay(b: PayIn, p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM fin_ledger WHERE client_uid=%s", (b.client_uid,)).fetchone():
            return {"ok": True, "repeat": True}
        if not conn.execute("SELECT 1 FROM fin_accounts WHERE code=%s AND active", (b.account,)).fetchone():
            raise HTTPException(400, "нет такого счёта")
        d, ym = today(), now_ym()
        if not DAY_FROM <= d.day <= DAY_TO:
            raise HTTPException(409, f"Аванс — с {DAY_FROM} по {DAY_TO} число. В другие дни — «Отметить выплату» у человека в ФОТ")
        r = rows(conn, p, ym, b.payee_id)
        if not r:
            raise HTTPException(409, "У сотрудника за месяц ещё ничего не начислено")
        r = r[0]
        if b.amount > r["max"]:
            raise HTTPException(409, f"Можно не больше {r['max']:,.0f} ₸ — столько заработано и ещё не выплачено".replace(",", " "))
        with conn.transaction():
            fid = _receipt(conn, p, f"Аванс {d} {r['name']} {b.amount:.0f}", b.receipt) if b.receipt else None
            row = add_ledger(conn, p, client_uid=b.client_uid, op_date=d, account=b.account, direction="out", amount=b.amount,
                             article="payroll", period=ym, payee_id=r["payee_id"], note=f"Аванс: {r['name']} за {ym}",
                             source="app", receipt_file_id=fid)
            db.audit(conn, p["id"], "advance_pay", "fin_ledger", row["id"], {"payee": b.payee_id, "amount": b.amount, "max": r["max"]})
    return {"ok": True, "ledger": row["id"], "left": r["max"] - b.amount}
