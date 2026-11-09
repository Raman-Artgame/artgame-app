"""Дизайн в воронке Битрикса «Дизайн РК» (HEAD 06–07.11.2026) и каталог референсов.

- Сделки воронки 13: Главный дизайнер и HEAD видят все и назначают дизайнера, размер и срок; помощник — где он в поле
  «Ответственный дизайнер». Стадии двигают сами (только открытые стадии воронки и «УТВЕРЖДЕНО»).
- Круги правок: каждый переход в «Правки» — новый круг в счётчике карточки, без доплаты (HEAD 07.11).
- Единицы: XS 0,5 / S 1 / M 2 / L 4 / XL 8 (design.unit.* в «Значениях»). Засчитываются, только когда макет и эскиз
  утверждены — сделка в «УТВЕРЖДЕНО». Если проект в работу не пошёл, HEAD снимает единицу с причиной.
- Каталог референсов: 1–2 исполнителя → HEAD «утверждаю» → pay.design.catalog, двоим пополам (начисление в ФОТ месяца).
Запись в Битрикс — тем же вебхуком, что у МОП (bxw.CALL), только поля дизайна, каждая запись в audit_log и сверяется.
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, bxw, db
from . import constants as consts
from .work import active

router = APIRouter(prefix="/api")

CAT = 13
DESIGNERS = {"lead_designer", "designer_asst"}
ALL = {"lead_designer", "head"}            # видят все сделки дизайна и назначают
F_DESIGNER, F_SIZE, F_DEADLINE = "UF_CRM_ARTGAME_DESIGNER", "UF_CRM_ARTGAME_DESIGN_COMPLEXITY", "UF_CRM_ARTGAME_DESIGN_DEADLINE"
F_FOLDER, F_LAYOUT = "UF_CRM_ARTGAME_PROJECT_URL", "UF_CRM_ARTGAME_APPROVED_LAYOUT"
# «Сложность дизайна» в Битриксе: S, M, L, X, XL. XS там нет — XS хранится в приложении (design_sizes); «X» не считаем.
SIZE_ENUM = {"s": "43343", "m": "43345", "l": "43347", "xl": "43351"}
ENUM_SIZE = {v: k for k, v in SIZE_ENUM.items()}
SIZES = ["xs", "s", "m", "l", "xl"]
WON, REVISE = f"C{CAT}:WON", f"C{CAT}:EXECUTING"
SELECT = ["ID", "TITLE", "STAGE_ID", "ASSIGNED_BY_ID", "DATE_MODIFY", "CLOSEDATE", F_DESIGNER, F_SIZE, F_DEADLINE, F_FOLDER, F_LAYOUT,
          bx.CITY, bx.OBJECT]


def need(p: dict):
    if p["role_code"] not in DESIGNERS | {"head"}:
        raise HTTPException(403, "Раздел дизайна — для дизайнеров и HEAD")


def unit_of(v: dict, size: str | None) -> float:
    return float(v.get(f"design.unit.{size}") or 0) if size else 0.0


def _people_by_bx(conn) -> dict:
    return {r["bitrix_user_id"]: r for r in conn.execute(
        "SELECT id, full_name, role_code, bitrix_user_id FROM people WHERE bitrix_user_id IS NOT NULL").fetchall()}


def _size(d: dict, local: dict) -> str | None:
    did = int(d["ID"])
    if did in local:
        return local[did]
    return ENUM_SIZE.get(str(d.get(F_SIZE) or ""))


def _rounds(conn, ids: list[int]) -> dict:
    return {r["deal_id"]: r["n"] for r in conn.execute(
        "SELECT deal_id, max(round) AS n FROM design_rounds WHERE deal_id = ANY(%s) GROUP BY deal_id", (ids,)).fetchall()}


def _date(v) -> str | None:
    return str(v)[:10] if v else None


def sync_units(conn, rows: list[dict], v: dict, local: dict, people: dict) -> int:
    """Сделки в «УТВЕРЖДЕНО» → единица дизайнеру из поля «Ответственный дизайнер» (один раз на сделку)."""
    added = 0
    rounds = _rounds(conn, [int(d["ID"]) for d in rows])
    for d in rows:
        if d.get("STAGE_ID") != WON:
            continue
        did = int(d["ID"])
        if conn.execute("SELECT 1 FROM design_units WHERE deal_id=%s", (did,)).fetchone():
            continue
        uid = int(d.get(F_DESIGNER) or 0) or None
        size = _size(d, local)
        at = d.get("CLOSEDATE") or d.get("DATE_MODIFY")
        conn.execute("""INSERT INTO design_units (deal_id, title, person_id, bitrix_user_id, size, units, rounds, approved_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (deal_id) DO NOTHING""",
                     (did, d.get("TITLE"), (people.get(uid) or {}).get("id"), uid, size, unit_of(v, size), rounds.get(did, 0),
                      at or datetime.now(timezone.utc)))
        added += 1
    return added


def month_start(ym: str | None = None) -> date:
    t = date.today() if not ym else date(int(ym[:4]), int(ym[5:7]), 1)
    return t.replace(day=1)


@router.get("/design/deals")
def deals(fresh: int = 0, p: dict = Depends(active)):
    need(p)
    me_bx = bx.bx_id(p)
    if p["role_code"] not in ALL and not me_bx:
        raise HTTPException(409, "HEAD ещё не связал вас с пользователем Битрикса (вкладка «Команда»)")
    rows = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": [CAT], "STAGE_SEMANTIC_ID": "P"}, "select": SELECT,
                                         "order": {"ID": "DESC"}}, fresh=bool(fresh))
    start = month_start()
    won = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": [CAT], "STAGE_SEMANTIC_ID": "S", ">=CLOSEDATE": start.isoformat(),
                                                   "<CLOSEDATE": date(start.year + start.month // 12, start.month % 12 + 1, 1).isoformat()},
                                        "select": SELECT}, fresh=bool(fresh))
    st = bx.stages()
    with db.pool.connection() as conn, conn.transaction():
        v = consts.latest(conn)
        people = _people_by_bx(conn)
        ids = [int(d["ID"]) for d in rows + won]
        local = {r["deal_id"]: r["size"] for r in conn.execute("SELECT deal_id, size FROM design_sizes WHERE deal_id = ANY(%s)", (ids,)).fetchall()}
        sync_units(conn, won, v, local, people)
        rounds = _rounds(conn, ids)
    out = []
    bxn = {u["id"]: u["name"] for u in bx_designers()} if any(int(d.get(F_DESIGNER) or 0) not in people for d in rows if d.get(F_DESIGNER)) else {}
    for d in rows:
        uid = int(d.get(F_DESIGNER) or 0) or None
        if p["role_code"] not in ALL and uid != me_bx:
            continue
        size = _size(d, local)
        out.append({"id": int(d["ID"]), "title": d.get("TITLE") or "", "stage": d.get("STAGE_ID"),
                    "stage_name": (st.get(d.get("STAGE_ID")) or {}).get("name", d.get("STAGE_ID")),
                    "designer_bx": uid, "designer": (people.get(uid) or {}).get("full_name") or bxn.get(uid), "size": size,
                    "units": unit_of(v, size), "deadline": _date(d.get(F_DEADLINE)), "folder": d.get(F_FOLDER) or "",
                    "layout": d.get(F_LAYOUT) or "", "rounds": rounds.get(int(d["ID"]), 0), "city": bx.city_name(d.get(bx.CITY)),
                    "manager_bx": int(d.get("ASSIGNED_BY_ID") or 0)})
    stages = sorted([{"id": k, "name": s["name"], "sort": s["sort"]} for k, s in st.items()
                     if k.startswith(f"C{CAT}:") and (s["semantic"] == "process" or k == WON)], key=lambda x: x["sort"])
    return {"deals": out, "stages": stages, "sizes": [{"code": s, "title": s.upper(), "units": unit_of(v, s)} for s in SIZES],
            "can_assign": p["role_code"] in ALL, "bx": bxw.enabled()}


@router.get("/design/team")
def team(p: dict = Depends(active)):
    need(p)
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT id, full_name, role_code, bitrix_user_id FROM people
                               WHERE status='active' AND role_code = ANY(%s) ORDER BY role_code, full_name""",
                            (sorted(DESIGNERS),)).fetchall()
    # HEAD 09.11: дизайнеры из Битрикса (должность «Дизайнер…»), которых ещё нет в приложении, — тоже в выборе (Малика)
    linked = {r["bitrix_user_id"] for r in rows if r["bitrix_user_id"]}
    return rows + [{"id": None, "full_name": u["name"], "role_code": None, "bitrix_user_id": u["id"], "bx_only": True}
                   for u in bx_designers() if u["id"] not in linked]


def bx_designers() -> list:
    try:
        return [u for u in bx.users() if "дизайн" in (u.get("position") or "").lower() and u["name"]]
    except Exception:   # Битрикс недоступен — выбор из своих
        return []


class DealIn(BaseModel):
    stage: str | None = None
    designer_bx: int | None = None
    size: str | None = None
    deadline: date | None = None
    folder: str | None = Field(default=None, max_length=500)
    layout: str | None = Field(default=None, max_length=500)


@router.post("/design/deals/{deal_id}")
def update(deal_id: int, b: DealIn, p: dict = Depends(active)):
    need(p)
    j = bx.read("crm.deal.get", {"id": deal_id}, fresh=True)
    d = j.get("result", j) if isinstance(j, dict) else None
    if not d or int(d.get("CATEGORY_ID") or -1) != CAT:
        raise HTTPException(404, "Это не сделка воронки «Дизайн РК»")
    lead = p["role_code"] in ALL
    cur_uid = int(d.get(F_DESIGNER) or 0) or None
    if not lead and cur_uid != bx.bx_id(p):
        raise HTTPException(403, "Это задача другого дизайнера")
    if not lead and (b.designer_bx is not None or b.size is not None):
        raise HTTPException(403, "Дизайнера и размер назначает Главный дизайнер")
    fields, note = {}, []
    if b.designer_bx is not None:
        fields[F_DESIGNER] = b.designer_bx or ""
        note.append("дизайнер назначен")
    if b.size is not None:
        if b.size not in SIZES:
            raise HTTPException(400, "размер: XS, S, M, L или XL")
        if b.size in SIZE_ENUM:
            fields[F_SIZE] = SIZE_ENUM[b.size]
        note.append(f"размер {b.size.upper()}")
    if b.deadline is not None:
        fields[F_DEADLINE] = b.deadline.isoformat()
        note.append(f"срок {b.deadline:%d.%m}")
    if b.folder is not None:
        fields[F_FOLDER] = b.folder.strip()
    if b.layout is not None:
        fields[F_LAYOUT] = b.layout.strip()
    with db.pool.connection() as conn:
        local = conn.execute("SELECT size FROM design_sizes WHERE deal_id=%s", (deal_id,)).fetchone()
    size = b.size or (local or {}).get("size") or ENUM_SIZE.get(str(d.get(F_SIZE) or ""))
    if b.stage is not None:
        st = bx.stages()
        ok = b.stage.startswith(f"C{CAT}:") and b.stage in st and (st[b.stage]["semantic"] == "process" or b.stage == WON)
        if not ok:
            raise HTTPException(400, "Такой стадии в воронке дизайна нет")
        if b.stage == WON:
            layout = b.layout if b.layout is not None else d.get(F_LAYOUT)
            designer = b.designer_bx if b.designer_bx is not None else cur_uid
            miss = [t for t, x in (("размер", size), ("ссылка на утверждённый эскиз", layout), ("дизайнер", designer)) if not x]
            if miss:
                raise HTTPException(409, "Перед «УТВЕРЖДЕНО» заполните: " + ", ".join(miss))
        if b.stage != d.get("STAGE_ID"):
            fields["STAGE_ID"] = b.stage
            note.append("стадия «" + st[b.stage]["name"] + "»")
    log = {"what": "design", "fields": fields}
    if fields and bxw.enabled():
        try:
            bxw.CALL("crm.deal.update", {"id": deal_id, "fields": fields, "params": {"REGISTER_SONET_EVENT": "Y"}})
            if note:
                bxw.CALL("crm.timeline.comment.add", {"fields": {"ENTITY_ID": deal_id, "ENTITY_TYPE": "deal",
                                                                 "COMMENT": f"{p['full_name']} (приложение, дизайн): {', '.join(note)}"}})
            bx._cache.clear()
            j2 = bx.read("crm.deal.get", {"id": deal_id}, fresh=True)
            after = j2.get("result", j2) if isinstance(j2, dict) else {}
            bad = [k for k, x in fields.items() if not bxw._same(after.get(k), x)]
            log["bx"] = "error" if bad else "ok"
            if bad:
                log["error"] = "не записалось: " + ", ".join(bad)
            d = after or d
        except Exception as ex:  # noqa: BLE001
            log["bx"], log["error"] = "error", str(ex)[:300]
    else:
        log["bx"] = "off" if fields else "nothing"
    with db.pool.connection() as conn, conn.transaction():
        if b.size is not None:
            conn.execute("""INSERT INTO design_sizes (deal_id, size, set_by) VALUES (%s,%s,%s)
                            ON CONFLICT (deal_id) DO UPDATE SET size=EXCLUDED.size, set_by=EXCLUDED.set_by, set_at=now()""",
                         (deal_id, b.size, p["id"]))
        moved = log.get("bx") in ("ok", "off") and "STAGE_ID" in fields
        if moved and fields["STAGE_ID"] == REVISE:
            n = (conn.execute("SELECT max(round) AS n FROM design_rounds WHERE deal_id=%s", (deal_id,)).fetchone()["n"] or 0) + 1
            conn.execute("INSERT INTO design_rounds (deal_id, round, person_id) VALUES (%s,%s,%s)", (deal_id, n, p["id"]))
            log["round"] = n
        if moved and fields["STAGE_ID"] == WON:
            v = consts.latest(conn)
            d2 = {**d, "STAGE_ID": WON, F_DESIGNER: fields.get(F_DESIGNER, cur_uid), "CLOSEDATE": datetime.now(timezone.utc)}
            sync_units(conn, [d2], v, {deal_id: size} if size else {}, _people_by_bx(conn))
        db.audit(conn, p["id"], "bx_write", "deal", deal_id, log)
    if log["bx"] == "error":
        raise HTTPException(502, "Битрикс: " + log.get("error", "ошибка"))
    return {"ok": True, "bx": log["bx"], "round": log.get("round")}


@router.get("/design/units")
def units(ym: str | None = None, p: dict = Depends(active)):
    """Единицы за месяц: свои; Главный дизайнер и HEAD — все. Норма и доплата — из «Значений» (если норма задана)."""
    need(p)
    start = month_start(ym)
    end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    with db.pool.connection() as conn:
        v = consts.latest(conn)
        cond, args = ("", []) if p["role_code"] in ALL else (" AND u.person_id=%s", [p["id"]])
        rows = conn.execute(f"""SELECT u.*, pe.full_name FROM design_units u LEFT JOIN people pe ON pe.id=u.person_id
                                WHERE u.approved_at >= %s AND u.approved_at < %s{cond} ORDER BY u.approved_at""",
                            [start, end, *args]).fetchall()
    mine = sum(float(r["units"]) for r in rows if r["status"] == "active" and r["person_id"] == p["id"])
    return {"month": f"{start:%Y-%m}", "rows": rows, "mine": mine, "norm": v.get("pay.design.norm_units"),
            "unit_over": v.get("pay.design.unit_over"), "can_cancel": p["role_code"] == "head"}


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/design/units/{deal_id}/cancel")
def unit_cancel(deal_id: int, b: CancelIn, p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "Снимает единицу только HEAD")
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("UPDATE design_units SET status='cancelled', reason=%s WHERE deal_id=%s AND status='active' RETURNING deal_id",
                            (b.reason, deal_id)).fetchone():
            raise HTTPException(409, "Единицы нет или уже снята")
        db.audit(conn, p["id"], "design_unit_cancel", "design_units", deal_id, {"reason": b.reason})
    return {"ok": True}


# ---------- каталог референсов ----------

class CatalogIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    style: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=500)
    authors: list[int] = Field(min_length=1, max_length=2)


def _authors_ok(conn, ids: list[int]):
    ok = conn.execute("SELECT count(*) AS n FROM people WHERE id = ANY(%s) AND role_code = ANY(%s) AND status='active'",
                      (ids, sorted(DESIGNERS))).fetchone()["n"]
    if ok != len(set(ids)):
        raise HTTPException(400, "Исполнители — один или два дизайнера")


@router.get("/design/catalogs")
def catalogs(p: dict = Depends(active)):
    need(p)
    with db.pool.connection() as conn:
        v = consts.latest(conn)
        rows = conn.execute("""SELECT c.*, (SELECT array_agg(full_name ORDER BY full_name) FROM people WHERE id = ANY(c.authors)) AS author_names
                               FROM design_catalogs c WHERE c.status <> 'cancelled' ORDER BY c.id DESC""").fetchall()
    return {"rows": rows, "amount": v.get("pay.design.catalog"), "is_head": p["role_code"] == "head"}


@router.post("/design/catalogs")
def catalog_add(b: CatalogIn, p: dict = Depends(active)):
    if p["role_code"] not in DESIGNERS:
        raise HTTPException(403, "Каталог заводит дизайнер")
    with db.pool.connection() as conn, conn.transaction():
        _authors_ok(conn, b.authors)
        row = conn.execute("""INSERT INTO design_catalogs (title, style, url, authors, created_by) VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                           (b.title.strip(), b.style, b.url, sorted(set(b.authors)), p["id"])).fetchone()
        db.audit(conn, p["id"], "catalog_add", "design_catalogs", row["id"], b.model_dump())
        return row


@router.post("/design/catalogs/{cid}")
def catalog_edit(cid: int, b: CatalogIn, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        c = conn.execute("SELECT * FROM design_catalogs WHERE id=%s FOR UPDATE", (cid,)).fetchone()
        if not c or (p["id"] not in c["authors"] and p["id"] != c["created_by"]):
            raise HTTPException(403, "Править может исполнитель каталога")
        if c["status"] not in ("draft", "returned"):
            raise HTTPException(409, "Каталог уже у HEAD или утверждён")
        _authors_ok(conn, b.authors)
        conn.execute("UPDATE design_catalogs SET title=%s, style=%s, url=%s, authors=%s WHERE id=%s",
                     (b.title.strip(), b.style, b.url, sorted(set(b.authors)), cid))
        db.audit(conn, p["id"], "catalog_edit", "design_catalogs", cid, b.model_dump())
    return {"ok": True}


@router.post("/design/catalogs/{cid}/send")
def catalog_send(cid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn, conn.transaction():
        c = conn.execute("SELECT * FROM design_catalogs WHERE id=%s FOR UPDATE", (cid,)).fetchone()
        if not c or (p["id"] not in c["authors"] and p["id"] != c["created_by"]):
            raise HTTPException(403, "Отправляет исполнитель каталога")
        if c["status"] not in ("draft", "returned"):
            raise HTTPException(409, "Каталог уже отправлен")
        if not (c["url"] or "").strip():
            raise HTTPException(409, "Добавьте ссылку на папку или рефборд")
        conn.execute("UPDATE design_catalogs SET status='sent', sent_at=now() WHERE id=%s", (cid,))
        db.audit(conn, p["id"], "catalog_send", "design_catalogs", cid)
        head = conn.execute("SELECT tg_id FROM people WHERE role_code='head' AND status='active' ORDER BY id LIMIT 1").fetchone()
    try:
        from . import notify
        if head and head.get("tg_id"):
            notify.SEND(head["tg_id"], f"Каталог референсов «{c['title']}» на утверждение. Приложение → «Дизайн» → «Каталоги».")
    except Exception as e:  # noqa: BLE001
        print("catalog notify:", e)
    return {"ok": True}


class DecideIn(BaseModel):
    approve: bool
    comment: str | None = Field(default=None, max_length=500)


@router.post("/design/catalogs/{cid}/decide")
def catalog_decide(cid: int, b: DecideIn, p: dict = Depends(active)):
    if p["role_code"] != "head":
        raise HTTPException(403, "Утверждает HEAD")
    if not b.approve and not (b.comment or "").strip():
        raise HTTPException(400, "Напишите, что поправить")
    with db.pool.connection() as conn, conn.transaction():
        c = conn.execute("SELECT * FROM design_catalogs WHERE id=%s FOR UPDATE", (cid,)).fetchone()
        if not c or c["status"] != "sent":
            raise HTTPException(409, "Каталог не ждёт решения")
        conn.execute("UPDATE design_catalogs SET status=%s, comment=%s, decided_by=%s, decided_at=now() WHERE id=%s",
                     ("approved" if b.approve else "returned", b.comment, p["id"], cid))
        db.audit(conn, p["id"], "catalog_" + ("approved" if b.approve else "returned"), "design_catalogs", cid, b.model_dump())
    return {"ok": True}


def accruals(conn, v: dict, start: datetime, end: datetime) -> tuple[dict, dict, list]:
    """Для ФОТ месяца: {person_id: единиц}, {person_id: [(сумма, текст, id)]} по каталогам, предупреждения."""
    units_by = {r["person_id"]: float(r["s"]) for r in conn.execute(
        """SELECT person_id, sum(units) AS s FROM design_units WHERE status='active' AND person_id IS NOT NULL
           AND approved_at >= %s AND approved_at < %s GROUP BY person_id""", (start, end)).fetchall()}
    cat_by: dict = {}
    warn = []
    amount = v.get("pay.design.catalog") or 0
    for c in conn.execute("SELECT * FROM design_catalogs WHERE status='approved' AND decided_at >= %s AND decided_at < %s",
                          (start, end)).fetchall():
        if not amount:
            warn.append("каталог референсов: нет pay.design.catalog в «Значениях»")
            break
        share = round(amount / len(c["authors"]), 2)
        for a in c["authors"]:
            cat_by.setdefault(a, []).append((share, f"каталог «{c['title']}»" + (" (пополам)" if len(c["authors"]) > 1 else ""), str(c["id"])))
    return units_by, cat_by, warn
