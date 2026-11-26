"""Задачи на дизайн при сделке (HEAD 25.11.2026 «в целом норм, давай попробуем»).

- МОП (или HEAD) в карточке сделки жмёт «Нужен дизайн» — на любой стадии, сколько угодно раз. Сделка остаётся на своей стадии.
- У дизайнера карточка во вкладке «Дизайн» с привычными стадиями воронки «Дизайн РК» (названия те же, хранятся здесь).
- Дизайнер видит свои и ещё не разобранные задачи; Главный дизайнер и HEAD — все и назначают исполнителя.
- Эскиз — файлом прямо в карточке: ложится в папку сделки ДИЗАЙН (HEAD 26.11: ссылок руками нет).
- Единиц задачи не дают: единица одна за весь проект (design_units), считается как раньше.
- В Битрикс ничего не пишем и в бот не шлём: новое видно цифрой на доске и в карточке сделки.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, bxw, db
from .design import ALL, SIZES, need
from .work import active

router = APIRouter(prefix="/api")

# Те же стадии и тот же порядок, что у дизайнеров в воронке «Дизайн РК»
STAGES = [("new", "Свежие заказы"), ("urgent", "СРОЧНО"), ("info", "Сбор информации"), ("work", "Взято в работу"),
          ("wait", "Жду ответ клиента"), ("fix", "Правки"), ("mop", "Менеджеры"), ("done", "УТВЕРЖДЕНО")]
NAME = dict(STAGES)
ASK = {"mop", "mop_vip", "head"}    # кто может попросить дизайн из карточки сделки

SQL = """SELECT t.*, d.full_name AS designer, c.full_name AS by_name, f.name AS file_name
           FROM design_tasks t LEFT JOIN people d ON d.id=t.designer_id JOIN people c ON c.id=t.created_by
           LEFT JOIN files f ON f.id=t.file_id AND f.status='ready'"""


def _out(r: dict) -> dict:
    return {"id": r["id"], "deal_id": r["deal_id"], "deal_title": r["deal_title"], "city": r["city"] or "", "title": r["title"],
            "note": r["note"] or "", "stage": r["stage"], "stage_name": NAME.get(r["stage"], r["stage"]),
            "designer_id": r["designer_id"], "designer": r["designer"] or "", "size": r["size"] or "",
            "deadline": r["deadline"].isoformat() if r["deadline"] else "", "link": r["link"] or "",
            "file_id": r["file_id"], "file_name": r["file_name"] or "", "by": r["by_name"],
            "created": r["created_at"].isoformat(), "updated": r["updated_at"].isoformat(),
            "approved": r["approved_at"].isoformat() if r["approved_at"] else ""}


def _bitrix(deal_id: int) -> str:
    try:
        return (bxw.portal() + f"/crm/deal/details/{deal_id}/") if bxw.portal() else ""
    except Exception:  # noqa: BLE001
        return ""


def ensure_object(conn, deal_id: int) -> int:
    """Строка сделки в objects — без неё файлу некуда лечь. До стадии работы сделки там нет: заводим со статусом early
    (в списках объектов её не видно; синхронизация сама сделает active, когда сделка дойдёт до работы)."""
    if conn.execute("SELECT 1 FROM objects WHERE id=%s", (deal_id,)).fetchone():
        return deal_id
    from .sync_objects import FOLDER_FIELD, split_title
    j = bx.read("crm.deal.get", {"id": deal_id})
    d = j.get("result", j) if isinstance(j, dict) else None
    if not d or not d.get("ID"):
        raise HTTPException(404, "Сделка не найдена")
    title, city = split_title(str(deal_id), d.get("TITLE") or f"Сделка {deal_id}")
    conn.execute("""INSERT INTO objects (id, title, city, bitrix_stage, bitrix_category, status, drive_folder, synced_at)
                    VALUES (%s,%s,%s,%s,%s,'early',%s,now()) ON CONFLICT (id) DO NOTHING""",
                 (deal_id, title or f"Сделка {deal_id}", city or bx.city_name(d.get(bx.CITY)) or None, d.get("STAGE_ID"),
                  int(d.get("CATEGORY_ID") or 0), d.get(FOLDER_FIELD) or None))
    db.audit(conn, None, "object_early", "objects", deal_id, {"stage": d.get("STAGE_ID")})
    return deal_id


@router.post("/design/deal/{deal_id}/object")
def deal_object(deal_id: int, p: dict = Depends(active)):
    """Перед загрузкой эскиза: у сделки должна быть строка в objects (папка ДИЗАЙН создаётся при самой загрузке)."""
    need(p)
    with db.pool.connection() as conn, conn.transaction():
        return {"id": ensure_object(conn, deal_id)}


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=1000)
    urgent: bool = False


@router.get("/bx/deals/{deal_id}/design-tasks")
def deal_tasks(deal_id: int, p: dict = Depends(active)):
    """Блок «Дизайн» в карточке сделки: МОП — своей сделки, HEAD и дизайнеры — любой."""
    if p["role_code"] in ASK:
        bx._deal(p, deal_id)
    else:
        need(p)
    with db.pool.connection() as conn:
        rows = conn.execute(SQL + " WHERE t.deal_id=%s AND t.status='active' ORDER BY t.id", (deal_id,)).fetchall()
    return {"items": [_out(r) for r in rows], "can_add": p["role_code"] in ASK}


@router.post("/bx/deals/{deal_id}/design-tasks")
def add_task(deal_id: int, b: TaskIn, p: dict = Depends(active)):
    if p["role_code"] not in ASK:
        raise HTTPException(403, "Дизайн просят МОП и HEAD из карточки сделки")
    d = bx._deal(p, deal_id)
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("""INSERT INTO design_tasks (deal_id, deal_title, city, title, note, stage, created_by)
                            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                         (deal_id, d.get("TITLE") or "", bx.city_name(d.get(bx.CITY)) or None, b.title.strip(),
                          (b.note or "").strip() or None, "urgent" if b.urgent else "new", p["id"])).fetchone()
        db.audit(conn, p["id"], "design_task_add", "design_tasks", r["id"], {"deal": deal_id, "title": b.title.strip()})
        row = conn.execute(SQL + " WHERE t.id=%s", (r["id"],)).fetchone()
    return _out(row)


@router.get("/design/tasks")
def board(p: dict = Depends(active)):
    """Доска дизайнера: открытые задачи и утверждённые за 30 дней."""
    need(p)
    see_all = p["role_code"] in ALL
    with db.pool.connection() as conn:
        rows = conn.execute(SQL + """ WHERE t.status='active' AND (t.stage<>'done' OR t.approved_at > now() - interval '30 days')
                                        AND (%s OR t.designer_id=%s OR t.designer_id IS NULL)
                                      ORDER BY t.deadline NULLS LAST, t.id""", (see_all, p["id"])).fetchall()
    return {"items": [{**_out(r), "bitrix": _bitrix(r["deal_id"])} for r in rows],
            "stages": [{"id": k, "name": n} for k, n in STAGES], "all": see_all, "me": p["id"], "sizes": SIZES}


class TaskEdit(BaseModel):
    stage: str | None = None
    designer_id: int | None = None
    size: str | None = None
    deadline: date | None = None
    link: str | None = Field(default=None, max_length=500)
    file_id: int | None = None


@router.post("/design/tasks/{tid}")
def edit(tid: int, b: TaskEdit, p: dict = Depends(active)):
    need(p)
    see_all = p["role_code"] in ALL
    sent = b.model_fields_set
    with db.pool.connection() as conn, conn.transaction():
        t = conn.execute("SELECT * FROM design_tasks WHERE id=%s AND status='active' FOR UPDATE", (tid,)).fetchone()
        if not t:
            raise HTTPException(404, "Нет такой задачи")
        if not see_all and t["designer_id"] not in (None, p["id"]):
            raise HTTPException(403, "Это задача другого дизайнера")
        upd: dict = {}
        if "designer_id" in sent and b.designer_id != t["designer_id"]:
            if not see_all and b.designer_id != p["id"]:
                raise HTTPException(403, "Назначают Главный дизайнер и HEAD; себе задачу можно взять")
            if b.designer_id and not conn.execute(
                    "SELECT 1 FROM people WHERE id=%s AND status='active' AND role_code IN ('lead_designer','designer_asst','head')",
                    (b.designer_id,)).fetchone():
                raise HTTPException(400, "Исполнитель — действующий дизайнер")
            upd["designer_id"] = b.designer_id
        if b.stage and b.stage != t["stage"]:
            if b.stage not in NAME:
                raise HTTPException(400, "Нет такой стадии")
            upd["stage"] = b.stage
            if not t["designer_id"] and "designer_id" not in upd and not see_all:
                upd["designer_id"] = p["id"]        # взял в работу — задача его
        if "size" in sent:
            if b.size and b.size not in SIZES:
                raise HTTPException(400, "Размер: XS, S, M, L или XL")
            upd["size"] = b.size or None
        if "deadline" in sent:
            upd["deadline"] = b.deadline
        if "link" in sent:
            upd["link"] = (b.link or "").strip() or None
        if "file_id" in sent and b.file_id:
            if not conn.execute("SELECT 1 FROM files WHERE id=%s AND object_id=%s AND kind='design' AND status='ready'",
                                (b.file_id, t["deal_id"])).fetchone():
                raise HTTPException(400, "Файл не из папки ДИЗАЙН этой сделки")
            upd["file_id"] = b.file_id
        if upd.get("stage") == "done":
            has = upd.get("file_id") or t["file_id"] or upd.get("link") or ("link" not in upd and t["link"]) or conn.execute(
                "SELECT 1 FROM files WHERE object_id=%s AND kind='design' AND status='ready' LIMIT 1", (t["deal_id"],)).fetchone()
            if not has:
                raise HTTPException(400, "Сначала загрузите эскиз — кнопка «Загрузить эскиз» в этой карточке")
            upd["approved_at"] = "now"
        elif "stage" in upd and t["stage"] == "done":
            upd["approved_at"] = None
        if upd:
            sets = ", ".join(f"{k}=now()" if v == "now" else f"{k}=%s" for k, v in upd.items())
            conn.execute(f"UPDATE design_tasks SET {sets}, updated_at=now() WHERE id=%s",
                         [v for v in upd.values() if v != "now"] + [tid])
            db.audit(conn, p["id"], "design_task_edit", "design_tasks", tid,
                     {k: (v.isoformat() if isinstance(v, date) else v) for k, v in upd.items()})
        row = conn.execute(SQL + " WHERE t.id=%s", (tid,)).fetchone()
    return {**_out(row), "bitrix": _bitrix(row["deal_id"])}


@router.post("/design/tasks/{tid}/cancel")
def cancel(tid: int, p: dict = Depends(active)):
    """Убрать задачу: тот, кто её поставил, Главный дизайнер или HEAD. Строка остаётся в базе со статусом cancelled."""
    with db.pool.connection() as conn, conn.transaction():
        t = conn.execute("SELECT * FROM design_tasks WHERE id=%s AND status='active'", (tid,)).fetchone()
        if not t:
            raise HTTPException(404, "Нет такой задачи")
        if p["role_code"] not in ALL and t["created_by"] != p["id"]:
            raise HTTPException(403, "Убрать задачу может тот, кто её поставил, Главный дизайнер или HEAD")
        if t["stage"] == "done":
            raise HTTPException(400, "Утверждённую задачу не убираем")
        conn.execute("UPDATE design_tasks SET status='cancelled', updated_at=now() WHERE id=%s", (tid,))
        db.audit(conn, p["id"], "design_task_cancel", "design_tasks", tid, {"deal": t["deal_id"]})
    return {"ok": True}
