"""HEAD 09.11: команда объекта, «Мои выплаты» онлайн, просмотр и скачивание файлов, вкладка «Видео»."""
from conftest import hdr
from test_dual_role import _shift
from test_files import JPEG  # noqa: F401
from test_production import VALS, Copying, team  # noqa: F401

from artgame import db, files


def test_crew(client, team):  # noqa: F811
    sup, lead, art = team[2000], team[3000], team[5000]
    assert client.post("/api/objects/731/crew", json={"person_id": sup}, headers=hdr(5000)).status_code == 403   # художник не ставит
    # HEAD 14.11: ставит только куратор ГИП объекта (и HEAD) — Главный, пока не ГИП этого объекта, не ставит
    assert client.get("/api/objects/731/crew", headers=hdr(3000)).json()["can_edit"] is False
    assert client.post("/api/objects/731/crew", json={"person_id": sup}, headers=hdr(3000)).status_code == 403
    with db.pool.connection() as c:
        c.execute("UPDATE objects SET gip_person_id=%s WHERE id=731", (lead,))
    d = client.get("/api/objects/731/crew", headers=hdr(3000)).json()
    assert d["can_edit"] and {c["id"] for c in d["candidates"]} >= {sup, art}
    assert client.get("/api/objects/731/crew", headers=hdr(5000)).json()["can_edit"] is False
    r = client.post("/api/objects/731/crew", json={"person_id": sup}, headers=hdr(3000)).json()   # куратор ГИП ставит саппорта
    assert [c["id"] for c in r["crew"]] == [sup]
    objs = client.get("/api/work/dict", headers=hdr(2000)).json()["objects"]
    assert objs[0]["id"] == 731 and objs[0]["mine"]
    assert not client.get("/api/work/dict", headers=hdr(5000)).json()["objects"][0].get("mine")
    client.post("/api/objects/731/crew", json={"person_id": sup, "on": False}, headers=hdr(1000))
    assert client.get("/api/objects/731/crew", headers=hdr(5000)).json()["crew"] == []
    assert lead


def test_my_pay_live(client, team):  # noqa: F811
    s = _shift(client, 2000, "mural", 3)
    assert client.get("/api/fin/my?ym=2026-11", headers=hdr(2000)).json()["accrued"] == 0   # на проверке — ещё не начислено
    client.post(f"/api/shift/{s['id']}/review", json={"approve": True}, headers=hdr(1000))
    my = client.get("/api/fin/my?ym=2026-11", headers=hdr(2000)).json()
    assert my["live"] and my["accrued"] == VALS["pay.support.shift"]   # сразу, без расчёта ФОТ HEAD
    with db.pool.connection() as c:   # онлайн-расчёт ничего не пишет
        assert c.execute("SELECT count(*) AS n FROM fin_accruals").fetchone()["n"] == 0


def test_range_and_download(client, team):  # noqa: F811
    assert files._range("bytes=0-9", 100) == (0, 9) and files._range("bytes=90-", 100) == (90, 99)
    assert files._range("bytes=-10", 100) == (90, 99) and files._range("bytes=200-", 100) is None and files._range("x", 100) is None
    f = client.post("/api/objects/731/photos", json={"client_uid": "00000000-0000-0000-0000-00000000a001", "data": JPEG}, headers=hdr(2000)).json()
    dl = client.get(f["url"] + "&dl=1")
    assert dl.status_code == 200 and dl.headers["content-disposition"].startswith("attachment") and "filename*=UTF-8''" in dl.headers["content-disposition"]
    full = client.get(f["url"])
    assert full.headers["content-disposition"].startswith("inline") and full.headers["accept-ranges"] == "bytes"
    part = client.get(f["url"], headers={"Range": "bytes=0-9"})   # видео на iPhone играет только так
    assert part.status_code == 206 and part.content == full.content[:10] and part.headers["content-range"].endswith(f"/{len(full.content)}")
    assert client.get("/api/media?scope=object&type=video&object_id=731", headers=hdr(5000)).json()["items"] == []
