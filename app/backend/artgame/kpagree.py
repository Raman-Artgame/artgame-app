"""«Клиент согласовал КП» (HEAD 26.11, схема «кто что заполняет»).

Цену и нормы МОП руками не вводит: калькулятор → «Записать в сделку» → КП. Когда клиент согласился, МОП жмёт
«Клиент согласовал КП»: сумма, сложность, смены, художники и срок закрепляются. Пересчитать можно только после
«Снять согласование» с причиной — снятие остаётся в истории и в ленте сделки Битрикса.
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import bx, bxw, db
from .work import active

router = APIRouter(prefix="/api")


def current(conn, deal_id: int) -> dict | None:
    r = conn.execute("""SELECT k.*, pp.full_name AS by_name FROM kp_agreed k JOIN people pp ON pp.id=k.agreed_by
                        WHERE k.deal_id=%s AND k.undone_at IS NULL""", (deal_id,)).fetchone()
    return r and {"total": float(r["total"]), "at": r["agreed_at"].isoformat(), "by": r["by_name"], **(r["data"] or {})}


def get(deal_id: int) -> dict | None:
    with db.pool.connection() as conn:
        return current(conn, deal_id)


def guard(deal_id: int, total: float | None) -> None:
    """Перед записью цены в сделку: согласованное КП не перезаписываем другой суммой."""
    a = get(deal_id)
    if a and total is not None and round(float(total)) != round(a["total"]):
        raise HTTPException(409, f"КП согласовано клиентом на {bxw._fmt(a['total'])}. Чтобы поменять цену, "
                                 "сначала «Снять согласование» в шаге «КП».")


@router.post("/bx/deals/{deal_id}/kp-agreed")
def agree(deal_id: int, p: dict = Depends(active)):
    d = bx._deal(p, deal_id, fresh=True)
    from .fill import saved_calc
    calc = saved_calc(deal_id)
    # закрепляем то, из чего собрано КП: сумму сохранённого расчёта (она же уходит в сделку «Записать в сделку»)
    total = float(((calc or {}).get("out") or {}).get("total") or d.get("OPPORTUNITY") or 0)
    if not calc or not total:
        raise HTTPException(400, "Сначала расчёт: шаг «Расчёт» → «Записать в сделку»")
    card = bx.deal_full(p, deal_id, False)
    if not any((f.get("title") or "").startswith("КП") for f in card.get("files") or []):
        raise HTTPException(400, "Сначала КП: шаг «КП» → скачать PDF, он ляжет в сделку")
    n = card.get("norm") or {}
    data = {"level": card.get("level") or "", "shifts": n.get("shifts"), "crew": n.get("crew"), "term": n.get("term"),
            "area": card.get("area")}
    with db.pool.connection() as conn, conn.transaction():
        if current(conn, deal_id):
            raise HTTPException(400, "КП уже согласовано")
        conn.execute("INSERT INTO kp_agreed (deal_id, total, data, agreed_by) VALUES (%s,%s,%s,%s)",
                     (deal_id, total, Jsonb(data), p["id"]))
        db.audit(conn, p["id"], "kp_agreed", "deal", deal_id, {"total": total, **data})
    bxw.write(p, deal_id, "КП согласовано", None, f"клиент согласовал КП на {bxw._fmt(total)} — сумма и нормы закреплены")
    return get(deal_id)


class UndoIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/bx/deals/{deal_id}/kp-agreed/undo")
def undo(deal_id: int, b: UndoIn, p: dict = Depends(active)):
    bx._deal(p, deal_id)
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("UPDATE kp_agreed SET undone_at=now(), undone_by=%s, undo_reason=%s WHERE deal_id=%s AND undone_at IS NULL RETURNING total",
                         (p["id"], b.reason.strip(), deal_id)).fetchone()
        if not r:
            raise HTTPException(404, "Согласования нет")
        db.audit(conn, p["id"], "kp_agreed_undo", "deal", deal_id, {"total": float(r["total"]), "reason": b.reason.strip()})
    bxw.write(p, deal_id, "согласование КП снято", None, f"снял согласование КП ({bxw._fmt(float(r['total']))}): {b.reason.strip()}")
    return {"ok": True}
