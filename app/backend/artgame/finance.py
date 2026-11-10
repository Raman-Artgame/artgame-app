"""Финансы ARTGAME (HEAD 06.11.2026): с ноября весь доход и расход ведётся здесь, Google Таблица — витрина.

Три книги (миграция 012):
- fin_ledger — журнал денег: приход и расход по дате денег и счёту (Kaspi ИП Яковлев, наличные, переводы HEAD).
- fin_accruals — начисления ФОТ по месяцу: смены × ставка роли, бонусы печати, доплата до минимума, оклады,
  % МОП, возмещение своих денег по чекам. Выплату отмечает только HEAD (строка «Выплата людям» в журнале денег).
- expenses — чеки сотрудников: на объект (project), склад расходников (stock), мастерская холстов (canvas),
  отдел продаж (sales). Закупки на склад и в мастерскую — расход бюджета, не объекта (HEAD 06.11).
Все ставки, лимиты и план бюджета — из «Значений» (pay.*, fin.*). Чего в «Значениях» нет, не считаем и говорим об этом.
"""
import calendar
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import constants as consts
from . import db, drive
from .deps import require_head
from .work import active, with_receipt

HIST_CUT = date(2026, 11, 1)   # живой учёт с ноября 2026 (= fin_bx.START); раньше — история из старых таблиц

router = APIRouter(prefix="/api")
TZ = ZoneInfo("Asia/Almaty")

# Ставка смены по роли: (ключ смены 10 ч, ключ часа или None). Ключи — лист «Значения».
RATE = {"support": ("pay.support.shift", "pay.support.hour"), "artist": ("pay.artist.shift", "pay.artist.hour"),
        "artist_pro": ("pay.pro.shift", "pay.pro.hour"), "lead_artist": ("pay.chief.shift", "pay.chief.hour"),
        "print_operator": ("pay.print.operator", None), "print_master": ("pay.print.master", None),
        "carpenter": ("pay.carpenter.shift", "pay.carpenter.hour")}
# «Мастерская» без проекта (HEAD 09.11): печать — своя ставка в час из «Значений»; нет ключа — как обычная смена (с предупреждением)
WORKSHOP_RATE = {"print_master": "pay.print.master.workshop_hour", "print_operator": "pay.print.operator.workshop_hour"}
# Роли на окладе (HEAD 06–07.11): плотник, помощник и главный дизайнер — сумма из «Значений».
SALARY_ROLE = {"carpenter": "pay.carpenter.month", "designer_asst": "pay.design_assistant.month",
               "lead_designer": "pay.design.lead.month"}
MINIMUM = {"lead_artist": "pay.chief.min_month", "artist_pro": "pay.pro.min_month"}
GROUP = {"support": "support", "artist": "core", "artist_pro": "core", "lead_artist": "core", "print_operator": "print",
         "print_master": "print", "mop": "sales", "mop_vip": "sales", "carpenter": "workshop",
         "lead_designer": "core", "designer_asst": "core"}
GROUP_TITLE = {"core": "Основной состав", "support": "Саппорты", "print": "Печать", "sales": "Продажи", "workshop": "Мастерская",
               "office": "Офис", "marketing": "Маркетинг", "contractor": "Подрядчики"}
IN_KINDS = {"income", "opening"}


# ---------- общее ----------

def ym_of(d) -> str:
    return f"{d.year}-{d.month:02d}"


def bounds(ym: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in ym.split("-"))
        return date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "месяц в виде 2026-11")


def now_ym() -> str:
    return ym_of(datetime.now(TZ))


def vals(conn) -> dict:
    return {k: v for k, v in consts.latest(conn).items() if isinstance(v, (int, float))}


def _f(x) -> float:
    return float(x or 0)


# ---------- справочники ----------

@router.get("/fin/dict")
def fin_dict(_: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        return {"accounts": conn.execute("SELECT code, title FROM fin_accounts WHERE active ORDER BY sort").fetchall(),
                "articles": conn.execute("SELECT code, title, kind, plan_key FROM fin_articles WHERE active ORDER BY sort").fetchall(),
                "payees": conn.execute("SELECT id, name, grp FROM fin_payees WHERE status='active' ORDER BY grp, name").fetchall(),
                "groups": GROUP_TITLE}


# ---------- журнал денег ----------

class LedgerIn(BaseModel):
    client_uid: UUID
    op_date: date
    account: str
    amount: float = Field(gt=0, le=10_000_000_000)
    article: str
    period: str | None = None            # к какому месяцу относится; по умолчанию месяц даты
    to_account: str | None = None        # для перевода между своими счетами
    deal_id: int | None = Field(default=None, gt=0)
    payee_id: int | None = None
    note: str | None = Field(default=None, max_length=500)
    receipt: str | None = Field(default=None, max_length=8_000_000)


def _receipt(conn, p: dict, name: str, data_url: str, deal_id: int | None = None) -> int:
    if not data_url.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "Чек — фото jpeg или png")
    try:
        drive_id = drive.save_receipt(conn, "office", name, data_url, deal_id=deal_id)
    except Exception as ex:  # Диск недоступен — повторить позже
        raise HTTPException(502, f"drive: {ex.__class__.__name__}")
    data, mime = drive.decode_data_url(data_url)
    return conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                           VALUES (gen_random_uuid(), 0, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                        (name, mime, len(data), drive_id, p["id"])).fetchone()["id"]


def add_ledger(conn, p: dict, *, client_uid, op_date: date, account: str, direction: str, amount: float, article: str,
               period: str, deal_id=None, payee_id=None, expense_id=None, transfer_id=None, note=None,
               receipt_file_id=None, source="manual", source_ref=None) -> dict:
    return conn.execute(
        """INSERT INTO fin_ledger (client_uid, op_date, account_code, direction, amount, article_code, period, deal_id, payee_id,
                                   expense_id, transfer_id, note, receipt_file_id, source, source_ref, created_by)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (client_uid, op_date, account, direction, amount, article, period, deal_id, payee_id, expense_id, transfer_id,
         note, receipt_file_id, source, source_ref, p["id"])).fetchone()


@router.post("/fin/ledger")
def ledger_add(e: LedgerIn, p: dict = Depends(require_head)):
    """HEAD вносит операцию: аренда, реклама, остаток на начало, оплата клиента наличными, перевод между счетами."""
    period = e.period or ym_of(e.op_date)
    bounds(period)
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM fin_ledger WHERE client_uid=%s", (e.client_uid,)).fetchone()
        if dup:
            return dup
        art = conn.execute("SELECT * FROM fin_articles WHERE code=%s AND active", (e.article,)).fetchone()
        if not art:
            raise HTTPException(400, "нет такой статьи")
        accounts = {r["code"] for r in conn.execute("SELECT code FROM fin_accounts WHERE active")}
        if e.account not in accounts:
            raise HTTPException(400, "нет такого счёта")
        if art["kind"] == "payroll":
            raise HTTPException(400, "выплату людям отмечайте в «ФОТ», там видно, сколько осталось")
        if e.payee_id and not conn.execute("SELECT 1 FROM fin_payees WHERE id=%s", (e.payee_id,)).fetchone():
            raise HTTPException(400, "нет такого получателя")
        fid = _receipt(conn, p, f"{e.op_date} {art['title']} {e.amount:.0f}", e.receipt, e.deal_id) if e.receipt else None
        if art["kind"] == "transfer":
            if e.to_account not in accounts or e.to_account == e.account:
                raise HTTPException(400, "перевод: укажите другой счёт, куда")
            tid = uuid4()
            out = add_ledger(conn, p, client_uid=e.client_uid, op_date=e.op_date, account=e.account, direction="out", amount=e.amount,
                             article="transfer", period=period, transfer_id=tid, note=e.note, receipt_file_id=fid)
            add_ledger(conn, p, client_uid=uuid4(), op_date=e.op_date, account=e.to_account, direction="in", amount=e.amount,
                       article="transfer", period=period, transfer_id=tid, note=e.note)
            row = out
        else:
            direction = "in" if art["kind"] in IN_KINDS and e.article != "refund" else "out"
            row = add_ledger(conn, p, client_uid=e.client_uid, op_date=e.op_date, account=e.account, direction=direction,
                             amount=e.amount, article=e.article, period=period, deal_id=e.deal_id, payee_id=e.payee_id,
                             note=e.note, receipt_file_id=fid)
        db.audit(conn, p["id"], "fin_ledger_add", "fin_ledger", row["id"], {"article": e.article, "amount": e.amount})
        return row


@router.get("/fin/ledger")
def ledger_list(ym: str | None = None, _: dict = Depends(require_head)):
    start, end = bounds(ym or now_ym())
    with db.pool.connection() as conn:
        rows = conn.execute(
            """SELECT l.*, a.title AS article_title, a.kind, ac.title AS account_title, py.name AS payee_name, pe.full_name AS author
               FROM fin_ledger l JOIN fin_articles a ON a.code=l.article_code JOIN fin_accounts ac ON ac.code=l.account_code
               LEFT JOIN fin_payees py ON py.id=l.payee_id LEFT JOIN people pe ON pe.id=l.created_by
               WHERE l.op_date >= %s AND l.op_date < %s ORDER BY l.op_date DESC, l.id DESC""", (start, end)).fetchall()
    return [with_receipt(r) for r in rows]


@router.post("/fin/ledger/{item_id}/cancel")
def ledger_cancel(item_id: int, p: dict = Depends(require_head)):
    """Ошибочная операция: не удаляем, помечаем «отменено» (у перевода — обе строки)."""
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("UPDATE fin_ledger SET status='cancelled' WHERE id=%s AND status='active' RETURNING *", (item_id,)).fetchone()
        if not row:
            raise HTTPException(409, "уже отменено или нет такой")
        if row["transfer_id"]:
            conn.execute("UPDATE fin_ledger SET status='cancelled' WHERE transfer_id=%s", (row["transfer_id"],))
        if row["article_code"] == "payroll" and row["payee_id"]:
            conn.execute("""UPDATE expenses SET payout_status='to_pay' WHERE payout_status='paid' AND id IN
                            (SELECT ref::bigint FROM fin_accruals WHERE kind='reimburse' AND payee_id=%s AND period=%s AND status='active')""",
                         (row["payee_id"], row["period"]))
        db.audit(conn, p["id"], "fin_ledger_cancel", "fin_ledger", item_id)
    return {"ok": True}


class AccountIn(BaseModel):
    account: str


@router.post("/fin/ledger/{item_id}/account")
def ledger_account(item_id: int, b: AccountIn, p: dict = Depends(require_head)):
    """Счёт у прихода из Битрикса (там счёт не указан, по умолчанию Kaspi) или у ошибочной операции."""
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM fin_accounts WHERE code=%s AND active", (b.account,)).fetchone():
            raise HTTPException(400, "нет такого счёта")
        row = conn.execute("UPDATE fin_ledger SET account_code=%s WHERE id=%s AND status='active' AND transfer_id IS NULL RETURNING id",
                           (b.account, item_id)).fetchone()
        if not row:
            raise HTTPException(404, "операция не найдена")
        db.audit(conn, p["id"], "fin_ledger_account", "fin_ledger", item_id, {"account": b.account})
    return {"ok": True}


def balances(conn, upto: date | None = None) -> list[dict]:
    """Остаток по каждому счёту на конец дня upto (по умолчанию — сейчас)."""
    return conn.execute(
        """SELECT ac.code, ac.title, coalesce(sum(CASE WHEN l.direction='in' THEN l.amount ELSE -l.amount END), 0) AS balance
           FROM fin_accounts ac LEFT JOIN fin_ledger l ON l.account_code=ac.code AND l.status='active' AND (%s::date IS NULL OR l.op_date < %s::date)
           WHERE ac.active GROUP BY ac.code, ac.title, ac.sort ORDER BY ac.sort""", (upto, upto)).fetchall()


# ---------- получатели ФОТ ----------

class PayeeIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    grp: str
    scheme: str = "salary"
    amount: float | None = Field(default=None, ge=0)
    amount_key: str | None = None
    pay_rule: str = "month"
    note: str | None = None
    status: str = "active"


def sync_payees(conn) -> int:
    """Каждый активный человек приложения с ролью — получатель (кроме HEAD). Новых добавляет, старых не трогает."""
    added = 0
    for pe in conn.execute("""SELECT p.id, p.full_name, p.role_code FROM people p LEFT JOIN fin_payees f ON f.person_id=p.id
                              WHERE f.id IS NULL AND p.status='active' AND p.role_code IS NOT NULL AND p.role_code <> 'head'""").fetchall():
        mop = pe["role_code"] in ("mop", "mop_vip")
        key = SALARY_ROLE.get(pe["role_code"])
        conn.execute("""INSERT INTO fin_payees (person_id, name, grp, scheme, amount_key, pay_rule) VALUES (%s,%s,%s,%s,%s,%s)""",
                     (pe["id"], pe["full_name"], GROUP.get(pe["role_code"], "core"), "mop" if mop else "salary" if key else "shifts",
                      key, "weekly" if pe["role_code"] == "support" else "month"))
        added += 1
    return added


@router.get("/fin/payees")
def payees(p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        sync_payees(conn)
        return conn.execute("""SELECT f.*, pe.role_code FROM fin_payees f LEFT JOIN people pe ON pe.id=f.person_id
                               ORDER BY f.status, f.grp, f.name""").fetchall()


def _check_payee(b: PayeeIn):
    if b.grp not in GROUP_TITLE or b.scheme not in ("shifts", "salary", "mop", "manual") or b.pay_rule not in ("month", "weekly") \
            or b.status not in ("active", "archived"):
        raise HTTPException(400, "проверьте группу, схему и график выплат")


@router.post("/fin/payees")
def payee_add(b: PayeeIn, p: dict = Depends(require_head)):
    """Получатель без приложения: бухгалтер, SMM, подрядчик. Оклад — суммой или ключом «Значений»."""
    _check_payee(b)
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("""INSERT INTO fin_payees (name, grp, scheme, amount, amount_key, pay_rule, note)
                              VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                           (b.name.strip(), b.grp, b.scheme, b.amount, b.amount_key, b.pay_rule, b.note)).fetchone()
        db.audit(conn, p["id"], "fin_payee_add", "fin_payees", row["id"], b.model_dump())
        return row


@router.post("/fin/payees/{payee_id}")
def payee_edit(payee_id: int, b: PayeeIn, p: dict = Depends(require_head)):
    _check_payee(b)
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("""UPDATE fin_payees SET name=%s, grp=%s, scheme=%s, amount=%s, amount_key=%s, pay_rule=%s, note=%s, status=%s
                              WHERE id=%s RETURNING *""",
                           (b.name.strip(), b.grp, b.scheme, b.amount, b.amount_key, b.pay_rule, b.note, b.status, payee_id)).fetchone()
        if not row:
            raise HTTPException(404, "нет такого получателя")
        db.audit(conn, p["id"], "fin_payee_edit", "fin_payees", payee_id, b.model_dump())
        return row


# ---------- начисление ФОТ ----------

def role_title(conn, code: str) -> str:
    r = conn.execute("SELECT title FROM roles WHERE code=%s", (code,)).fetchone()
    return r["title"] if r else code


def _hm(x, default: str) -> tuple[int, int]:
    t = str(x if x not in (None, "") else default).strip().replace(".", ":")
    try:
        h, m = (t.split(":") + ["0"])[:2]   # «0:00», «0:00:00», «6»
        return int(float(h)) % 24, int(float(m or 0))
    except ValueError:
        return _hm(default, "0:00") if default != t else (0, 0)


def night_hours(v: dict, start: datetime, end: datetime | None) -> float:
    """Ночные часы смены — pay.night.from / pay.night.to из «Значений» (HEAD 10.11: как в «Значениях», 22:00–06:00), по времени Алматы."""
    if not end or end <= start or not v.get("pay.night.from") or not v.get("pay.night.to"):   # без ключей ночь не считаем
        return 0.0
    (fh, fm), (th, tm) = _hm(v.get("pay.night.from"), "22:00"), _hm(v.get("pay.night.to"), "6:00")
    a, b = start.astimezone(TZ), end.astimezone(TZ)
    total, day = 0.0, (a - timedelta(days=1)).date()
    while datetime(day.year, day.month, day.day, tzinfo=TZ) <= b:
        n0 = datetime(day.year, day.month, day.day, fh, fm, tzinfo=TZ)
        n1 = datetime(day.year, day.month, day.day, th, tm, tzinfo=TZ)
        if n1 <= n0:
            n1 += timedelta(days=1)
        total += max(0.0, (min(b, n1) - max(a, n0)).total_seconds()) / 3600
        day += timedelta(days=1)
    return round(total, 2)


def shift_pay(v: dict, role: str, hours: float, night: float = 0.0) -> tuple[float, str]:
    """Оплата одной смены: полная смена (от 90 % нормы часов) — ставка смены, короче — по часу (или доля смены).
    Сверх нормы часов — каждый час по часовой ставке (правило «Переработка — по той же ставке»; HEAD 09.11: смены дольше 16 ч).
    Ночные часы — плюс pay.night % к часовой ставке (HEAD 09.11)."""
    keys = RATE.get(role)
    if not keys or not v.get(keys[0]):
        return 0.0, f"нет ставки {keys[0] if keys else 'для роли'} в «Значениях»"
    full = v.get("shift.hours", 10) or 10
    shift_rate = v[keys[0]]
    hour_rate = (v.get(keys[1]) if keys[1] else None) or shift_rate / full
    if hours >= full * 0.9:
        pay = float(shift_rate) + max(0.0, hours - full) * hour_rate
    else:
        pay = hours * hour_rate
    pay += min(night, hours) * hour_rate * (v.get("pay.night") or 0) / 100
    return round(pay, 2), ""


def company_revenue(y: int, m: int) -> tuple[float | None, str]:
    """Выручка компании за месяц (с НДС) — тот же источник, что у «Месяца» МОП: лист «Проекты <год>» по концу работ."""
    from . import fin
    try:
        return sum(r["sum"] for r in fin.month_rows(y, m)), ""
    except Exception as e:  # noqa: BLE001
        return None, f"выручка месяца не прочитана ({e}) — % МОП не начислен"


def mop_pay(v: dict, gross: float) -> tuple[float, float, float, int]:
    """% МОП по решению HEAD 03.11: ступень по всей выручке без НДС, процент от всей выручки, бонус за план на 3-й ступени."""
    net = gross / (1 + (v.get("vat") or 0) / 100)
    steps = [(v.get(f"pay.mop.step{i}.from") or 0, v.get(f"pay.mop.step{i}.pct") or 0) for i in (1, 2, 3)]
    step = max([i for i, (frm, _) in enumerate(steps, 1) if frm and net > frm] or [0])
    pct = steps[step - 1][1] if step else 0
    return round(net), round(net * pct / 100), (v.get("pay.mop.bonus_plan") or 0) if step == 3 else 0, step


def compute(conn, ym: str, by: dict, only_person: int | None = None) -> dict:
    """Пересчёт начислений месяца. Старые автоначисления помечаются «отменено», ручные остаются. Ничего не удаляется.
    only_person — пересчёт одного человека (онлайн-«Мои выплаты» в откатываемой транзакции, my_pay)."""
    start, end = bounds(ym)
    v = vals(conn)
    sync_payees(conn)
    warn: list[str] = []
    one = "" if only_person is None else " AND payee_id IN (SELECT id FROM fin_payees WHERE person_id=%s)"
    conn.execute("UPDATE fin_accruals SET status='cancelled' WHERE period=%s AND status='active' AND kind <> 'manual'" + one,
                 (ym,) if only_person is None else (ym, only_person))
    payees_ = conn.execute("""SELECT f.*, pe.role_code FROM fin_payees f LEFT JOIN people pe ON pe.id=f.person_id
                              WHERE f.status='active'""" + ("" if only_person is None else " AND f.person_id=%s"),
                           () if only_person is None else (only_person,)).fetchall()
    revenue, rev_warn = (None, "")
    if any(x["scheme"] == "mop" for x in payees_):
        revenue, rev_warn = company_revenue(start.year, start.month)
        if rev_warn:
            warn.append(rev_warn)

    def acc(pid, kind, amount, detail, ref=None):
        if amount:
            conn.execute("INSERT INTO fin_accruals (period, payee_id, kind, amount, detail, ref, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                         (ym, pid, kind, round(amount, 2), detail, ref, by["id"]))

    t0, t1 = datetime(start.year, start.month, 1, tzinfo=TZ), datetime(end.year, end.month, 1, tzinfo=TZ)
    from . import design
    units_by, cat_by, dwarn = design.accruals(conn, v, t0, t1)
    warn += dwarn
    from . import media
    reels_by, rwarn = media.reels_accruals(conn, v, t0, t1)
    warn += rwarn
    for f in payees_:
        role = f["role_code"]
        if f["scheme"] == "shifts" and f["person_id"]:
            shifts = conn.execute("""SELECT id, started_at, ended_at, bonus, kind, trip, role_code FROM shifts WHERE person_id=%s AND status='approved'
                                     AND started_at >= %s AND started_at < %s ORDER BY started_at""", (f["person_id"], t0, t1)).fetchall()
            piece, bonus, missing = 0.0, 0.0, ""
            by_role: dict[str, int] = {}
            for s in shifts:   # две роли (HEAD 08.11): каждая смена — по ставке своей роли
                hours = ((s["ended_at"] - s["started_at"]).total_seconds() / 3600) if s["ended_at"] else (v.get("shift.hours") or 10)
                r = s["role_code"] or role
                wk = WORKSHOP_RATE.get(r) if s["kind"] == "workshop" else None
                night = night_hours(v, s["started_at"], s["ended_at"])
                if wk and v.get(wk):
                    pay, miss = round(hours * v[wk] + min(night, hours) * v[wk] * (v.get("pay.night") or 0) / 100, 2), ""
                else:
                    pay, miss = shift_pay(v, r, hours, night)
                    if wk:
                        miss = f"нет ставки {wk} в «Значениях» — мастерская посчитана как смена"
                missing = miss or missing
                piece += pay
                bonus += _f(s["bonus"])
                by_role[r] = by_role.get(r, 0) + 1
            if shifts and missing:
                warn.append(f"{f['name']}: {missing}")
            roads = sum(s["kind"] == "road" for s in shifts)
            split = ", ".join(f"{role_title(conn, r)} {n}" for r, n in by_role.items()) if len(by_role) > 1 else ""
            acc(f["id"], "piece", piece, f"{len(shifts)} смен" + (f" ({split})" if split else "") + (f", из них дорога {roads}" if roads else ""),
                ",".join(str(s["id"]) for s in shifts))
            # суточные (HEAD 08.11): за каждый день со сменой или дорогой в командировке — pay.trip_food из «Значений»
            trip_days = sorted({s["started_at"].astimezone(TZ).date() for s in shifts if s["trip"]})
            if trip_days:
                food = v.get("pay.trip_food")
                if food:
                    acc(f["id"], "trip_food", food * len(trip_days), f"суточные {len(trip_days)} дн. × {food:,.0f} ₸".replace(",", " "))
                else:
                    warn.append(f"{f['name']}: {len(trip_days)} дн. командировки, но pay.trip_food в «Значениях» нет — суточные не начислены")
            acc(f["id"], "bonus", bonus, "бонус печати сверх плана")
            fixed = _f(f["amount"]) or (v.get(f["amount_key"]) or 0 if f["amount_key"] else 0)   # оклад сверх смен, если задан
            acc(f["id"], "salary", fixed, "оклад")
            minimum = v.get(MINIMUM.get(role, ""), 0)
            if minimum and piece + bonus + fixed < minimum:
                acc(f["id"], "topup", minimum - piece - bonus - fixed, f"доплата до минимума {minimum:,.0f} ₸".replace(",", " "))
        elif f["scheme"] == "salary":
            amount = _f(f["amount"]) or (v.get(f["amount_key"]) if f["amount_key"] else 0)
            if amount:
                acc(f["id"], "salary", amount, "оклад")
            else:
                warn.append(f"{f['name']}: оклад не задан (сумма или ключ «Значений»)")
        elif f["scheme"] == "mop":
            acc(f["id"], "salary", v.get("pay.mop.salary") or 0, "оклад МОП")
            if revenue is not None:
                net, pct_sum, plan, step = mop_pay(v, revenue)
                acc(f["id"], "mop_pct", pct_sum, f"ступень {step}, выручка без НДС {net:,.0f} ₸".replace(",", " "))
                acc(f["id"], "mop_bonus", plan, "бонус за план")
        if role == "lead_designer" and f["person_id"] and units_by.get(f["person_id"]):
            u, norm, rate = units_by[f["person_id"]], v.get("pay.design.norm_units"), v.get("pay.design.unit_over") or 0
            if norm is None:
                warn.append(f"{f['name']}: {u:g} ед. дизайна — норма pay.design.norm_units ждёт решения, сверх нормы не начислено")
            elif u > norm and rate:
                acc(f["id"], "design_units", (u - norm) * rate, f"{u - norm:g} ед. сверх нормы {norm:g} × {rate:,.0f} ₸".replace(",", " "))
        for amount, detail, ref in cat_by.get(f["person_id"], []) if f["person_id"] else []:
            acc(f["id"], "catalog", amount, detail, ref)
        if f["person_id"] in reels_by:   # рилс, утверждённые HEAD («Продакшн»)
            acc(f["id"], "reels", *reels_by[f["person_id"]])
        if f["person_id"]:   # свои деньги по одобренным чекам — к возмещению
            for e in conn.execute("""SELECT e.id, e.amount, c.title FROM expenses e JOIN expense_categories c ON c.code=e.category
                                     WHERE e.person_id=%s AND e.paid_by='own' AND e.status='approved' AND e.payout_status IN ('to_pay','paid')
                                       AND e.created_at >= %s AND e.created_at < %s""", (f["person_id"], t0, t1)).fetchall():
                acc(f["id"], "reimburse", _f(e["amount"]), f"чек: {e['title']}", str(e["id"]))
    if only_person is None:
        db.audit(conn, by["id"], "fin_payroll_compute", "fin_accruals", ym, {"warn": warn})
    return {"warn": warn}


@router.post("/fin/payroll/{ym}/compute")
def payroll_compute(ym: str, p: dict = Depends(require_head)):
    from .fin_bx import START
    if ym < f"{START:%Y-%m}":
        raise HTTPException(400, "до ноября 2026 ФОТ — история из «ФОТ 2026», пересчёт её не трогает")
    with db.pool.connection() as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('fin_compute'))")
        out = compute(conn, ym, p)
    return {**payroll(ym, p), **out}


@router.get("/fin/payroll/{ym}")
def payroll(ym: str, p: dict = Depends(require_head)):
    """Начислено, выплачено и осталось по каждому получателю за месяц."""
    bounds(ym)
    with db.pool.connection() as conn:
        pays = conn.execute("SELECT * FROM fin_payees ORDER BY grp, name").fetchall()
        accs = conn.execute("SELECT * FROM fin_accruals WHERE period=%s AND status='active' ORDER BY id", (ym,)).fetchall()
        paid = conn.execute("""SELECT payee_id, coalesce(sum(amount),0) AS s, max(op_date) AS last FROM fin_ledger
                               WHERE period=%s AND article_code='payroll' AND status='active' GROUP BY payee_id""", (ym,)).fetchall()
    paid_by = {r["payee_id"]: r for r in paid}
    rows = []
    for f in pays:
        lines = [a for a in accs if a["payee_id"] == f["id"]]
        accrued = sum(_f(a["amount"]) for a in lines)
        got = _f(paid_by.get(f["id"], {}).get("s"))
        if not lines and not got and f["status"] != "active":
            continue
        rows.append({"id": f["id"], "name": f["name"], "grp": f["grp"], "group": GROUP_TITLE[f["grp"]], "scheme": f["scheme"],
                     "pay_rule": f["pay_rule"], "lines": lines, "accrued": accrued, "paid": got,
                     "left": round(accrued - got, 2), "last_paid": paid_by.get(f["id"], {}).get("last")})
    return {"month": ym, "rows": rows, "accrued": sum(r["accrued"] for r in rows), "paid": sum(r["paid"] for r in rows),
            "left": sum(r["left"] for r in rows)}


class ManualIn(BaseModel):
    payee_id: int
    amount: float = Field(ge=-10_000_000, le=10_000_000)   # минус — удержание, ноль нельзя
    detail: str = Field(min_length=2, max_length=200)


@router.post("/fin/payroll/{ym}/accrual")
def payroll_manual(ym: str, b: ManualIn, p: dict = Depends(require_head)):
    """Премия, удержание, командировочные, разовая оплата подрядчику — вручную, с причиной."""
    bounds(ym)
    if not b.amount:
        raise HTTPException(400, "сумма не может быть нулём")
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM fin_payees WHERE id=%s", (b.payee_id,)).fetchone():
            raise HTTPException(404, "нет такого получателя")
        row = conn.execute("""INSERT INTO fin_accruals (period, payee_id, kind, amount, detail, created_by)
                              VALUES (%s,%s,'manual',%s,%s,%s) RETURNING *""", (ym, b.payee_id, b.amount, b.detail, p["id"])).fetchone()
        db.audit(conn, p["id"], "fin_accrual_manual", "fin_accruals", row["id"], b.model_dump())
        return row


@router.post("/fin/accruals/{acc_id}/cancel")
def accrual_cancel(acc_id: int, p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("UPDATE fin_accruals SET status='cancelled' WHERE id=%s AND kind='manual' AND status='active' RETURNING id", (acc_id,)).fetchone():
            raise HTTPException(409, "отменить можно только ручное начисление")
        db.audit(conn, p["id"], "fin_accrual_cancel", "fin_accruals", acc_id)
    return {"ok": True}


class PayIn(BaseModel):
    client_uid: UUID
    payee_id: int
    amount: float = Field(gt=0, le=100_000_000)
    account: str
    op_date: date
    note: str | None = Field(default=None, max_length=300)


@router.post("/fin/payroll/{ym}/pay")
def payroll_pay(ym: str, b: PayIn, p: dict = Depends(require_head)):
    """Только HEAD отмечает «выплачено»: строка в журнале денег. Когда месяц человека закрыт — его чеки «выплачено»."""
    bounds(ym)
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM fin_ledger WHERE client_uid=%s", (b.client_uid,)).fetchone()
        if dup:
            return dup
        f = conn.execute("SELECT * FROM fin_payees WHERE id=%s", (b.payee_id,)).fetchone()
        if not f:
            raise HTTPException(404, "нет такого получателя")
        if not conn.execute("SELECT 1 FROM fin_accounts WHERE code=%s AND active", (b.account,)).fetchone():
            raise HTTPException(400, "нет такого счёта")
        row = add_ledger(conn, p, client_uid=b.client_uid, op_date=b.op_date, account=b.account, direction="out", amount=b.amount,
                         article="payroll", period=ym, payee_id=b.payee_id, note=b.note or f"{f['name']} за {ym}", source="app")
        accrued = _f(conn.execute("SELECT coalesce(sum(amount),0) AS s FROM fin_accruals WHERE period=%s AND payee_id=%s AND status='active'",
                                  (ym, b.payee_id)).fetchone()["s"])
        paid = _f(conn.execute("""SELECT coalesce(sum(amount),0) AS s FROM fin_ledger WHERE period=%s AND payee_id=%s
                                  AND article_code='payroll' AND status='active'""", (ym, b.payee_id)).fetchone()["s"])
        if accrued and paid >= accrued:
            conn.execute("""UPDATE expenses SET payout_status='paid' WHERE payout_status='to_pay' AND id IN
                            (SELECT ref::bigint FROM fin_accruals WHERE kind='reimburse' AND payee_id=%s AND period=%s AND status='active')""",
                         (b.payee_id, ym))
        db.audit(conn, p["id"], "fin_pay", "fin_ledger", row["id"], {"payee": b.payee_id, "amount": b.amount, "period": ym})
        return {**row, "accrued": accrued, "paid": paid, "left": round(accrued - paid, 2)}


@router.get("/fin/my")
def my_pay(ym: str | None = None, p: dict = Depends(active)):
    """Каждый видит своё: начислено, выплачено, осталось (без чужих сумм)."""
    ym = ym or now_ym()
    bounds(ym)
    with db.pool.connection() as conn:
        f = conn.execute("SELECT * FROM fin_payees WHERE person_id=%s", (p["id"],)).fetchone()
        v = vals(conn)
        roles = p.get("roles") or [p["role_code"]]
        rate = my_rate(v, roles[0], f)
        if p.get("reels") and v.get("pay.reels") and not any(x["label"].startswith("Рилс") for x in rate):   # «Оплачиваемые рилс» (HEAD 09.11)
            rate.append({"label": "Рилс после утверждения HEAD" + (f" (до {v['pay.reels.max']:g} в месяц)" if v.get("pay.reels.max") else ""),
                         "amount": v["pay.reels"]})
        for r in roles[1:]:   # вторая роль (HEAD 08.11): её ставки — отдельными строками с названием роли
            t = role_title(conn, r)
            rate += [{**x, "label": f"{t} · {x['label']}"} for x in my_rate(v, r, None) if "Минимум" not in x["label"] and "Суточные" not in x["label"]]
        if len(roles) > 1:
            t0 = role_title(conn, roles[0])
            rate = [x if " · " in x["label"] else {**x, "label": f"{t0} · {x['label']}"} for x in rate]
        # онлайн (HEAD 09.11: «почему цифры не считаются»): начислено считается сразу по принятым сменам —
        # тот же compute, только для себя и в транзакции, которая откатывается; ФОТ месяца закрывает HEAD.
        from .fin_bx import START
        live = ym >= f"{START:%Y-%m}" and p["role_code"] != "head"
        lines = []
        if live:
            with conn.transaction(force_rollback=True):
                compute(conn, ym, p, only_person=p["id"])
                f = conn.execute("SELECT * FROM fin_payees WHERE person_id=%s", (p["id"],)).fetchone()
                if f:
                    lines = conn.execute("""SELECT kind, amount, detail FROM fin_accruals WHERE period=%s AND payee_id=%s AND status='active'
                                            ORDER BY id""", (ym, f["id"])).fetchall()
        if not f:
            return {"month": ym, "lines": [], "accrued": 0, "paid": 0, "left": 0, "rate": rate, "live": live}
        if not live:
            lines = conn.execute("""SELECT kind, amount, detail FROM fin_accruals WHERE period=%s AND payee_id=%s AND status='active' ORDER BY id""",
                                 (ym, f["id"])).fetchall()
        pays = conn.execute("""SELECT op_date, amount FROM fin_ledger WHERE period=%s AND payee_id=%s AND article_code='payroll'
                               AND status='active' ORDER BY op_date""", (ym, f["id"])).fetchall()
    accrued, paid = sum(_f(x["amount"]) for x in lines), sum(_f(x["amount"]) for x in pays)
    return {"month": ym, "lines": lines, "payments": pays, "accrued": accrued, "paid": paid, "left": round(accrued - paid, 2), "rate": rate, "live": live}


def my_rate(v: dict, role: str | None, f: dict | None) -> list[dict]:
    """Своя ставка из «Значений» строками для «Мои» (таблицу всех ставок не показываем)."""
    out = []
    if f and f["scheme"] == "salary" or not f and role in SALARY_ROLE:
        amount = _f(f["amount"]) if f else 0
        amount = amount or v.get((f or {}).get("amount_key") or SALARY_ROLE.get(role, ""))
        if amount:
            out.append({"label": "Оклад в месяц", "amount": amount})
    elif f and f["scheme"] == "mop" or role in ("mop", "mop_vip"):
        if v.get("pay.mop.salary"):
            out.append({"label": "Оклад МОП", "amount": v["pay.mop.salary"]})
    else:
        keys = RATE.get(role)
        if keys and v.get(keys[0]):
            out.append({"label": f"Смена {v.get('shift.hours', 10):g} ч", "amount": v[keys[0]]})
        if keys and keys[1] and v.get(keys[1]):
            out.append({"label": "Час (смена короче)", "amount": v[keys[1]]})
        if v.get(MINIMUM.get(role, "")):
            out.append({"label": "Минимум в месяц", "amount": v[MINIMUM[role]]})
        if keys and v.get("pay.trip_food"):   # командировка (HEAD 08.11): дорога — как смена, плюс суточные
            out.append({"label": "Суточные в командировке, за день", "amount": v["pay.trip_food"]})
    if role in WORKSHOP_RATE and v.get(WORKSHOP_RATE[role]):
        out.append({"label": "Мастерская без проекта, в час", "amount": v[WORKSHOP_RATE[role]]})
    if role == "lead_designer":
        if v.get("pay.design.unit_over"):
            out.append({"label": "Единица дизайна сверх нормы", "amount": v["pay.design.unit_over"]})
    if role in ("lead_artist", "artist_pro", "print_master") and v.get("pay.reels"):
        out.append({"label": "Рилс после утверждения HEAD" + (f" (до {v['pay.reels.max']:g} в месяц)" if v.get("pay.reels.max") else ""),
                    "amount": v["pay.reels"]})
    if role in ("lead_designer", "designer_asst") and v.get("pay.design.catalog"):
        out.append({"label": "Каталог референсов (двоим — пополам)", "amount": v["pay.design.catalog"]})
    return out


# ---------- сводка месяца ----------

@router.get("/fin/summary")
def summary(ym: str | None = None, p: dict = Depends(require_head)):
    """Прибыль месяца (начисления) и деньги месяца (журнал). Выручка — по концу работ, деньги — по дате оплаты."""
    ym = ym or now_ym()
    start, end = bounds(ym)
    t0, t1 = datetime(start.year, start.month, 1, tzinfo=TZ), datetime(end.year, end.month, 1, tzinfo=TZ)
    warn = []
    with db.pool.connection() as conn:
        v = vals(conn)
        gross, w = company_revenue(start.year, start.month)
        if w:
            warn.append(w.replace(" — % МОП не начислен", ""))
        # чеки сотрудников по статьям: на объект, склад, мастерская холстов, отдел продаж
        exp = {r["article"]: _f(r["s"]) for r in conn.execute(
            """SELECT c.article, sum(e.amount) AS s FROM expenses e JOIN expense_categories c ON c.code=e.category
               WHERE e.status='approved' AND e.created_at >= %s AND e.created_at < %s GROUP BY c.article""", (t0, t1)).fetchall()}
        led = conn.execute("""SELECT l.article_code, a.kind, a.title, a.plan_key, l.direction, sum(l.amount) AS s FROM fin_ledger l
                              JOIN fin_articles a ON a.code=l.article_code WHERE l.status='active' AND l.period=%s
                              GROUP BY l.article_code, a.kind, a.title, a.plan_key, l.direction""", (ym,)).fetchall()
        payroll_acc = _f(conn.execute("SELECT coalesce(sum(amount),0) AS s FROM fin_accruals WHERE period=%s AND status='active'",
                                      (ym,)).fetchone()["s"])
        reimb = _f(conn.execute("SELECT coalesce(sum(amount),0) AS s FROM fin_accruals WHERE period=%s AND status='active' AND kind='reimburse'",
                                (ym,)).fetchone()["s"])
        cash = conn.execute("""SELECT a.kind, l.article_code, a.title, l.direction, sum(l.amount) AS s FROM fin_ledger l
                               JOIN fin_articles a ON a.code=l.article_code WHERE l.status='active' AND l.op_date >= %s AND l.op_date < %s
                                 AND a.kind <> 'transfer' GROUP BY a.kind, l.article_code, a.title, l.direction ORDER BY a.kind""",
                            (start, end)).fetchall()
        company_paid = _f(conn.execute("""SELECT coalesce(sum(e.amount),0) AS s FROM expenses e WHERE e.status='approved'
                                          AND e.paid_by='company' AND e.created_at >= %s AND e.created_at < %s""", (t0, t1)).fetchone()["s"])
        opening, closing = balances(conn, start), balances(conn, end)
        plans = conn.execute("SELECT code, title, kind, plan_key FROM fin_articles WHERE plan_key IS NOT NULL AND active ORDER BY sort").fetchall()
        hist = start < HIST_CUT   # до ноября 2026: расходы проектов — оценки старой таблицы «Проекты 2026»
        hist_mat = _f(conn.execute("""SELECT coalesce(sum(materials + transport + other), 0) AS s FROM fin_projects
                                      WHERE year=%s AND month=%s""", (start.year, start.month)).fetchone()["s"]) if hist else 0.0
    vat_pct = v.get("vat") or 0
    net = gross / (1 + vat_pct / 100) if gross is not None else None
    budget = {}
    for r in led:
        if r["kind"] in ("fixed", "variable", "tax"):
            budget.setdefault(r["article_code"], {"title": r["title"], "kind": r["kind"], "fact": 0.0, "plan": None})
            budget[r["article_code"]]["fact"] += _f(r["s"]) * (1 if r["direction"] == "out" else -1)
    for a in plans:
        b = budget.setdefault(a["code"], {"title": a["title"], "kind": a["kind"], "fact": 0.0, "plan": None})
        plan = v.get(a["plan_key"])
        if plan and a["plan_key"].endswith("_year"):
            plan = round(plan / 12)
        elif plan and a["plan_key"].endswith("_day"):      # ₸ в день × дней в месяце
            plan = round(plan * (end - start).days)
        b["plan"] = plan
    if net is not None and v.get("fin.var.ads_pct"):
        budget.setdefault("ads", {"title": "Реклама", "kind": "variable", "fact": 0.0, "plan": None})["plan"] = round(net * v["fin.var.ads_pct"] / 100)
    if hist:   # HEAD 08.11: до ноября факта нет — постоянные и переменные считаем по нынешним ставкам «Значений» (оценка)
        for code, b in budget.items():
            if b["plan"] and not b["fact"] and code != "ads":   # «ads» (% от выручки) — не поверх отдельных статей рекламы
                b["fact"], b["estimate"] = float(b["plan"]), True
    fixed = sum(b["fact"] for b in budget.values() if b["kind"] == "fixed")
    variable = sum(b["fact"] for b in budget.values() if b["kind"] == "variable")
    taxes_paid = sum(b["fact"] for b in budget.values() if b["kind"] == "tax")
    # чеки «своими» уже сидят в ФОТ как возмещение — в расходах статей их не считаем второй раз
    costs = {"project": exp.get("project", 0.0), "stock": exp.get("stock", 0.0), "canvas": exp.get("canvas", 0.0),
             "sales": exp.get("sales", 0.0), "payroll": payroll_acc - reimb, "fixed": fixed, "variable": variable, "materials": hist_mat}
    if hist:
        warn.append("до ноября 2026 — история: материалы и транспорт — оценки из «Проекты 2026»; постоянные и переменные (аренда, "
                    "подписки, реклама) — по нынешним ставкам «Значений»; оклады вне «ФОТ 2026» не входят")
    profit = None if net is None else round(net - sum(costs.values()), 2)
    ipn_pct = v.get("fin.tax.ipn")
    if not ipn_pct:
        warn.append("нет ключа fin.tax.ipn в «Значениях» — ИПН не оценён")
    inflow = sum(_f(r["s"]) for r in cash if r["direction"] == "in" and r["kind"] != "opening")
    outflow = sum(_f(r["s"]) for r in cash if r["direction"] == "out")
    return {"month": ym, "warn": warn,
            "revenue": {"gross": gross, "net": None if net is None else round(net), "vat": None if gross is None else round(gross - net)},
            "costs": costs, "profit": profit,
            "ipn": round(max(profit, 0) * ipn_pct / 100) if profit is not None and ipn_pct else None,
            "budget": [{"code": k, **b} for k, b in budget.items()],
            "cash": {"opening": opening, "closing": closing, "in": inflow, "out": outflow,
                     "lines": [{**r, "s": _f(r["s"])} for r in cash], "company_paid_receipts": company_paid}}


@router.get("/fin/year")
def year_overview(y: int | None = None, p: dict = Depends(require_head)):
    """Обзор года для графиков «Финансы → Обзор» (HEAD 09.11: «с диаграммами, как в артефакте финансов»):
    по месяцам — выручка, расходы по видам, прибыль, деньги; за год — города и структура расходов. Те же числа, что «Сводка»."""
    from . import fin
    now = datetime.now(TZ)
    y = y or now.year
    last = now.month if y == now.year else 12
    months, cities = [], {}
    for mo in range(1, last + 1):
        s = summary(f"{y}-{mo:02d}", p)
        try:
            rows = fin.month_rows(y, mo)
        except Exception:  # noqa: BLE001 — лист не прочитан: без городов и сделок
            rows = []
        for r in rows:
            c = (r["city"] or "Другой").split(" (")[0].strip() or "Другой"
            cities[c] = cities.get(c, 0.0) + _f(r["sum"])
        months.append({"month": f"{y}-{mo:02d}", "gross": s["revenue"]["gross"], "net": s["revenue"]["net"], "costs": s["costs"],
                       "profit": s["profit"], "cash_in": s["cash"]["in"], "cash_out": s["cash"]["out"], "deals": len(rows),
                       "estimate": f"{y}-{mo:02d}" < f"{HIST_CUT:%Y-%m}"})
    return {"year": y, "months": months, "cities": sorted(({"city": k, "sum": round(v)} for k, v in cities.items()), key=lambda x: -x["sum"])}
