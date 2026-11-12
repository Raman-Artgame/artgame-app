"""Google Диск — хранилище файлов объектов. Команда работает только через приложение (HEAD 04.11).

Раскладка как в прототипе: ПРОЕКТЫ → год → «ММ МЕСЯЦ» → «№ · НАЗВАНИЕ — ГОРОД» → подпапки SUBFOLDERS.
ID папок запоминаются в objects.drive_folder и objects.folders.

Чеки расходов (HEAD 08.11): есть сделка → папка сделки / «Расходы чеки»; нет сделки (или у сделки ещё нет папки)
→ ARTGAME.KZ / 10 ФИНАНСЫ / Расходы чеки / <отдел> / год / «ММ МЕСЯЦ». Этот путь — единственный для всех трат.
"""
import base64
import json
from datetime import datetime

import httpx

from .config import settings

PROJECTS_ROOT_ID = "1_33LDppwOu02ToP4c3uUS-mPux5mPIJf"
# Папка сделки (утверждено HEAD 10.11, названия буква в букву с тредом Диска):
#   ДИЗАЙН (эскизы) / Утвержденные дизайны · ДИЗАЙН / Фото объекта (фото для наложения макетов)
#   МЕДИА / Отчёты (всё, что снято на объекте) · МЕДИА / Продакшн (утверждённое HEAD) · МЕДИА / Рилс
#   ДОКУМЕНТЫ · ПРИХОДЫ ЧЕКИ (оплаты клиентов) · РАСХОДЫ ЧЕКИ.  Других подпапок приложение не создаёт.
SUBFOLDERS = {"report": "МЕДИА/Отчёты", "prod_photo": "МЕДИА/Продакшн/Фото", "prod_video": "МЕДИА/Продакшн/Видео", "reels": "МЕДИА/Рилс", "design": "ДИЗАЙН",
              "design_ok": "ДИЗАЙН/Утвержденные дизайны", "site": "ДИЗАЙН/Фото объекта", "doc": "ДОКУМЕНТЫ", "receipt": "РАСХОДЫ ЧЕКИ",
              "income": "ПРИХОДЫ ЧЕКИ"}   # чеки и платёжки клиентов (HEAD 10.11 «да»)
FOLDERS_V = 4   # 4: Продакшн делится на Фото и Видео (HEAD 12.11); старше — ID подпапок ищутся заново по именам (07.11 приложение плодило «Дизайн» и «Фото объекта» рядом)
FOLDER_OF = {"photo": "report", "media": "report"}   # вид файла в базе → подпапка сделки


def key_of(kind: str, media_type: str | None = None) -> str:
    """Подпапка для загрузки: рилс — в «МЕДИА / Рилс», остальное медиа и фото с объекта — в «МЕДИА / Отчёты»."""
    if kind == "media" and media_type == "reels":
        return "reels"
    if kind == "prod":   # утверждённое HEAD — в «МЕДИА / Продакшн / Фото» или «… / Видео» (HEAD 12.11)
        return "prod_photo" if media_type == "photo" else "prod_video"
    return FOLDER_OF.get(kind, kind)


MONTHS = ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ", "АПРЕЛЬ", "МАЙ", "ИЮНЬ", "ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ", "ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ"]
# «10 ФИНАНСЫ / Расходы чеки» на диске ARTGAME.KZ; сервисному аккаунту дан доступ только к этой папке.
RECEIPTS_ROOT_ID = "1PCTnoVlAqBhvwUgBRIc8dd4murbKKnkB"
DEPTS = {"sales": "01 Продажи", "mural": "02 Роспись", "print": "03 Печать", "design": "04 Дизайн",
         "stock": "05 Склад и мастерская холстов", "office": "06 РАСХОДЫ HEAD", "income": "07 Приходы клиентов"}
# Чеки оплат клиентов (HEAD 10.11): папка сделки / «ПРИХОДЫ ЧЕКИ», рядом с «Расходы чеки». Создаётся при первом чеке,
# в SUBFOLDERS не входит — иначе пустая папка появилась бы в каждой сделке. Сделка без папки → «07 Приходы клиентов».
INCOME = "ПРИХОДЫ ЧЕКИ"
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

    def ls(self, parent: str) -> list[dict]:
        """Содержимое папки (папки и файлы) с типом и размером."""
        out, token = [], None
        while True:
            r = httpx.get(API, headers=self.h, timeout=30, params={**ALL, "corpora": "allDrives", "pageSize": 200,
                          "q": f"'{parent}' in parents and trashed = false", "fields": "nextPageToken,files(id,name,mimeType,size)",
                          **({"pageToken": token} if token else {})})
            r.raise_for_status()
            j = r.json()
            out += j.get("files", [])
            token = j.get("nextPageToken")
            if not token:
                return out

    def child(self, parent: str, name: str) -> str:
        # регистр не важен: DRIVE01 создаёт «ДИЗАЙН», приложение искало «Дизайн» и плодило вторую папку
        found = [f for f in self.ls(parent) if f.get("mimeType") == FOLDER and f["name"].casefold() == name.casefold()]
        found.sort(key=lambda f: f["name"] != name)   # точное имя (утверждённое) — первым, «Дизайн» рядом с «ДИЗАЙН» не берём
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

    def stream(self, file_id: str, rng: str | None = None):
        """Отдаёт содержимое файла кусками (для просмотра в приложении). rng — заголовок Range (видео на iPhone без него не играет)."""
        with httpx.stream("GET", f"{API}/{file_id}", headers={**self.h, **({"Range": rng} if rng else {})}, timeout=120,
                          params={"alt": "media", "supportsAllDrives": "true"}) as r:
            r.raise_for_status()
            yield from r.iter_bytes(256 * 1024)

    def copy(self, file_id: str, parent: str, name: str | None = None) -> str:
        """Копия файла в другую папку (утверждённый материал → «Продакшн»). Оригинал остаётся в «Отчётах»."""
        r = httpx.post(f"{API}/{file_id}/copy", headers=self.h, timeout=120, params={"supportsAllDrives": "true", "fields": "id"},
                       json={"parents": [parent], **({"name": name} if name else {})})
        r.raise_for_status()
        return r.json()["id"]

    def pdf_from_html(self, parent: str, name: str, html: str) -> str:
        """PDF из HTML (паспорт сделки, HEAD 12.11): HTML → временный Google Документ → PDF в папку → документ в корзину.
        Своей библиотеки PDF на сервере нет — Google делает PDF сам."""
        meta = {"name": name.rsplit(".", 1)[0], "parents": [parent], "mimeType": "application/vnd.google-apps.document"}
        r = httpx.post(UPLOAD, headers=self.h, timeout=120, params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id"},
                       files={"metadata": ("metadata", json.dumps(meta), "application/json"), "file": ("passport.html", html.encode(), "text/html")})
        r.raise_for_status()
        doc = r.json()["id"]
        try:
            e = httpx.get(f"{API}/{doc}/export", headers=self.h, timeout=120, params={"mimeType": "application/pdf"})
            e.raise_for_status()
            return self.upload(parent, name, e.content, "application/pdf")
        finally:
            try:
                httpx.patch(f"{API}/{doc}", headers=self.h, timeout=30, params={"supportsAllDrives": "true"}, json={"trashed": True})
            except Exception:  # noqa: BLE001 — временный документ останется в папке, PDF уже есть
                pass

    def thumbnail(self, file_id: str) -> bytes | None:
        link = self.meta(file_id).get("thumbnailLink")
        if not link:
            return None
        r = httpx.get(link.replace("=s220", "=s480"), headers=self.h, timeout=30)
        return r.content if r.status_code == 200 else None


def ensure_folders(conn, obj: dict, d: Drive | None = None) -> dict:
    """Папка сделки и подпапки; создаёт недостающие, запоминает ID в базе. Объект 0 «Офис» папки не имеет."""
    if obj["id"] == 0:
        raise ValueError("у «Офис / без объекта» нет папки сделки")
    folders = dict(obj.get("folders") or {})
    if folders.get("v") != FOLDERS_V:
        folders = {"v": FOLDERS_V}
    if all(k in folders for k in SUBFOLDERS) and obj.get("drive_folder"):
        return folders
    d = d or Drive()
    root = obj.get("drive_folder") or d.project_folder(obj)
    for k, name in SUBFOLDERS.items():
        if k not in folders:
            parent = root
            for part in name.split("/"):
                parent = d.child(parent, part)
            folders[k] = parent
    conn.execute("UPDATE objects SET drive_folder=%s, folders=%s WHERE id=%s", (root, json.dumps(folders), obj["id"]))
    return folders


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    head, _, b64 = data_url.partition(",")
    mime = head.removeprefix("data:").removesuffix(";base64") or "image/jpeg"
    return base64.b64decode(b64), mime


def _ext(mime: str) -> str:
    return ".png" if mime == "image/png" else ".jpg"


def save_photo(conn, obj: dict, name: str, data_url: str, kind: str = "photo") -> str:
    """Фото объекта (или другой файл) в подпапку сделки. Возвращает ID файла на Диске."""
    data, mime = decode_data_url(data_url)
    d = Drive()
    return d.upload(ensure_folders(conn, obj, d)[key_of(kind)], name + _ext(mime), data, mime)


def folder_of(conn, obj: dict, kind: str, d: "Drive | None" = None, media_type: str | None = None) -> str:
    """ID подпапки сделки для вида файла (photo/media → МЕДИА / Отчёты, рилс → МЕДИА / Рилс)."""
    return ensure_folders(conn, obj, d)[key_of(kind, media_type)]


def receipt_folder(conn, d: Drive, dept: str, deal_id: int | None) -> tuple[str, bool]:
    """Куда класть чек: (ID папки, в папку сделки ли). Сделка без папки в приложении → папка отдела."""
    if deal_id:
        obj = conn.execute("SELECT * FROM objects WHERE id=%s", (deal_id,)).fetchone()
        if obj and obj["id"] != 0:
            return ensure_folders(conn, obj, d)["receipt"], True
    root = RECEIPTS_ROOT_ID or settings.drive_receipts
    if not root:
        raise RuntimeError("не задана папка «10 ФИНАНСЫ / Расходы чеки»")
    now = datetime.now()
    month = d.child(d.child(d.child(root, DEPTS.get(dept, DEPTS["office"])), str(now.year)),
                    f"{now.month:02d} {MONTHS[now.month - 1]}")
    return month, False


def save_income_receipt(conn, name: str, data_url: str, deal_id: int) -> str:
    """Чек оплаты клиента → папка сделки / «ПРИХОДЫ ЧЕКИ» (нет папки сделки → 10 ФИНАНСЫ / … / 07 Приходы клиентов)."""
    data, mime = decode_data_url(data_url)
    d = Drive()
    obj = conn.execute("SELECT * FROM objects WHERE id=%s", (deal_id,)).fetchone() if deal_id else None
    if obj and obj["id"] != 0:
        folder = ensure_folders(conn, obj, d)["income"]
    else:
        folder, _ = receipt_folder(conn, d, "income", None)
        if deal_id and f"сделка {deal_id}" not in name:
            name += f" сделка {deal_id}"
    return d.upload(folder, name + _ext(mime), data, mime)


def save_receipt(conn, dept: str, name: str, data_url: str, deal_id: int | None = None) -> str:
    """Единая точка для чеков всех трат (смены, МОП, склад, финансы). Возвращает ID файла на Диске."""
    data, mime = decode_data_url(data_url)
    d = Drive()
    folder, in_deal = receipt_folder(conn, d, dept, deal_id)
    if deal_id and not in_deal and f"сделка {deal_id}" not in name:
        name += f" сделка {deal_id}"
    return d.upload(folder, name + _ext(mime), data, mime)
