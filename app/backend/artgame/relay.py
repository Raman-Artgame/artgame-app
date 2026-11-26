"""Эстафета сделки (HEAD 26.11.2026 «отлично, давай так сделаем»): МОП → дизайн → производство → сдача → закрытие.

На каждом участке один хозяин и одна кнопка:
1. МОП «+ Нужен дизайн» (designtasks.py).
2. Дизайнер «Утверждено» — файл эскиза получает метку «В работу» (files.approved_at). Утверждённым считается только
   отмеченный файл (и старые «Утверждённые дизайны» с Диска), а не ссылка на папку в поле «Эскиз».
3. МОП «В производство» — одна кнопка вместо «Перевести в работу» + «Передать куратору ГИП»: стадия «Выполнение проекта»,
   старт и сдача в сделку, куратор ГИП в приложении (права ГИП), сообщение ГИП с утверждённым эскизом.
4. Куратор ГИП ставит людей (gip.py) и жмёт «Работы сданы» (closing.py).
5. МОП «На закрытие», HEAD «Закрыть» (closing.py).
Полоска пути — /path: пять отрезков по данным приложения, без Битрикса.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import bx, bxw, db
from .work import active

router = APIRouter(prefix="/api")

WORK = "UC_AV00QK"                                  # «Выполнение проекта»
AFTER = {WORK, "UC_BMKDS4", "WON"}                  # уже в производстве или дальше
BEFORE = {"NEW", "PREPARATION", "UC_VZFPUP", "UC_YV66BV", "UC_1EXUAC", "FINAL_INVOICE"}   # продажи до работы
APPROVED_STAGE = "UC_YV66BV"                        # «Утвержденный дизайн» (возврат из воронки «Дизайн РК»)
ASK = {"mop", "mop_vip", "head"}
LEGACY = "утвержд"                                  # «ДИЗАЙН / Утвержденные дизайны» на Диске (promo.sync_designs)
DESIGN_EDIT = {"lead_designer", "designer_asst", "head"}


# ---------- метка «В работу» ----------

def approved_file(conn, deal_id: int) -> dict | None:
    """Утверждённый эскиз сделки: последний отмеченный «В работу», иначе файл из «Утвержденных дизайнов» Диска."""
    return conn.execute(
        """SELECT id, name, mime, approved_at, created_at FROM files
           WHERE object_id=%s AND kind='design' AND status='ready' AND (approved_at IS NOT NULL OR coalesce(note, '') ILIKE %s)
           ORDER BY approved_at DESC NULLS LAST, created_at DESC LIMIT 1""", (deal_id, f"%{LEGACY}%")).fetchone()


def mark(conn, deal_id: int, file_id: int | None, by: int) -> int | None:
    """«Утверждено»: выбранный файл (или последний эскиз сделки) получает метку «В работу». Возвращает id файла."""
    if file_id:
        f = conn.execute("SELECT id FROM files WHERE id=%s AND object_id=%s AND kind='design' AND status='ready'",
                         (file_id, deal_id)).fetchone()
    else:
        f = conn.execute("""SELECT id FROM files WHERE object_id=%s AND kind='design' AND status='ready'
                            ORDER BY created_at DESC LIMIT 1""", (deal_id,)).fetchone()
    if not f:
        return None
    conn.execute("UPDATE files SET approved_at=now(), approved_by=%s WHERE id=%s", (by, f["id"]))
    db.audit(conn, by, "design_file_approved", "files", f["id"], {"deal": deal_id})
    return f["id"]


class MarkIn(BaseModel):
    on: bool = True


@router.post("/design/files/{fid}/approve")
def approve_file(fid: int, b: MarkIn, p: dict = Depends(active)):
    """Поставить или снять метку «В работу» на эскизе вручную (если утвердили не тот вариант). Дизайнеры и HEAD."""
    if p["role_code"] not in DESIGN_EDIT:
        raise HTTPException(403, "Эскиз в работу отмечают дизайнеры и HEAD")
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT id, object_id FROM files WHERE id=%s AND kind='design' AND status='ready'", (fid,)).fetchone()
        if not f:
            raise HTTPException(404, "Нет такого эскиза")
        if b.on:
            mark(conn, f["object_id"], fid, p["id"])
        else:
            conn.execute("UPDATE files SET approved_at=NULL, approved_by=NULL WHERE id=%s", (fid,))
            db.audit(conn, p["id"], "design_file_unapproved", "files", fid, {"deal": f["object_id"]})
    return {"ok": True, "approved": b.on}


# ---------- полоска пути ----------

def path(conn, deal_id: int, stage: str | None = None) -> dict:
    """Пять отрезков: дизайн · утверждён · производство · сдано · закрыто. state: done | now | todo | skip."""
    o = conn.execute("""SELECT o.bitrix_stage, o.gip_person_id, o.done_on, o.closed_at, g.full_name AS gip
                        FROM objects o LEFT JOIN people g ON g.id=o.gip_person_id WHERE o.id=%s AND o.id<>0""", (deal_id,)).fetchone() or {}
    stage = stage or o.get("bitrix_stage") or ""
    code = stage.split(":")[-1]
    t = conn.execute("""SELECT count(*) FILTER (WHERE stage<>'done') AS open, count(*) FILTER (WHERE stage='done') AS done
                        FROM design_tasks WHERE deal_id=%s AND status='active'""", (deal_id,)).fetchone()
    nfiles = conn.execute("SELECT count(*) AS n FROM files WHERE object_id=%s AND kind='design' AND status='ready'",
                          (deal_id,)).fetchone()["n"]
    ok = approved_file(conn, deal_id)
    had_design = bool(t["open"] or t["done"] or nfiles or code == APPROVED_STAGE)
    approved = bool(ok or t["done"] or code == APPROVED_STAGE)
    in_work = code in AFTER
    closed = bool(o.get("closed_at")) or code == "WON"
    done_on = o.get("done_on")

    def st(is_done: bool, is_now: bool, skip: bool = False) -> str:
        return "skip" if skip else "done" if is_done else "now" if is_now else "todo"

    no_design = not had_design and in_work
    steps = [
        {"key": "design", "title": "Дизайн", "state": st(had_design and (approved or not t["open"]) and bool(nfiles or approved),
                                                          bool(t["open"]) or (not had_design and not in_work), no_design),
         "detail": f"задач в работе: {t['open']}" if t["open"] else "эскизы есть" if nfiles else "дизайна не было" if no_design else "МОП: «+ Нужен дизайн», если нужен"},
        {"key": "approved", "title": "Утверждён", "state": st(approved and not t["open"], had_design and not approved, no_design),
         "detail": (ok["name"] if ok else "утверждено") if approved else "дизайна не было" if no_design else "дизайнер жмёт «Утверждено»"},
        {"key": "work", "title": "В работе", "state": st(in_work and bool(o.get("gip_person_id")), approved or in_work or code == "FINAL_INVOICE"),
         "detail": ("ГИП " + o["gip"]) if o.get("gip") else "ГИП не назначен: МОП «ГИП и сроки»" if in_work else "МОП жмёт «В производство»"},
        {"key": "handed", "title": "Сдано", "state": st(bool(done_on) or closed, in_work and not done_on),
         "detail": done_on.strftime("%d.%m") if done_on else "ГИП жмёт «Работы сданы»" if in_work else ""},
        {"key": "closed", "title": "Закрыто", "state": st(closed, code == "UC_BMKDS4" or bool(done_on)),
         "detail": "закрыто HEAD" if closed else "МОП «На закрытие», HEAD «Закрыть»"},
    ]
    # «сейчас» — только один отрезок: первый не закрытый
    seen = False
    for s in steps:
        if s["state"] in ("now", "todo") and not seen:
            s["state"], seen = "now", True
        elif s["state"] == "now":
            s["state"] = "todo"
    return {"steps": steps, "approved": {"id": ok["id"], "name": ok["name"]} if ok else None}


@router.get("/deals/{deal_id}/path")
def get_path(deal_id: int, stage: str | None = None, p: dict = Depends(active)):
    """Полоска пути: МОП и HEAD — в карточке сделки (stage передаёт экран), команда — в карточке проекта."""
    with db.pool.connection() as conn:
        return path(conn, deal_id, stage)


# ---------- «В производство» ----------

@router.get("/bx/deals/{deal_id}/production")
def production_form(deal_id: int, p: dict = Depends(active)):
    """Что подставить в окно «В производство»: ГИП, старт, сдача, утверждённый эскиз, чего не хватает."""
    if p["role_code"] not in ASK:
        raise HTTPException(403, "В производство передают МОП и HEAD")
    d = bx._deal(p, deal_id, fresh=True)
    from . import fill
    from .gip import candidates
    cur = d.get("STAGE_ID") or ""
    miss = [] if cur in AFTER else fill.gate(p, deal_id, cur, WORK, done=("start", "end"))
    with db.pool.connection() as conn:
        o = conn.execute("SELECT gip_person_id FROM objects WHERE id=%s", (deal_id,)).fetchone() or {}
        ok = approved_file(conn, deal_id)
        open_tasks = conn.execute("SELECT count(*) AS n FROM design_tasks WHERE deal_id=%s AND status='active' AND stage<>'done'",
                                  (deal_id,)).fetchone()["n"]
    from .files import sign
    return {"stage": cur, "in_work": cur in AFTER, "missing": miss, "gip_id": o.get("gip_person_id"),
            "candidates": candidates(p),
            "start": str(d.get(bxw.F_START) or "")[:10], "end": str(d.get(bxw.F_END) or "")[:10],
            "sketch": {"id": ok["id"], "name": ok["name"], "thumb": sign(ok["id"], "thumb") if (ok["mime"] or "").startswith("image/") else None} if ok else None,
            "design_open": open_tasks}


class ProdIn(BaseModel):
    gip_id: int
    start: date
    end: date


@router.post("/bx/deals/{deal_id}/production")
def to_production(deal_id: int, b: ProdIn, p: dict = Depends(active)):
    """Одна кнопка: стадия «Выполнение проекта» + старт и сдача в сделку + куратор ГИП + сообщение ГИП."""
    if p["role_code"] not in ASK or p.get("_view_as"):
        raise HTTPException(403, "В производство передают МОП и HEAD")
    if b.end < b.start:
        raise HTTPException(400, "Сдача раньше старта")
    d = bx._deal(p, deal_id, fresh=True)
    cur = d.get("STAGE_ID") or ""
    if cur not in BEFORE | AFTER:
        raise HTTPException(409, "Сделка не в продажах: в производство передают из «Продаж»")
    from . import fill
    from .gip import GIP_ROLES, assign
    miss = [] if cur in AFTER else fill.gate(p, deal_id, cur, WORK, done=("start", "end"))
    if miss:
        raise HTTPException(409, "сначала заполните: " + ", ".join(miss))
    with db.pool.connection() as conn:
        gip = conn.execute("""SELECT full_name FROM people WHERE id=%s AND status='active'
                              AND (role_code = ANY(%s) OR acting_role = ANY(%s))""", (b.gip_id, list(GIP_ROLES), list(GIP_ROLES))).fetchone()
        ok = approved_file(conn, deal_id)
    if not gip:
        raise HTTPException(400, "Куратор ГИП — Главный художник, Художник-Про или Мастер печати")
    fields = {bxw.F_START: b.start.isoformat(), bxw.F_END: b.end.isoformat()}
    if cur not in AFTER:
        fields["STAGE_ID"] = WORK
    note = (f"передал в производство: куратор ГИП {gip['full_name']}, старт {b.start:%d.%m.%Y}, сдача {b.end:%d.%m.%Y}"
            + (f", эскиз «{ok['name']}»" if ok else ", утверждённого эскиза нет"))
    r = bxw.write(p, deal_id, "в производство", fields, note)
    if r["bx"] == "error":
        raise HTTPException(502, r.get("error") or "Битрикс не записал")
    from .designtasks import ensure_object
    with db.pool.connection() as conn, conn.transaction():
        ensure_object(conn, deal_id)
        conn.execute("""UPDATE objects SET status=CASE WHEN status='early' THEN 'active' ELSE status END,
                        bitrix_stage=CASE WHEN %s THEN %s ELSE bitrix_stage END WHERE id=%s""", ("STAGE_ID" in fields, WORK, deal_id))
        out = assign(conn, p, deal_id, b.gip_id,
                     extra=f" Старт {b.start:%d.%m}, сдача {b.end:%d.%m}. "
                           + ("Утверждённый эскиз — первым в карточке проекта." if ok else "Утверждённого эскиза пока нет — спроси МОП."))
        db.audit(conn, p["id"], "to_production", "objects", deal_id, {"gip": b.gip_id, "start": b.start.isoformat(), "end": b.end.isoformat()})
    out()
    return {"ok": True, "bx": r["bx"], "stage_moved": "STAGE_ID" in fields}
