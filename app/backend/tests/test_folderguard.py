"""HEAD 27.11: сторож папок — у каждой открытой сделки обеих воронок есть папка; сбой и пустой «Объект» видны HEAD и МОП."""
from artgame import bx, db, drive, folderguard
from artgame.config import settings
from artgame.sync_objects import F_OBJECT, FOLDER_FIELD
from conftest import hdr
from test_cabinets import dz  # noqa: F401


class Disk:
    def __init__(self, down=()):
        self.made, self.down, self.subs, self.nosub, self.tree = [], set(down), set(), set(), {}

    def ls(self, parent):
        return self.tree.get(parent, [])

    def child(self, parent, name):
        if parent in self.nosub:
            raise RuntimeError("Диск 500")
        self.subs.add((parent, name))
        return f"{parent}/{name}"

    def project_folder(self, obj):
        if obj["id"] in self.down:
            raise RuntimeError("Диск 503")
        self.made.append((obj["id"], obj["title"], obj.get("city")))
        return f"F{obj['id']}"


def D(i, title, obj=None, cat="0", folder=None, mop="4565"):
    return {"ID": str(i), "TITLE": title, "CATEGORY_ID": cat, "STAGE_ID": "NEW", "DATE_CREATE": "2026-11-23T09:53:36+03:00",
            "ASSIGNED_BY_ID": mop, FOLDER_FIELD: folder, F_OBJECT: obj}


def test_guard(client, dz, monkeypatch):  # noqa: F811
    ids, calls = dz
    bound = []
    monkeypatch.setattr(drive, "bind_deal", lambda conn, deal, fid: bound.append((deal, fid)) or "ok")
    monkeypatch.setattr(settings, "drive_bind", True)
    deals = [D(1601, "1601 · КИРИЛЛ", "DoctorDizel", cat="13"),            # название не сходится с объектом, воронка «Дизайн РК»
             D(1745, "1745 · ZHANAT КАРТИНА КОПИЯ — АСТАНА"),              # «Объект» пуст — папка всё равно создаётся
             D(1749, "1749 · ДЕТЕЙЛИНГ", "Детейлинг", folder="HAVE"),      # папка уже есть — Диск не трогаем
             D(1750, "1750 · СЛОМАННАЯ", "Школа")]
    disk = Disk(down={1750})
    with db.pool.connection() as c:
        r = folderguard.run(c, deals, disk)
        assert r == {"open": 4, "made": 2, "errors": 1, "subs": 3, "pulled": 0}
        # HEAD 28.11: в каждой папке сторож досоздаёт подпапки — и в той, что уже была (1749)
        assert {("F1601", "ДИЗАЙН"), ("F1745", "МЕДИА"), ("HAVE", "ДИЗАЙН"), ("HAVE/ДИЗАЙН", "Фото объекта"), ("HAVE", "ПРИХОДЫ ЧЕКИ")} <= disk.subs
        assert not any(p.startswith("F1750") for p, _ in disk.subs)
        assert disk.made == [(1601, "DoctorDizel", None), (1745, "ZHANAT КАРТИНА КОПИЯ", "АСТАНА")]
        assert bound == [(1601, "F1601"), (1745, "F1745")]
        bad = folderguard.problems(c)
        assert [(x["id"], x["no_folder"], x["no_object"], x["no_subs"]) for x in bad] == [(1750, True, False, False), (1745, False, True, False)]
        assert "Диск 503" in bad[0]["error"]
        c.commit()
        # HEAD видит в Пульте
        p = client.get("/api/head/pulse", headers=hdr(1000)).json()
        assert [x["id"] for x in p["folders"]] == [1750, 1745]
        # Диск ожил, МОП вписал объект, 1749 закрыли — всё чисто, второй папки никто не сделал
        deals[1][F_OBJECT], deals[1][FOLDER_FIELD], deals[0][FOLDER_FIELD] = "Картина", "F1745", "F1601"
        disk.down.clear()
        assert folderguard.run(c, [deals[0], deals[1], deals[3]], disk) == {"open": 3, "made": 1, "errors": 0, "subs": 1, "pulled": 0}
        assert folderguard.problems(c) == [] and len(disk.made) == 3
        assert c.execute("SELECT count(*) AS n FROM deal_folders").fetchone()["n"] == 3
        # подпапки создать не вышло — видно HEAD; сделка с заданием на дизайн идёт вне лимита
        c.execute("UPDATE deal_folders SET subs_at=NULL")
        disk.nosub = {"F1601"}
        folderguard.run(c, [deals[0], deals[1]], disk)
        assert [(x["id"], x["no_subs"]) for x in folderguard.problems(c)] == [(1601, True)]
        disk.nosub.clear()
        folderguard.run(c, [deals[0], deals[1]], disk)
        assert folderguard.problems(c) == []


def test_mop_sees_in_today(client, dz):  # noqa: F811
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"], "bitrix_user_id": 4565}, headers=hdr(1000))
    bx._cache.clear()
    with db.pool.connection() as c:
        folderguard.run(c, [D(1601, "1601 · КАФЕ — АСТАНА")], Disk(down={1601}))
    rows = [x for x in client.get("/api/bx/today", headers=hdr(6000)).json()["queue"]["today"] if x.get("action") == "folder"]
    assert len(rows) == 1 and rows[0]["id"] == 1601 and "нет папки" in rows[0]["why"]


def test_pull_design_from_drive(client, dz):  # noqa: F811
    """HEAD 28.11: эскизы и фото стен, положенные на Диск руками, видны в задании — дизайнеру на Диск ходить незачем."""
    mop = client.post("/api/register", json={"full_name": "МОП"}, headers=hdr(6000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop", "zones": ["sales"], "bitrix_user_id": 4565}, headers=hdr(1000))
    t = client.post("/api/bx/deals/1601/design-tasks", json={"title": "Холл", "deadline": "2026-12-05"}, headers=hdr(6000)).json()
    FOLDER = "application/vnd.google-apps.folder"
    disk = Disk()
    disk.tree = {"HAVE": [{"id": "DZ", "name": "Дизайн", "mimeType": FOLDER}],
                 "DZ": [{"id": "s1", "name": "эскиз 1.png", "mimeType": "image/png", "size": "100"},
                        {"id": "x1", "name": "смета.xlsx", "mimeType": "application/vnd.ms-excel"},
                        {"id": "PH", "name": "Фото объекта", "mimeType": FOLDER}],
                 "PH": [{"id": "p1", "name": "стена.jpg", "mimeType": "image/jpeg", "size": "50"}]}
    with db.pool.connection() as c:
        c.execute("DELETE FROM files WHERE object_id=1601")
        deal = D(1601, "1601 · КАФЕ — АСТАНА", "Кафе", folder="HAVE")
        assert folderguard.run(c, [deal], disk)["pulled"] == 2
        assert folderguard.run(c, [deal], disk)["pulled"] == 0          # второй раз не дублирует
        got = c.execute("SELECT kind, name FROM files WHERE object_id=1601 ORDER BY kind").fetchall()
        assert [(r["kind"], r["name"]) for r in got] == [("brief", "стена.jpg"), ("design", "эскиз 1.png")]
    row = client.get("/api/bx/deals/1601/design-tasks", headers=hdr(6000)).json()["items"][0]
    assert row["id"] == t["id"] and row["sketches"] == 1 and row["materials"] == 1
