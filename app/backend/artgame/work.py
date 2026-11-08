"""Раздел «Смены и расходы». Отправка идемпотентна по client_uid (офлайн-очередь на телефоне)."""
from datetime import datetime
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import math

from . import constants as consts
from . import db, drive, sync_objects
from .deps import current_person

router = APIRouter(prefix="/api")

# Кто проверяет какую зону (ARCHITECTURE.md «Роли и зоны»). HEAD — всё, ГИП — свой объект.
CHECKS = {"lead_artist": {"mural"}, "artist_pro": {"mural"}, "print_master": {"print"}, "lead_designer": {"design"}}
# Лестница (константы, HEAD 06.11): Саппорт → Художник → Главный → Про. По зоне проверяют только тех, кто ниже по уровню:
# Главный не проверяет Главного и Про; Про проверяет Главного. ГИП своего объекта и HEAD — всех.
RANK_SQL = "(SELECT r.level FROM people pp JOIN roles r ON r.code=pp.role_code WHERE pp.id=x.person_id)"


def active(p: dict = Depends(current_person)) -> dict:
    if p["status"] != "active":
        raise HTTPException(403, "pending")
    return p


def check_zone(conn, p: dict, zone: str, object_id: int):
    if zone not in p["zones"]:
        raise HTTPException(400, "zone not assigned")
    o = conn.execute("SELECT status FROM objects WHERE id=%s", (object_id,)).fetchone()
    if not o or o["status"] != "active":
        raise HTTPException(400, "object closed or missing")


# Саппорт тратит только на такси и докупку на объект (HEAD 08.11).
ROLE_CATS = {"support": ("transport", "purchase")}


def cats_for(conn, role: str | None) -> list[dict]:
    rows = conn.execute("SELECT code, title FROM expense_categories WHERE active AND article='project' ORDER BY sort").fetchall()
    allow = ROLE_CATS.get(role or "")
    return [r for r in rows if not allow or r["code"] in allow]


@router.get("/work/dict")
def work_dict(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {
            "objects": conn.execute("SELECT id, title, city FROM objects WHERE status='active' AND (id=0 OR bitrix_stage=%s) ORDER BY id DESC",
                                    (sync_objects.WORK,)).fetchall(),
            "categories": cats_for(conn, p["role_code"]),
            "zones": p["zones"],
            "printer": consts.latest(conn).get("print.tech.printer"),
            "role": p["role_code"],
            # подсказки смены (HEAD 08.11): ТБ из «Значений», этапы работ
            "safety": {k: x for k, x in consts.latest(conn).items() if k.startswith("safety.")},
            "stages": [{"key": k, "title": t} for k, t in __import__("artgame.promo", fromlist=["STAGES"]).STAGES],
        }


def object_cond(conn, object_id: int) -> dict:
    """Условия объекта из сделки (заполняет МОП, команда не выбирает — HEAD 08.11): сложность — поле сделки «Сложность»
    (иначе из расчёта), высота / улица / сложная поверхность — из расчёта в карточке сделки, площадь и адрес — из сделки."""
    o = conn.execute("SELECT id, title, city, level, area_m2, address, geo, level_guess FROM objects WHERE id=%s", (object_id,)).fetchone()
    if not o:
        raise HTTPException(404, "no object")
    c = conn.execute("SELECT data FROM deal_calc WHERE deal_id=%s", (object_id,)).fetchone()
    i = ((c or {}).get("data") or {}).get("in") or {}
    lvl = ""
    if o["level"]:
        try:
            from . import bx
            lvl = bx.level_key(o["level"])
        except Exception:  # noqa: BLE001 — Битрикс недоступен: возьмём из расчёта
            lvl = o["level"] if o["level"] in COMPLEXITY else ""
    src = "deal" if lvl else None
    if not lvl and i.get("service") == "mural" and i.get("level") in COMPLEXITY:
        lvl, src = i["level"], "calc"
    if not lvl and o["level_guess"] in COMPLEXITY and i.get("service") in (None, "mural"):
        lvl, src = o["level_guess"], "price"   # МОП не указал — оценка по сумме сделки и площади (HEAD 08.11)
    from .promo import map_url
    return {"id": o["id"], "title": o["title"], "city": o["city"], "address": o["address"], "complexity_src": src,
            "map": map_url(o["city"], o["address"], o["geo"]),
            "area": float(o["area_m2"]) if o["area_m2"] is not None else (float(i["area"]) if i.get("area") else None),
            "service": i.get("service"), "complexity": lvl or None,
            "at_height": "height" in (i.get("extras") or []), "outdoor": bool(i.get("outdoor")), "hard_surface": bool(i.get("surface"))}


def apply_cond(conn, s) -> None:
    """Роспись: сложность и условия берём из сделки, если МОП их заполнил (выбор на телефоне не нужен)."""
    if s.zone_code != "mural" or not s.object_id:
        return
    c = object_cond(conn, s.object_id)
    if c["complexity"]:
        s.complexity, s.at_height, s.outdoor, s.hard_surface = c["complexity"], c["at_height"], c["outdoor"], c["hard_surface"]


class ShiftIn(BaseModel):
    client_uid: UUID
    object_id: int
    zone_code: str
    started_at: datetime
    ended_at: datetime | None = None
    area_m2: float | None = Field(default=None, ge=0)
    complexity: str | None = None
    note: str | None = None
    geo_lat: float | None = None
    geo_lon: float | None = None
    printer: str | None = Field(default=None, max_length=100)
    at_height: bool = False
    outdoor: bool = False
    hard_surface: bool = False


COMPLEXITY = ("easy", "medium", "hard", "author")
ROLE_NORM = {"support": "norm.role.support", "artist_pro": "norm.role.pro"}
PRINT_BONUS = {"print_operator": "pay.print.bonus_operator", "print_master": "pay.print.bonus_master"}


def _n(v: dict, key: str, default=None):
    x = v.get(key, default)
    return x if isinstance(x, (int, float)) else default


def shift_norm(v: dict, s: ShiftIn, role: str | None) -> dict:
    """Норма/план, КПД и бонус смены по «Значениям». Чего нет в «Значениях» — не считаем."""
    full = _n(v, "shift.hours", 10)
    hours = (s.ended_at - s.started_at).total_seconds() / 3600 if s.ended_at else full
    out = {"plan_m2": None, "kpd": None, "bonus": None}
    if s.zone_code == "mural" and s.complexity in COMPLEXITY:
        base = _n(v, f"norm.mural.{s.complexity}")
        if base:
            k = 1.0
            for flag, key in ((s.at_height, "norm.k.height"), (s.outdoor, "norm.k.outdoor"), (s.hard_surface, "norm.k.surface")):
                if flag:
                    k *= _n(v, key, 1)
            k *= _n(v, ROLE_NORM.get(role, ""), 1)
            out["plan_m2"] = round(base * k * min(hours, full * 1.5) / full, 2)
    elif s.zone_code == "print":
        out["plan_m2"] = _n(v, "print.plan_per_shift")
        step, rate = _n(v, "pay.print.bonus_step_m2"), _n(v, PRINT_BONUS.get(role, ""))
        if out["plan_m2"] and step and rate and s.area_m2:
            out["bonus"] = max(0, math.floor((s.area_m2 - out["plan_m2"]) / step)) * rate
    if out["plan_m2"] and s.area_m2 is not None:
        out["kpd"] = round(s.area_m2 / out["plan_m2"], 3)
    return out


@router.post("/shifts")
def add_shift(s: ShiftIn, p: dict = Depends(active)):
    if s.ended_at and s.ended_at <= s.started_at:
        raise HTTPException(400, "end before start")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (s.client_uid,)).fetchone()
        if dup:
            return dup
        check_zone(conn, p, s.zone_code, s.object_id)
        if s.complexity and s.complexity not in COMPLEXITY:
            raise HTTPException(400, "bad complexity")
        apply_cond(conn, s)
        n = shift_norm(consts.latest(conn), s, p["role_code"])
        row = conn.execute(
            """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, area_m2,
                                   complexity, note, geo_lat, geo_lon, printer, at_height, outdoor, hard_surface,
                                   plan_m2, kpd, bonus)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (s.client_uid, p["id"], s.object_id, s.zone_code, s.started_at, s.ended_at, s.area_m2,
             s.complexity, s.note, s.geo_lat, s.geo_lon, s.printer, s.at_height, s.outdoor, s.hard_surface,
             n["plan_m2"], n["kpd"], n["bonus"])).fetchone()
        if not row:  # параллельный повтор успел раньше
            return conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (s.client_uid,)).fetchone()
        db.audit(conn, p["id"], "shift_add", "shifts", row["id"])
        return row


# ---------- смена по шагам (HEAD 08.11): начать с фото «до» → закончить с фото «после», м² и «что сделал» ----------

class StartIn(BaseModel):
    client_uid: UUID
    object_id: int
    zone_code: str
    started_at: datetime
    photo_before: str = Field(min_length=30, max_length=8_000_000)
    geo_lat: float | None = None
    geo_lon: float | None = None


class FinishIn(BaseModel):
    client_uid: UUID                    # тот же, что при «Начать»: офлайн-очередь шлёт по порядку, ID смены телефону не нужен
    ended_at: datetime
    area_m2: float | None = Field(default=None, ge=0)
    work_done: str = Field(min_length=3, max_length=2000)
    photo_after: str = Field(min_length=30, max_length=8_000_000)
    printer: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000)
    stage: str | None = None            # этап, который закрыла смена (promo.STAGES)


def _photo(conn, p, object_id: int, uid: UUID, tag: str, data: str, note: str) -> int:
    from .files import get_object, store_photo
    return store_photo(conn, p, get_object(conn, object_id), uuid5(uid, tag), data, note)["id"]


def _shift_out(conn, row: dict) -> dict:
    out = dict(row)
    o = conn.execute("SELECT title, city FROM objects WHERE id=%s", (row["object_id"],)).fetchone()
    out["object_title"] = o["title"] if o else ""
    return photos(out)


@router.get("/shifts/open")
def open_shift(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        row = conn.execute("SELECT * FROM shifts WHERE person_id=%s AND status='open' ORDER BY started_at DESC LIMIT 1", (p["id"],)).fetchone()
        return {"shift": _shift_out(conn, row) if row else None}


@router.post("/shifts/start")
def start_shift(b: StartIn, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (b.client_uid,)).fetchone()
        if dup:
            return _shift_out(conn, dup)
        check_zone(conn, p, b.zone_code, b.object_id)
        if not b.object_id:
            raise HTTPException(400, "Смена — только на объекте")
        if conn.execute("SELECT 1 FROM shifts WHERE person_id=%s AND status='open'", (p["id"],)).fetchone():
            raise HTTPException(409, "Смена уже идёт — сначала закончи её")
        ph = _photo(conn, p, b.object_id, b.client_uid, "before", b.photo_before, "до смены")
        row = conn.execute(
            """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, geo_lat, geo_lon, status, photo_before)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'open',%s) ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (b.client_uid, p["id"], b.object_id, b.zone_code, b.started_at, b.geo_lat, b.geo_lon, ph)).fetchone()
        if not row:
            row = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (b.client_uid,)).fetchone()
        else:
            db.audit(conn, p["id"], "shift_start", "shifts", row["id"])
        return _shift_out(conn, row)


@router.post("/shifts/finish")
def finish_shift(b: FinishIn, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("SELECT * FROM shifts WHERE client_uid=%s AND person_id=%s FOR UPDATE", (b.client_uid, p["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Смена не найдена")
        if row["status"] != "open":   # повтор из офлайн-очереди
            return _shift_out(conn, row)
        if b.ended_at <= row["started_at"]:
            raise HTTPException(400, "end before start")
        from .promo import STAGE_KEYS
        if b.stage and b.stage not in STAGE_KEYS:
            raise HTTPException(400, "bad stage")
        ph = _photo(conn, p, row["object_id"], b.client_uid, "after", b.photo_after, "после смены")
        s = ShiftIn(client_uid=b.client_uid, object_id=row["object_id"], zone_code=row["zone_code"], started_at=row["started_at"],
                    ended_at=b.ended_at, area_m2=b.area_m2, printer=b.printer if row["zone_code"] == "print" else None)
        apply_cond(conn, s)
        n = shift_norm(consts.latest(conn), s, p["role_code"])
        row = conn.execute(
            """UPDATE shifts SET status='submitted', ended_at=%s, area_m2=%s, work_done=%s, note=%s, photo_after=%s, printer=%s,
                   complexity=%s, at_height=%s, outdoor=%s, hard_surface=%s, plan_m2=%s, kpd=%s, bonus=%s, stage=%s
               WHERE id=%s RETURNING *""",
            (b.ended_at, b.area_m2, b.work_done.strip(), b.note, ph, s.printer, s.complexity, s.at_height, s.outdoor, s.hard_surface,
             n["plan_m2"], n["kpd"], n["bonus"], b.stage, row["id"])).fetchone()
        db.audit(conn, p["id"], "shift_finish", "shifts", row["id"])
        return _shift_out(conn, row)


@router.get("/work/object/{object_id}")
def object_promo(object_id: int, zone: str = "mural", p: dict = Depends(active)):
    """Живая карточка объекта: условия из сделки, норма на смену, эскизы с Диска, ход работ, фото до/после, кто на объекте."""
    with db.pool.connection() as conn:
        c = object_cond(conn, object_id)
        probe = ShiftIn(client_uid=UUID(int=0), object_id=object_id, zone_code=zone, started_at=datetime.now(), complexity=c["complexity"],
                        at_height=c["at_height"], outdoor=c["outdoor"], hard_surface=c["hard_surface"])
        c["plan_m2"] = shift_norm(consts.latest(conn), probe, p["role_code"])["plan_m2"]
        from . import promo
        obj = conn.execute("SELECT * FROM objects WHERE id=%s", (object_id,)).fetchone()
        promo.maybe_sync(conn, obj)
        c["sketches"] = promo.sketches(conn, object_id)
        c.update(promo.progress(conn, object_id, c["area"]))
        c["now"] = [r["full_name"] for r in conn.execute(
            """SELECT DISTINCT pe.full_name FROM shifts s JOIN people pe ON pe.id=s.person_id
               WHERE s.object_id=%s AND s.status='open' ORDER BY 1""", (object_id,)).fetchall()]
        return c


class ExpenseIn(BaseModel):
    client_uid: UUID
    object_id: int
    zone_code: str
    category: str
    amount: float = Field(ge=0)
    paid_by: str = "own"
    receipt: str | None = Field(default=None, max_length=8_000_000)  # data:image/jpeg;base64,… (сжато на телефоне)
    note: str | None = None


@router.post("/expenses")
def add_expense(e: ExpenseIn, p: dict = Depends(active)):
    if e.paid_by not in ("own", "company"):
        raise HTTPException(400, "bad paid_by")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone()
        if dup:
            return dup
        check_zone(conn, p, e.zone_code, e.object_id)
        if e.category not in {c["code"] for c in cats_for(conn, p["role_code"])}:
            raise HTTPException(400, "bad category")
        drive_id = None
        if e.receipt:
            if not e.receipt.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
                raise HTTPException(400, "bad receipt")
            name = f"Чек {datetime.now():%Y-%m-%d %H-%M} {p['full_name']} {e.amount:.0f}"
            try:
                drive_id = drive.save_receipt(conn, e.zone_code, name, e.receipt, deal_id=e.object_id or None)
            except Exception as ex:  # Диск недоступен — телефон повторит позже
                raise HTTPException(502, f"drive: {ex.__class__.__name__}")
        row = conn.execute(
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, receipt_url, note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (e.client_uid, p["id"], e.object_id, e.zone_code, e.category, e.amount, e.paid_by, None, e.note)).fetchone()
        if not row:
            return with_receipt(conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone())
        if drive_id:
            data, mime = drive.decode_data_url(e.receipt)
            f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                                VALUES (gen_random_uuid(), %s, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                             (e.object_id, name, mime, len(data), drive_id, p["id"])).fetchone()
            row = conn.execute("UPDATE expenses SET receipt_file_id=%s WHERE id=%s RETURNING *", (f["id"], row["id"])).fetchone()
        row = self_approve(conn, p, row)
        db.audit(conn, p["id"], "expense_add", "expenses", row["id"])
        return with_receipt(row)


def self_approve(conn, p: dict, row: dict) -> dict:
    """Трата самого HEAD (HEAD 08.11: «расход на планшет никуда не подгрузился») не ждёт проверки у него же:
    сразу «принято», свои деньги — «к выплате», и она сразу в «Финансах»."""
    if p["role_code"] != "head" or p.get("_view_as") or row["status"] != "submitted":
        return row
    return conn.execute("""UPDATE expenses SET status='approved', checked_by=%s, checked_at=now(),
                             payout_status=CASE WHEN paid_by='own' THEN 'to_pay' ELSE payout_status END,
                             reason=coalesce(reason, 'трата HEAD — без проверки') WHERE id=%s RETURNING *""", (p["id"], row["id"])).fetchone()


def photos(s: dict) -> dict:
    """Фото стены до / после смены — подписанные миниатюры."""
    from .files import sign
    for k in ("photo_before", "photo_after"):
        s[k + "_url"] = sign(s[k], "thumb") if s.get(k) else None
        s[k + "_full"] = sign(s[k], "content") if s.get(k) else None
    return s


def with_receipt(e: dict) -> dict:
    """Подписанная ссылка на чек (живёт 12 ч)."""
    from .files import sign
    e["receipt_url"] = sign(e["receipt_file_id"], "content") if e.get("receipt_file_id") else None
    return e


@router.get("/my")
def my(p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {
            "shifts": [photos(s) for s in conn.execute("""SELECT s.*, o.title AS object_title FROM shifts s JOIN objects o ON o.id=s.object_id
                                      WHERE person_id=%s ORDER BY started_at DESC LIMIT 100""", (p["id"],)).fetchall()],
            "expenses": [with_receipt(e) for e in conn.execute("""SELECT e.*, o.title AS object_title FROM expenses e JOIN objects o ON o.id=e.object_id
                                        WHERE person_id=%s ORDER BY created_at DESC LIMIT 100""", (p["id"],)).fetchall()],
        }


TABLE = {"shift": "shifts", "expense": "expenses"}


@router.post("/{kind}/{item_id}/cancel")
def cancel(kind: str, item_id: int, p: dict = Depends(active)):
    """Сам отменяет свою запись, пока её не проверили. Не удаляем — помечаем."""
    t = TABLE.get(kind)
    if not t:
        raise HTTPException(404)
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute(f"UPDATE {t} SET status='cancelled' WHERE id=%s AND person_id=%s AND status IN ('submitted','open') RETURNING id",
                           (item_id, p["id"])).fetchone()
        if not row:
            raise HTTPException(409, "not cancellable")
        db.audit(conn, p["id"], f"{kind}_cancel", t, item_id)
    return {"ok": True}


def review_filter(p: dict) -> tuple[str, list]:
    """SQL-условие: какие записи человек может проверять (не свои)."""
    if p["role_code"] == "head":
        return "TRUE", []
    zones = sorted(CHECKS.get(p["role_code"], set()))
    own = f"(SELECT level FROM roles WHERE code=%s)"
    return (f"((x.zone_code = ANY(%s) AND COALESCE({RANK_SQL}, 0) < {own}) OR o.gip_person_id = %s) AND x.person_id <> %s",
            [zones, p["role_code"], p["id"], p["id"]])


@router.get("/review")
def review_list(p: dict = Depends(active)):
    cond, args = review_filter(p)
    with db.pool.connection() as conn:
        out = {}
        for kind, t in TABLE.items():
            out[t] = conn.execute(
                f"""SELECT x.*, o.title AS object_title, pe.full_name AS person_name
                    FROM {t} x JOIN objects o ON o.id=x.object_id JOIN people pe ON pe.id=x.person_id
                    WHERE x.status='submitted' AND {cond} ORDER BY x.created_at""", args).fetchall()
        cats = {c["code"]: c for c in conn.execute("SELECT code, title, article FROM expense_categories").fetchall()}
        flags = {}   # покупки по каталогу: почему ждёт HEAD (выше потолка / нет ориентира)
        for r in conn.execute("""SELECT expense_id, array_agg(DISTINCT flag) AS f FROM stock_lines
                                 WHERE expense_id = ANY(%s) AND flag IN ('over_cap','no_ref') GROUP BY expense_id""",
                              ([e["id"] for e in out["expenses"]],)).fetchall():
            flags[r["expense_id"]] = [{"over_cap": "выше потолка цены", "no_ref": "нет ориентира цены"}[f] for f in sorted(r["f"], reverse=True)]
        for e in out["expenses"]:   # трата отдела продаж: вместо «Офис / без объекта» — статья и сделка
            c = cats.get(e["category"]) or {}
            e["category_title"] = c.get("title", e["category"])
            if c.get("article") in ("stock", "canvas"):
                fl = flags.get(e["id"])
                tail = (" · " + ", ".join(fl)) if fl else (" · сверх лимита" if e.get("over_limit") else "")
                e["object_title"] = ("Склад" if c["article"] == "stock" else "Мастерская холстов") + " · " + e["category_title"] + tail
            if c.get("article") == "sales":
                e["object_title"] = "Отдел продаж · " + e["category_title"] + (f" · сделка № {e['deal_id']}" if e.get("deal_id") else "") + (" · сверх лимита" if e.get("over_limit") else "")
        out["expenses"] = [with_receipt(e) for e in out["expenses"]]
        out["shifts"] = [photos(x) for x in out["shifts"]]
        if p["role_code"] != "head":
            for x in out["shifts"]:
                x.pop("bonus", None)
        return out


class Decision(BaseModel):
    approve: bool
    reason: str | None = None


@router.post("/{kind}/{item_id}/review")
def review(kind: str, item_id: int, d: Decision, p: dict = Depends(active)):
    t = TABLE.get(kind)
    if not t:
        raise HTTPException(404)
    if not d.approve and not (d.reason or "").strip():
        raise HTTPException(400, "reason required")
    cond, args = review_filter(p)
    with db.pool.connection() as conn, conn.transaction():
        ok = conn.execute(f"SELECT x.id FROM {t} x JOIN objects o ON o.id=x.object_id WHERE x.id=%s AND x.status='submitted' AND {cond}",
                          [item_id, *args]).fetchone()
        if not ok:
            raise HTTPException(403, "cannot review")
        status = "approved" if d.approve else "rejected"
        extra = ", payout_status = CASE WHEN paid_by='own' THEN 'to_pay' ELSE payout_status END" if t == "expenses" and d.approve else ""
        conn.execute(f"UPDATE {t} SET status=%s, reason=%s, checked_by=%s, checked_at=now(){extra} WHERE id=%s",
                     (status, d.reason, p["id"], item_id))
        db.audit(conn, p["id"], f"{kind}_{status}", t, item_id, {"reason": d.reason})
    return {"ok": True, "status": status}
