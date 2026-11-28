"""Сторож папок сделок (HEAD 27.11.2026: «чтобы всё создавалось, чтобы всё возможно было загрузить»).

Было: приложение делало папку только по кнопке «В сделку», а сделкам, заведённым прямо в Битриксе, — серверный робот,
который молча вставал, если «Объект» пуст (1745) или не сходится с названием (1743). 27.11 папки не было у 9 из 27
открытых сделок.

Стало: каждые 10 минут (таймер sync_objects) по всем открытым сделкам воронок «Продажи РК» и «Дизайн РК»:
- папки в сделке нет → ищем на Диске «№ ·», не нашли — создаём (имя из «Объекта», пусто — из названия сделки;
  ничто создание не блокирует), ID и ссылку пишем в сделку (drive.bind_deal, под тем же флагом ARTGAME_DRIVE_BIND);
- не вышло → строка с ошибкой: её видит HEAD в Пульте и МОП в «Сегодня»; следующая попытка — через 10 минут;
- «Объект» пуст → папка всё равно есть, а МОП видит «заполни Объект».
С 28.11 (вопрос Малики «папка есть, а папки Дизайн внутри нет»): в каждой папке сделки сторож досоздаёт подпапки
drive.SUBFOLDERS (ДИЗАЙН, МЕДИА, ДОКУМЕНТЫ, РАСХОДЫ ЧЕКИ, ПРИХОДЫ ЧЕКИ) — до SUB_LIMIT сделок за проход, раз в сутки перепроверяет.
Ничего не переносит и не удаляет: перекладывает папки по месяцам по-прежнему только робот DRIVE01.
"""
from . import db, drive
from .sync_objects import F_CITY, F_OBJECT, FOLDER_FIELD, _city, split_title

CATEGORIES = (0, 13)
LIMIT = 15          # новых папок за проход: Диск не торопим, остальные — через 10 минут
SUB_LIMIT = 15      # папок за проход, в которых проверяем подпапки
SUB_RECHECK = "1 day"   # подпапку могли удалить руками — раз в сутки смотрим снова
SELECT = ["ID", "TITLE", "CATEGORY_ID", "STAGE_ID", "DATE_CREATE", "ASSIGNED_BY_ID", FOLDER_FIELD, F_OBJECT, F_CITY]


def open_deals(rd) -> list[dict]:
    out, start = [], 0
    while start is not None:
        j = rd("crm.deal.list", {"filter": {"CATEGORY_ID": list(CATEGORIES), "CLOSED": "N"}, "select": SELECT,
                                 "order": {"ID": "DESC"}, "start": start})   # свежие сделки первыми: по ним работают сегодня
        if isinstance(j, list):
            out += j
            break
        out += j.get("result", [])
        start = j.get("next")
    return out


def name_of(d: dict) -> tuple[str, str | None]:
    """Имя папки: «Объект», иначе название сделки без номера и города, иначе «СДЕЛКА №»."""
    name, city = split_title(str(d["ID"]), d.get("TITLE") or "")
    obj = (d.get(F_OBJECT) or "").strip() or name or f"Сделка {d['ID']}"
    return obj, city or _city(d.get(F_CITY))


def subfolders(dv, folder: str) -> None:
    """Все подпапки сделки: что есть (в любом регистре) — не трогаем, чего нет — создаём."""
    for name in drive.SUBFOLDERS.values():
        parent = folder
        for part in name.split("/"):
            parent = dv.child(parent, part)


def run(conn, deals: list[dict], dv=None) -> dict:
    made = errors = subs = 0
    fresh = {r["deal_id"] for r in conn.execute(
        f"SELECT deal_id FROM deal_folders WHERE subs_at > now() - interval '{SUB_RECHECK}'").fetchall()}
    # сделки с заданием на дизайн — первыми и сверх лимита: туда дизайнер пойдёт сегодня
    prio = {r["deal_id"] for r in conn.execute("SELECT DISTINCT deal_id FROM design_tasks WHERE status='active' AND stage<>'done'").fetchall()}
    known = {r["deal_id"]: r for r in conn.execute("SELECT * FROM deal_folders").fetchall()}
    seen = []
    for d in deals:
        did = int(d["ID"])
        seen.append(did)
        no_obj = not (d.get(F_OBJECT) or "").strip()
        mop = int(d["ASSIGNED_BY_ID"]) if str(d.get("ASSIGNED_BY_ID") or "").isdigit() else None
        fid, state, err, by_app = d.get(FOLDER_FIELD) or None, "ok", None, bool(known.get(did, {}).get("made_by_app"))
        if not fid and known.get(did, {}).get("state") == "ok" and known[did]["folder_id"] and not drive.settings.drive_bind:
            fid = known[did]["folder_id"]        # папка сделана, в сделку её запишет робот по метке — Диск заново не спрашиваем
        elif not fid:
            if made + errors >= LIMIT:
                continue
            try:
                dv = dv or drive.Drive()
                obj, city = name_of(d)
                fid = dv.project_folder({"id": did, "title": obj, "city": city, "created": d.get("DATE_CREATE")})
                if drive.bind_deal(conn, did, fid) == "error":
                    state, err = "error", "папка на Диске есть, но в сделку не записалась — повторю через 10 минут"
                made, by_app = made + 1, True
            except Exception as ex:  # noqa: BLE001 — одна сделка не должна останавливать остальные (так встал робот на 1709)
                state, err = "error", f"{type(ex).__name__}: {str(ex)[:200]}"
                errors += 1
        was = known.get(did)
        conn.execute("""INSERT INTO deal_folders (deal_id, title, mop_bx_id, folder_id, state, error, no_object, made_by_app, checked_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
                        ON CONFLICT (deal_id) DO UPDATE SET title=EXCLUDED.title, mop_bx_id=EXCLUDED.mop_bx_id, folder_id=EXCLUDED.folder_id,
                            state=EXCLUDED.state, error=EXCLUDED.error, no_object=EXCLUDED.no_object, made_by_app=EXCLUDED.made_by_app, checked_at=now()""",
                     (did, d.get("TITLE") or "", mop, fid, state, err, no_obj, by_app))
        if fid and state == "ok" and did not in fresh and (did in prio or subs < SUB_LIMIT):
            subs += 1
            try:
                dv = dv or drive.Drive()
                subfolders(dv, fid)
                conn.execute("UPDATE deal_folders SET subs_at=now(), subs_error=NULL WHERE deal_id=%s", (did,))
            except Exception as ex:  # noqa: BLE001 — повторим в следующий проход, HEAD видит на Пульте
                conn.execute("UPDATE deal_folders SET subs_error=%s WHERE deal_id=%s", (f"{type(ex).__name__}: {str(ex)[:200]}", did))
        if state == "error" and not (was and was["state"] == "error"):
            db.audit(conn, None, "deal_folder_error", "deal", did, {"error": err})
        elif by_app and not (was and was["made_by_app"]):
            db.audit(conn, None, "deal_folder_made", "deal", did, {"folder": fid, "no_object": no_obj})
    conn.execute("DELETE FROM deal_folders WHERE NOT (deal_id = ANY(%s))", (seen,))   # сделка закрыта — строка больше не нужна
    return {"open": len(seen), "made": made, "errors": errors, "subs": subs}


def problems(conn, mop_bx_id: int | None = None, ids: list[int] | None = None) -> list[dict]:
    """Что показать людям: нет папки (ошибка) и пустой «Объект». Для МОП — только его сделки."""
    rows = conn.execute("""SELECT deal_id, title, state, error, no_object, subs_error FROM deal_folders
                           WHERE (state='error' OR no_object OR subs_error IS NOT NULL) AND (%s::bigint IS NULL OR mop_bx_id=%s) AND (%s::bigint[] IS NULL OR deal_id = ANY(%s))
                           ORDER BY state='error' DESC, deal_id""", (mop_bx_id, mop_bx_id, ids, ids)).fetchall()
    return [{"id": r["deal_id"], "title": r["title"], "no_folder": r["state"] == "error", "error": r["error"] or r["subs_error"] or "", "no_object": r["no_object"],
             "no_subs": bool(r["subs_error"])} for r in rows]
