"""22.11 (робот DRIVE01 встал на сделке 1709): папку сделки, которую сделало приложение, помечаем меткой робота
в appProperties; под флагом ARTGAME_DRIVE_BIND — сразу пишем в сделку (ID и ссылка). Без базы и сети: Диск и Битрикс подменены."""
import httpx

from artgame import bxw, db, drive
from artgame.config import settings


class Conn:
    def __init__(self):
        self.sql = []

    def execute(self, sql, args=None):
        self.sql.append((sql, args))


def fake_bitrix(monkeypatch, deal):
    calls = []

    def call(method, params):
        calls.append((method, params))
        if method == "crm.deal.update":
            deal.update(params["fields"])
            return {"result": True}
        return {"result": dict(deal)}
    monkeypatch.setattr(settings, "bitrix_webhook", "https://example.invalid/rest/1/x/")
    monkeypatch.setattr(settings, "drive_bind", True)
    monkeypatch.setattr(bxw, "CALL", call)
    audits = []
    monkeypatch.setattr(db, "audit", lambda conn, *a: audits.append(a))
    return calls, audits


class FakeDrive:
    def project_folder(self, obj):
        return "F1"

    def child(self, parent, name):
        return parent + "/" + name


def test_new_folder_written_to_deal(monkeypatch):
    deal = {"ID": "1709", drive.F_FOLDER: None, drive.F_FOLDER_URL: None}
    calls, audits = fake_bitrix(monkeypatch, deal)
    conn = Conn()
    drive.ensure_folders(conn, {"id": 1709, "drive_folder": None, "folders": {}}, FakeDrive())
    assert deal[drive.F_FOLDER] == "F1" and deal[drive.F_FOLDER_URL] == "https://drive.google.com/drive/folders/F1"
    assert [m for m, _ in calls] == ["crm.deal.get", "crm.deal.update", "crm.deal.get"]   # запись сверена чтением
    assert audits[0][4]["bx"] == "ok"
    assert conn.sql[-1][1][0] == "F1"


def test_folder_already_in_deal_not_touched(monkeypatch):
    deal = {"ID": "1709", drive.F_FOLDER: "OTHER"}
    calls, _ = fake_bitrix(monkeypatch, deal)
    drive.ensure_folders(Conn(), {"id": 1709, "drive_folder": None, "folders": {}}, FakeDrive())
    assert [m for m, _ in calls] == ["crm.deal.get"] and deal[drive.F_FOLDER] == "OTHER"
    # папка уже известна приложению — Битрикс не спрашиваем
    calls.clear()
    drive.ensure_folders(Conn(), {"id": 1709, "drive_folder": "F1", "folders": {}}, FakeDrive())
    assert calls == []


def test_bitrix_error_does_not_break_upload(monkeypatch):
    _, audits = fake_bitrix(monkeypatch, {})

    def down(method, params):
        raise RuntimeError("Битрикс 503")
    monkeypatch.setattr(bxw, "CALL", down)
    folders = drive.ensure_folders(Conn(), {"id": 1709, "drive_folder": None, "folders": {}}, FakeDrive())
    assert folders["design"] == "F1/ДИЗАЙН" and audits[0][4]["bx"] == "error"


def test_bitrix_off(monkeypatch):
    monkeypatch.setattr(settings, "bitrix_webhook", "")
    assert drive.bind_deal(Conn(), 1709, "F1") == "off"


def test_flag_off_no_bitrix_call(monkeypatch):
    """ARTGAME_DRIVE_BIND не включён (по умолчанию): в Битрикс не пишем и не читаем, папка создаётся как обычно."""
    deal = {"ID": "1709", drive.F_FOLDER: None}
    calls, audits = fake_bitrix(monkeypatch, deal)
    monkeypatch.setattr(settings, "drive_bind", False)
    folders = drive.ensure_folders(Conn(), {"id": 1709, "drive_folder": None, "folders": {}}, FakeDrive())
    assert calls == [] and audits == [] and deal[drive.F_FOLDER] is None and folders["design"] == "F1/ДИЗАЙН"
    assert drive.settings.__class__().drive_bind is False      # по умолчанию выключено


def test_created_project_folder_marked_for_drive01(monkeypatch):
    posted = []
    d = object.__new__(drive.Drive)
    d.h = {}
    monkeypatch.setattr(drive, "_CHILD", {})
    monkeypatch.setattr(d, "find", lambda q: [])
    monkeypatch.setattr(d, "ls", lambda parent: [{"id": "Y", "name": "2026", "mimeType": drive.FOLDER}] if parent == drive.PROJECTS_ROOT_ID else [])

    def post(url, **kw):
        posted.append(kw["json"])
        return httpx.Response(200, json={"id": "N%d" % len(posted)}, request=httpx.Request("POST", url))
    monkeypatch.setattr(drive.httpx, "post", post)
    fid = d.project_folder({"id": 1709, "title": "Белый ветер", "city": "Астана"})
    month, project = posted
    assert "appProperties" not in month                      # год/месяц — без метки
    assert project["name"] == "1709 · БЕЛЫЙ ВЕТЕР — АСТАНА" and fid == "N2"
    assert project["appProperties"] == {"managedBy": "DRIVE01", "dealId": "1709", "homeParentId": "N1", "year": project["appProperties"]["year"]}
