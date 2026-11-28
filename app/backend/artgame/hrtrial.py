"""Пробный день кандидата (HEAD 28.11): «на тестовом дне он попадает под руководство Куратора ГИП — чтобы у него это
появилось и он заполнил подробный комментарий с обязательными пунктами, подходит человек или нет, с оценкой звёздами».

HEAD в карточке кандидата ставит «Пробная смена» (дата + сделка) → оценщик — куратор ГИП сделки (objects.gip_person_id),
HEAD может выбрать другого. Оценщику — сообщение в бот и карточка «Пробный день» в приложении (над всеми разделами).
Оценка: 1–5 звёзд, 7 пунктов (да / частично / нет), итог, комментарий от COMMENT_MIN знаков — без них не отправить.
HEAD видит оценку в карточке кандидата; не оценили к вечеру следующего дня — строка в Пульте.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import db, hr_forms
from .config import settings
from .work import active

router = APIRouter(prefix="/api/hr/trials")

ITEMS = [
    ("time", "Пришёл вовремя, предупреждал о задержке"),
    ("neat", "Аккуратность: чистая работа, порядок на объекте"),
    ("speed", "Скорость: успевает норму смены"),
    ("task", "Понимает задачу и слушает указания"),
    ("safety", "Соблюдает ТБ"),
    ("team", "Отношение и работа в команде"),
    ("skill", "Навыки по направлению: рисунок, покраска, печать"),
]
MARKS = {"yes": "Да", "part": "Частично", "no": "Нет"}
VERDICT = {"take": "Брать", "maybe": "Под вопросом", "no": "Не брать"}
COMMENT_MIN = 150   # «полноценный подробный комментарий» — 3–4 предложения
EVALUATORS = ("lead_artist", "artist_pro", "print_master", "lead_designer", "head")   # кого HEAD может поставить вместо ГИП


def evaluator_for(conn, object_id: int | None) -> int | None:
    o = object_id and conn.execute("SELECT gip_person_id FROM objects WHERE id=%s", (object_id,)).fetchone()
    return o["gip_person_id"] if o else None


def notify(conn, cid: int) -> None:
    """Оценщику — в бот: кто, когда, где. Сбой Telegram — не мешает назначению."""
    c = conn.execute("""SELECT c.*, o.title AS obj, pe.tg_id FROM candidates c LEFT JOIN objects o ON o.id=c.trial_object
                        LEFT JOIN people pe ON pe.id=c.trial_by WHERE c.id=%s""", (cid,)).fetchone()
    if not (c and c["tg_id"] and settings.bot_token):
        return
    f = hr_forms.FORMS.get(c["dir"]) or {}
    day = c["trial_on"].strftime("%d.%m") if c["trial_on"] else "дата уточняется"
    text = (f"Пробный день кандидата: {c['full_name']} ({(f.get('title') or ['', ''])[0]}, тел. {c['phone']}), {day}"
            + (f" в {c['trial_time']}" if c["trial_time"] else "") + (f", объект «{c['obj']}»" if c["obj"] else "")
            + (f", место: {c['trial_place']}" if c["trial_place"] else "") + ". Ты руководишь им в этот день. После смены оцени в приложении: "
            "звёзды, 7 пунктов и подробный комментарий — подходит или нет. Карточка — вверху приложения.")
    try:
        from . import notify as nt
        nt.SEND(c["tg_id"], text)
    except Exception as e:  # noqa: BLE001
        print("trial notify:", e)


def _brief(c: dict) -> list[list[str]]:
    """Коротко из анкеты для оценщика: без дохода и ожиданий — только то, что нужно на объекте (телефон — отдельно, для встречи)."""
    a = c["answers"] or {}
    keep = [("city", "Город"), ("years", "Опыт"), ("style", "Стиль"), ("paints", "Краски"), ("tools", "Инструменты"),
            ("height", "Высота"), ("m2", "Объём за смену"), ("big", "Крупный объект")]
    out = []
    for k, t in keep:
        v = c.get(k) if k == "city" else a.get(k)
        if isinstance(v, list):
            v = ", ".join(v)
        if v:
            out.append([t, str(v)])
    return out


def _out(conn, c: dict, full: bool = False) -> dict:
    from .hr import _thumb_url
    f = hr_forms.FORMS.get(c["dir"]) or {}
    o = c["trial_object"] and conn.execute("SELECT title FROM objects WHERE id=%s", (c["trial_object"],)).fetchone()
    r = {"id": c["id"], "full_name": c["full_name"], "dir_title": (f.get("title") or ["", ""])[0], "trial_on": c["trial_on"] and c["trial_on"].isoformat(),
         "object": o["title"] if o else None, "object_id": c["trial_object"], "done": bool(c["trial_reviewed_at"]),
         "time": c["trial_time"], "place": c["trial_place"], "bring": c["trial_bring"],
         "state": c["trial_state"] or "ok",
         "phone": c["phone"]}   # HEAD 28.11 «дыры»: куратору нужно созвониться с кандидатом, чтобы встретить на объекте
    if full:
        ph = conn.execute("SELECT id FROM candidate_files WHERE cand_id=%s AND kind='photo' AND drive_id<>'' ORDER BY id LIMIT 6", (c["id"],)).fetchall()
        r |= {"brief": _brief(c), "photos": [_thumb_url(x["id"]) for x in ph], "items": ITEMS, "marks": MARKS, "verdicts": VERDICT,
              "comment_min": COMMENT_MIN}
    return r


@router.get("")
def mine(p: dict = Depends(active)):
    """Мои пробные дни без оценки — карточка «Пробный день» вверху приложения. День уже наступил или завтра."""
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT * FROM candidates WHERE trial_by=%s AND stage='trial' AND trial_reviewed_at IS NULL
                               AND (trial_state='wait' OR (coalesce(trial_state, 'ok')='ok' AND trial_on <= %s))
                               ORDER BY trial_state='wait' DESC, trial_on""",
                            (p["id"], date.today() + timedelta(days=1))).fetchall()
        return {"items": [_out(conn, c) for c in rows]}


def _mine(conn, cid: int, p: dict) -> dict:
    c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
    if not c or (c["trial_by"] != p["id"] and p["role_code"] != "head"):
        raise HTTPException(404, "Нет такого пробного дня")
    return c


@router.get("/{cid}")
def card(cid: int, p: dict = Depends(active)):
    with db.pool.connection() as conn:
        return _out(conn, _mine(conn, cid, p), full=True)


class ReviewIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    items: dict[str, str]
    verdict: str
    comment: str = Field(max_length=4000)


class ConfirmIn(BaseModel):
    day: date
    time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    place: str = Field(default="", max_length=200)
    bring: str = Field(default="", max_length=300)


@router.post("/{cid}/confirm")
def confirm(cid: int, b: ConfirmIn, p: dict = Depends(active)):
    """Куратор ГИП подтверждает день (тот, что выбрал кандидат, или свой) — бот сразу шлёт кандидату приглашение (HEAD 28.11)."""
    if p.get("_view_as"):
        raise HTTPException(403, "view only")
    if b.day < date.today():
        raise HTTPException(400, "День уже прошёл")
    with db.pool.connection() as conn, conn.transaction():
        c = _mine(conn, cid, p)
        if c["stage"] != "trial" or c["trial_reviewed_at"]:
            raise HTTPException(409, "Пробный день уже не ждёт подтверждения")
        moved = c["trial_on"] != b.day
        conn.execute("""UPDATE candidates SET trial_on=%s, trial_time=%s, trial_place=%s, trial_bring=%s, trial_state='ok',
                        trial_sent_at=NULL, trial_remind_at=NULL, updated_at=now() WHERE id=%s""",
                     (b.day, b.time, b.place.strip() or None, b.bring.strip() or None, cid))
        db.audit(conn, p["id"], "hr_trial_confirm", "candidates", cid, {"day": str(b.day), "moved": moved})
        c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
        from . import hrbot
        hrbot.confirmed(conn, c)
        c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
    _tell_head(p, f"Пробный день {c['full_name']}: {p['full_name']} подтвердил {c['trial_on']:%d.%m} в {b.time}"
                  + ("" if c["trial_sent_at"] else ". У кандидата нет Telegram — отправь приглашение в WhatsApp из карточки") + ".")
    return {"ok": True, "sent": bool(c["trial_sent_at"])}


@router.post("/{cid}/noshow")
def noshow(cid: int, p: dict = Depends(active)):
    """Кандидат не пришёл (HEAD 28.11 «дыры»): без звёзд и пунктов, итог «не брать», HEAD узнаёт сразу."""
    if p.get("_view_as"):
        raise HTTPException(403, "view only")
    with db.pool.connection() as conn, conn.transaction():
        c = _mine(conn, cid, p)
        if c["trial_reviewed_at"]:
            raise HTTPException(409, "Пробный день уже оценён")
        conn.execute("""UPDATE candidates SET trial_verdict='no', trial_review=%s, trial_reviewed_at=now(), trial_reviewed_by=%s,
                        updated_at=now() WHERE id=%s""", (Jsonb({"noshow": True, "comment": "Не пришёл на пробный день"}), p["id"], cid))
        db.audit(conn, p["id"], "hr_trial_noshow", "candidates", cid, {})
    _tell_head(p, f"Пробный день {c['full_name']}: не пришёл (отметил {p['full_name']}). Команда → Кандидаты.")
    return {"ok": True}


def _tell_head(p: dict, text: str) -> None:
    if settings.head_tg_id and settings.bot_token and p.get("role_code") != "head":
        try:
            from . import notify as nt
            nt.SEND(settings.head_tg_id, text)
        except Exception as e:  # noqa: BLE001
            print("trial head notify:", e)


@router.post("/{cid}")
def review(cid: int, b: ReviewIn, p: dict = Depends(active)):
    if p.get("_view_as"):
        raise HTTPException(403, "view only")
    miss = [t for k, t in ITEMS if b.items.get(k) not in MARKS]
    if miss:
        raise HTTPException(400, "Отметь все пункты: " + "; ".join(miss))
    if b.verdict not in VERDICT:
        raise HTTPException(400, "Итог: брать, под вопросом или не брать")
    text = " ".join(b.comment.split())
    if len(text) < COMMENT_MIN:
        raise HTTPException(400, f"Комментарий подробнее: что делал, что получилось, что нет, брать ли и почему (ещё {COMMENT_MIN - len(text)} знаков)")
    with db.pool.connection() as conn, conn.transaction():
        c = _mine(conn, cid, p)
        if c["trial_reviewed_at"]:
            raise HTTPException(409, "Пробный день уже оценён")
        conn.execute("""UPDATE candidates SET trial_stars=%s, trial_verdict=%s, trial_review=%s, trial_reviewed_at=now(),
                        trial_reviewed_by=%s, updated_at=now() WHERE id=%s""",
                     (b.stars, b.verdict, Jsonb({"items": {k: b.items[k] for k, _ in ITEMS}, "comment": text}), p["id"], cid))
        db.audit(conn, p["id"], "hr_trial_review", "candidates", cid, {"stars": b.stars, "verdict": b.verdict})
    _tell_head(p, f"Пробный день {c['full_name']}: {p['full_name']} — {'★' * b.stars}, «{VERDICT[b.verdict]}». Команда → Кандидаты.")
    return {"ok": True}


def hrbot_invite(conn, c: dict) -> dict:
    from .hrbot import invite
    return invite(conn, c)


def for_head(conn, c: dict) -> dict | None:
    """В карточку кандидата у HEAD: кто оценивает, оценка целиком, из кого выбрать оценщика."""
    if not (c["trial_on"] or c["trial_by"] or c["trial_reviewed_at"] or c["trial_state"]):
        return None
    who = lambda pid: pid and (conn.execute("SELECT full_name FROM people WHERE id=%s", (pid,)).fetchone() or {}).get("full_name")  # noqa: E731
    rv = c["trial_review"] or {}
    tg = c["trial_by"] and (conn.execute("SELECT tg_id FROM people WHERE id=%s", (c["trial_by"],)).fetchone() or {}).get("tg_id")
    return {"by": c["trial_by"], "by_name": who(c["trial_by"]), "by_bot": bool(tg), "noshow": bool(rv.get("noshow")), "gip": evaluator_for(conn, c["trial_object"]),
            "stars": c["trial_stars"], "verdict": c["trial_verdict"] and VERDICT[c["trial_verdict"]], "verdict_code": c["trial_verdict"],
            "comment": rv.get("comment"), "items": [[t, MARKS.get((rv.get("items") or {}).get(k), "")] for k, t in ITEMS] if rv else [],
            "at": c["trial_reviewed_at"], "reviewer": who(c["trial_reviewed_by"]),
            "late": bool(not c["trial_reviewed_at"] and c["trial_on"] and c["trial_on"] < date.today()),
            "invite": hrbot_invite(conn, c), "cand_bot": bool(c["tg_id"])}


def for_candidate(conn, c: dict) -> dict:
    """Статус для самого кандидата по его ссылке: без оценок, звёзд и причин отказа."""
    s = c["stage"]
    if s == "trial":
        v = {k: x for k, x in hrbot_invite(conn, c).items() if k != "sent_at"}
        if v["state"] != "ok":   # день ещё не подтверждён — время/место/куратора не показываем, только выбор дня
            v = {"state": v["state"], "day": v["day"], "days": pick_days()}
        return {"step": "trial", **v}
    if s == "interview":
        return {"step": "meet", "day": c["meet_on"] and c["meet_on"].isoformat()}
    if s == "hired":
        return {"step": "hired", "phone": c["phone"]}
    return {"step": "base" if s in ("reserve", "rejected") else "got"}


def pick_days() -> list[str]:
    """Дни на выбор кандидату: с завтра на две недели."""
    t = date.today()
    return [(t + timedelta(days=i)).isoformat() for i in range(1, 15)]


def evaluators(conn) -> list[list]:
    return [[r["id"], r["full_name"]] for r in conn.execute(
        "SELECT id, full_name FROM people WHERE status='active' AND role_code = ANY(%s) ORDER BY full_name", (list(EVALUATORS),))]


def objects(conn) -> list[dict]:
    """Проекты в работе для пробного дня (HEAD 28.11: «список проектов в работе не выкатывается»): номер, название, город, ГИП."""
    return conn.execute("""SELECT o.id, o.title, o.city, pe.full_name AS gip FROM objects o LEFT JOIN people pe ON pe.id=o.gip_person_id
                           WHERE o.status='active' AND o.closed_at IS NULL ORDER BY o.id DESC""").fetchall()


def late_count(conn) -> int:
    """Пульт: пробный день прошёл (вчера и раньше), оценки нет."""
    return conn.execute("""SELECT count(*) AS n FROM candidates WHERE stage='trial' AND trial_on < %s AND trial_reviewed_at IS NULL""",
                        (date.today(),)).fetchone()["n"]
