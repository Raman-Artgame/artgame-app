"""«Мой путь» на сервере (HEAD 11.11): отметки чек-листа пути и подтверждение наставником.

- Сотрудник отмечает у себя «есть» — пункт уходит наставнику; подтверждённый пункт сам не снимает.
- Наставник подтверждает или возвращает с комментарием («что доделать»). HEAD видит и подтверждает всех.
- Кто наставник — по ветке роли (MENTORS): Главный и Про ведут саппортов и художников, Про — Главных,
  Мастер печати — операторов, Главный дизайнер — дизайнеров; остальное — HEAD.
- Путь считается от основной роли (у и.о. — от неё же: путь к роли, которую он исполняет).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .work import active

router = APIRouter(prefix="/api/grow")

MENTORS = {"support": {"lead_artist", "artist_pro"}, "artist": {"lead_artist", "artist_pro"}, "lead_artist": {"artist_pro"},
           "print_operator": {"print_master"}, "designer_asst": {"lead_designer"}}
EXAM = ("print_operator", 0)   # пункт «Экзамен оператора сдан Мастеру» = people.print_exam_on (ставка после экзамена, HEAD 13.11)
PATHS = {"support", "artist", "lead_artist", "artist_pro", "print_operator", "print_master", "designer_asst", "lead_designer", "mop", "mop_vip"}


def is_head(p: dict) -> bool:
    return p["role_code"] == "head" or p.get("role_main") == "head"


def mentor_of(p: dict, path: str) -> bool:
    return is_head(p) or p["role_code"] in MENTORS.get(path, set())


def _rows(conn, person_id: int, path: str) -> list[dict]:
    return conn.execute("""SELECT g.idx, g.marked_at, g.confirmed_at, g.returned_at, g.note,
                                  c.full_name AS confirmed_name, r.full_name AS returned_name
                             FROM grow_marks g LEFT JOIN people c ON c.id = g.confirmed_by LEFT JOIN people r ON r.id = g.returned_by
                            WHERE g.person_id = %s AND g.path = %s ORDER BY g.idx""", (person_id, path)).fetchall()


def _path(path: str) -> str:
    if path not in PATHS:
        raise HTTPException(400, "unknown path")
    return path


@router.get("/my")
def my(path: str, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return {"marks": _rows(conn, p["id"], _path(path))}


class Mark(BaseModel):
    path: str
    idx: int = Field(ge=0, lt=100)
    on: bool


@router.post("/my")
def mark(b: Mark, p: dict = Depends(active)):
    _path(b.path)
    with db.pool.connection() as conn:
        cur = conn.execute("SELECT confirmed_at FROM grow_marks WHERE person_id=%s AND path=%s AND idx=%s", (p["id"], b.path, b.idx)).fetchone()
        if cur and cur["confirmed_at"] and not b.on:
            raise HTTPException(400, "Пункт подтверждён наставником — снять может только он")
        conn.execute("""INSERT INTO grow_marks (person_id, path, idx, marked_at) VALUES (%s, %s, %s, CASE WHEN %s THEN now() END)
                        ON CONFLICT (person_id, path, idx) DO UPDATE SET marked_at = CASE WHEN %s THEN coalesce(grow_marks.marked_at, now()) END,
                               updated_at = now()""", (p["id"], b.path, b.idx, b.on, b.on))
        return {"marks": _rows(conn, p["id"], b.path)}


class Import(BaseModel):
    path: str
    idx: list[int] = Field(max_length=100)


@router.post("/my/import")
def import_local(b: Import, p: dict = Depends(active)):
    """Разовый перенос отметок, поставленных до 11.11 в телефоне (localStorage): только если на сервере пусто."""
    _path(b.path)
    with db.pool.connection() as conn:
        if not conn.execute("SELECT 1 FROM grow_marks WHERE person_id=%s AND path=%s", (p["id"], b.path)).fetchone():
            for i in sorted({i for i in b.idx if 0 <= i < 100}):
                conn.execute("INSERT INTO grow_marks (person_id, path, idx, marked_at) VALUES (%s, %s, %s, now()) ON CONFLICT DO NOTHING",
                             (p["id"], b.path, i))
        return {"marks": _rows(conn, p["id"], b.path)}


@router.get("/team")
def team(p: dict = Depends(active)):
    """Наставнику: люди его веток — сколько отмечено, подтверждено и что ждёт его подтверждения."""
    paths = sorted(PATHS) if is_head(p) else sorted(k for k, v in MENTORS.items() if p["role_code"] in v)
    if not paths:
        return {"people": []}
    with db.pool.connection() as conn:
        people = conn.execute("""SELECT pe.id, pe.full_name, pe.role_code AS path, r.title AS role_title, pe.acting_role, pe.print_exam_on
                                   FROM people pe JOIN roles r ON r.code = pe.role_code
                                  WHERE pe.status = 'active' AND pe.role_code = ANY(%s) AND pe.id <> %s ORDER BY pe.full_name""",
                              (paths, p["id"])).fetchall()
        for x in people:
            x["marks"] = _rows(conn, x["id"], x["path"])
        return {"people": people}


class Confirm(BaseModel):
    person_id: int
    path: str
    idx: int = Field(ge=0, lt=100)
    ok: bool
    note: str | None = Field(default=None, max_length=500)
    exam_on: date | None = None   # для пункта экзамена оператора: с какого дня ставка после экзамена


def set_exam(conn, person_id: int, by: int, on: date | None):
    """Экзамен оператора: дата в «Команде» и пункт 1 пути «Оператор → Мастер» — одно и то же (HEAD 13.11)."""
    conn.execute("UPDATE people SET print_exam_on=%s, updated_at=now() WHERE id=%s", (on, person_id))
    if on:
        conn.execute("""INSERT INTO grow_marks (person_id, path, idx, marked_at, confirmed_by, confirmed_at) VALUES (%s, %s, %s, now(), %s, now())
                        ON CONFLICT (person_id, path, idx) DO UPDATE SET marked_at = coalesce(grow_marks.marked_at, now()), confirmed_by = %s,
                               confirmed_at = coalesce(grow_marks.confirmed_at, now()), returned_by = NULL, returned_at = NULL, updated_at = now()""",
                     (person_id, *EXAM, by, by))
    else:
        conn.execute("""UPDATE grow_marks SET marked_at = NULL, confirmed_by = NULL, confirmed_at = NULL, updated_at = now()
                        WHERE person_id=%s AND path=%s AND idx=%s""", (person_id, *EXAM))


@router.post("/confirm")
def confirm(b: Confirm, p: dict = Depends(active)):
    _path(b.path)
    if b.person_id == p["id"]:
        raise HTTPException(403, "Свои пункты подтверждает наставник")
    if not mentor_of(p, b.path):
        raise HTTPException(403, "Не ваша ветка")
    with db.pool.connection() as conn:
        who = conn.execute("SELECT role_code FROM people WHERE id=%s AND status='active'", (b.person_id,)).fetchone()
        if not who or who["role_code"] != b.path:
            raise HTTPException(404, "Нет такого сотрудника на этом пути")
        if b.ok:
            conn.execute("""INSERT INTO grow_marks (person_id, path, idx, marked_at, confirmed_by, confirmed_at)
                            VALUES (%s, %s, %s, now(), %s, now())
                            ON CONFLICT (person_id, path, idx) DO UPDATE SET marked_at = coalesce(grow_marks.marked_at, now()),
                                   confirmed_by = %s, confirmed_at = now(), returned_by = NULL, returned_at = NULL, note = %s, updated_at = now()""",
                         (b.person_id, b.path, b.idx, p["id"], p["id"], b.note))
        else:
            conn.execute("""INSERT INTO grow_marks (person_id, path, idx, returned_by, returned_at, note) VALUES (%s, %s, %s, %s, now(), %s)
                            ON CONFLICT (person_id, path, idx) DO UPDATE SET marked_at = NULL, confirmed_by = NULL, confirmed_at = NULL,
                                   returned_by = %s, returned_at = now(), note = %s, updated_at = now()""",
                         (b.person_id, b.path, b.idx, p["id"], b.note, p["id"], b.note))
        if (b.path, b.idx) == EXAM:
            set_exam(conn, b.person_id, p["id"], (b.exam_on or date.today()) if b.ok else None)
        db.audit(conn, p["id"], "grow_confirm" if b.ok else "grow_return", "person", b.person_id, {"path": b.path, "idx": b.idx, "note": b.note})
        return {"marks": _rows(conn, b.person_id, b.path)}
