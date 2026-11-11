"""Обращение на правку (HEAD 11.11): «если человек ошибся или не внёс вовремя — чтобы у него было обращение».

Сотрудник подаёт обращение: что (не внёс смену / расход, ошибка в смене / расходе), за какой день, почему, фото или чек.
Данные не меняются, пока HEAD не утвердил. Путь тот же, что у смен: сначала куратор (ГИП объекта или старший по зоне)
ставит оценку и пишет комментарий, потом HEAD утверждает или отклоняет. Обращения кураторов — сразу к HEAD.

Деньги: месяц открыт — исправление сразу в ФОТ этого месяца. Месяц раньше текущего (закрыт) не переоткрываем:
поздняя смена / чек считаются в ФОТ месяца утверждения (pay_ym), исправление уже принятой записи — строкой
«доначисление / удержание» (pay_delta). Подать можно не позже чем через 60 дней. Ничего не удаляется.
"""
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db, drive
from .work import (DIRECT_SQL, HAS_CUR_SQL, SHOP, TZ, WORKSHOP_ROLES, WORKSHOP_ZONES, Decision, RateIn, active, cats_for,
                   check_rate, check_zone, is_trip, overlap, review_filter, shift_role, stage_of, _photo)

router = APIRouter(prefix="/api")
MAX_DAYS = 60
KINDS = {"shift_late": "Не внёс смену", "expense_late": "Не внёс расход", "shift_fix": "Ошибка в смене", "expense_fix": "Ошибка в расходе"}


class AppealIn(BaseModel):
    client_uid: UUID
    kind: Literal["shift_late", "expense_late", "shift_fix", "expense_fix"]
    why: str = Field(min_length=5, max_length=2000)
    day: date | None = None
    target_id: int | None = None
    object_id: int = 0
    zone_code: str | None = None
    workshop: str | None = Field(default=None, max_length=60)
    role: str | None = None
    start_time: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")
    hours: float | None = Field(default=None, gt=0, le=48)
    area_m2: float | None = Field(default=None, ge=0)
    work_done: str | None = Field(default=None, max_length=2000)
    photo: str | None = Field(default=None, max_length=8_000_000)
    amount: float | None = Field(default=None, gt=0, le=100_000_000)
    category: str | None = None
    paid_by: Literal["own", "company"] = "own"
    note: str | None = Field(default=None, max_length=1000)
    receipt: str | None = Field(default=None, max_length=8_000_000)


def _hm(t: str | None, default: tuple[int, int] = (9, 0)) -> tuple[int, int]:
    if not t:
        return default
    h, m = (int(x) for x in t.split(":"))
    if h > 23 or m > 59:
        raise HTTPException(422, "Время начала — от 0:00 до 23:59")
    return h, m


def _today() -> date:
    return datetime.now(TZ).date()


def _check_day(day: date | None) -> date:
    if not day:
        raise HTTPException(400, "Укажи день")
    if day > _today():
        raise HTTPException(400, "День ещё не наступил")
    if day < _today() - timedelta(days=MAX_DAYS):
        raise HTTPException(400, f"Обращение — не позже чем через {MAX_DAYS} дней. Старше — напиши HEAD в «Чат»")
    return day


def ym(d) -> str:
    return f"{d:%Y-%m}"


def is_closed(day: date) -> bool:
    """Месяц раньше текущего — закрыт: прошлый ФОТ не переоткрываем (HEAD 11.11)."""
    from .finance import now_ym
    return ym(day) < now_ym()


def _hours(s: dict) -> float:
    return round((s["ended_at"] - s["started_at"]).total_seconds() / 3600, 2) if s["ended_at"] else 10.0


def _save_receipt(conn, p: dict, zone: str, object_id: int, amount: float, data_url: str) -> int:
    if not data_url.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "bad receipt")
    name = f"Чек {datetime.now():%Y-%m-%d %H-%M} {p['full_name']} {amount:.0f} (обращение)"
    try:
        drive_id = drive.save_receipt(conn, zone, name, data_url, deal_id=object_id or None)
    except Exception as ex:  # noqa: BLE001 — Диск недоступен: телефон повторит
        raise HTTPException(502, f"drive: {ex.__class__.__name__}")
    data, mime = drive.decode_data_url(data_url)
    return conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                           VALUES (gen_random_uuid(), %s, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                        (object_id, name, mime, len(data), drive_id, p["id"])).fetchone()["id"]


@router.post("/appeals")
def add_appeal(b: AppealIn, p: dict = Depends(active)):
    from psycopg.types.json import Jsonb
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM appeals WHERE client_uid=%s", (b.client_uid,)).fetchone()
        if dup:
            return out(conn, dup)
        data, old, target = {}, None, None
        if b.kind in ("shift_fix", "expense_fix"):
            t = "shifts" if b.kind == "shift_fix" else "expenses"
            target = conn.execute(f"SELECT * FROM {t} WHERE id=%s AND person_id=%s", (b.target_id, p["id"])).fetchone() if b.target_id else None
            if not target:
                raise HTTPException(404, "Запись не найдена")
            if target["status"] not in ("submitted", "approved", "rejected"):
                raise HTTPException(400, "Эту запись исправлять не нужно")
            if conn.execute("SELECT 1 FROM appeals WHERE kind=%s AND target_id=%s AND status='submitted'", (b.kind, b.target_id)).fetchone():
                raise HTTPException(409, "По этой записи обращение уже подано — дождись решения")
            at = target["started_at"] if t == "shifts" else target["created_at"]
            day = _check_day(at.astimezone(TZ).date())
            obj, zone = target["object_id"], target["zone_code"]
            if t == "shifts":
                old = {"start_time": f"{at.astimezone(TZ):%H:%M}", "hours": _hours(target),
                       "area_m2": float(target["area_m2"]) if target["area_m2"] is not None else None,
                       "work_done": target["work_done"], "status": target["status"]}
                data = {k: v for k, v in {"start_time": b.start_time, "hours": b.hours, "area_m2": b.area_m2,
                                          "work_done": (b.work_done or "").strip() or None}.items() if v is not None}
                if b.start_time:
                    _hm(b.start_time)
            else:
                old = {"amount": float(target["amount"]), "note": target["note"], "status": target["status"]}
                data = {k: v for k, v in {"amount": b.amount, "note": (b.note or "").strip() or None}.items() if v is not None}
            if not any(old.get(k) != v for k, v in data.items()) and target["status"] != "rejected":
                raise HTTPException(400, "Напиши, что исправить: новые часы, м², сумму или описание")
        elif b.kind == "shift_late":
            day = _check_day(b.day)
            shop = bool(b.workshop)
            obj, zone = (0 if shop else b.object_id), b.zone_code or ""
            if shop and (not set(p.get("roles") or [p["role_code"]]) & set(WORKSHOP_ROLES) or zone not in WORKSHOP_ZONES):
                raise HTTPException(400, "Мастерская без проекта — у печати")
            check_zone(conn, p, zone, obj, past=True)
            if not obj and not shop:
                raise HTTPException(400, "Смена — только на объекте")
            if not b.hours:
                raise HTTPException(400, "Сколько часов работал?")
            if len((b.work_done or "").strip()) < 3:
                raise HTTPException(400, "Напиши, что сделал")
            h, m = _hm(b.start_time)
            start = datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)
            if start + timedelta(hours=b.hours) > datetime.now(TZ) + timedelta(minutes=10):
                raise HTTPException(400, "Эта смена ещё не закончилась — внеси её на вкладке «Смена»")
            busy = overlap(conn, p["id"], start, start + timedelta(hours=b.hours))   # HEAD 11.11: несколько смен в день — без пересечений
            if busy:
                raise HTTPException(409, busy)
            if conn.execute("""SELECT 1 FROM appeals WHERE person_id=%s AND kind='shift_late' AND day=%s AND object_id=%s AND status='submitted'
                                 AND coalesce(data->>'start_time','') = %s""", (p["id"], day, obj, f"{h}:{m:02d}")).fetchone():
                raise HTTPException(409, "Такое обращение уже подано — дождись решения")
            data = {"start_time": f"{h}:{m:02d}", "hours": b.hours, "area_m2": None if shop else b.area_m2, "work_done": b.work_done.strip(),
                    "workshop": b.workshop.strip() if shop else None, "role": shift_role(p, zone, b.role)}
            if b.photo and not shop:
                data["photo_id"] = _photo(conn, p, obj, b.client_uid, "appeal", b.photo, "по обращению")
        else:   # expense_late
            day = _check_day(b.day)
            obj, zone = b.object_id, b.zone_code or ""
            check_zone(conn, p, zone, obj, past=True)
            if not b.amount:
                raise HTTPException(400, "Укажи сумму")
            if b.category not in {c["code"] for c in cats_for(conn, p["role_code"])}:
                raise HTTPException(400, "bad category")
            data = {"amount": b.amount, "category": b.category, "paid_by": b.paid_by, "note": (b.note or "").strip() or None}
            if b.receipt:
                data["receipt_file_id"] = _save_receipt(conn, p, zone, obj, b.amount, b.receipt)
        row = conn.execute("""INSERT INTO appeals (client_uid, person_id, kind, target_id, object_id, zone_code, day, why, data, old)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                           (b.client_uid, p["id"], b.kind, b.target_id if target else None, obj, zone, day, b.why.strip(),
                            Jsonb(data), Jsonb(old) if old else None)).fetchone()
        db.audit(conn, p["id"], "appeal_add", "appeals", row["id"], {"kind": b.kind, "day": day.isoformat()})
        return out(conn, row)


def out(conn, a: dict) -> dict:
    """Обращение для экрана: подписи, фото, чек, что было → что станет."""
    from .files import sign
    a = dict(a)
    a["kind_title"] = KINDS[a["kind"]]
    if "object_title" not in a:
        o = conn.execute("SELECT title FROM objects WHERE id=%s", (a["object_id"],)).fetchone()
        a["object_title"] = o["title"] if o else ""
    d = a["data"] or {}
    if a["object_id"] == 0 and (d.get("workshop") or a["zone_code"] == "print"):
        a["object_title"] = SHOP + (f" · {d['workshop']}" if d.get("workshop") else "")
    a["photo_url"] = sign(d["photo_id"], "thumb") if d.get("photo_id") else None
    a["photo_full"] = sign(d["photo_id"], "content") if d.get("photo_id") else None
    a["receipt_url"] = sign(d["receipt_file_id"], "content") if d.get("receipt_file_id") else None
    if d.get("category"):
        c = conn.execute("SELECT title FROM expense_categories WHERE code=%s", (d["category"],)).fetchone()
        a["category_title"] = c["title"] if c else d["category"]
    return a


@router.get("/appeals/my")
def my_appeals(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT a.*, cb.full_name AS cur_name FROM appeals a LEFT JOIN people cb ON cb.id=a.cur_by
                               WHERE a.person_id=%s ORDER BY a.created_at DESC LIMIT 50""", (p["id"],)).fetchall()
        return [out(conn, a) for a in rows]


@router.post("/appeals/{aid}/cancel")
def cancel_appeal(aid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("UPDATE appeals SET status='cancelled' WHERE id=%s AND person_id=%s AND status='submitted' RETURNING id",
                            (aid, p["id"])).fetchone():
            raise HTTPException(409, "not cancellable")
        db.audit(conn, p["id"], "appeal_cancel", "appeals", aid)
    return {"ok": True}


def review_appeals(conn, p: dict) -> list[dict]:
    """Обращения на проверке: куратору — ещё не оценённые у младших, HEAD — все (с этапом, как у смен)."""
    cond, args = review_filter(p)
    rows = conn.execute(f"""SELECT x.*, o.title AS object_title, pe.full_name AS person_name, pe.role_code AS person_role,
                                   cb.full_name AS cur_name, {DIRECT_SQL} AS direct, {HAS_CUR_SQL} AS has_cur
                            FROM appeals x JOIN objects o ON o.id=x.object_id JOIN people pe ON pe.id=x.person_id
                            LEFT JOIN people cb ON cb.id=x.cur_by
                            WHERE x.status='submitted' AND {cond} ORDER BY x.created_at""", args).fetchall()
    res = []
    for a in rows:
        a = out(conn, a)
        a["stage"] = stage_of(a)
        a["closed"] = is_closed(a["day"])
        res.append(a)
    return res


@router.post("/appeals/{aid}/rate")
def rate_appeal(aid: int, b: RateIn, p: dict = Depends(active)):
    """Куратор: оценка (не внёс смену — звёзды; остальное — «верно / есть вопрос») и комментарий. Решает HEAD."""
    if p["role_code"] == "head":
        raise HTTPException(400, "HEAD утверждает сразу")
    cond, args = review_filter(p)
    with db.pool.connection() as conn, conn.transaction():
        a = conn.execute(f"SELECT x.* FROM appeals x JOIN objects o ON o.id=x.object_id WHERE x.id=%s AND x.status='submitted' AND {cond}",
                         [aid, *args]).fetchone()
        if not a:
            raise HTTPException(403, "оценить можно обращение младшего, ещё без оценки")
        note = check_rate(a["kind"], b)
        conn.execute("UPDATE appeals SET cur_by=%s, cur_at=now(), cur_stars=%s, cur_ok=%s, cur_note=%s WHERE id=%s",
                     (p["id"], b.stars if a["kind"] == "shift_late" else None, b.ok if a["kind"] != "shift_late" else None, note, aid))
        db.audit(conn, p["id"], "appeal_rate", "appeals", aid, {"stars": b.stars, "ok": b.ok, "note": note})
    return {"ok": True}


@router.post("/appeals/{aid}/decide")
def decide(aid: int, d: Decision, p: dict = Depends(active)):
    """HEAD утверждает (запись появляется / исправляется) или отклоняет с причиной."""
    if p["role_code"] != "head":
        raise HTTPException(403, "утверждает HEAD")
    if not d.approve and not (d.reason or "").strip():
        raise HTTPException(400, "reason required")
    from .finance import now_ym, one_shift_pay, vals
    with db.pool.connection() as conn, conn.transaction():
        a = conn.execute("SELECT * FROM appeals WHERE id=%s AND status='submitted' FOR UPDATE", (aid,)).fetchone()
        if not a:
            raise HTTPException(409, "обращение уже решено")
        if not d.approve:
            conn.execute("UPDATE appeals SET status='rejected', reason=%s, checked_by=%s, checked_at=now() WHERE id=%s", (d.reason, p["id"], aid))
            db.audit(conn, p["id"], "appeal_rejected", "appeals", aid, {"reason": d.reason})
            return {"ok": True, "status": "rejected"}
        x, closed, cur = a["data"] or {}, is_closed(a["day"]), now_ym()
        pay_ym = cur if closed else None
        note = f"по обращению № {aid}"
        result, delta = None, None
        if a["kind"] == "shift_late":
            h, m = _hm(x.get("start_time"))
            start = datetime(a["day"].year, a["day"].month, a["day"].day, h, m, tzinfo=TZ)
            shop = bool(x.get("workshop"))
            result = conn.execute(
                """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, status, area_m2, work_done, photo_after,
                                       trip, role_code, backfill, kind, task, submitted_at, cur_by, cur_at, cur_stars, cur_note,
                                       checked_by, checked_at, reason, pay_ym, appeal_id)
                   VALUES (%s,%s,%s,%s,%s,%s,'approved',%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s) RETURNING id""",
                (uuid5(a["client_uid"], "shift"), a["person_id"], a["object_id"], a["zone_code"], start, start + timedelta(hours=float(x["hours"])),
                 x.get("area_m2"), x.get("work_done"), x.get("photo_id"), False if shop else is_trip(conn, a["person_id"], a["object_id"]),
                 x.get("role"), "workshop" if shop else "work", x.get("workshop"), a["submitted_at"], a["cur_by"], a["cur_at"], a["cur_stars"],
                 a["cur_note"], p["id"], note, pay_ym, aid)).fetchone()["id"]
        elif a["kind"] == "expense_late":
            own = x.get("paid_by", "own") == "own"
            result = conn.execute(
                """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, receipt_file_id, note, created_at,
                                         backfill, status, payout_status, submitted_at, cur_by, cur_at, cur_ok, cur_note, checked_by, checked_at,
                                         reason, pay_ym, appeal_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,'approved',%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s) RETURNING id""",
                (uuid5(a["client_uid"], "expense"), a["person_id"], a["object_id"], a["zone_code"], x["category"], x["amount"],
                 x.get("paid_by", "own"), x.get("receipt_file_id"), x.get("note"),
                 datetime(a["day"].year, a["day"].month, a["day"].day, 12, 0, tzinfo=TZ), "to_pay" if own else "none",
                 a["submitted_at"], a["cur_by"], a["cur_at"], a["cur_ok"], a["cur_note"], p["id"], note, pay_ym, aid)).fetchone()["id"]
        elif a["kind"] == "shift_fix":
            s = conn.execute("SELECT * FROM shifts WHERE id=%s FOR UPDATE", (a["target_id"],)).fetchone()
            st = s["started_at"].astimezone(TZ)
            h, m = _hm(x.get("start_time"), (st.hour, st.minute))
            start = st.replace(hour=h, minute=m, second=0, microsecond=0)
            end = start + timedelta(hours=float(x.get("hours") or _hours(s)))
            result = s["id"]
            if s["status"] != "approved" or not closed:   # месяц открыт или смена не была принята — правим саму смену
                conn.execute("""UPDATE shifts SET started_at=%s, ended_at=%s, area_m2=%s, work_done=%s, status='approved', checked_by=%s,
                                  checked_at=now(), reason=%s, appeal_id=%s, pay_ym=CASE WHEN %s THEN %s ELSE pay_ym END,
                                  cur_by=coalesce(cur_by, %s), cur_at=coalesce(cur_at, %s), cur_note=coalesce(cur_note, %s) WHERE id=%s""",
                             (start, end, x.get("area_m2", s["area_m2"]), x.get("work_done") or s["work_done"], p["id"], note, aid,
                              s["status"] != "approved" and closed, cur, a["cur_by"], a["cur_at"], a["cur_note"], s["id"]))
            else:   # принятая смена закрытого месяца: смену не трогаем, разница — строкой ФОТ текущего месяца
                v, role = vals(conn), s["role_code"] or (conn.execute("SELECT role_code FROM people WHERE id=%s", (s["person_id"],)).fetchone()["role_code"])
                delta = round(one_shift_pay(v, role, s["kind"], start, end)[0] - one_shift_pay(v, role, s["kind"], s["started_at"], s["ended_at"])[0], 2)
        else:   # expense_fix
            e = conn.execute("SELECT * FROM expenses WHERE id=%s FOR UPDATE", (a["target_id"],)).fetchone()
            amount = x.get("amount", float(e["amount"]))
            result = e["id"]
            if e["status"] != "approved" or (not closed and e["payout_status"] != "paid"):
                conn.execute("""UPDATE expenses SET amount=%s, note=%s, status='approved', checked_by=%s, checked_at=now(), reason=%s, appeal_id=%s,
                                  payout_status=CASE WHEN paid_by='own' AND payout_status<>'paid' THEN 'to_pay' ELSE payout_status END,
                                  pay_ym=CASE WHEN %s THEN %s ELSE pay_ym END WHERE id=%s""",
                             (amount, x.get("note", e["note"]), p["id"], note, aid, e["status"] != "approved" and closed, cur, e["id"]))
            else:   # уже выплачено или месяц закрыт: разница своих денег — строкой ФОТ текущего месяца
                delta = round(amount - float(e["amount"]), 2) if e["paid_by"] == "own" else 0
        conn.execute("""UPDATE appeals SET status='approved', reason=%s, checked_by=%s, checked_at=now(), result_id=%s, pay_ym=%s, pay_delta=%s
                        WHERE id=%s""", (d.reason, p["id"], result, cur if delta else pay_ym, delta, aid))
        db.audit(conn, p["id"], "appeal_approved", "appeals", aid, {"result": result, "delta": delta, "pay_ym": cur if delta else pay_ym})
    return {"ok": True, "status": "approved", "result_id": result, "pay_delta": delta}
