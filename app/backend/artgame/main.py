"""ARTGAME API. Вход: Telegram initData в заголовке X-Telegram-Init-Data."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from datetime import date

from pydantic import BaseModel, Field

from . import constants as consts
from . import appeals, closing, marketing, dm, projchat, feedback, gip, grow, head, items, tgbot, viewas, weekly, trips, recurring
from . import bx, bxw, db, deal_money, design, designobj, files, fill, fin_export, finance, kit, leads, media, places, price, projects, sales_exp, stock, weblogin, work
from .config import settings
from .deps import current_person, load_person, require_head, tg_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    if db.pool is None:
        db.open_pool()
    db.migrate(db.pool)
    yield


app = FastAPI(title="ARTGAME", lifespan=lifespan)
app.include_router(weekly.router)
app.include_router(projchat.router)   # чат проекта (HEAD 13.11)
app.include_router(recurring.router)   # график постоянных оплат (HEAD 12.11)
app.include_router(trips.router)
app.include_router(marketing.router)   # контент-план маркетинга (HEAD 14.11)
app.include_router(media.router)   # до work: там общий /{kind}/{id}/review
app.include_router(appeals.router)   # до work: /appeals/{id}/rate|cancel, а не общий /{kind}/{id}/…
app.include_router(work.router)
app.include_router(grow.router)   # «Мой путь»: отметки и наставник (HEAD 11.11)
app.include_router(files.router)
app.include_router(places.router)
app.include_router(bx.router)
app.include_router(bxw.router)
app.include_router(leads.router)
app.include_router(sales_exp.router)
app.include_router(weblogin.router)
app.include_router(finance.router)
app.include_router(fin_export.router)
app.include_router(deal_money.router)   # итоги оплат сделок по журналу (HEAD 10.11)
app.include_router(stock.router)
app.include_router(price.router)
app.include_router(projects.router)
app.include_router(fill.router)
app.include_router(kit.router)
app.include_router(design.router)
app.include_router(head.router)
app.include_router(items.router)
app.include_router(feedback.router)
app.include_router(dm.router)   # «Диалог с HEAD» (09.11)
app.include_router(tgbot.router)   # бот: ответ на «Старт» (HEAD 08.11)
app.include_router(gip.router)
app.include_router(designobj.router)   # дизайн в карточке проекта на любой стадии (HEAD 14.11)
app.include_router(closing.router)   # закрытие сделки через HEAD: паспорт, «Закрыть» и «Вернуть» (HEAD 12.11)
viewas.install(app)


@app.exception_handler(Exception)
async def _crash(request, ex: Exception):
    """Непредвиденная ошибка: в журнал службы полный текст, на экран — коротко, чтобы было что прислать."""
    import traceback
    from fastapi.responses import JSONResponse
    traceback.print_exc()
    return JSONResponse({"detail": f"Ошибка сервера ({type(ex).__name__}: {str(ex)[:160]}). Пришлите это сообщение в тред."}, status_code=500)


@app.get("/api/health")
def health():
    with db.pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "env": settings.env_name, "places": places.key_ok()}


class RegisterIn(BaseModel):
    full_name: str
    phone: str | None = None


@app.post("/api/register")
def register(body: RegisterIn, user: dict = Depends(tg_user)):
    """Сам по ссылке. Статус pending, пока HEAD не назначит роль. HEAD узнаётся по ARTGAME_HEAD_TG_ID."""
    tg_id = int(user["id"])
    is_head = settings.head_tg_id and tg_id == settings.head_tg_id
    with db.pool.connection() as conn:
        existing = load_person(conn, tg_id)
        if existing:
            return existing
        row = conn.execute(
            """INSERT INTO people (tg_id, tg_username, full_name, phone, role_code, status)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (tg_id, user.get("username"), body.full_name.strip(), body.phone,
             "head" if is_head else None, "active" if is_head else "pending"),
        ).fetchone()
        if is_head:
            conn.execute("INSERT INTO person_zones (person_id, zone_code) SELECT %s, code FROM zones WHERE code<>'marketing'", (row["id"],))
        db.audit(conn, row["id"], "register", "people", row["id"])
        p = load_person(conn, tg_id)
    if not is_head and settings.head_tg_id and settings.bot_token:
        try:   # HEAD узнаёт о заявке сразу, роль назначает во вкладке «Команда»
            from . import notify
            who = body.full_name.strip() + (f" (@{user['username']})" if user.get("username") else "")
            notify.SEND(settings.head_tg_id, f"Новый человек в приложении: {who}. Назначьте роль во вкладке «Команда».")
        except Exception as e:  # noqa: BLE001
            print("register notify:", e)
    return p


@app.get("/api/me")
def me(p: dict = Depends(current_person)):
    return p


class ProfileIn(BaseModel):
    """Анкета «Мои данные» (HEAD 09.11): человек заполняет сам; имя в приложении — отсюда, не из Telegram."""
    last_name: str = Field(min_length=2, max_length=60)
    first_name: str = Field(min_length=2, max_length=60)
    middle_name: str | None = Field(default=None, max_length=60)
    birth_date: date
    phone: str = Field(min_length=10, max_length=20)
    city: str = Field(min_length=2, max_length=60)
    emergency_name: str | None = Field(default=None, max_length=80)
    emergency_phone: str | None = Field(default=None, max_length=20)
    clothes_size: str | None = Field(default=None, max_length=10)


@app.post("/api/profile")
def profile(body: ProfileIn, p: dict = Depends(current_person)):
    import re
    from datetime import datetime, timezone
    clean = lambda x: re.sub(r"\s+", " ", (x or "").strip()) or None   # noqa: E731
    first, last = clean(body.first_name), clean(body.last_name)
    if not re.fullmatch(r"[^\d@/:]{2,60}", first or "") or not re.fullmatch(r"[^\d@/:]{2,60}", last or ""):
        raise HTTPException(422, "Имя и фамилия — буквами, как в документах")
    today = date.today()
    if not (date(1940, 1, 1) <= body.birth_date <= date(today.year - 14, today.month, min(today.day, 28))):
        raise HTTPException(422, "Проверьте дату рождения")
    phone = re.sub(r"[^\d+]", "", body.phone)
    if len(re.sub(r"\D", "", phone)) < 10:
        raise HTTPException(422, "Телефон — полностью, с кодом")
    data = {"last_name": last, "first_name": first, "middle_name": clean(body.middle_name), "birth_date": body.birth_date,
            "phone": phone, "city": clean(body.city), "emergency_name": clean(body.emergency_name),
            "emergency_phone": clean(body.emergency_phone), "clothes_size": clean(body.clothes_size), "full_name": f"{first} {last}"}
    with db.pool.connection() as conn, conn.transaction():
        conn.execute(f"UPDATE people SET {', '.join(k + '=%s' for k in data)}, profile_at=%s WHERE id=%s",
                     (*data.values(), datetime.now(timezone.utc), p["id"]))
        db.audit(conn, p["id"], "profile", "people", p["id"], {k: v for k, v in data.items() if k in ("full_name", "city")})
        return load_person(conn, p["id"], by="id")


@app.get("/api/people")
def people(_: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        return conn.execute(
            """SELECT p.id, p.full_name, p.tg_username, p.role_code, p.status, p.bitrix_user_id, p.city, p.phone, p.birth_date, p.last_name, p.first_name, p.middle_name, p.emergency_name, p.emergency_phone, p.clothes_size, p.profile_at, p.extra_roles, p.reels, p.pays, p.acting_role, p.acting_since, p.acting_promo, p.acting_note, p.print_exam_on,
                      coalesce(array_agg(z.zone_code ORDER BY z.zone_code) FILTER (WHERE z.zone_code IS NOT NULL), '{}') AS zones
               FROM people p LEFT JOIN person_zones z ON z.person_id = p.id
               GROUP BY p.id ORDER BY p.created_at""").fetchall()


class AssignIn(BaseModel):
    role_code: str | None = None
    zones: list[str] | None = None
    status: str | None = None   # active | blocked (уход: вход закрыт, история остаётся)
    bitrix_user_id: int | None = None   # пользователь Битрикса (0 — снять связку): по нему МОП видит свои сделки
    city: str | None = None             # город сотрудника: объект в другом городе — командировка (HEAD 08.11)
    reels: bool | None = None        # «Оплачиваемые рилс» (HEAD 09.11): «Продакшн» и рилс в оплату любому человеку
    pays: bool | None = None         # «Вносит оплаты клиентов» (HEAD 10.11): вкладка «Оплаты», любая сделка, с чеком
    acting_role: str | None = None   # и.о. (HEAD 09.11): "" — снять; права новой роли, ставка прежняя
    acting_promo: date | None = None  # день повышения (напр. 15.12 — день рождения команды)
    acting_note: str | None = None
    print_exam_on: date | None = None   # оператор печати сдал экзамен — с этого дня ставка pay.print.operator_exam (HEAD 13.11)
    no_print_exam: bool | None = None   # снять отметку экзамена
    extra_roles: list[str] | None = None  # вторая роль (HEAD 08.11): напр. оператор печати + саппорт; ставки — по роли смены


@app.post("/api/people/{person_id}")
def assign(person_id: int, body: AssignIn, head: dict = Depends(require_head)):
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM people WHERE id=%s", (person_id,)).fetchone():
            raise HTTPException(404, "no person")
        if body.role_code is not None:
            if not conn.execute("SELECT 1 FROM roles WHERE code=%s", (body.role_code,)).fetchone():
                raise HTTPException(400, "bad role")
            conn.execute("UPDATE people SET role_code=%s, status=CASE WHEN status='pending' THEN 'active' ELSE status END, updated_at=now() WHERE id=%s",
                         (body.role_code, person_id))
            # повышение: роль стала той, что исполнял, — «и.о.» снимается само (запись остаётся в журнале)
            conn.execute("""UPDATE people SET acting_role=NULL, acting_since=NULL, acting_promo=NULL, acting_note=NULL
                            WHERE id=%s AND acting_role=%s""", (person_id, body.role_code))
        if body.status is not None:
            if body.status not in ("active", "blocked"):
                raise HTTPException(400, "bad status")
            conn.execute("UPDATE people SET status=%s, updated_at=now() WHERE id=%s", (body.status, person_id))
        if body.bitrix_user_id is not None:
            uid = body.bitrix_user_id or None
            if uid and conn.execute("SELECT 1 FROM people WHERE bitrix_user_id=%s AND id<>%s", (uid, person_id)).fetchone():
                raise HTTPException(409, "этот пользователь Битрикса уже связан с другим человеком")
            conn.execute("UPDATE people SET bitrix_user_id=%s, updated_at=now() WHERE id=%s", (uid, person_id))
        if body.city is not None:
            conn.execute("UPDATE people SET city=%s, updated_at=now() WHERE id=%s", (body.city.strip() or None, person_id))
        if body.extra_roles is not None:
            main = conn.execute("SELECT role_code FROM people WHERE id=%s", (person_id,)).fetchone()["role_code"]
            extra = list(dict.fromkeys(r for r in body.extra_roles if r and r not in ("head", main)))
            if extra and len(conn.execute("SELECT code FROM roles WHERE code = ANY(%s)", (extra,)).fetchall()) != len(extra):
                raise HTTPException(400, "bad role")
            conn.execute("UPDATE people SET extra_roles=%s, updated_at=now() WHERE id=%s", (extra, person_id))
        if body.reels is not None:
            conn.execute("UPDATE people SET reels=%s, updated_at=now() WHERE id=%s", (body.reels, person_id))
        if body.pays is not None:
            conn.execute("UPDATE people SET pays=%s, updated_at=now() WHERE id=%s", (body.pays, person_id))
        if body.acting_role is not None:
            a = body.acting_role or None
            if a and (a == "head" or not conn.execute("SELECT 1 FROM roles WHERE code=%s", (a,)).fetchone()):
                raise HTTPException(400, "bad role")
            conn.execute("""UPDATE people SET acting_role=%s, acting_since=CASE WHEN %s::text IS NULL THEN NULL
                            WHEN acting_role IS DISTINCT FROM %s THEN current_date ELSE acting_since END,
                            acting_promo=CASE WHEN %s::text IS NULL THEN NULL ELSE acting_promo END, updated_at=now() WHERE id=%s""",
                         (a, a, a, a, person_id))
        if body.acting_promo is not None:
            conn.execute("UPDATE people SET acting_promo=%s, updated_at=now() WHERE id=%s", (body.acting_promo, person_id))
        if body.print_exam_on is not None or body.no_print_exam:
            from .grow import set_exam   # дата экзамена = пункт 1 пути «Оператор → Мастер печати»
            set_exam(conn, person_id, head["id"], None if body.no_print_exam else body.print_exam_on)
        if body.acting_note is not None:
            conn.execute("UPDATE people SET acting_note=%s, updated_at=now() WHERE id=%s", (body.acting_note.strip() or None, person_id))
        if body.zones is not None:
            conn.execute("DELETE FROM person_zones WHERE person_id=%s", (person_id,))
            for z in body.zones:
                conn.execute("INSERT INTO person_zones (person_id, zone_code) VALUES (%s,%s)", (person_id, z))
        db.audit(conn, head["id"], "assign", "people", person_id, body.model_dump(mode="json", exclude_none=True))
        return conn.execute("SELECT id, role_code, status, extra_roles, reels, pays, acting_role, acting_since, acting_promo, acting_note, print_exam_on FROM people WHERE id=%s", (person_id,)).fetchone()


@app.get("/api/constants")
def constants(p: dict = Depends(current_person)):
    """Последний снимок «Значений», только ключи, которые видит роль человека."""
    with db.pool.connection() as conn:
        row = conn.execute("SELECT fetched_at, values FROM constants_versions ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"values": {}, "fetched_at": None}
    return {"fetched_at": row["fetched_at"], "values": consts.visible(row["values"], p["role_code"])}


@app.post("/api/constants/refresh")
def constants_refresh(head: dict = Depends(require_head)):
    """Кнопка HEAD «обновить константы сейчас»."""
    values = consts.parse_rows(consts.fetch_rows())
    with db.pool.connection() as conn:
        changed = consts.store_if_changed(conn, values)
        db.audit(conn, head["id"], "constants_refresh", data={"changed": changed, "keys": len(values)})
    return {"changed": changed, "keys": len(values)}
