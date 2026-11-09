"""Живая карточка объекта (HEAD 08.11: «Что предстоит» — данные сами + интерактивно).

- Сложность: поле сделки → расчёт МОП → оценка по сумме сделки и площади против прайса «Значений» (guess_level).
  Сумма сделки в базу приложения не попадает: при синхронизации сохраняется только оценка уровня.
- Эскизы: сервер сам забирает картинки и PDF из папки сделки «ДИЗАЙН» на Диске (вложенные папки тоже),
  «Утверждённые дизайны» — первыми и обложкой (sync_designs; таймер объектов и первый показ карточки).
- Ход работ: сделано м² по сменам, этапы, лента фото «до / после» из смен, карта по адресу сделки.
"""
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from . import drive

LEVELS = ("easy", "medium", "hard", "author")
LEVEL_DEF = {"easy": (17000, 12000, 100), "medium": (22000, 17000, 100), "hard": (27000, 22000, 100), "author": (50000, 27000, 400)}
STAGES = [("prep", "Грунт"), ("transfer", "Перенос эскиза"), ("paint", "Роспись"), ("detail", "Детали"), ("lacquer", "Лак"), ("handover", "Сдача")]
STAGE_KEYS = {k for k, _ in STAGES}
IMG = ("image/", "application/pdf")
DESIGN_ROOT = "дизайн"
APPROVED = "утвержд"
FRESH = timedelta(minutes=30)
MAX_FILES = 60


def guess_level(v: dict, area, amount) -> str | None:
    """Уровень росписи, чья цена по прайсу ближе всего к сумме сделки. Ставки — из «Значений» (запасные — как в price.py)."""
    try:
        m2, total = float(area or 0), float(amount or 0)
    except (TypeError, ValueError):
        return None
    if m2 <= 0 or total <= 0:
        return None
    g = lambda k, d: float(str(v.get(k)).replace(",", ".")) if v.get(k) not in (None, "") else d  # noqa: E731
    s0 = g("mural.start", 30)
    best, diff = None, None
    for lk in LEVELS:
        a, b, e = (g(f"mural.{lk}.{x}", LEVEL_DEF[lk][i]) for i, x in enumerate("abe"))
        rate = a if m2 <= s0 else b if m2 >= e else a - (a - b) * (m2 - s0) / (e - s0)
        d = abs(m2 * rate - total)
        if diff is None or d < diff:
            best, diff = lk, d
    return best


def parse_geo(addr) -> str | None:
    """Адрес сделки «улица|широта;долгота|…» → «широта;долгота»."""
    if not isinstance(addr, str) or "|" not in addr:
        return None
    part = addr.split("|")[1].strip()
    try:
        lat, lon = (float(x) for x in part.split(";"))
    except ValueError:
        return None
    return f"{lat};{lon}"


def map_url(city, address, geo) -> str | None:
    if geo:
        lat, lon = geo.split(";")
        return f"https://2gis.kz/geo/{lon},{lat}"
    q = " ".join(x for x in (city, address) if x)
    return f"https://2gis.kz/search/{quote(q)}" if address else None


def _system_person(conn) -> int | None:
    r = conn.execute("SELECT id FROM people WHERE role_code='head' AND status='active' ORDER BY id LIMIT 1").fetchone()
    return r["id"] if r else None


def sync_designs(conn, obj: dict, d=None) -> int:
    """Картинки из «ДИЗАЙН» сделки → files(kind=design). Уже известные (по drive_id) не дублируются. Возвращает, сколько добавлено."""
    root = obj.get("drive_folder")
    who = _system_person(conn)
    if not root or not who or obj["id"] == 0:
        return 0
    d = d or drive.Drive()
    queue = [(f["id"], f["name"]) for f in d.ls(root) if f.get("mimeType") == drive.FOLDER and f["name"].casefold() == DESIGN_ROOT]
    found, depth = [], 0
    while queue and depth < 4 and len(found) < MAX_FILES:
        nxt = []
        for fid, path in queue:
            for f in d.ls(fid):
                if f.get("mimeType") == drive.FOLDER:
                    nxt.append((f["id"], f"{path}/{f['name']}"))
                elif (f.get("mimeType") or "").startswith(IMG):
                    found.append((f, path))
        queue, depth = nxt, depth + 1
    known = {r["drive_id"] for r in conn.execute("SELECT drive_id FROM files WHERE object_id=%s AND drive_id IS NOT NULL", (obj["id"],))}
    added = 0
    for f, path in found[:MAX_FILES]:
        if f["id"] in known:
            continue
        conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, note, status, uploaded_by)
                        VALUES (%s, %s, 'design', %s, %s, %s, %s, %s, 'ready', %s) ON CONFLICT (client_uid) DO NOTHING""",
                     (uuid.uuid5(uuid.NAMESPACE_URL, "drive:" + f["id"]), obj["id"], f["name"], f.get("mimeType"),
                      int(f["size"]) if f.get("size") else None, f["id"], "Диск: " + path, who))
        added += 1
    conn.execute("UPDATE objects SET design_synced_at=now() WHERE id=%s", (obj["id"],))
    return added


def maybe_sync(conn, obj: dict) -> None:
    """При показе карточки: если эскизы давно не сверялись — сверить (ошибка Диска карточку не ломает)."""
    t = obj.get("design_synced_at")
    if t and datetime.now(timezone.utc) - t < FRESH:
        return
    try:
        sync_designs(conn, obj)
    except Exception as ex:  # noqa: BLE001
        print(f"designs {obj['id']}: {ex}")
        conn.execute("UPDATE objects SET design_synced_at=now() WHERE id=%s", (obj["id"],))


def sketches(conn, object_id: int, limit: int = 12) -> list[dict]:
    """Эскизы: утверждённые первыми. Картинки — с миниатюрой, PDF — ссылкой."""
    from .files import links
    rows = conn.execute(
        """SELECT f.*, pe.full_name AS by FROM files f JOIN people pe ON pe.id=f.uploaded_by
           WHERE f.object_id=%s AND f.kind='design' AND f.status='ready' AND (f.mime LIKE 'image/%%' OR f.mime='application/pdf')
           ORDER BY (coalesce(f.note, '') ILIKE %s) DESC, f.created_at DESC LIMIT %s""",
        (object_id, f"%{APPROVED}%", limit)).fetchall()
    return [{**links(f), "approved": APPROVED in (f["note"] or "").casefold(), "path": (f["note"] or "").removeprefix("Диск: ")} for f in rows]


def progress(conn, object_id: int, area, viewer: dict | None = None) -> dict:
    """Ход работ по сменам: м², этапы, лента «до / после».
    Текст отчёта чужой смены (HEAD 09.11: «почему у Бейбарыса виден отчёт Лизы») видят только автор, ГИП объекта, Про и HEAD;
    остальным — фото и этап, без текста и м²."""
    from .files import sign
    from .gip import can_see
    full = viewer is None or can_see(conn, viewer, object_id)
    r = conn.execute("""SELECT count(*) AS n, coalesce(sum(area_m2), 0) AS m2 FROM shifts
                        WHERE object_id=%s AND status IN ('submitted', 'approved')""", (object_id,)).fetchone()
    done_st = {x["stage"] for x in conn.execute("SELECT DISTINCT stage FROM shifts WHERE object_id=%s AND stage IS NOT NULL "
                                                 "AND status IN ('submitted', 'approved')", (object_id,))}
    feed = []
    for s in conn.execute("""SELECT s.id, s.person_id, s.started_at, s.area_m2, s.work_done, s.stage, s.photo_before, s.photo_after, pe.full_name
                             FROM shifts s JOIN people pe ON pe.id=s.person_id
                             WHERE s.object_id=%s AND s.status IN ('submitted', 'approved') AND (s.photo_before IS NOT NULL OR s.photo_after IS NOT NULL)
                             ORDER BY s.started_at DESC LIMIT 8""", (object_id,)).fetchall():
        own = full or (viewer and s["person_id"] == viewer["id"])
        feed.append({"id": s["id"], "at": s["started_at"].isoformat(), "who": s["full_name"],
                     "m2": float(s["area_m2"]) if s["area_m2"] and own else None,
                     "work_done": s["work_done"] if own else None, "stage": s["stage"],
                     "before": sign(s["photo_before"], "thumb") if s["photo_before"] else None,
                     "after": sign(s["photo_after"], "thumb") if s["photo_after"] else None,
                     "before_full": sign(s["photo_before"], "content") if s["photo_before"] else None,
                     "after_full": sign(s["photo_after"], "content") if s["photo_after"] else None})
    m2 = float(r["m2"])
    area = float(area) if area else None
    last = max((i for i, (k, _) in enumerate(STAGES) if k in done_st), default=-1)
    return {"shifts": r["n"], "done_m2": round(m2, 2), "pct": min(100, round(m2 / area * 100)) if area else None,
            "stages": [{"key": k, "title": t, "done": k in done_st or i < last} for i, (k, t) in enumerate(STAGES)],
            "feed": feed}
