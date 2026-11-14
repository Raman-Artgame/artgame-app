"""Перенос смены на другой объект (HEAD 14.11: в 1611 УйДомДонер оказались смены и фото других объектов —
в «Прошлой смене» объект стоял первым по умолчанию). Только HEAD. Смена, её фото «до/после» и все фото смены
переходят на выбранный объект: в базе и на Диске (файл переезжает в «МЕДИА / Отчёты» нужной сделки). Ничего не удаляется.
"""
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from . import db, drive
from .deps import require_head
from .work import is_trip

router = APIRouter(prefix="/api")


class MoveIn(BaseModel):
    object_id: int


@router.get("/head/move-targets")
def targets(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        return conn.execute("SELECT id, title, city FROM objects WHERE id<>0 ORDER BY id DESC LIMIT 300").fetchall()


def _move_files(obj: dict, ids: list[str]) -> None:
    try:
        d = drive.Drive()
        with db.pool.connection() as conn:
            parent = drive.folder_of(conn, obj, "photo", d)
        for fid in ids:
            d.move(fid, parent)
    except Exception as e:  # noqa: BLE001 — в базе уже перенесено; на Диске можно повторить кнопкой ещё раз
        print("shift move drive:", e, file=sys.stderr)


@router.post("/shifts/{sid}/move")
def move(sid: int, b: MoveIn, bg: BackgroundTasks, p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        s = conn.execute("SELECT * FROM shifts WHERE id=%s FOR UPDATE", (sid,)).fetchone()
        if not s or s["status"] == "cancelled":
            raise HTTPException(404, "Смена не найдена")
        if b.object_id == 0 or s["object_id"] == 0:
            raise HTTPException(400, "Смену мастерской не переносим")
        o = conn.execute("SELECT * FROM objects WHERE id=%s", (b.object_id,)).fetchone()
        if not o:
            raise HTTPException(404, "Нет такого объекта")
        if s["object_id"] == b.object_id:
            raise HTTPException(400, "Смена уже на этом объекте")
        if o["closed_at"]:
            raise HTTPException(409, "Этот проект уже закрыт — смены на него не вносятся")
        files = conn.execute("""SELECT id, drive_id FROM files WHERE id = ANY(
                                  SELECT unnest(ARRAY[%s::bigint, %s::bigint]) UNION SELECT file_id FROM shift_photos WHERE shift_id=%s)""",
                             (s["photo_before"], s["photo_after"], sid)).fetchall()
        conn.execute("UPDATE shifts SET object_id=%s, trip=%s WHERE id=%s", (b.object_id, is_trip(conn, s["person_id"], b.object_id), sid))
        if files:
            conn.execute("UPDATE files SET object_id=%s WHERE id = ANY(%s)", (b.object_id, [f["id"] for f in files]))
        db.audit(conn, p["id"], "shift_move", "shifts", sid, {"from": s["object_id"], "to": b.object_id, "files": [f["id"] for f in files]})
    ids = [f["drive_id"] for f in files if f["drive_id"]]
    if ids:
        bg.add_task(_move_files, o, ids)
    return {"ok": True, "files": len(files), "object_id": b.object_id, "object_title": o["title"]}
