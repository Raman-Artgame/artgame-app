"""«Смотреть как сотрудник» (HEAD 08.11): HEAD открывает приложение глазами любого человека или роли.

Заголовок X-View-As: <id человека> или role:<код роли>. Принимается только от действующего HEAD.
- Только просмотр: любой запрос кроме GET/HEAD/OPTIONS с этим заголовком сервер отклоняет (403) ещё до обработчика.
- Журнал: начало и конец просмотра — view_as_start / view_as_stop от имени HEAD; всё, что сервер сам пишет в журнал
  во время просмотра (открыл сделку и т. п.), записывается на HEAD с пометкой view_as, а не на сотрудника.
- Роль без человека: интерфейс роли на данных самого HEAD (команда ещё не вся зарегистрирована).
- Рабочие места во фрейме ходят по подписанной ссылке без заголовка — ссылка несёт пометку просмотра (places.token),
  запись в базу места и сохранение документа по ней закрыты.
"""
from contextvars import ContextVar

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from . import db

HEADER = "x-view-as"
READ = {"GET", "HEAD", "OPTIONS"}
RO_MSG = "Режим просмотра: от имени сотрудника ничего не меняется. Вернитесь к себе, чтобы действовать."

# Роль → зона по умолчанию (как в «Команде»): без зоны «Смена» закрыта.
ROLE_ZONE = {"support": "mural", "artist": "mural", "artist_pro": "mural", "lead_artist": "mural", "print_operator": "print",
             "print_master": "print", "mop": "sales", "mop_vip": "sales", "lead_designer": "design", "designer_asst": "design"}

# Один изменяемый словарь на запрос: middleware кладёт его до обработчиков, current_person дописывает, кто смотрит.
# Словарь — общий объект, поэтому виден и в потоках, куда FastAPI уносит синхронные обработчики.
VIEW: ContextVar[dict | None] = ContextVar("artgame_view_as", default=None)


def ctx() -> dict | None:
    d = VIEW.get()
    return d if d and d.get("viewer") else None


class ViewAsMiddleware:
    """Чистый ASGI: ставит словарь просмотра и закрывает запись при заголовке X-View-As."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        raw = next((v.decode() for k, v in scope.get("headers", []) if k.decode().lower() == HEADER), "").strip()
        token = VIEW.set({"as": raw or None})
        try:
            if raw and scope["method"] not in READ:
                return await JSONResponse({"detail": RO_MSG, "view_as": True}, status_code=403)(scope, receive, send)
            return await self.app(scope, receive, send)
        finally:
            VIEW.reset(token)


def resolve(conn, head: dict, raw: str, load_person) -> dict:
    """HEAD + значение заголовка → человек, которого показываем. Пометки _view_* видит экран (баннер)."""
    if head["role_code"] != "head" or head["status"] != "active":
        raise HTTPException(403, "смотреть как сотрудник может только HEAD")
    if raw.startswith("role:"):
        role = raw[5:]
        r = conn.execute("SELECT code, title FROM roles WHERE code=%s", (role,)).fetchone()
        if not r or role == "head":
            raise HTTPException(400, "нет такой роли")
        p = {**head, "role_code": role, "zones": [ROLE_ZONE[role]] if role in ROLE_ZONE else [],
             "full_name": f"Пример: {r['title']}"}
        target = {"kind": "role", "role": role}
    else:
        try:
            pid = int(raw)
        except ValueError:
            raise HTTPException(400, "bad view-as")
        p = load_person(conn, pid, by="id")
        if not p:
            raise HTTPException(404, "нет такого человека")
        target = {"kind": "person", "id": pid}
    p["_view_as"] = {**target, "viewer_id": head["id"], "viewer_name": head["full_name"],
                     "status": p["status"], "role_code": p["role_code"]}
    if p["status"] != "active":   # ждёт роли или вход закрыт — экран покажет, что видит сам человек
        p["_view_as"]["note"] = "ждёт роли" if p["status"] == "pending" else "вход закрыт"
    d = VIEW.get()
    if d is not None:
        d.update(viewer=head["id"], target=target)
    return p


def audit_owner(person_id, data):
    """Для db.audit: во время просмотра запись идёт на HEAD с пометкой, на кого он смотрел."""
    d = ctx()
    if not d:
        return person_id, data
    return d["viewer"], {**(data or {}), "view_as": d["target"], **({"for": person_id} if person_id != d["viewer"] else {})}


def mark(viewer: int, target: dict):
    """Рабочее место по ссылке просмотра: та же пометка для журнала внутри обработчика."""
    d = VIEW.get()
    if d is not None:
        d.update(viewer=viewer, target=target)


# ---------- начало и конец просмотра (запросы без заголовка, от самого HEAD) ----------

def _head(p):
    if p["role_code"] != "head" or p["status"] != "active":
        raise HTTPException(403, "head only")
    return p


def install(app):
    from pydantic import BaseModel

    from .deps import current_person

    class StartIn(BaseModel):
        target: str   # id человека или role:<код>

    @app.get("/api/view-as/options")
    def view_options(p: dict = Depends(current_person)):
        """Кого можно посмотреть: люди (кроме HEAD) и роли."""
        _head(p)
        with db.pool.connection() as conn:
            people = conn.execute(
                """SELECT p.id, p.full_name, p.role_code, p.status, r.title AS role_title, r.level
                   FROM people p LEFT JOIN roles r ON r.code=p.role_code
                   WHERE p.id<>%s ORDER BY p.status='active' DESC, r.level NULLS LAST, p.full_name""", (p["id"],)).fetchall()
            roles = conn.execute("SELECT code, title FROM roles WHERE code<>'head' ORDER BY level NULLS LAST, title").fetchall()
        return {"people": people, "roles": roles}

    @app.post("/api/view-as/start")
    def view_start(body: StartIn, p: dict = Depends(current_person)):
        _head(p)
        from .deps import load_person
        with db.pool.connection() as conn:
            t = resolve(conn, p, body.target.strip(), load_person)
            db.audit(conn, p["id"], "view_as_start", "people", t["_view_as"].get("id"),
                     {"target": body.target, "name": t["full_name"], "role": t["role_code"]})
        return {"ok": True, "name": t["full_name"], "role_code": t["role_code"]}

    @app.post("/api/view-as/stop")
    def view_stop(body: StartIn, p: dict = Depends(current_person)):
        _head(p)
        with db.pool.connection() as conn:
            db.audit(conn, p["id"], "view_as_stop", "people", None, {"target": body.target})
        return {"ok": True}

    app.add_middleware(ViewAsMiddleware)
