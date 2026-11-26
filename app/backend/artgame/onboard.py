"""Знакомство нового сотрудника (HEAD 26.11): после «Принять» человек сначала читает «Правила игры» своей роли и ТБ
и принимает соглашение о неразглашении и интеллектуальной собственности. Пока не закончил — смены и расходы закрыты.

Каждое «Прочитал» / «Принимаю» — строка onboard_acks: документ, версия, отпечаток текста (sha256), ФИО, телефон, время,
IP и браузер. Новая версия соглашения (NDA_VERSION) — все, кто обязан, принимают заново.
"""
import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import db
from .deps import current_person, require_head

router = APIRouter(prefix="/api/onboard")

# «Правила игры» есть у этих ролей (frontend/src/duties.js DUTIES); ТБ — у росписи и печати (main.jsx ART, PRINT)
DUTY_ROLES = {"support", "artist", "lead_artist", "artist_pro", "print_operator", "print_master", "mop", "mop_vip",
              "carpenter", "lead_designer", "designer_asst"}
SAFETY_ROLES = {"support", "artist", "lead_artist", "artist_pro", "print_operator", "print_master", "carpenter"}

# ЧЕРНОВИК, проверяет юрист (HEAD 26.11). Текст = Claude Doc «Соглашение о конфиденциальности и ИС (черновик)».
NDA_VERSION = "1-draft"
NDA_TITLE = "Соглашение о конфиденциальности и интеллектуальной собственности"
NDA = [
    ["1. Стороны", [
        "1.1. [ИП / ТОО, БИН — уточнит юрист], далее «Компания» (бренд ARTGAME), и человек, принявший соглашение в приложении "
        "ARTGAME под своим ФИО и номером телефона, далее «Участник».",
        "1.2. Соглашение действует независимо от того, работает Участник по трудовому договору, договору оказания услуг "
        "или проходит пробную смену."]],
    ["2. Конфиденциальная информация", [
        "2.1. Конфиденциально всё, что Участник узнал на работе и в приложении: клиенты, их контакты, адреса объектов, "
        "суммы и условия сделок; цены, ставки, зарплаты, бонусы, финансовые данные Компании; эскизы, макеты и "
        "дизайн-проекты до их публикации Компанией; методики, учебники, чек-листы, скрипты продаж, настройки оборудования "
        "и печати; данные сотрудников, подрядчиков и поставщиков; содержание приложения ARTGAME, Битрикса, Диска и рабочих чатов.",
        "2.2. Не конфиденциально то, что Компания сама опубликовала, и то, что Участник знал до работы из открытых источников."]],
    ["3. Что Участник обязуется", [
        "3.1. Не передавать конфиденциальную информацию третьим лицам и не использовать её в своих интересах.",
        "3.2. Не выкладывать фото и видео объектов, эскизы и макеты в личные соцсети и портфолио без разрешения HEAD. "
        "После публикации на странице ARTGAME можно делать репост с отметкой ARTGAME.",
        "3.3. Не предлагать клиентам Компании работу напрямую, мимо Компании, во время работы и [12] месяцев после.",
        "3.4. Не копировать файлы, базы и переписки на личные носители сверх того, что нужно для работы.",
        "3.5. При уходе удалить или вернуть файлы и материалы Компании.",
        "3.6. Сразу сообщить HEAD, если кто-то просит такую информацию или произошла утечка."]],
    ["4. Интеллектуальная собственность", [
        "4.1. Исключительные имущественные права на всё, что Участник создал по заданию Компании или для её клиентов, "
        "принадлежат Компании с момента создания: эскизы, росписи, макеты печати, фото, видео, рилс, тексты, сценарии "
        "и другие результаты.",
        "4.2. Компания вправе использовать, изменять, публиковать и продавать эти результаты без дополнительной оплаты "
        "и без указания имени автора. Вознаграждение за права входит в оплату смен и работ.",
        "4.3. Личные неимущественные права автора остаются за Участником по закону.",
        "4.4. Работы, созданные Участником до начала работы, остаются его. Фото работ из анкеты Компания использует "
        "только для оценки кандидата.",
        "4.5. Бренд ARTGAME, логотип, книги, учебники и приложение принадлежат Компании. Использовать их вне работы нельзя."]],
    ["5. Срок", [
        "5.1. Соглашение действует с момента принятия в приложении.",
        "5.2. Обязанность не разглашать действует всё время работы и [3] года после. Права по разделу 4 остаются "
        "у Компании бессрочно."]],
    ["6. Ответственность", [
        "6.1. При нарушении Участник возмещает Компании убытки и удаляет опубликованное. Штраф: [сумма или нет].",
        "6.2. Нарушение может быть основанием для прекращения сотрудничества."]],
    ["7. Прочее", [
        "7.1. Участник принимает соглашение кнопкой «Принимаю» в приложении. Приложение сохраняет ФИО, телефон, дату, "
        "время и версию текста.",
        "7.2. Новая версия соглашения принимается заново тем же способом.",
        "7.3. Споры решаются переговорами, затем в суде по месту регистрации Компании, по законодательству "
        "Республики Казахстан."]],
]
NDA_SHA = hashlib.sha256(json.dumps([NDA_VERSION, NDA_TITLE, NDA], ensure_ascii=False).encode()).hexdigest()

TITLES = {"duties": "Правила игры твоей роли", "safety": "Техника безопасности", "nda": "Соглашение о неразглашении и ИС"}


def docs_for(role: str | None) -> list[str]:
    return [d for d, ok in (("duties", role in DUTY_ROLES), ("safety", role in SAFETY_ROLES), ("nda", True)) if ok]


def main_role(p: dict) -> str | None:
    return p.get("role_main") or p.get("role_code")


def status(conn, person: dict) -> list[dict]:
    """Шаги и что пройдено. Соглашение — только текущей версии; «Правила игры» — именно этой роли."""
    role = main_role(person)
    acks = conn.execute("SELECT doc, role_code, sha256, version, at FROM onboard_acks WHERE person_id=%s ORDER BY at",
                        (person["id"],)).fetchall()
    out = []
    for d in docs_for(role):
        hit = [a for a in acks if a["doc"] == d and (d != "nda" or a["sha256"] == NDA_SHA) and (d != "duties" or a["role_code"] == role)]
        out.append({"doc": d, "title": TITLES[d], "role": role if d == "duties" else None,
                    "done": bool(hit), "at": hit[-1]["at"] if hit else None, "version": hit[-1]["version"] if hit else None})
    return out


def pending(conn, person: dict) -> list[str]:
    """Что ещё не пройдено. Пусто — если ознакомление не требуется (старые сотрудники, HEAD) или всё пройдено."""
    if not person.get("onboard_from") or person.get("role_code") in (None, "head") or person.get("status") != "active":
        return []
    return [s["doc"] for s in status(conn, person) if not s["done"]]


def require(conn, person_id: int) -> None:
    """Принятый кандидат / HEAD отправил на ознакомление: с этого момента — шаги знакомства до первой смены."""
    conn.execute("UPDATE people SET onboard_from=coalesce(onboard_from, now()) WHERE id=%s", (person_id,))


@router.get("")
def mine(p: dict = Depends(current_person)):
    with db.pool.connection() as conn:
        steps = status(conn, p)
        return {"required": bool(p.get("onboard_from")), "pending": pending(conn, p), "steps": steps,
                "nda": {"version": NDA_VERSION, "sha256": NDA_SHA, "title": NDA_TITLE, "sections": NDA, "draft": True},
                "full_name": p.get("full_name"), "phone": p.get("phone")}


class Ack(BaseModel):
    doc: str = Field(pattern="^(duties|safety|nda)$")
    version: str = Field(min_length=1, max_length=80)
    sha256: str = Field(min_length=8, max_length=80)
    full_name: str | None = Field(default=None, max_length=120)
    agree: bool = False


@router.post("/ack")
def ack(b: Ack, request: Request, p: dict = Depends(current_person)):
    if p.get("_view_as"):
        raise HTTPException(403, "view only")
    role = main_role(p)
    if b.doc not in docs_for(role):
        raise HTTPException(400, "not your doc")
    name = None
    if b.doc == "nda":
        if b.sha256 != NDA_SHA or b.version != NDA_VERSION:
            raise HTTPException(409, "Текст соглашения обновился — открой его заново")
        name = " ".join((b.full_name or "").split())
        if not b.agree or len(name) < 5:
            raise HTTPException(400, "Впиши ФИО полностью и отметь «Прочитал и согласен»")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "") or "").split(",")[0].strip()
    with db.pool.connection() as conn:
        conn.execute("""INSERT INTO onboard_acks (person_id, doc, role_code, version, sha256, full_name, phone, ip, ua)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                     (p["id"], b.doc, role if b.doc == "duties" else None, b.version, b.sha256, name or p.get("full_name"),
                      p.get("phone"), ip[:64], (request.headers.get("user-agent") or "")[:300]))
        db.audit(conn, p["id"], "onboard_ack", "people", p["id"], {"doc": b.doc, "version": b.version, "sha256": b.sha256})
        left = pending(conn, p)
        if not left and p.get("onboard_from"):
            _tell_head(conn, p)
        return {"pending": left, "steps": status(conn, p)}


def _tell_head(conn, p: dict) -> None:
    """Всё прочитано и соглашение принято — HEAD в «HEAD»-чат одной строкой (раз)."""
    seen = conn.execute("SELECT 1 FROM audit_log WHERE action='onboard_done' AND entity_id=%s LIMIT 1", (str(p["id"]),)).fetchone()
    if seen:
        return
    db.audit(conn, p["id"], "onboard_done", "people", p["id"], {})
    from .config import settings
    if not (settings.head_tg_id and settings.bot_token):
        return
    try:
        from . import notify
        notify.SEND(settings.head_tg_id, f"{p.get('full_name')}: прочитал правила и ТБ, принял соглашение о неразглашении и ИС. Смены открыты.")
    except Exception as e:  # noqa: BLE001 — уведомление не главное
        print("onboard notify:", e)


@router.post("/send/{person_id}")
def send(person_id: int, h: dict = Depends(require_head)):
    """HEAD: отправить на ознакомление уже работающего (например, когда юрист утвердит соглашение)."""
    with db.pool.connection() as conn:
        if not conn.execute("SELECT 1 FROM people WHERE id=%s", (person_id,)).fetchone():
            raise HTTPException(404, "no person")
        require(conn, person_id)
        db.audit(conn, h["id"], "onboard_send", "people", person_id, {})
    return {"ok": True}


@router.get("/person/{person_id}")
def person(person_id: int, h: dict = Depends(require_head)):
    with db.pool.connection() as conn:
        pp = conn.execute("SELECT * FROM people WHERE id=%s", (person_id,)).fetchone()
        if not pp:
            raise HTTPException(404, "no person")
        return card(conn, pp)


def card(conn, pp: dict) -> dict:
    """Для HEAD: требуется ли, что пройдено, когда и какую версию принял."""
    return {"required": bool(pp.get("onboard_from")), "from": pp.get("onboard_from"), "steps": status(conn, pp),
            "done": not pending(conn, pp)}


def done_at(steps: list[dict]) -> datetime | None:
    ts = [s["at"] for s in steps if s["at"]]
    return max(ts) if ts and all(s["done"] for s in steps) else None
