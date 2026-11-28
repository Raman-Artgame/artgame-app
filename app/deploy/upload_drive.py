"""Загрузка файла копии в папку Google Диска сервисным аккаунтом (ARTGAME_GOOGLE_SA_FILE, BACKUP_DRIVE_FOLDER)."""
import os
import sys
from pathlib import Path

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account


def main(path: str):
    creds = service_account.Credentials.from_service_account_file(
        os.environ["ARTGAME_GOOGLE_SA_FILE"], scopes=["https://www.googleapis.com/auth/drive"])
    creds.refresh(Request())
    p = Path(path)
    meta = {"name": p.name, "parents": [os.environ["BACKUP_DRIVE_FOLDER"]]}
    import json
    files = {"metadata": ("metadata", json.dumps(meta), "application/json"),
             "file": (p.name, p.read_bytes(), "application/gzip")}
    r = httpx.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true",
                   headers={"Authorization": f"Bearer {creds.token}"}, files=files, timeout=300)
    r.raise_for_status()
    print("uploaded", r.json().get("id"))


if __name__ == "__main__":
    main(sys.argv[1])
