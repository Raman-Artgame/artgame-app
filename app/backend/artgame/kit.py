"""Сбор на объект (HEAD 07.11.2026): чек-лист выезда росписи и печати — что взяли, что вернули, в каком состоянии.

Собирают и сдают: Главный художник, Художник-Про, Мастер настенной печати, ГИП объекта, HEAD. Остальные с зоной
видят список своего объекта. Аэрозоль — строками «номер цвета — штук», фасадная — общие литры, остальное количеством.
Списки позиций — из таблицы «Чек-лист выезда — художники» (Шаблон: МАТ / ОБР / РАС), памятки X13 и сборов печати.
Цен и ставок здесь нет. Инвентарные номера оборудования и онлайн-остатки — позже, отдельным блоком склада.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import db, sync_objects
from .work import active

router = APIRouter(prefix="/api")

EDIT_ROLES = {"lead_artist", "artist_pro", "print_master", "head"}
STATES = ["исправно", "есть замечание", "сломано", "потеряно"]

KIT = {
    "mural": {
        "mat": [("МАТ-02", "Кэпы", "шт"), ("МАТ-04", "Акрил художественный", "шт"), ("МАТ-05", "Краска для аэрографа", "фл."),
                ("МАТ-06", "Лак", "л"), ("МАТ-07", "Маркеры", "шт"), ("МАТ-08", "Заправки", "шт"), ("МАТ-09", "Шпаклёвка", "кг"),
                ("МАТ-10", "Карандаши", "шт"), ("МАТ-11", "Распечатка макета", "шт"), ("МАТ-12", "Трафареты (плоттер / пластик)", "шт"),
                ("МАТ-13", "Валики + насадки", "компл."), ("МАТ-14", "Палка для валика", "шт"), ("МАТ-15", "Кисти разных размеров", "шт"),
                ("МАТ-16", "Кюветы разных размеров", "шт")],
        "obr": [("ОБР-01", "Шуруповёрт + насадки"), ("ОБР-02", "Стремянки / подмостья"), ("ОБР-03", "Вышка-тура"),
                ("ОБР-04", "Лазерный уровень"), ("ОБР-05", "Краскопульт Bosch"), ("ОБР-06", "Безвоздушный аппарат + ключи"),
                ("ОБР-07", "Аэрографы + компрессор"), ("ОБР-08", "VR-очки"), ("ОБР-09", "Удлинители"), ("ОБР-10", "GoPro + штатив"),
                ("ОБР-11", "Петличный микрофон"), ("ОБР-12", "Свет для съёмки"), ("ОБР-13", "Нож канцелярский + лезвия"),
                ("ОБР-14", "Рулетка"), ("ОБР-15", "Колонка + зарядка"), ("ОБР-16", "Страховочная привязь")],
        "ras": [("РАС-01", "Пакеты для кювет и валиков"), ("РАС-02", "Плёнка укрывная"), ("РАС-03", "Скотч малярный"),
                ("РАС-04", "Скотч обычный"), ("РАС-05", "Тарелки одноразовые"), ("РАС-06", "Соусники"), ("РАС-07", "Стаканчики"),
                ("РАС-08", "Контейнеры с крышкой 1 л"), ("РАС-09", "Тряпки"), ("РАС-10", "Салфетки сухие / влажные"),
                ("РАС-11", "Мусорные пакеты"), ("РАС-12", "Вода"), ("РАС-13", "Перчатки, респиратор, очки")],
        "pre": ["Макет согласован, распечатка взята", "План объекта утверждён HEAD", "Всё по списку загружено в машину"],
        "post": ["Зона работы убрана, мусор вывезен", "Инструмент очищен и сдан", "Остатки материалов сданы, «вернул» заполнен"],
        "aerosol": True, "facade": True,
    },
    "print": {
        "mat": [("ПЧ-01", "УФ-чернила", "бут."), ("ПЧ-02", "Запасной набор чернил", "компл."), ("ПЧ-03", "Спирт 90%", "л"),
                ("ПЧ-04", "CLEANER", "л"), ("ПЧ-05", "Шприцы 20 мл", "шт"), ("ПЧ-06", "Бумага для теста", "лист"),
                ("ПЧ-07", "Шпаклёвка, грунт", "кг"), ("ПЧ-08", "Маркеры основных цветов", "шт"), ("ПЧ-09", "Мини-акрил с кистями", "шт"),
                ("ПЧ-10", "Пеноплекс под холст", "лист")],
        "obr": [("ПО-01", "Принтер: части по сумкам, салазки или платформа"), ("ПО-02", "Ноутбук с Better Print и UltraPrint, ключи-флешки"),
                ("ПО-03", "Кабели USB и питания"), ("ПО-04", "ИБП"), ("ПО-05", "Капа в своём пакете"), ("ПО-06", "Набор инструментов"),
                ("ПО-07", "Шлифмашина с наждачкой"), ("ПО-08", "Стремянка"), ("ПО-09", "Складной стул"), ("ПО-10", "Рулетка, уровень"),
                ("ПО-11", "Шуруповёрт, дюбель-шурупы (холсты)")],
        "ras": [("ПР-01", "Салфетки влажные"), ("ПР-02", "Салфетки сухие"), ("ПР-03", "Безворсовые салфетки"), ("ПР-04", "Пакеты"),
                ("ПР-05", "Скотч малярный")],
        "pre": ["Файл в печать проверен: TIFF CMYK или PNG, 100–150 DPI", "Всё по списку загружено"],
        "post": ["Принтер в нулевой точке, головы закрыты салфетками и крышкой", "ТО принтера, учёт расходников",
                 "О поломках сообщено мастеру и HEAD"],
        "aerosol": True, "facade": False,
    },
}


def kit_dict(zone: str) -> dict:
    k = KIT[zone]
    return {"zone": zone, "mat": [{"code": c, "title": t, "unit": u} for c, t, u in k["mat"]],
            "obr": [{"code": c, "title": t} for c, t in k["obr"]], "ras": [{"code": c, "title": t} for c, t in k["ras"]],
            "pre": k["pre"], "post": k["post"], "aerosol": k["aerosol"], "facade": k["facade"], "states": STATES}


def can_edit(conn, p: dict, object_id: int) -> bool:
    if p["role_code"] in EDIT_ROLES:
        return True
    o = conn.execute("SELECT gip_person_id FROM objects WHERE id=%s", (object_id,)).fetchone()
    return bool(o and o["gip_person_id"] == p["id"])


def _zone(p: dict, zone: str):
    if zone not in KIT:
        raise HTTPException(400, "зона: mural или print")
    if p["role_code"] != "head" and zone not in p["zones"]:
        raise HTTPException(403, "эта зона вам не назначена")


def _num(x) -> float:
    try:
        return max(0.0, float(str(x).replace(",", ".")))
    except (TypeError, ValueError):
        return 0.0


def clean(items: dict, zone: str) -> dict:
    """Принимаем только известные строки; числа неотрицательные; аэрозоль и «доп.» — свободный текст до 60 знаков."""
    k = KIT[zone]
    known_mat = {c for c, _, _ in k["mat"]}
    known_obr = {c for c, _ in k["obr"]}
    known_ras = {c for c, _ in k["ras"]}
    q = lambda r: {"taken": _num(r.get("taken")), "returned": None if r.get("returned") in (None, "") else _num(r.get("returned"))}
    out = {
        "aerosol": [{"color": str(r.get("color") or "").strip()[:60], **q(r)} for r in (items.get("aerosol") or [])[:80]
                    if str(r.get("color") or "").strip()] if k["aerosol"] else [],
        "facade": q(items.get("facade") or {}) if k["facade"] else None,
        "mat": {c: q(r) for c, r in (items.get("mat") or {}).items() if c in known_mat},
        "extra": [{"title": str(r.get("title") or "").strip()[:80], "unit": str(r.get("unit") or "шт")[:10], **q(r)}
                  for r in (items.get("extra") or [])[:30] if str(r.get("title") or "").strip()],
        "obr": {c: {"took": bool(r.get("took")), "state_out": r.get("state_out") if r.get("state_out") in STATES else None,
                    "back": bool(r.get("back")), "state_in": r.get("state_in") if r.get("state_in") in STATES else None,
                    "note": str(r.get("note") or "")[:120]}
                for c, r in (items.get("obr") or {}).items() if c in known_obr},
        "ras": {c: bool(v) for c, v in (items.get("ras") or {}).items() if c in known_ras},
        "pre": [bool(x) for x in (items.get("pre") or [])][:len(k["pre"])],
        "post": [bool(x) for x in (items.get("post") or [])][:len(k["post"])],
    }
    return out


def usage(items: dict) -> dict:
    """Расход при сдаче: взято − вернул. Аэрозоль — по номерам цвета, фасадная — литры."""
    used = lambda r: round(max(0.0, (r.get("taken") or 0) - (r.get("returned") or 0)), 2)
    return {"aerosol": [{"color": r["color"], "used": used(r)} for r in items.get("aerosol", [])],
            "aerosol_total": sum(used(r) for r in items.get("aerosol", [])),
            "facade_l": used(items["facade"]) if items.get("facade") else None,
            "mat": {c: used(r) for c, r in items.get("mat", {}).items()},
            "lost": [c for c, r in items.get("obr", {}).items() if r.get("took") and (r.get("state_in") == "потеряно" or not r.get("back"))]}


@router.get("/kit/dict")
def api_dict(p: dict = Depends(active)):
    zones = [z for z in KIT if p["role_code"] == "head" or z in p["zones"]]
    return {"zones": {z: kit_dict(z) for z in zones}, "can_edit_role": p["role_code"] in EDIT_ROLES}


@router.get("/kit")
def api_list(p: dict = Depends(active)):
    """Списки по активным объектам: свои зоны. Кто может править — для каждого списка."""
    with db.pool.connection() as conn:
        objs = conn.execute("SELECT id, title, city, gip_person_id FROM objects WHERE status='active' AND (id=0 OR bitrix_stage=%s) ORDER BY id DESC",
                            (sync_objects.WORK,)).fetchall()
        lists = conn.execute("""SELECT k.id, k.object_id, k.zone_code, k.status, k.updated_at, k.closed_at, pe.full_name AS updated_name
                                FROM kit_lists k LEFT JOIN people pe ON pe.id = coalesce(k.updated_by, k.created_by)""").fetchall()
    zones = [z for z in KIT if p["role_code"] == "head" or z in p["zones"]]
    by = {(x["object_id"], x["zone_code"]): x for x in lists}
    return {"objects": [{**o, "can_edit": p["role_code"] in EDIT_ROLES or o["gip_person_id"] == p["id"],
                         "lists": {z: by.get((o["id"], z)) for z in zones}} for o in objs], "zones": zones}


@router.get("/kit/{object_id}/{zone}")
def api_get(object_id: int, zone: str, p: dict = Depends(active)):
    _zone(p, zone)
    with db.pool.connection() as conn:
        o = conn.execute("SELECT id, title, city FROM objects WHERE id=%s", (object_id,)).fetchone()
        if not o:
            raise HTTPException(404, "нет такого объекта")
        k = conn.execute("SELECT * FROM kit_lists WHERE object_id=%s AND zone_code=%s", (object_id, zone)).fetchone()
        edit = can_edit(conn, p, object_id)
    out = {"object": o, "dict": kit_dict(zone), "list": k, "can_edit": edit and (not k or k["status"] == "open")}
    if k and k["status"] == "closed":
        out["usage"] = usage(k["items"])
    return out


class KitIn(BaseModel):
    items: dict = Field(default_factory=dict)


@router.post("/kit/{object_id}/{zone}")
def api_save(object_id: int, zone: str, b: KitIn, p: dict = Depends(active)):
    _zone(p, zone)
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM objects WHERE id=%s AND status='active'", (object_id,)).fetchone():
            raise HTTPException(400, "объект закрыт или не найден")
        if not can_edit(conn, p, object_id):
            raise HTTPException(403, "Сбор ведут Главный художник, Художник-Про, Мастер печати и ГИП объекта")
        items = clean(b.items, zone)
        k = conn.execute("SELECT id, status FROM kit_lists WHERE object_id=%s AND zone_code=%s FOR UPDATE", (object_id, zone)).fetchone()
        if k and k["status"] == "closed":
            raise HTTPException(409, "Проект уже сдан, список закрыт")
        if k:
            conn.execute("UPDATE kit_lists SET items=%s, updated_by=%s, updated_at=now() WHERE id=%s", (Jsonb(items), p["id"], k["id"]))
            kid = k["id"]
        else:
            kid = conn.execute("""INSERT INTO kit_lists (object_id, zone_code, items, created_by, updated_by) VALUES (%s,%s,%s,%s,%s)
                                  RETURNING id""", (object_id, zone, Jsonb(items), p["id"], p["id"])).fetchone()["id"]
        db.audit(conn, p["id"], "kit_save", "kit_lists", kid, {"object": object_id, "zone": zone})
        return conn.execute("SELECT * FROM kit_lists WHERE id=%s", (kid,)).fetchone()


@router.post("/kit/{object_id}/{zone}/close")
def api_close(object_id: int, zone: str, p: dict = Depends(active)):
    """«Сдать проект»: всё, что взяли, отмечено «вернул» и состоянием. Дальше список только для чтения."""
    _zone(p, zone)
    with db.pool.connection() as conn, conn.transaction():
        if not can_edit(conn, p, object_id):
            raise HTTPException(403, "Сдаёт тот, кто ведёт сбор")
        k = conn.execute("SELECT * FROM kit_lists WHERE object_id=%s AND zone_code=%s FOR UPDATE", (object_id, zone)).fetchone()
        if not k or k["status"] != "open":
            raise HTTPException(409, "Списка нет или он уже сдан")
        it = k["items"]
        miss = [c for c, r in it.get("obr", {}).items() if r.get("took") and not (r.get("back") or r.get("state_in") == "потеряно")]
        miss += [c for c, r in it.get("obr", {}).items() if r.get("took") and not r.get("state_in")]
        noret = [r["color"] for r in it.get("aerosol", []) if r.get("taken") and r.get("returned") is None]
        noret += [c for c, r in it.get("mat", {}).items() if r.get("taken") and r.get("returned") is None]
        if it.get("facade") and it["facade"].get("taken") and it["facade"].get("returned") is None:
            noret.append("фасадная")
        if miss or noret:
            raise HTTPException(409, "Не всё отмечено: " + ", ".join(sorted(set(miss)) + noret)[:300])
        conn.execute("UPDATE kit_lists SET status='closed', closed_by=%s, closed_at=%s WHERE id=%s",
                     (p["id"], datetime.now(timezone.utc), k["id"]))
        db.audit(conn, p["id"], "kit_close", "kit_lists", k["id"], usage(it))
    return {"ok": True, "usage": usage(it)}
