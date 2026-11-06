"""Google Диск — хранилище файлов объектов. Команда работает только через приложение (HEAD 04.11).

Раскладка как в прототипе: ПРОЕКТЫ → год → «ММ МЕСЯЦ» → «№ · НАЗВАНИЕ — ГОРОД» → подпапки SUBFOLDERS.
ID папок запоминаются в objects.drive_folder и objects.folders. Офис (объект 0) — папка ARTGAME_DRIVE_INBOX.
"""
import base64
import json
from datetime import datetime

import httpx

from .config import settings

PROJECTS_ROOT_ID = "1_33LDppwOu02ToP4c3uUS-mPux5mPIJf"
SUBFOLDERS = {"photo": "Фото объекта", "design": "Дизайн", "receipt": "Чеки", "doc": "Документы"}
MONTHS = ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ", "АПРЕЛЬ", "МАЙ", "ИЮНЬ", "ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ", "ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ"]
API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
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
        r = httpx.post(UPLOAD, headers=self.h, timeout=120,
                       params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id"},
                       files={"metadata": ("metadata", json.dumps(meta), "application/json"), "file": (name, data, mime)})
        r.raise_for_status()
        return r.json()["id"]

    def resumable(self, parent: str, name: str, mime: str, size: int, origin: str) -> str:
        """Ссылка для загрузки большого файла прямо из браузера в Google (сервер файл не пропускает)."""
        r = httpx.post(UPLOAD, timeout=30, params={"uploadType": "resumable", "supportsAllDrives": "true", "fields": "id,size"},
                       headers={**self.h, "X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size), "Origin": origin},
                       json={"name": name, "parents": [parent]})
        r.raise_for_status()
        return r.headers["Location"]

    def meta(self, file_id: str) -> dict:
        r = httpx.get(f"{API}/{file_id}", headers=self.h, timeout=30,
                      params={"supportsAllDrives": "true", "fields": "id,name,size,mimeType,parents,thumbnailLink"})
        r.raise_for_status()
        return r.json()

    def stream(self, file_id: str):
        """Отдаёт содержимое файла кусками (для просмотра в приложении)."""
        with httpx.stream("GET", f"{API}/{file_id}", headers=self.h, timeout=120,
                          params={"alt": "media", "supportsAllDrives": "true"}) as r:
            r.raise_for_status()
            yield from r.iter_bytes(256 * 1024)

    def thumbnail(self, file_id: str) -> bytes | None:
        link = self.meta(file_id).get("thumbnailLink")
        if not link:
            return None
        r = httpx.get(link.replace("=s220", "=s480"), headers=self.h, timeout=30)
        return r.content if r.status_code == 200 else None


def ensure_folders(conn, obj: dict, d: Drive | None = None) -> dict:
    """Папка сделки и подпапки; создаёт недостающие, запоминает ID в базе."""
    if obj["id"] == 0:
        return {k: settings.drive_inbox for k in SUBFOLDERS}
    folders = dict(obj.get("folders") or {})
    if all(k in folders for k in SUBFOLDERS) and obj.get("drive_folder"):
        return folders
    d = d or Drive()
    root = obj.get("drive_folder") or d.project_folder(obj)
    for k, name in SUBFOLDERS.items():
        folders.setdefault(k, d.child(root, name))
    conn.execute("UPDATE objects SET drive_folder=%s, folders=%s WHERE id=%s", (root, json.dumps(folders), obj["id"]))
    return folders


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    head, _, b64 = data_url.partition(",")
    mime = head.removeprefix("data:").removesuffix(";base64") or "image/jpeg"
    return base64.b64decode(b64), mime


def save_photo(conn, obj: dict, name: str, data_url: str, kind: str = "receipt") -> str:
    """Сохраняет сжатое фото (чек или фото объекта) в подпапку. Возвращает ID файла на Диске."""
    data, mime = decode_data_url(data_url)
    d = Drive()
    folders = ensure_folders(conn, obj, d)
    return d.upload(folders[kind], name + (".png" if mime == "image/png" else ".jpg"), data, mime)


def save_sales_receipt(name: str, data_url: str) -> str:
    """Чек трат отдела продаж: «Отдел продаж — чеки / год / ММ МЕСЯЦ» (в папке офиса, а если её нет — в ПРОЕКТЫ)."""
    data, mime = decode_data_url(data_url)
    d = Drive()
    now = datetime.now()
    root = d.child(settings.drive_inbox or PROJECTS_ROOT_ID, "Отдел продаж — чеки")
    month = d.child(d.child(root, str(now.year)), f"{now.month:02d} {MONTHS[now.month - 1]}")
    return d.upload(month, name + (".png" if mime == "image/png" else ".jpg"), data, mime)


def save_office_receipt(folder: str, name: str, data_url: str) -> str:
    """Чеки не по объекту (финансы, склад, мастерская холстов): «<папка> / год / ММ МЕСЯЦ» в папке офиса."""
    data, mime = decode_data_url(data_url)
    d = Drive()
    now = datetime.now()
    root = d.child(settings.drive_inbox or PROJECTS_ROOT_ID, folder)
    month = d.child(d.child(root, str(now.year)), f"{now.month:02d} {MONTHS[now.month - 1]}")
    return d.upload(month, name + (".png" if mime == "image/png" else ".jpg"), data, mime)
