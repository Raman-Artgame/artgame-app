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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)
