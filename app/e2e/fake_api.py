"""API для сквозного теста: Google Диск подменён памятью."""
import uvicorn

from artgame import drive
from artgame.main import app

STORE, PENDING = {}, {}


class FakeDrive:
    def project_folder(self, obj): return f"deal-{obj['id']}"
    def child(self, parent, name): return f"{parent}/{name}"

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

    def stream(self, fid): yield STORE[fid]["data"]
    def thumbnail(self, fid): return STORE[fid]["data"]


drive.Drive = FakeDrive

# Битрикс: те же ответы шлюза, что в tests/test_bx.py (только чтение)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "tests"))
from artgame import bx  # noqa: E402
from test_bx import fake as fake_bx  # noqa: E402
bx.READ = fake_bx

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
BX_CALLS = []


def fake_write(method, params):
    BX_CALLS.append({"method": method, "params": {k: v for k, v in params.items() if k != "fields"} | {"fields": {
        k: ("файл" if isinstance(v, (dict, list)) else v) for k, v in (params.get("fields") or {}).items()}}})
    if method == "tasks.task.add":
        return {"result": {"task": {"id": "777"}}}
    if method == "crm.deal.update":
        DEALS[str(params["id"])].update({k: v for k, v in params["fields"].items() if not isinstance(v, (dict, list))})
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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)
