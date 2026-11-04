"""Фото и чеки → Google Диск, в папку сделки: ПРОЕКТЫ → год → «ММ МЕСЯЦ» → «№ · НАЗВАНИЕ — ГОРОД» → «Журнал работ (фото и чеки)».
Та же раскладка, что в прототипе. Папка сделки запоминается в objects.drive_folder. Офис — в ARTGAME_DRIVE_INBOX."""
import base64
import json
from datetime import datetime

import httpx

from .config import settings

PROJECTS_ROOT_ID = "1_33LDppwOu02ToP4c3uUS-mPux5mPIJf"
PHOTO_SUBFOLDER = "Журнал работ (фото и чеки)"
MONTHS = ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ", "АПРЕЛЬ", "МАЙ", "ИЮНЬ", "ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ", "ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ"]
API = "https://www.googleapis.com/drive/v3/files"
ALL = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
FOLDER = "application/vnd.google-apps.folder"


def _token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        settings.google_sa_file, scopes=["https://www.googleapis.com/auth/drive"])
    creds.refresh(Request())
    return creds.token


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


class Drive:
    def __init__(self):
        self.h = {"Authorization": f"Bearer {_token()}"}

    def find(self, q: str) -> list[dict]:
        r = httpx.get(API, headers=self.h, timeout=30, params={**ALL, "corpora": "allDrives", "q": q + " and trashed = false",
                                                               "fields": "files(id,name,parents)", "pageSize": 50})
        r.raise_for_status()
        return r.json()["files"]

    def child(self, parent: str, name: str) -> str:
        found = self.find(f"'{parent}' in parents and name = '{_q(name)}' and mimeType = '{FOLDER}'")
        if found:
            return found[0]["id"]
        r = httpx.post(API, headers=self.h, timeout=30, params={"supportsAllDrives": "true"},
                       json={"name": name, "mimeType": FOLDER, "parents": [parent]})
        r.raise_for_status()
        return r.json()["id"]

    def project_folder(self, obj: dict) -> str:
        prefix = f"{obj['id']} ·"
        for f in self.find(f"name contains '{_q(prefix)}' and mimeType = '{FOLDER}'"):
            if f["name"].startswith(prefix):
                return f["id"]
        now = datetime.now()
        year = self.child(PROJECTS_ROOT_ID, str(now.year))
        month = self.child(year, f"{now.month:02d} {MONTHS[now.month - 1]}")
        name = f"{obj['id']} · {obj['title'].upper()}" + (f" — {obj['city'].upper()}" if obj.get("city") else "")
        return self.child(month, name)

    def upload(self, parent: str, name: str, data: bytes, mime: str) -> str:
        meta = {"name": name, "parents": [parent]}
        r = httpx.post("https://www.googleapis.com/upload/drive/v3/files", headers=self.h, timeout=120,
                       params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id,webViewLink"},
                       files={"metadata": ("metadata", json.dumps(meta), "application/json"), "file": (name, data, mime)})
        r.raise_for_status()
        return r.json()["webViewLink"]


def save_photo(conn, obj: dict, name: str, data_url: str) -> str:
    """Возвращает ссылку на файл. Папку сделки запоминает в objects.drive_folder."""
    head, _, b64 = data_url.partition(",")
    mime = head.removeprefix("data:").removesuffix(";base64") or "image/jpeg"
    data = base64.b64decode(b64)
    d = Drive()
    if obj["id"] == 0:
        parent = settings.drive_inbox
    else:
        folder = obj.get("drive_folder") or d.project_folder(obj)
        if not obj.get("drive_folder"):
            conn.execute("UPDATE objects SET drive_folder=%s WHERE id=%s", (folder, obj["id"]))
        parent = d.child(folder, PHOTO_SUBFOLDER)
    return d.upload(parent, name + (".png" if mime == "image/png" else ".jpg"), data, mime)
