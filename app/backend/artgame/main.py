"""ARTGAME API. Вход: Telegram initData в заголовке X-Telegram-Init-Data."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from . import constants as consts
from . import head, viewas
from . import bx, bxw, db, design, files, fill, fin_export, finance, kit, leads, places, price, projects, sales_exp, stock, weblogin, work
from .config import settings
from .deps import current_person, load_person, require_head, tg_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    if db.pool is None:
        db.open_pool()
    db.migrate(db.pool)
    yield


app = FastAPI(title="ARTGAME", lifespan=lifespan)
app.include_router(work.router)
app.include_router(files.router)
app.include_router(places.router)
app.include_router(bx.router)
app.include_router(bxw.router)
app.include_router(leads.router)
app.include_router(sales_exp.router)
app.include_router(weblogin.router)
app.include_router(finance.router)
app.include_router(fin_export.router)
app.include_router(stock.router)
app.include_router(price.router)
app.include_router(projects.router)
app.include_router(fill.router)
app.include_router(kit.router)
app.include_router(design.router)
app.include_router(head.router)
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
            conn.execute("INSERT INTO person_zones (person_id, zone_code) SELECT %s, code FROM zones", (row["id"],))
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


@app.get("/api/people")
def people(_: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        return conn.execute(
            """SELECT p.id, p.full_name, p.tg_username, p.role_code, p.status, p.bitrix_user_id,
                      coalesce(array_agg(z.zone_code ORDER BY z.zone_code) FILTER (WHERE z.zone_code IS NOT NULL), '{}') AS zones
               FROM people p LEFT JOIN person_zones z ON z.person_id = p.id
               GROUP BY p.id ORDER BY p.created_at""").fetchall()


class AssignIn(BaseModel):
    role_code: str | None = None
    zones: list[str] | None = None
    status: str | None = None   # active | blocked (уход: вход закрыт, история остаётся)
    bitrix_user_id: int | None = None   # пользователь Битрикса (0 — снять связку): по нему МОП видит свои сделки


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
        if body.status is not None:
            if body.status not in ("active", "blocked"):
                raise HTTPException(400, "bad status")
            conn.execute("UPDATE people SET status=%s, updated_at=now() WHERE id=%s", (body.status, person_id))
        if body.bitrix_user_id is not None:
            uid = body.bitrix_user_id or None
            if uid and conn.execute("SELECT 1 FROM people WHERE bitrix_user_id=%s AND id<>%s", (uid, person_id)).fetchone():
                raise HTTPException(409, "этот пользователь Битрикса уже связан с другим человеком")
            conn.execute("UPDATE people SET bitrix_user_id=%s, updated_at=now() WHERE id=%s", (uid, person_id))
        if body.zones is not None:
            conn.execute("DELETE FROM person_zones WHERE person_id=%s", (person_id,))
            for z in body.zones:
                conn.execute("INSERT INTO person_zones (person_id, zone_code) VALUES (%s,%s)", (person_id, z))
        db.audit(conn, head["id"], "assign", "people", person_id, body.model_dump(exclude_none=True))
        return conn.execute("SELECT id, role_code, status FROM people WHERE id=%s", (person_id,)).fetchone()


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
