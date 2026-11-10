"""Раскладка чеков (HEAD 08.11): сделка → «Расходы чеки» в папке сделки; без сделки → 10 ФИНАНСЫ / Расходы чеки / отдел / год / месяц."""
from datetime import datetime

from artgame import drive


class FakeDrive:
    def __init__(self):
        self.made, self.up = [], []

    def child(self, parent, name):
        self.made.append((parent, name))
        return f"{parent}/{name}"

    def project_folder(self, obj):
        return f"deal{obj['id']}"

    def upload(self, parent, name, data, mime):
        self.up.append((parent, name))
        return "file1"


class Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, args):
        row = self.rows.get(args[0]) if sql.startswith("SELECT") else None
        return type("R", (), {"fetchone": lambda s: row})()


def test_receipt_folders(monkeypatch):
    d = FakeDrive()
    monkeypatch.setattr(drive, "Drive", lambda: d)
    monkeypatch.setattr(drive, "RECEIPTS_ROOT_ID", "FIN")
    now = datetime.now()
    month = f"{now.year}/{now.month:02d} {drive.MONTHS[now.month - 1]}"
    conn = Conn({1347: {"id": 1347, "title": "ТЦ", "city": None, "drive_folder": "deal1347",
                        "folders": {"photo": "p", "design": "d", "receipt": "deal1347/Расходы чеки", "doc": "x"}}})
    jpg = "data:image/jpeg;base64,/9j/AA=="
    drive.save_receipt(conn, "sales", "Чек A", jpg, deal_id=1347)
    assert d.up[-1] == ("deal1347/РАСХОДЫ ЧЕКИ", "Чек A.jpg")   # старые ID без версии — найдены заново по утверждённым именам
    drive.save_receipt(conn, "sales", "Чек B", jpg, deal_id=999)          # у сделки нет папки → отдел, № в имени
    assert d.up[-1] == (f"FIN/01 Продажи/{month}", "Чек B сделка 999.jpg")
    drive.save_receipt(conn, "print", "Чек C", jpg)
    assert d.up[-1][0] == f"FIN/03 Печать/{month}"
    drive.save_receipt(conn, "office", "Чек D", jpg, deal_id=None)
    assert d.up[-1][0] == f"FIN/06 РАСХОДЫ HEAD/{month}"
    monkeypatch.setattr(drive, "RECEIPTS_ROOT_ID", "")
    try:
        drive.save_receipt(conn, "office", "Чек E", jpg)
        raise AssertionError("без папки чек не должен уходить в 02 ПРОЕКТЫ")
    except RuntimeError:
        pass



def test_child_prefers_approved_name():
    """HEAD 10.11: рядом лежат «ДИЗАЙН» и дубль «Дизайн» — приложение берёт утверждённое имя буква в букву."""
    d = object.__new__(drive.Drive)
    d.ls = lambda parent: [{"id": "dup", "name": "Дизайн", "mimeType": drive.FOLDER}, {"id": "ok", "name": "ДИЗАЙН", "mimeType": drive.FOLDER}]
    assert d.child("root", "ДИЗАЙН") == "ok"
