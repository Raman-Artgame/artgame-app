"""HR: кандидаты (HEAD 26.11 «отдел HR в приложении… для тех, с кем ещё не коммуницировали»).

Путь: ссылка-вакансия `/?job=art` (метка `&src=instagram`) → анкета шагами без входа (hr_forms) → фото работ и резюме
на Диск («02 КОМАНДА КЗ / Kandidaty / ГГГГ-ММ familiya-imya-телефон») → «Команда → Кандидаты» у HEAD:
Новый → Связались → Собеседование → Пробная смена → Принят / Резерв / Отказ, звёзды и заметка.
«Принять» ставит роль: человек входит в приложение (бот → «ARTGAME» → имя и тот же телефон) и сразу получает её.
Таблицы: строка в «Базе кандидатов» при отправке анкеты и на каждом шаге, в «Сотрудниках» — при «Принять» (hr_sheets).
"""
import re
import secrets
import sys
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import db, drive, files, hr_forms, hr_sheets
from .deps import require_head

router = APIRouter(prefix="/api/hr")

TEAM_ROOT_ID = "14rhrxFjMtb9_hHBpk_BMSuWp1b1LC6a4"   # «02 КОМАНДА КЗ» (там же обе таблицы); сервисному аккаунту дан доступ
KANDIDATY = "Kandidaty"
STAGES = ("new", "talk", "interview", "trial", "hired", "reserve", "rejected")
OPEN = ("new", "talk", "interview", "trial")
WAIT_DAYS = 2           # «ответим за 2 дня»: дольше без движения — подсветка на доске и в Пульте
MAX_PHOTOS = 10
MAX_FILE = 11_000_000   # data URL: фото сжимается на телефоне, PDF резюме — до ~8 МБ
UPLOAD_HOURS = 24       # дослать фото и резюме по своей ссылке можно сутки
HOUR_LIMIT = 60         # анкет в час на всё приложение — защита открытой страницы
RESUME_MIME = {"application/pdf": "pdf", "application/msword": "doc", "image/jpeg": "jpg", "image/png": "png",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}
LAT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяәғқңөұүһі",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts",
                "ch", "sh", "shch", "", "y", "", "e", "yu", "ya", "a", "g", "k", "n", "o", "u", "u", "h", "i"]))


def latin(s: str) -> str:
    """Имена файлов и папок на Диске — латиницей (HEAD)."""
    out = "".join(LAT.get(ch, ch) for ch in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", out).strip("-")[:60] or "kandidat"


def _form(d: str) -> dict:
    f = hr_forms.FORMS.get(d)
    if not f:
        raise HTTPException(404, "Нет такой вакансии")
    return f


def _role_titles(conn) -> dict:
    return {r["code"]: r["title"] for r in conn.execute("SELECT code, title FROM roles").fetchall()}


# ---------- анкета: без входа ----------

@router.get("/form/{d}")
def form(d: str):
    """Без ставок (HEAD 26.11: «не выкатывать все наши условия»): только как устроен рост — шаг «Как у нас устроено»."""
    f = _form(d)
    with db.pool.connection() as conn:
        return {"dir": d, "title": f["title"], "lead": f["lead"], "steps": with_start(conn, f)}


def with_start(conn, f: dict) -> list:
    """Стартовая ставка — одна цифра, из «Значений» (HEAD 26.11: «все начинают с Саппорта, от 10 000 за смену»).
    Ключа нет или не утверждён — фраза без цифры, остальные условия не раскрываем."""
    import json
    from . import constants as consts
    v = consts.latest(conn).get(f.get("start_key") or "")
    money = f"{int(v):,} ₸".replace(",", " ") if isinstance(v, (int, float)) and v > 0 else None
    raw = json.dumps(f["steps"], ensure_ascii=False)
    raw = raw.replace("{start}", money) if money else re.sub(r":? (10 сағ ауысымға |ауысымға )?\{start\}( за смену( 10 ч)?)?", "", raw)
    return json.loads(raw)


class ApplyIn(BaseModel):
    dir: str
    answers: dict
    lang: str = "ru"
    src: str | None = Field(default=None, max_length=40)


def clean(form: dict, a: dict) -> dict:
    """Только вопросы анкеты; списки — из вариантов (+ «свой вариант» строкой), текст обрезается."""
    out: dict = {}
    for k, it in hr_forms.keys(form).items():
        v = a.get(k)
        if it["t"] in ("text",):
            if isinstance(v, str) and v.strip():
                out[k] = re.sub(r"[ \t]+", " ", v.strip())[: 1200 if it.get("long") else 200]
        elif it["t"] == "one":
            ok = {x[0] for x in it["opts"]}
            if isinstance(v, str) and v in ok:
                out[k] = v
        elif it["t"] == "chips":
            ok = {x[0] for x in it["opts"]}
            v = [x for x in (v if isinstance(v, list) else []) if isinstance(x, str) and x in ok]
            if it.get("max"):
                v = v[: it["max"]]
            if v:
                out[k] = v
            o = a.get(k + "_other")
            if it.get("other") and isinstance(o, str) and o.strip():
                out[k + "_other"] = o.strip()[:120]
        elif it["t"] == "resume":
            if isinstance(a.get("resume_text"), str) and a["resume_text"].strip():
                out["resume_text"] = a["resume_text"].strip()[:4000]
    return out


@router.post("/apply")
def apply(b: ApplyIn):
    f = _form(b.dir)
    a = clean(f, b.answers)
    name, ph, city = a.get("full_name", ""), hr_sheets.phone(a.get("phone")), a.get("city", "")
    if len(name) < 3 or not re.search(r"[A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]{2}", name):
        raise HTTPException(422, "Напиши фамилию и имя")
    if not re.fullmatch(r"8\d{10}", ph):
        raise HTTPException(422, "Телефон — 11 цифр, например 8 777 123 45 67")
    if len(city) < 2:
        raise HTTPException(422, "Напиши город")
    a["phone"] = ph
    src = (b.src or a.get("source") or "").strip()[:40] or None
    with db.pool.connection() as conn, conn.transaction():
        if conn.execute("SELECT count(*) AS n FROM candidates WHERE created_at > now() - interval '1 hour'").fetchone()["n"] >= HOUR_LIMIT:
            raise HTTPException(429, "Слишком много анкет за час. Попробуй чуть позже.")
        # тот же человек заполнил ещё раз, пока его ведут, — обновляем анкету, вторую карточку не заводим
        old = conn.execute("SELECT * FROM candidates WHERE phone=%s AND dir=%s AND stage = ANY(%s) ORDER BY id DESC LIMIT 1 FOR UPDATE",
                           (ph, b.dir, list(OPEN))).fetchone()
        if old:
            conn.execute("""UPDATE candidates SET full_name=%s, city=%s, level=%s, answers=%s, lang=%s, source=coalesce(source, %s),
                            updated_at=now() WHERE id=%s""", (name, city, _hint_code(conn, b.dir, a, old["id"]), Jsonb(a), _lang(b.lang), src, old["id"]))
            db.audit(conn, None, "hr_apply_again", "candidates", old["id"], {"dir": b.dir})
            return {"token": old["token"], "again": True}
        token = secrets.token_urlsafe(18)
        cid = conn.execute("""INSERT INTO candidates (token, dir, full_name, phone, city, level, answers, lang, source)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (token, b.dir, name, ph, city, _hint_code(conn, b.dir, a, None), Jsonb(a), _lang(b.lang), src)).fetchone()["id"]
        db.audit(conn, None, "hr_apply", "candidates", cid, {"dir": b.dir, "src": src})
    return {"token": token, "again": False}


def _photos(conn, cid: int | None) -> int:
    return cid and conn.execute("SELECT count(*) AS n FROM candidate_files WHERE cand_id=%s AND kind='photo' AND drive_id<>''", (cid,)).fetchone()["n"] or 0


def _hint_code(conn, d: str, a: dict, cid: int | None) -> str | None:
    """Уровень кандидата — по ответам (hr_forms.level_hint), кандидат его не выбирает (HEAD 26.11)."""
    h = hr_forms.level_hint(d, a, _photos(conn, cid))
    return h and h["code"]


def _lang(x: str) -> str:
    return "kk" if x == "kk" else "ru"


def _by_token(conn, token: str, lock: bool = False) -> dict:
    if not (16 <= len(token) <= 64):
        raise HTTPException(404, "Анкета не найдена")
    c = conn.execute("SELECT * FROM candidates WHERE token=%s" + (" FOR UPDATE" if lock else ""), (token,)).fetchone()
    if not c:
        raise HTTPException(404, "Анкета не найдена")
    return c


def folder(conn, c: dict, d: "drive.Drive") -> str:
    """Папка кандидата на Диске: «02 КОМАНДА КЗ / Kandidaty / 2026-11 familiya-imya-87771234567»."""
    if c["drive_folder"]:
        return c["drive_folder"]
    month = c["created_at"].strftime("%Y-%m")
    fid = d.child(d.child(TEAM_ROOT_ID, KANDIDATY), f"{month} {latin(c['full_name'])}-{c['phone']}")
    conn.execute("UPDATE candidates SET drive_folder=%s WHERE id=%s", (fid, c["id"]))
    return fid


class FileIn(BaseModel):
    kind: str
    data: str = Field(max_length=MAX_FILE)


@router.post("/c/{token}/file")
def upload(token: str, b: FileIn):
    """Фото работ (до 10, сжаты на телефоне) или резюме файлом — в папку кандидата на Диске."""
    if b.kind not in ("photo", "resume"):
        raise HTTPException(400, "Не тот файл")
    m = re.match(r"data:([\w./+-]+);base64,", b.data)
    mime = m and m.group(1)
    if b.kind == "photo" and mime not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Нужно фото (JPEG или PNG)")
    if b.kind == "resume" and mime not in RESUME_MIME:
        raise HTTPException(400, "Резюме — PDF, Word или фото")
    data, mime = drive.decode_data_url(b.data)
    d = drive.Drive()
    # HEAD 27.11 «очень долго»: раньше Диск грузился внутри транзакции под блокировкой анкеты — фото шли строго по одному
    # и держали соединение с базой. Теперь коротко: проверка, папка, номер, строка-заготовка; загрузка — без базы, параллельно.
    with db.pool.connection() as conn, conn.transaction():
        c = _by_token(conn, token, lock=True)
        if datetime.now(timezone.utc) - c["created_at"] > timedelta(hours=UPLOAD_HOURS):
            raise HTTPException(409, "Ссылка устарела. Пришли файлы менеджеру, который с тобой свяжется.")
        rows = conn.execute("SELECT name FROM candidate_files WHERE cand_id=%s AND kind=%s", (c["id"], b.kind)).fetchall()
        n = len(rows)
        if b.kind == "photo" and n >= MAX_PHOTOS:
            raise HTTPException(400, f"Достаточно {MAX_PHOTOS} фото")
        if b.kind == "resume" and n >= 3:
            raise HTTPException(400, "Резюме уже загружено")
        try:
            parent = folder(conn, c, d)   # Диск — только при первом файле, потом id из базы
        except Exception as ex:   # noqa: BLE001
            raise drive.fail(ex)
        k = max([int(m.group(1)) for r in rows if (m := re.search(r"-(\d+)\.\w+$", r["name"]))] + [n]) + 1   # после удаления номера не повторяются
        name = (f"foto-{k:02d}." + ("png" if mime == "image/png" else "jpg")) if b.kind == "photo" \
            else f"rezyume-{latin(c['full_name'])}" + (f"-{k}" if n else "") + "." + RESUME_MIME.get(mime, "bin")
        fid = conn.execute("INSERT INTO candidate_files (cand_id, kind, name, mime, size, drive_id) VALUES (%s,%s,%s,%s,%s,'') RETURNING id",
                           (c["id"], b.kind, name, mime, len(data))).fetchone()["id"]
    try:
        drive_id = d.upload(parent, name, data, mime)
    except Exception as ex:   # noqa: BLE001
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM candidate_files WHERE id=%s", (fid,))
        raise drive.fail(ex)
    with db.pool.connection() as conn:
        conn.execute("UPDATE candidate_files SET drive_id=%s WHERE id=%s", (drive_id, fid))
    return {"ok": True, "n": n + 1, "id": fid}


@router.delete("/c/{token}/file/{fid}")
def unupload(token: str, fid: int):
    """Кандидат убрал фото или резюме (HEAD 27.11). С Диска не стираем — переносим в «udaleno» в его папке."""
    with db.pool.connection() as conn, conn.transaction():
        c = _by_token(conn, token, lock=True)
        if datetime.now(timezone.utc) - c["created_at"] > timedelta(hours=UPLOAD_HOURS):
            raise HTTPException(409, "Ссылка устарела. Напиши менеджеру, который с тобой свяжется.")
        f = conn.execute("DELETE FROM candidate_files WHERE id=%s AND cand_id=%s RETURNING drive_id", (fid, c["id"])).fetchone()
        if not f:
            raise HTTPException(404, "Файл не найден")
        parent = c["drive_folder"]
    if f["drive_id"] and parent:
        try:
            d = drive.Drive()
            d.move(f["drive_id"], d.child(parent, "udaleno"))
        except Exception as ex:   # noqa: BLE001 — в анкете файла уже нет; на Диске остался в папке кандидата
            print("hr unupload:", ex)
    return {"ok": True}


@router.post("/c/{token}/done")
def done(token: str, bg: BackgroundTasks):
    """Кандидат дослал файлы: анкета видна HEAD как «Новый», строка уходит в «Базу кандидатов»."""
    with db.pool.connection() as conn, conn.transaction():
        c = _by_token(conn, token, lock=True)
        conn.execute("UPDATE candidates SET submitted_at=coalesce(submitted_at, now()), level=%s, updated_at=now() WHERE id=%s",
                     (_hint_code(conn, c["dir"], c["answers"] or {}, c["id"]), c["id"]))
    bg.add_task(sync, c["id"], True)
    if not c["submitted_at"]:   # HEAD 28.11 «дыры»: о новой анкете HEAD узнаёт сразу, а не когда зайдёт в «Кандидаты»
        bg.add_task(_tell_head_new, c["full_name"], c["dir"], c["city"])
    return {"ok": True}


def _tell_head_new(name: str, dir_: str, city: str | None) -> None:
    from .config import settings
    if not (settings.head_tg_id and settings.bot_token):
        return
    try:
        from . import notify as nt
        t = (hr_forms.FORMS.get(dir_) or {}).get("title") or ["", ""]
        nt.SEND(settings.head_tg_id, f"Новая анкета: {name} — {t[0]}{', ' + city if city else ''}. Команда → Кандидаты.")
    except Exception as e:  # noqa: BLE001
        print("hr new notify:", e)


@router.get("/c/{token}")
def mine(token: str):
    with db.pool.connection() as conn:
        c = _by_token(conn, token)
        fl = conn.execute("SELECT id, kind, mime FROM candidate_files WHERE cand_id=%s AND drive_id<>'' ORDER BY id", (c["id"],)).fetchall()
        from . import hrtrial
        st = hrtrial.for_candidate(conn, c)   # статус для самого кандидата: собеседование, выбор дня пробной, приглашение (HEAD 28.11)
    n = {}
    for x in fl:
        n[x["kind"]] = n.get(x["kind"], 0) + 1
    # свои фото — чтобы после перезагрузки страницы их было видно и можно было убрать (HEAD 27.11)
    return {"dir": c["dir"], "done": bool(c["submitted_at"]), "files": n, "name": (c["full_name"] or "").split(" ")[-1], "status": st, "bot": bool(c["tg_id"]),
            "photos": [{"id": x["id"], "thumb": _thumb_url(x["id"])} for x in fl if x["kind"] == "photo"]}


class DayIn(BaseModel):
    day: date


@router.post("/c/{token}/trial-day")
def pick_day(token: str, b: DayIn):
    """Кандидат сам выбирает день пробной (HEAD 28.11) — куратор ГИП получает «подтверди». Выбрать заново можно до смены."""
    from . import hrbot, hrtrial
    if b.day.isoformat() not in hrtrial.pick_days():
        raise HTTPException(400, "Выбери день из списка")
    with db.pool.connection() as conn, conn.transaction():
        c = _by_token(conn, token, lock=True)
        if c["stage"] != "trial" or c["trial_reviewed_at"]:
            raise HTTPException(409, "Пробный день сейчас не назначается")
        conn.execute("""UPDATE candidates SET trial_on=%s, trial_state='wait', trial_sent_at=NULL, trial_remind_at=NULL, updated_at=now()
                        WHERE id=%s""", (b.day, c["id"]))
        db.audit(conn, None, "hr_trial_pick", "candidates", c["id"], {"day": str(b.day)})
        c = conn.execute("SELECT * FROM candidates WHERE id=%s", (c["id"],)).fetchone()
        hrbot.ask_gip(conn, c)
    return {"ok": True}


@router.post("/candidates/{cid}/invite-sent")
def invite_sent(cid: int, p: dict = Depends(require_head)):
    """HEAD нажал «Отправить в WhatsApp» — отмечаем, чтобы в карточке было видно, что кандидат знает (HEAD 28.11)."""
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("UPDATE candidates SET trial_sent_at=now() WHERE id=%s AND stage='trial' RETURNING trial_sent_at", (cid,)).fetchone()
        if not r:
            raise HTTPException(409, "Пробный день не назначен")
        db.audit(conn, p["id"], "hr_trial_invite", "candidates", cid, {})
    return {"sent_at": r["trial_sent_at"].isoformat()}


# ---------- таблицы ----------

def sync(cid: int, prior: bool = False) -> None:
    """Строка в «Базе кандидатов» (и в «Сотрудниках», если принят). Сбой Google — в журнал службы, повтор при следующем шаге."""
    try:
        with db.pool.connection() as conn:
            c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
            titles = _role_titles(conn)
            if prior and c["prior"] is None:
                p = hr_sheets.find_prior(c["phone"])
                conn.execute("UPDATE candidates SET prior=%s WHERE id=%s", (Jsonb(p or {}), cid))
            if c["drive_folder"] is None:
                try:
                    folder(conn, c, drive.Drive())
                    c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
                except Exception as e:   # noqa: BLE001
                    print("hr folder:", e, file=sys.stderr)
            sheet = c["sheet_name"] or hr_forms.FORMS[c["dir"]]["sheet"]
            url = drive.FOLDER_URL + c["drive_folder"] if c["drive_folder"] else ""
            hr_sheets.base_upsert(sheet, c, titles.get(c["level"]), url)
            conn.execute("UPDATE candidates SET sheet_name=%s, sheet_at=now() WHERE id=%s", (sheet, cid))
            if c["stage"] == "hired" and not c["staff_at"]:
                hr_sheets.staff_append(c, titles.get(c["hired_role"]) or c["hired_role"], c["hired_role"] == "support")
                conn.execute("UPDATE candidates SET staff_at=now() WHERE id=%s", (cid,))
    except Exception as e:   # noqa: BLE001
        print("hr sync:", cid, e.__class__.__name__, e, file=sys.stderr)


SYNC = sync   # тесты подменяют


# ---------- HEAD: «Команда → Кандидаты» ----------

def _out(c: dict, thumb: int | None = None) -> dict:
    now = datetime.now(timezone.utc)
    return {"id": c["id"], "dir": c["dir"], "dir_title": hr_forms.DIR_TITLE.get(c["dir"], c["dir"]), "full_name": c["full_name"],
            "phone": c["phone"], "city": c["city"], "level": c["level"], "stage": c["stage"], "stars": c["stars"], "note": c["note"],
            "reason": c["reason"], "self_refused": c["self_refused"], "source": c["source"],
            "meet_on": c["meet_on"] and c["meet_on"].isoformat(), "trial_on": c["trial_on"] and c["trial_on"].isoformat(),
            "token": c["token"], "bot": bool(c["tg_id"]), "trial_object": c["trial_object"], "trial_time": c["trial_time"], "trial_place": c["trial_place"], "trial_bring": c["trial_bring"],
            "trial_paid": bool(c["trial_acc"]), "hired_role": c["hired_role"], "person_id": c["person_id"],
            "prior": c["prior"] or None, "created_at": c["created_at"].isoformat(), "stage_at": c["stage_at"].isoformat(),
            "submitted": bool(c["submitted_at"]),
            "waiting": c["stage"] in ("new", "talk") and now - c["stage_at"] > timedelta(days=WAIT_DAYS),
            "thumb": thumb and _thumb_url(thumb), "in_sheet": bool(c["sheet_at"])}


def _thumb_url(fid: int) -> str:
    return files.sign(fid, "hrthumb").replace("/api/files/", "/api/hr/files/")


@router.get("/candidates")
def board(p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        titles = _role_titles(conn)
        rows = conn.execute("""SELECT c.*, (SELECT min(f.id) FROM candidate_files f WHERE f.cand_id=c.id AND f.kind='photo' AND f.drive_id<>'') AS th
                               FROM candidates c ORDER BY c.stage_at DESC LIMIT 500""").fetchall()
    items = [{**_out(r, r["th"]), "level_title": titles.get(r["level"])} for r in rows]
    return {"items": items, "links": {d: f"/?job={d}" for d in hr_forms.FORMS}, "dirs": hr_forms.DIR_TITLE,
            "new": sum(1 for i in items if i["stage"] == "new" and i["submitted"]), "waiting": sum(1 for i in items if i["waiting"])}


@router.get("/candidates/{cid}")
def card(cid: int, p: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Нет такого кандидата")
        fl = conn.execute("SELECT * FROM candidate_files WHERE cand_id=%s AND drive_id<>'' ORDER BY id", (cid,)).fetchall()
        f = hr_forms.FORMS.get(c["dir"])
        titles = _role_titles(conn)
        from . import hrtrial
        trial = hrtrial.for_head(conn, c)
        evals = hrtrial.evaluators(conn)
        objs = hrtrial.objects(conn)
        ob = None
        if c["person_id"]:
            from . import onboard
            ob = onboard.card(conn, conn.execute("SELECT * FROM people WHERE id=%s", (c["person_id"],)).fetchone())
    h = hr_forms.level_hint(c["dir"], c["answers"] or {}, sum(1 for x in fl if x["kind"] == "photo"))
    return {**_out(c), "answers": c["answers"], "lang": c["lang"], "hint": h and {**h, "title": titles.get(h["code"], h["code"])},
            "folder": c["drive_folder"] and drive.FOLDER_URL + c["drive_folder"],
            "files": [{"id": x["id"], "kind": x["kind"], "name": x["name"], "thumb": x["mime"].startswith("image/") and _thumb_url(x["id"]),
                       "url": f"https://drive.google.com/file/d/{x['drive_id']}/view"} for x in fl],
            "steps": f and f["steps"], "roles": [[k, titles[k]] for k, _ in (f["levels"] if f else []) if k in titles], "onboard": ob,
            "trial": trial, "evaluators": evals, "objects": objs}


class StepIn(BaseModel):
    stage: str | None = None
    stars: int | None = Field(default=None, ge=0, le=5)    # 0 — снять
    note: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=200)
    self_refused: bool | None = None
    meet_on: date | None = None
    trial_on: date | None = None
    trial_object: int | None = None
    trial_by: int | None = None          # оценщик пробного дня; не указан — куратор ГИП сделки (HEAD 28.11)
    trial_time: str | None = Field(default=None, pattern=r"^([01]?\d|2[0-3]):[0-5]\d$|^$")   # во сколько прийти
    trial_place: str | None = Field(default=None, max_length=200)   # адрес / куда подойти
    trial_bring: str | None = Field(default=None, max_length=300)   # что взять с собой
    hired_role: str | None = None


@router.post("/candidates/{cid}")
def step(cid: int, b: StepIn, bg: BackgroundTasks, p: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        c = conn.execute("SELECT * FROM candidates WHERE id=%s FOR UPDATE", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Нет такого кандидата")
        upd: dict = {}
        if b.stage is not None:
            if b.stage not in STAGES:
                raise HTTPException(400, "Нет такого шага")
            if b.stage == "hired":
                f = hr_forms.FORMS.get(c["dir"])
                role = b.hired_role or c["hired_role"] or (f and f["levels"][0][0])   # старт — первая ступень (HEAD 26.11)
                if not role or not conn.execute("SELECT 1 FROM roles WHERE code=%s", (role,)).fetchone() or role == "head":
                    raise HTTPException(400, "Выбери роль, с которой человек начнёт")
                upd |= {"hired_role": role, "hired_at": datetime.now(timezone.utc)}
            if b.stage in ("reserve", "rejected") and not (b.reason or c["reason"]):
                raise HTTPException(400, "Коротко: почему")
            if b.stage != c["stage"]:
                upd |= {"stage": b.stage, "stage_at": datetime.now(timezone.utc)}
        for k in ("note", "reason", "self_refused", "meet_on", "trial_on", "trial_object", "trial_time", "trial_place", "trial_bring"):
            v = getattr(b, k)
            if v is not None:
                upd[k] = (v.strip() or None) if isinstance(v, str) else v
        if b.stars is not None:
            upd["stars"] = b.stars or None
        # пробный день (HEAD 28.11): оценивает куратор ГИП сделки или тот, кого выбрал HEAD
        from . import hrtrial
        new_by = None
        if b.trial_by is not None or "trial_object" in upd or (upd.get("stage") == "trial" and not c["trial_by"]):
            new_by = b.trial_by or hrtrial.evaluator_for(conn, upd.get("trial_object", c["trial_object"])) or c["trial_by"]
            if b.trial_by and not conn.execute("SELECT 1 FROM people WHERE id=%s AND status='active'", (b.trial_by,)).fetchone():
                raise HTTPException(400, "Нет такого сотрудника")
            if new_by and new_by != c["trial_by"]:
                upd["trial_by"] = new_by
        if not upd:
            raise HTTPException(400, "Нечего менять")
        # пробный день (HEAD 28.11): без даты — день выбирает кандидат; дату поставил HEAD — её подтверждает куратор ГИП.
        # Поменялись дата/время/место/куратор — прежнее приглашение уже неверно: снова ждём подтверждения.
        if upd.get("stage") == "trial" or (c["stage"] == "trial" and "trial_on" in upd and upd["trial_on"] != c["trial_on"]):
            st = "wait" if upd.get("trial_on", c["trial_on"]) else "pick"
            if st != c["trial_state"]:
                upd["trial_state"] = st
        if c["trial_sent_at"] and any(k in upd and upd[k] != c[k] for k in ("trial_on", "trial_time", "trial_place", "trial_by", "trial_object")):
            upd |= {"trial_sent_at": None, "trial_remind_at": None}
            if c["trial_state"] == "ok" and upd.get("trial_state") is None:
                upd["trial_state"] = "wait"
        conn.execute(f"UPDATE candidates SET {', '.join(k + '=%s' for k in upd)}, updated_at=now() WHERE id=%s", (*upd.values(), cid))
        if upd.get("stage") == "hired":
            link_hired(conn, cid)
        db.audit(conn, p["id"], "hr_step", "candidates", cid, {k: str(v) for k, v in upd.items() if k != "note"})
        old, c = c, conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
        if "trial_by" in upd or (("trial_on" in upd or upd.get("stage") == "trial") and c["trial_by"]):
            if c["stage"] == "trial" and not c["trial_reviewed_at"]:
                from . import hrbot
                hrbot.ask_gip(conn, c) if c["trial_state"] == "wait" else hrtrial.notify(conn, cid)
        from . import hrbot
        hrbot.on_step(conn, c, old)   # кандидату в бот: собеседование, выбор дня, решение (HEAD 28.11 «автоматически»)
        c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
    bg.add_task(SYNC, cid)
    return _out(c)


def link_hired(conn, cid: int) -> None:
    """Принят и уже есть в приложении (вошёл раньше с тем же телефоном) — сразу ставим роль; нет — поставит регистрация."""
    c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
    for pp in conn.execute("SELECT id, phone, role_code, status FROM people WHERE phone IS NOT NULL AND status<>'blocked'").fetchall():
        if hr_sheets.phone(pp["phone"]) == c["phone"]:
            _give_role(conn, pp, c)
            return


def _give_role(conn, person: dict, c: dict) -> None:
    if person["role_code"] in (None,):
        conn.execute("""UPDATE people SET role_code=%s, status='active', city=coalesce(city, %s), updated_at=now() WHERE id=%s""",
                     (c["hired_role"], c["city"], person["id"]))
        from .viewas import ROLE_ZONE
        z = ROLE_ZONE.get(c["hired_role"])
        if z:
            conn.execute("INSERT INTO person_zones (person_id, zone_code) VALUES (%s,%s) ON CONFLICT DO NOTHING", (person["id"], z))
    conn.execute("UPDATE candidates SET person_id=%s WHERE id=%s", (person["id"], c["id"]))
    from .onboard import require
    require(conn, person["id"])   # HEAD 26.11: до первой смены — правила роли, ТБ, соглашение о неразглашении и ИС
    db.audit(conn, None, "hr_hired_login", "people", person["id"], {"candidate": c["id"], "role": c["hired_role"]})
    pay_trial(conn, c["id"])


def pay_trial(conn, cid: int) -> int | None:
    """Пробная смена оплачивается, только если человека приняли (HEAD 26.11). Принят и вошёл в приложение — одно ручное
    начисление в ФОТ текущего месяца по ставке смены его стартовой роли из «Значений». Не приняли — ничего не начисляется."""
    c = conn.execute("SELECT * FROM candidates WHERE id=%s", (cid,)).fetchone()
    if c["stage"] != "hired" or not c["trial_on"] or not c["person_id"] or c["trial_acc"]:
        return None
    from . import constants as consts
    from .finance import RATE, sync_payees
    amount = consts.latest(conn).get(RATE.get(c["hired_role"], (None,))[0])
    if not isinstance(amount, (int, float)) or amount <= 0:
        return None   # ставки нет в «Значениях» — HEAD внесёт вручную, в карточке видно «пробная не начислена»
    sync_payees(conn)
    payee = conn.execute("SELECT id FROM fin_payees WHERE person_id=%s", (c["person_id"],)).fetchone()
    if not payee:
        return None
    ym = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5))).strftime("%Y-%m")
    acc = conn.execute("""INSERT INTO fin_accruals (period, payee_id, kind, amount, detail, ref) VALUES (%s,%s,'manual',%s,%s,%s) RETURNING id""",
                       (ym, payee["id"], amount, f"Пробная смена {c['trial_on']:%d.%m} — оплачивается при приёме", f"candidate:{cid}")).fetchone()["id"]
    conn.execute("UPDATE candidates SET trial_acc=%s WHERE id=%s", (acc, cid))
    db.audit(conn, None, "hr_trial_paid", "fin_accruals", acc, {"candidate": cid, "amount": amount})
    return acc


def on_register(conn, person_id: int, phone: str | None) -> bool:
    """Регистрация в приложении: телефон принятого кандидата → роль и зона без ожидания HEAD. Возвращает, нашли ли."""
    ph = hr_sheets.phone(phone)
    if not ph:
        return False
    c = conn.execute("SELECT * FROM candidates WHERE phone=%s AND stage='hired' AND person_id IS NULL ORDER BY hired_at DESC LIMIT 1",
                     (ph,)).fetchone()
    if not c:
        return False
    _give_role(conn, conn.execute("SELECT id, role_code FROM people WHERE id=%s", (person_id,)).fetchone(), c)
    return True


@router.delete("/candidates/{cid}")
def remove(cid: int, p: dict = Depends(require_head)):
    """HEAD 28.11 «просто удали» (тестовые анкеты): анкета и её файлы — из приложения, строка — из «Базы кандидатов»,
    папка — в корзину Диска. Принятого, который уже вошёл в приложение, так не удалить."""
    with db.pool.connection() as conn, conn.transaction():
        c = conn.execute("SELECT * FROM candidates WHERE id=%s FOR UPDATE", (cid,)).fetchone()
        if not c:
            raise HTTPException(404, "Нет такого кандидата")
        if c["person_id"] or c["trial_acc"]:
            raise HTTPException(400, "Уже в команде и вошёл в приложение — так не удалить")
        conn.execute("DELETE FROM candidate_files WHERE cand_id=%s", (cid,))
        conn.execute("DELETE FROM candidates WHERE id=%s", (cid,))
        db.audit(conn, p["id"], "hr_delete", "candidates", cid, {"name": c["full_name"], "phone": c["phone"], "dir": c["dir"]})
    left = []
    if c["sheet_name"]:
        with db.pool.connection() as conn:   # тот же телефон в другой живой анкете — строку не трогаем
            twin = conn.execute("SELECT 1 FROM candidates WHERE phone=%s AND sheet_name=%s", (c["phone"], c["sheet_name"])).fetchone()
        if not twin:
            try:
                hr_sheets.base_clear(c["sheet_name"], c["phone"])
            except Exception as ex:   # noqa: BLE001
                left.append(f"строка в базе «{c['sheet_name']}»"); print("hr remove sheet:", ex)
    if c["staff_at"]:
        left.append("строка в «Сотрудниках» — убрать вручную")
    if c["drive_folder"]:
        try:
            drive.Drive().trash(c["drive_folder"])
        except Exception as ex:   # noqa: BLE001
            left.append("папка на Диске"); print("hr remove folder:", ex)
    return {"ok": True, "left": left}


@router.get("/files/{fid}/hrthumb")
def thumb(fid: int, exp: int, sig: str):
    files.check_sig(fid, "hrthumb", exp, sig)
    with db.pool.connection() as conn:
        f = conn.execute("SELECT * FROM candidate_files WHERE id=%s", (fid,)).fetchone()
    if not f:
        raise HTTPException(404, "no file")
    data = files._thumb_cached(f["drive_id"], f["mime"], f["size"])
    if data is None:
        raise HTTPException(404, "no thumbnail")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
