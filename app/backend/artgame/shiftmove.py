"""Перенос смены на другой объект (HEAD 14.11: в 1611 УйДомДонер оказались смены и фото других объектов —
в «Прошлой смене» объект стоял первым по умолчанию). Только HEAD. Смена, её фото «до/после» и все фото смены
переходят на выбранный объект: в базе и на Диске (файл переезжает в «МЕДИА / Отчёты» нужной сделки). Ничего не удаляется.
"""
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from . import db, drive, sync_objects
from .deps import require_head
from .work import is_trip

router = APIRouter(prefix="/api")


SHOP0 = "Без объекта / Мастерская"


class MoveIn(BaseModel):
    object_id: int


@router.get("/head/move-targets")
def targets(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        # HEAD 15.11: «оставь только актуальные проекты, которые в выполнении и оплатах» — стадии sync_objects.ACTIVE
        rows = conn.execute("""SELECT id, title, city FROM objects WHERE id<>0 AND closed_at IS NULL AND bitrix_stage = ANY(%s)
                               ORDER BY (bitrix_stage = %s) DESC, id DESC""", (list(sync_objects.ACTIVE), sync_objects.WORK)).fetchall()
    # HEAD 15.11 (Асель): работала не на объекте — смену переносят в «Без объекта / Мастерская» (object_id 0)
    return [{"id": 0, "title": SHOP0, "city": None}, *rows]


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
        if s["kind"] == "road":
            raise HTTPException(400, "Дорогу командировки не переносим")
        o = conn.execute("SELECT * FROM objects WHERE id=%s", (b.object_id,)).fetchone()
        if not o:
            raise HTTPException(404, "Нет такого объекта")
        if s["object_id"] == b.object_id:
            raise HTTPException(400, "Смена уже на этом объекте")
        if o["closed_at"] and b.object_id != 0:
            raise HTTPException(409, "Этот проект уже закрыт — смены на него не вносятся")
        files = conn.execute("""SELECT id, drive_id FROM files WHERE id = ANY(
                                  SELECT unnest(ARRAY[%s::bigint, %s::bigint]) UNION SELECT file_id FROM shift_photos WHERE shift_id=%s)""",
                             (s["photo_before"], s["photo_after"], sid)).fetchall()
        conn.execute("UPDATE shifts SET object_id=%s, trip=%s WHERE id=%s", (b.object_id, b.object_id != 0 and is_trip(conn, s["person_id"], b.object_id), sid))
        if files:
            conn.execute("UPDATE files SET object_id=%s WHERE id = ANY(%s)", (b.object_id, [f["id"] for f in files]))
        db.audit(conn, p["id"], "shift_move", "shifts", sid, {"from": s["object_id"], "to": b.object_id, "files": [f["id"] for f in files]})
    ids = [f["drive_id"] for f in files if f["drive_id"]]
    if ids and b.object_id != 0:   # без объекта папки сделки нет — на Диске фото остаются, где были
        bg.add_task(_move_files, o, ids)
    return {"ok": True, "files": len(files), "object_id": b.object_id, "object_title": SHOP0 if b.object_id == 0 else o["title"]}


# ---------- фото с объекта не на том объекте (HEAD 14.11: в 1611 фото добавляли через «Добавить фото с объекта», без смены) ----------

class FileMoveIn(BaseModel):
    object_id: int
    same_day: bool = False   # и все фото этого человека на этом объекте за тот же день


@router.post("/files/{fid}/move")
def move_file(fid: int, b: FileMoveIn, bg: BackgroundTasks, p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT * FROM files WHERE id=%s AND kind IN ('photo','media') AND status='ready'", (fid,)).fetchone()
        if not f:
            raise HTTPException(404, "Фото не найдено")
        if b.object_id == 0 or b.object_id == f["object_id"]:
            raise HTTPException(400, "Выберите другой объект")
        o = conn.execute("SELECT * FROM objects WHERE id=%s", (b.object_id,)).fetchone()
        if not o:
            raise HTTPException(404, "Нет такого объекта")
        if o["closed_at"] and b.object_id != 0:
            raise HTTPException(409, "Этот проект уже закрыт")
        rows = [f]
        if b.same_day:
            rows = conn.execute("""SELECT * FROM files WHERE object_id=%s AND uploaded_by=%s AND kind IN ('photo','media') AND status='ready'
                                   AND (created_at AT TIME ZONE 'Asia/Almaty')::date = (%s AT TIME ZONE 'Asia/Almaty')::date""",
                                (f["object_id"], f["uploaded_by"], f["created_at"])).fetchall()
        ids = [r["id"] for r in rows]
        linked = conn.execute("""SELECT DISTINCT s.id FROM shifts s LEFT JOIN shift_photos sp ON sp.shift_id=s.id
                                 WHERE s.status<>'cancelled' AND (s.photo_before = ANY(%s) OR s.photo_after = ANY(%s) OR sp.file_id = ANY(%s))""",
                              (ids, ids, ids)).fetchall()
        if linked:
            raise HTTPException(409, "Это фото смены — перенесите смену целиком: «Вся история проекта» → «Перенести на другой объект»")
        conn.execute("UPDATE files SET object_id=%s WHERE id = ANY(%s)", (b.object_id, ids))
        db.audit(conn, p["id"], "file_move", "files", fid, {"from": f["object_id"], "to": b.object_id, "files": ids})
    drv = [r["drive_id"] for r in rows if r["drive_id"]]
    if drv:
        bg.add_task(_move_files, o, drv)
    return {"ok": True, "files": len(ids), "object_id": b.object_id, "object_title": o["title"]}
