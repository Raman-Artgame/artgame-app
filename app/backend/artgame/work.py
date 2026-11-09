"""Раздел «Смены и расходы». Отправка идемпотентна по client_uid (офлайн-очередь на телефоне)."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import math

from . import constants as consts
from . import db, drive, sync_objects
from .config import settings
from .deps import current_person

TZ = ZoneInfo("Asia/Almaty")
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


def check_zone(conn, p: dict, zone: str, object_id: int, past: bool = False):
    if zone not in p["zones"]:
        raise HTTPException(400, "zone not assigned")
    o = conn.execute("SELECT status FROM objects WHERE id=%s", (object_id,)).fetchone()
    if not o or o["status"] not in (("active", "done") if past else ("active",)):
        raise HTTPException(400, "object closed or missing")


def backfill_window() -> dict:
    """Задним числом (HEAD 09.11: «чтобы ребята всё заполнили с 1 ноября»): с какого дня и до какого числа открыто."""
    today = datetime.now(TZ).date()
    a, b = date.fromisoformat(settings.backfill_from), date.fromisoformat(settings.backfill_until)
    return {"from": a.isoformat(), "until": b.isoformat(), "open": a <= today <= b}


def check_past_day(day: date) -> datetime:
    w = backfill_window()
    if not w["open"]:
        raise HTTPException(400, f"Внести задним числом можно было до {w['until']}")
    if day < date.fromisoformat(w["from"]) or day >= datetime.now(TZ).date():
        raise HTTPException(400, f"Дата — с {w['from']} по вчера")
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=TZ)


# Саппорт тратит только на такси и докупку на объект (HEAD 08.11).
ROLE_CATS = {"support": ("transport", "purchase"),
             # дизайнеры — только такси / доставка и «Другое» (HEAD 09.11)
             "lead_designer": ("transport", "other"), "designer_asst": ("transport", "other")}
# Категории только для некоторых ролей: проживание в командировке — Главный, Про, Мастер печати (HEAD 08.11)
CAT_ROLES = {"lodging": {"lead_artist", "artist_pro", "print_master", "head"}}


def cats_for(conn, role: str | None) -> list[dict]:
    rows = conn.execute("SELECT code, title FROM expense_categories WHERE active AND article='project' ORDER BY sort").fetchall()
    allow = ROLE_CATS.get(role or "")
    return [r for r in rows if (not allow or r["code"] in allow) and (r["code"] not in CAT_ROLES or role in CAT_ROLES[r["code"]])]


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
            "workshop": WORKSHOP_TASKS if set(p.get("roles") or [p["role_code"]]) & set(WORKSHOP_ROLES) else None,
            "roles": p.get("roles") or [p["role_code"]],   # две роли: в какой роли смена — по зоне объекта, можно сменить
            # подсказки смены (HEAD 08.11): ТБ из «Значений», этапы работ
            "safety": {k: x for k, x in consts.latest(conn).items() if k.startswith("safety.")},
            "stages": [{"key": k, "title": t} for k, t in __import__("artgame.promo", fromlist=["STAGES"]).STAGES],
            # задним числом с 1.11 (HEAD 09.11): объекты — и уже сданные
            "backfill": {**backfill_window(), "objects": conn.execute(
                "SELECT id, title, city FROM objects WHERE status='active' AND id<>0 AND bitrix_stage=%s ORDER BY id DESC",
                (sync_objects.WORK,)).fetchall()},   # HEAD 09.11: только «Выполнение проекта» — завершённые HEAD сам возвращает туда
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
    photo_before: str | None = Field(default=None, max_length=8_000_000)   # обязательно на объекте; в мастерской — нет
    geo_lat: float | None = None
    geo_lon: float | None = None
    role: str | None = None             # две роли (HEAD 08.11): в какой роли смена; по умолчанию — по зоне объекта
    workshop: str | None = Field(default=None, max_length=60)   # «Мастерская» без проекта (HEAD 09.11): ТО принтера и т. п.


PRINT_ROLES = ("print_master", "print_operator")
WORKSHOP_ROLES = PRINT_ROLES   # «Мастерская» без проекта (HEAD 09.11)
WORKSHOP_ZONES = ("print",)
WORKSHOP_TASKS = ["ТО принтера", "Ремонт и запчасти", "Тест печати", "Подготовка к объекту", "Обучение", "Другое"]


def shift_role(p: dict, zone: str, want: str | None = None) -> str:
    """Роль смены: выбранная (из своих), иначе по зоне — печать → роль печати, роспись → роль художника, иначе текущая."""
    roles = p.get("roles") or [p["role_code"]]
    if want and want in roles:
        return want
    pick = [r for r in roles if (r in PRINT_ROLES) == (zone == "print")]
    cur = p["role_code"] if p["role_code"] in roles else roles[0]   # и.о.: ставка — по основной роли, не по исполняемой
    return cur if cur in pick or not pick else pick[0]


class FinishIn(BaseModel):
    client_uid: UUID                    # тот же, что при «Начать»: офлайн-очередь шлёт по порядку, ID смены телефону не нужен
    ended_at: datetime
    area_m2: float | None = Field(default=None, ge=0)
    work_done: str = Field(min_length=3, max_length=2000)
    photo_after: str | None = Field(default=None, max_length=8_000_000)   # обязательно на объекте; в мастерской — нет
    printer: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000)
    stage: str | None = None            # этап, который закрыла смена (promo.STAGES)


def _photo(conn, p, object_id: int, uid: UUID, tag: str, data: str, note: str) -> int:
    from .files import get_object, store_photo
    return store_photo(conn, p, get_object(conn, object_id), uuid5(uid, tag), data, note)["id"]


def is_trip(conn, person_id: int, object_id: int) -> bool:
    """Командировка (HEAD 08.11): МОП отметил на объекте — так и есть; иначе город сотрудника ≠ город объекта."""
    o = conn.execute("SELECT city, trip FROM objects WHERE id=%s", (object_id,)).fetchone()
    if not o or object_id == 0:
        return False
    if o["trip"] is not None:
        return bool(o["trip"])
    pc = (conn.execute("SELECT city FROM people WHERE id=%s", (person_id,)).fetchone() or {}).get("city")
    norm = lambda x: (x or "").split("(")[0].strip().casefold()  # noqa: E731
    return bool(pc and o["city"] and norm(pc) != norm(o["city"]))


def _shift_out(conn, row: dict) -> dict:
    out = dict(row)
    o = conn.execute("SELECT title, city FROM objects WHERE id=%s", (row["object_id"],)).fetchone()
    out["object_title"] = o["title"] if o else ""
    return shop_title(photos(out))


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
        shop = bool(b.workshop)
        if shop:   # мастерская: без объекта, только печать (HEAD 09.11)
            b.object_id = 0
            if not set(p.get("roles") or [p["role_code"]]) & set(WORKSHOP_ROLES) or b.zone_code not in WORKSHOP_ZONES:
                raise HTTPException(400, "Мастерская без проекта — у печати")
        check_zone(conn, p, b.zone_code, b.object_id)
        if not b.object_id and not shop:
            raise HTTPException(400, "Смена — только на объекте")
        if not shop and not (b.photo_before and len(b.photo_before) >= 30):
            raise HTTPException(422, "Нужно фото стены до начала")
        if conn.execute("SELECT 1 FROM shifts WHERE person_id=%s AND status='open'", (p["id"],)).fetchone():
            raise HTTPException(409, "Смена уже идёт — сначала закончи её")
        ph = None if shop else _photo(conn, p, b.object_id, b.client_uid, "before", b.photo_before, "до смены")
        row = conn.execute(
            """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, geo_lat, geo_lon, status, photo_before, trip, role_code, kind, task)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'open',%s,%s,%s,%s,%s) ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (b.client_uid, p["id"], b.object_id, b.zone_code, b.started_at, b.geo_lat, b.geo_lon, ph, False if shop else is_trip(conn, p["id"], b.object_id),
             shift_role(p, b.zone_code, b.role), "workshop" if shop else "work", b.workshop.strip() if shop else None)).fetchone()
        if not row:
            row = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (b.client_uid,)).fetchone()
        else:
            db.audit(conn, p["id"], "shift_start", "shifts", row["id"])
        return _shift_out(conn, row)


class TripIn(BaseModel):
    trip: bool | None = None   # None — считать по городу


@router.post("/objects/{object_id}/trip")
def set_trip(object_id: int, b: TripIn, p: dict = Depends(active)):
    """МОП поправляет командировку на объекте (HEAD 08.11). Пишется только в приложении, в Битрикс — нет."""
    if p["role_code"] not in ("mop", "mop_vip", "head") or p.get("_view_as"):
        raise HTTPException(403, "командировку отмечает МОП или HEAD")
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("UPDATE objects SET trip=%s WHERE id=%s AND id<>0 RETURNING id, trip", (b.trip, object_id)).fetchone()
        if not row:
            raise HTTPException(404, "объекта ещё нет в приложении")
        db.audit(conn, p["id"], "object_trip", "objects", object_id, {"trip": b.trip})
        return row


@router.get("/objects/{object_id}/trip")
def get_trip(object_id: int, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        o = conn.execute("SELECT id, city, trip FROM objects WHERE id=%s", (object_id,)).fetchone()
        if not o:
            raise HTTPException(404)
        return o


class PastIn(BaseModel):
    client_uid: UUID
    object_id: int
    zone_code: str
    day: date
    hours: float = Field(gt=0, le=16)
    area_m2: float | None = Field(default=None, ge=0)
    work_done: str = Field(min_length=3, max_length=2000)
    photo_after: str | None = Field(default=None, max_length=8_000_000)   # фото по возможности
    role: str | None = None
    workshop: str | None = Field(default=None, max_length=60)   # мастерская без проекта (печать, HEAD 09.11)


@router.post("/shifts/past")
def past_shift(b: PastIn, p: dict = Depends(active)):
    """«Прошлая смена» (HEAD 09.11): внести смену задним числом с 1.11 — сразу на проверку, с пометкой backfill."""
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (b.client_uid,)).fetchone()
        if dup:
            return _shift_out(conn, dup)
        shop = bool(b.workshop)
        if shop:
            b.object_id, b.area_m2 = 0, None
            if not set(p.get("roles") or [p["role_code"]]) & set(WORKSHOP_ROLES) or b.zone_code not in WORKSHOP_ZONES:
                raise HTTPException(400, "Мастерская без проекта — у печати")
        check_zone(conn, p, b.zone_code, b.object_id, past=True)
        if not b.object_id and not shop:
            raise HTTPException(400, "Смена — только на объекте")
        start = check_past_day(b.day)
        if conn.execute("""SELECT 1 FROM shifts WHERE person_id=%s AND status NOT IN ('rejected','cancelled')
                           AND started_at >= %s AND started_at < %s + interval '1 day'""", (p["id"], start.replace(hour=0), start.replace(hour=0))).fetchone():
            raise HTTPException(409, "В этот день смена уже есть")
        ph = _photo(conn, p, b.object_id, b.client_uid, "after", b.photo_after, "после (задним числом)") if b.photo_after and not shop else None
        row = conn.execute(
            """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, status, area_m2, work_done, photo_after,
                                   trip, role_code, backfill, kind, task)
               VALUES (%s,%s,%s,%s,%s,%s,'submitted',%s,%s,%s,%s,%s,true,%s,%s) RETURNING *""",
            (b.client_uid, p["id"], b.object_id, b.zone_code, start, start + timedelta(hours=b.hours), b.area_m2, b.work_done, ph,
             False if shop else is_trip(conn, p["id"], b.object_id), shift_role(p, b.zone_code, b.role),
             "workshop" if shop else "work", b.workshop.strip() if shop else None)).fetchone()
        db.audit(conn, p["id"], "shift_past", "shifts", row["id"], {"day": b.day.isoformat()})
        return _shift_out(conn, row)


class PhotoIn(BaseModel):
    client_uid: UUID                    # у каждого фото свой — повтор не создаёт дубль
    photo: str = Field(min_length=30, max_length=8_000_000)


@router.post("/shifts/{sid}/photos")
def add_shift_photo(sid: int, b: PhotoIn, p: dict = Depends(active)):
    """Ещё фото к своей смене задним числом (HEAD 09.11: «неограниченное количество фотографий»), пока она не проверена."""
    with db.pool.connection() as conn, conn.transaction():
        s = conn.execute("SELECT * FROM shifts WHERE id=%s AND person_id=%s", (sid, p["id"])).fetchone()
        if not s:
            raise HTTPException(404, "Смена не найдена")
        if not s["backfill"] or s["status"] != "submitted" or not s["object_id"]:
            raise HTTPException(400, "Фото добавляются к отчёту задним числом на объекте, пока он на проверке")
        fid = _photo(conn, p, s["object_id"], b.client_uid, "extra", b.photo, "отчёт задним числом")
        conn.execute("INSERT INTO shift_photos (shift_id, file_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (sid, fid))
        n = conn.execute("SELECT count(*) AS n FROM shift_photos WHERE shift_id=%s", (sid,)).fetchone()["n"]
        return {"ok": True, "count": n}


class RoadIn(BaseModel):
    client_uid: UUID
    object_id: int
    zone_code: str
    day: datetime                      # день дороги (время — когда выехал)
    direction: str = "there"           # there | back
    note: str | None = Field(default=None, max_length=500)
    ticket: str | None = Field(default=None, max_length=8_000_000)   # фото билета / чека (по желанию)


@router.post("/shifts/road")
def road_day(b: RoadIn, p: dict = Depends(active)):
    """День дороги в командировку (HEAD 08.11): идёт на проверку как смена и оплачивается по ставке смены роли."""
    if b.direction not in ("there", "back"):
        raise HTTPException(400, "bad direction")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM shifts WHERE client_uid=%s", (b.client_uid,)).fetchone()
        if dup:
            return _shift_out(conn, dup)
        check_zone(conn, p, b.zone_code, b.object_id)
        if not is_trip(conn, p["id"], b.object_id):
            raise HTTPException(400, "Объект не командировочный: дорога не считается. Город — в «Команде», отметка — у МОП в сделке")
        day0 = b.day.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        if conn.execute("SELECT 1 FROM shifts WHERE person_id=%s AND kind='road' AND status IN ('submitted','approved') "
                        "AND started_at >= %s AND started_at < %s + interval '1 day'", (p["id"], day0, day0)).fetchone():
            raise HTTPException(409, "Дорога в этот день уже отмечена")
        ph = _photo(conn, p, b.object_id, b.client_uid, "ticket", b.ticket, "билет / дорога") if b.ticket else None
        hours = consts.latest(conn).get("shift.hours") or 10
        start = b.day.astimezone(TZ)
        row = conn.execute(
            """INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, status, kind, trip, work_done, note, photo_after, role_code)
               VALUES (%s,%s,%s,%s,%s,%s,'submitted','road',true,%s,%s,%s,%s) RETURNING *""",
            (b.client_uid, p["id"], b.object_id, b.zone_code, start, start + timedelta(hours=float(hours)),
             "Дорога " + ("на объект" if b.direction == "there" else "обратно"), b.note, ph, shift_role(p, b.zone_code))).fetchone()
        db.audit(conn, p["id"], "shift_road", "shifts", row["id"], {"direction": b.direction})
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
        shop = row["kind"] == "workshop"
        if not shop and not (b.photo_after and len(b.photo_after) >= 30):
            raise HTTPException(422, "Нужно фото в конце смены")
        ph = None if shop else _photo(conn, p, row["object_id"], b.client_uid, "after", b.photo_after, "после смены")
        s = ShiftIn(client_uid=b.client_uid, object_id=row["object_id"], zone_code=row["zone_code"], started_at=row["started_at"],
                    ended_at=b.ended_at, area_m2=b.area_m2, printer=b.printer if row["zone_code"] == "print" else None)
        apply_cond(conn, s)
        n = {"plan_m2": None, "kpd": None, "bonus": None} if shop else shift_norm(consts.latest(conn), s, p["role_code"])   # мастерская — без плана
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
        c["trip"] = is_trip(conn, p["id"], object_id)   # командировка для этого человека: в смене кнопка «Дорога», суточные
        c["trip_set"] = obj["trip"]
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
    day: date | None = None            # задним числом с 1.11 (HEAD 09.11)


@router.post("/expenses")
def add_expense(e: ExpenseIn, p: dict = Depends(active)):
    if e.paid_by not in ("own", "company"):
        raise HTTPException(400, "bad paid_by")
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM expenses WHERE client_uid=%s", (e.client_uid,)).fetchone()
        if dup:
            return dup
        check_zone(conn, p, e.zone_code, e.object_id, past=bool(e.day))
        at = check_past_day(e.day).replace(hour=12) if e.day else None
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
            """INSERT INTO expenses (client_uid, person_id, object_id, zone_code, category, amount, paid_by, receipt_url, note, created_at, backfill)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,coalesce(%s, now()),%s)
               ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
            (e.client_uid, p["id"], e.object_id, e.zone_code, e.category, e.amount, e.paid_by, None, e.note, at, bool(e.day))).fetchone()
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


def more_photos(conn, rows: list[dict]) -> list[dict]:
    """Доп. фото смены (отчёт задним числом, HEAD 09.11): s["photos"] = [{url, full}] — подписанные ссылки."""
    from .files import sign
    ids = [r["id"] for r in rows]
    by = {}
    if ids:
        for r in conn.execute("SELECT shift_id, file_id FROM shift_photos WHERE shift_id = ANY(%s) ORDER BY id", (ids,)).fetchall():
            by.setdefault(r["shift_id"], []).append({"url": sign(r["file_id"], "thumb"), "full": sign(r["file_id"], "content")})
    for r in rows:
        r["photos"] = by.get(r["id"], [])
    return rows


def shop_title(s: dict) -> dict:
    """Смена в мастерской: вместо «Офис / без объекта» — «Мастерская · ТО принтера»."""
    if s.get("kind") == "workshop":
        s["object_title"] = "Мастерская" + (f" · {s['task']}" if s.get("task") else "")
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
            "shifts": more_photos(conn, [shop_title(photos(s)) for s in conn.execute("""SELECT s.*, o.title AS object_title FROM shifts s JOIN objects o ON o.id=s.object_id
                                      WHERE person_id=%s ORDER BY started_at DESC LIMIT 100""", (p["id"],)).fetchall()]),
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
        out["shifts"] = more_photos(conn, [shop_title(photos(x)) for x in out["shifts"]])
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
