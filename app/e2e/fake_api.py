"""API для сквозного теста: Google Диск подменён памятью."""
import uvicorn
from fastapi import Request

from artgame import drive
from artgame.config import settings

settings.public_origin = "https://test.app.artgame.world"   # e2e = среда test: открыт «Пройти как сотрудник · тест»
from artgame.main import app  # noqa: E402

STORE, PENDING = {}, {}


class FakeDrive:
    def project_folder(self, obj): return f"deal-{obj['id']}"
    def child(self, parent, name): return f"{parent}/{name}"

    def ls(self, parent):
        """Папка сделки 731 на Диске: ДИЗАЙН / Утвержденные дизайны / эскиз — для живой карточки."""
        F = "application/vnd.google-apps.folder"
        if parent == "deal-731":
            return [{"id": "dz731", "name": "ДИЗАЙН", "mimeType": F}]
        if parent == "dz731":
            return [{"id": "ok731", "name": "Утвержденные дизайны", "mimeType": F}]
        if parent == "ok731":
            STORE.setdefault("drvSKETCH731", {"parents": ["ok731"], "size": "1", "mimeType": "image/png",
                                              "data": open(__file__.replace("fake_api.py", "chek.png"), "rb").read()})
            return [{"id": "drvSKETCH731", "name": "Эскиз кафе.png", "mimeType": "image/png", "size": "1"}]
        return []

    def upload(self, parent, name, data, mime):
        i = f"drv{len(STORE):08d}"
        STORE[i] = {"parents": [parent], "size": str(len(data)), "mimeType": mime, "data": data}
        return i

    def resumable(self, parent, name, mime, size, origin):
        PENDING["next"] = {"parents": [parent], "size": str(size), "mimeType": mime, "data": b"x" * size}
        return "https://upload.example/session"

    def meta(self, fid):
        if fid not in STORE and fid.startswith("drvBIG"):
            STORE[fid] = PENDING.pop("next")
        return STORE[fid]

    def copy(self, fid, parent, name=None):
        i = f"drv{len(STORE):08d}"
        STORE[i] = {**STORE[fid], "parents": [parent]}
        return i

    def stream(self, fid, rng=None):
        d = STORE[fid]["data"]
        if rng:
            a, b = map(int, rng.split("=")[1].split("-"))
            d = d[a:b + 1]
        yield d
    def thumbnail(self, fid): return STORE[fid]["data"]

    def pdf_from_html(self, parent, name, html):   # паспорт сделки (closing.save_pdf): PDF — в «ДОКУМЕНТЫ» сделки
        return self.upload(parent, name, html.encode(), "application/pdf")


drive.Drive = FakeDrive

# Битрикс: те же ответы шлюза, что в tests/test_bx.py (только чтение)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "tests"))
from artgame import bx  # noqa: E402
from test_bx import fake as fake_bx  # noqa: E402
# стадии воронки 0 как в Битриксе: и «Оплата+закрывающие документы», и «Оплата получена» (закрытие сделки, zakrytie.cjs)
CLOSE_STAGES = [{"STATUS_ID": "UC_BMKDS4", "NAME": "Оплата+закрывающие документы", "SORT": "120"},
                {"STATUS_ID": "WON", "NAME": "Оплата получена", "SORT": "200", "EXTRA": {"SEMANTICS": "success"}}]


def _read(method, params):
    r = fake_bx(method, params)
    if method == "crm.status.list" and params["filter"].get("ENTITY_ID") == "DEAL_STAGE":
        r = {"result": sorted(r["result"] + CLOSE_STAGES, key=lambda x: int(x["SORT"]))}
    return r


bx.READ = _read

# WhatsApp: клиентка лида 3001 (Дана) написала 2 ч назад и ждёт ответа
from datetime import datetime, timedelta, timezone  # noqa: E402
from test_bx import DIALOGS, HISTORY  # noqa: E402
DIALOGS.append({"ID": "1", "OWNER_TYPE_ID": "1", "OWNER_ID": "3001", "ASSOCIATED_ENTITY_ID": "71",
                "LAST_UPDATED": datetime.now(timezone.utc).isoformat()})
HISTORY[71] = {"users": {"4995": {"connector": True}}, "message": {"1": {"id": "1", "senderid": "4995", "text": "Сколько стоит роспись?",
                                                                        "date": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}}}

# Запись в Битрикс: вебхук подменён, вызовы складываются в BX_CALLS (смотрит тест через /api/_e2e/bx_calls)
from artgame import bxw  # noqa: E402
from artgame.config import settings  # noqa: E402
from test_bx import DEALS, LEADS  # noqa: E402
settings.bitrix_webhook = "https://fake.bitrix24.kz/rest/1/key/"
# «Проекты»: объект в работе у другого МОП (Тимур), старт 2 дня назад, норма 12 смен / 10 раб. дней
DEALS["1700"] = {"ID": "1700", "TITLE": "1700 · ШКОЛА — ШЫМКЕНТ", "STAGE_ID": "UC_AV00QK", "CATEGORY_ID": "0", "OPPORTUNITY": "2400000.00",
                 "ASSIGNED_BY_ID": "4693", "CONTACT_ID": "0", "COMPANY_ID": "0", "UF_CRM_6881101914D8D": None,
                 "DATE_MODIFY": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), "UF_CRM_ARTGAME_AREA_M2": "120",
                 "UF_CRM_ARTGAME_NORM_SHIFTS": "12", "UF_CRM_ARTGAME_TERM_DAYS": "10", "UF_CRM_ARTGAME_COMPLEXITY": "901"}
BX_CALLS = []


def fake_write(method, params):
    BX_CALLS.append({"method": method, "params": {k: v for k, v in params.items() if k != "fields"} | {"fields": {
        k: ("файл" if isinstance(v, (dict, list)) else v) for k, v in (params.get("fields") or {}).items()}}})
    if method == "tasks.task.add":
        return {"result": {"task": {"id": "777"}}}
    if method == "crm.deal.update":
        # файл ложится в поле как в Битриксе: {id, downloadUrl}; простые поля — как есть
        fake = {"id": 500 + len(BX_CALLS), "downloadUrl": "https://fake.bitrix24.kz/file"}
        DEALS[str(params["id"])].update({k: (fake if isinstance(v, dict) else [fake] * len(v) if isinstance(v, list) else v)
                                         for k, v in params["fields"].items()})
    if method == "crm.lead.update":
        LEADS[str(params["id"])].update(params["fields"])
    if method == "crm.contact.add":
        return {"result": 2300}
    if method == "crm.deal.add":
        DEALS["9100"] = {**params["fields"], "ID": "9100", "DATE_MODIFY": "2026-11-05T10:00:00+05:00", "CATEGORY_ID": "0",
                         "COMPANY_ID": "0", "CONTACT_ID": str(params["fields"].get("CONTACT_ID") or 0)}
        return {"result": 9100}
    return {"result": True}


bxw.CALL = fake_write


@app.get("/api/_e2e/bx_calls")
def _bx_calls():
    return BX_CALLS


@app.post("/api/_e2e/deal/{deal_id}")
def _deal_fields(deal_id: str, fields: dict):
    """Поля сделки в подменённом Битриксе: например, «Поступление 1» без даты, как вносили до 10.11 (oplaty.cjs).
    Сделки ещё нет — заводится (zakrytie.cjs)."""
    DEALS.setdefault(deal_id, {"ID": deal_id, "CATEGORY_ID": "0", "CONTACT_ID": "0", "COMPANY_ID": "0"}).update(fields)
    bx._cache.clear()
    return DEALS[deal_id]


# Бот: сообщения складываются в SENT (код входа с компьютера смотрит тест)
from artgame import notify  # noqa: E402
SENT = []
notify.SEND = lambda tg, text: SENT.append({"tg": tg, "text": text})
from artgame import dm  # noqa: E402
dm.SEND = lambda tg, text: SENT.append({"tg": tg, "text": text, "dm": True}) and None   # «Диалог с HEAD»: бот никуда не пишет
dm.BOT = lambda m, **p: SENT.append({"bot": m, **{k: v for k, v in p.items() if k != "reply_markup"}}) or {"message_id": len(SENT)}   # уведомление «Новое сообщение»


@app.get("/api/_e2e/sent")
def _sent():
    return SENT


@app.post("/api/_e2e/store/{fid}")
async def _store(fid: str, request: Request):
    """Картинка в подменённом Диске (marketing.cjs): тело запроса — байты файла."""
    STORE[fid] = {"parents": ["e2e"], "size": "1", "mimeType": request.headers.get("content-type", "image/jpeg"), "data": await request.body()}
    return {"ok": True}


@app.post("/api/_e2e/consts")
def _consts(values: dict):
    from psycopg.types.json import Jsonb
    from artgame import db
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO constants_versions (checksum, values) VALUES (md5(random()::text), %s)",
                     (Jsonb({k: {"value": v, "status": "Утверждено"} for k, v in values.items()}),))
    return {"ok": True}


# Анкета «Мои данные» (HEAD 09.11): в сквозных тестах люди считаются заполнившими анкету, кроме tg 8800 —
# на нём kabinety.cjs проверяет саму анкету при первом входе.
from artgame import db as _db  # noqa: E402


@app.middleware("http")
async def _profile_done(request, call_next):
    resp = await call_next(request)
    if request.url.path == "/api/register":
        with _db.pool.connection() as c:
            c.execute("UPDATE people SET profile_at=now() WHERE profile_at IS NULL AND tg_id <> 8800")
    return resp


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)

