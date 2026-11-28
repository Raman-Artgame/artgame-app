"""HEAD 26.11 «отдел HR»: анкета кандидата без входа → фото и резюме на Диск → «Кандидаты» у HEAD → строка в базе кандидатов,
«Принять» → строка в «Сотрудниках» и роль при входе с тем же телефоном."""
from artgame import db, drive, hr, hr_sheets
from conftest import hdr

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
PDF = "data:application/pdf;base64,JVBERi0xLjQK"


class FakeDrive:
    up: list = []

    def child(self, parent, name):
        return f"{parent}/{name}"

    def upload(self, parent, name, data, mime):
        FakeDrive.up.append((parent, name, mime))
        return f"drv-{len(FakeDrive.up)}"


ANS = {"full_name": "Садыкова Айгерим", "phone": "+7 777 123-45-67", "city": "Астана", "birth": "03.05.2000", "years": "3–5 лет", "m2": "10–20 м²", "lead": "да, бригада из 4", "schedule": "Полный день", "income": "300 000",
       "style": ["Реализм", "Орнамент, этно", "Поп-арт", "Минимализм"], "style_other": "гризайль", "theme": ["Детская", "Марсиане"],
       "paints": ["Фасадная"], "junk": "x", "resume_text": "Расписала 3 кафе"}


def test_candidate_path(client, monkeypatch):
    FakeDrive.up = []
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    rows, staff = {}, []
    monkeypatch.setattr(hr_sheets, "find_prior", lambda ph: {"sheet": "Художники", "status": "Резерв", "contact": "окт 2026"})
    monkeypatch.setattr(hr_sheets, "base_upsert", lambda sheet, c, lvl, url: rows.__setitem__(c["phone"], (sheet, hr_sheets.status_of(c), lvl, url)) or 5)
    monkeypatch.setattr(hr_sheets, "staff_append", lambda c, title, sup: staff.append((c["full_name"], title, sup)) or 60)
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))

    # анкета открыта без входа; ставок в ней нет (HEAD 26.11: «не выкатывать все наши условия»)
    f = client.get("/api/hr/form/art").json()
    assert "{start}" not in str(f) and "Все начинают с Саппорта, даже опытные" in str(f)   # ставки ещё нет — без цифры
    with db.pool.connection() as c:
        c.execute("""INSERT INTO constants_versions (values, checksum) VALUES (%s, 'h0')""",
                  ('{"pay.support.shift": {"value": "10 000", "status": "Утверждено"}, "pay.artist.shift": {"value": "15 000", "status": "Утверждено"}}',))
    f = client.get("/api/hr/form/art").json()
    assert "Все начинают с Саппорта, даже опытные: 10 000 ₸ за смену 10 ч" in str(f) and "15 000" not in str(f)
    for d in ("print", "mop", "design", "video"):
        assert client.get(f"/api/hr/form/{d}").status_code == 200
    assert f["title"][0] == "Художник по росписи" and len(f["steps"]) == 8 and "levels" not in f
    assert f["steps"][1]["intro"][0][1][0].startswith("Все начинают с Саппорта")
    assert f["steps"][-1]["title"][0] == "Ожидания" and "если по итогам берём" in str(f["steps"][1]["intro"])
    assert client.get("/api/hr/form/nope").status_code == 404

    bad = client.post("/api/hr/apply", json={"dir": "art", "answers": {**ANS, "phone": "12"}})
    assert bad.status_code == 422
    r = client.post("/api/hr/apply", json={"dir": "art", "answers": ANS, "src": "instagram"}).json()
    tok = r["token"]
    assert not r["again"]
    # фото и резюме — в папку кандидата латиницей
    assert client.post(f"/api/hr/c/{tok}/file", json={"kind": "photo", "data": PNG}).json()["n"] == 1
    assert client.post(f"/api/hr/c/{tok}/file", json={"kind": "resume", "data": PDF}).json()["n"] == 1
    assert client.post(f"/api/hr/c/{tok}/file", json={"kind": "resume", "data": "data:text/html;base64,PGI+"}).status_code == 400
    assert FakeDrive.up[0][0].endswith("/Kandidaty/" + FakeDrive.up[0][0].split("/Kandidaty/")[1])
    assert "sadykova-aygerim-87771234567" in FakeDrive.up[0][0] and FakeDrive.up[0][1] == "foto-01.png"
    assert FakeDrive.up[1][1] == "rezyume-sadykova-aygerim.pdf"
    assert client.post(f"/api/hr/c/{tok}/done").json()["ok"]
    m = client.get(f"/api/hr/c/{tok}").json()
    assert {k: m[k] for k in ("dir", "done", "files")} == {"dir": "art", "done": True, "files": {"photo": 1, "resume": 1}}
    assert len(m["photos"]) == 1 and m["photos"][0]["thumb"].startswith("/api/hr/files/")
    # HEAD 27.11: кандидат убирает лишнее фото — из анкеты пропадает, на Диске переезжает в «udaleno»; номер не повторяется
    moved = []
    monkeypatch.setattr(FakeDrive, "move", lambda self, fid, parent, name=None: moved.append((fid, parent)), raising=False)
    extra = client.post(f"/api/hr/c/{tok}/file", json={"kind": "photo", "data": PNG}).json()
    assert extra["n"] == 2 and FakeDrive.up[-1][1] == "foto-02.png"
    assert client.delete(f"/api/hr/c/{tok}/file/{extra['id']}").json()["ok"]
    assert moved and moved[0][1].endswith("/udaleno") and client.get(f"/api/hr/c/{tok}").json()["files"]["photo"] == 1
    assert client.delete(f"/api/hr/c/{tok}/file/{extra['id']}").status_code == 404
    assert client.delete(f"/api/hr/c/{'x' * 20}/file/{extra['id']}").status_code == 404
    assert rows["87771234567"][:3] == ("Художники", "Пригласить", "Художник")

    # заполнил второй раз, пока ведём, — та же карточка
    assert client.post("/api/hr/apply", json={"dir": "art", "answers": ANS}).json() == {"token": tok, "again": True}

    # HEAD: доска; чужим не видно
    assert client.get("/api/hr/candidates", headers=hdr(5555)).status_code == 403
    b = client.get("/api/hr/candidates", headers=hdr(1000)).json()
    assert b["new"] == 1 and len(b["items"]) == 1
    it = b["items"][0]
    assert it["phone"] == "87771234567" and it["prior"]["status"] == "Резерв" and it["thumb"].startswith("/api/hr/files/")
    cid = it["id"]
    cd = client.get(f"/api/hr/candidates/{cid}", headers=hdr(1000)).json()
    a = cd["answers"]
    assert a["style"] == ["Реализм", "Орнамент, этно", "Поп-арт"] and a["style_other"] == "гризайль"
    assert a["theme"] == ["Детская"] and "junk" not in a and a["resume_text"] == "Расписала 3 кафе"
    assert cd["hint"]["code"] == "artist" and cd["hint"]["score"] == 7 and "руководил людьми" in cd["hint"]["why"]
    assert cd["roles"][0] == ["support", "Саппорт"] and a["schedule"] == "Полный день"
    assert len(cd["files"]) == 2 and cd["files"][1]["url"].startswith("https://drive.google.com/file/d/")

    # шаги: звёзды и заметка, резерв без причины нельзя
    r = client.post(f"/api/hr/candidates/{cid}", json={"stage": "interview", "stars": 4, "note": "сильная в шрифтах"}, headers=hdr(1000)).json()
    assert r["stage"] == "interview" and r["stars"] == 4
    assert client.post(f"/api/hr/candidates/{cid}", json={"stage": "reserve"}, headers=hdr(1000)).status_code == 400
    assert client.post(f"/api/hr/candidates/{cid}", json={"stage": "hired", "hired_role": "head"}, headers=hdr(1000)).status_code == 400
    with db.pool.connection() as c:
        c.execute("""INSERT INTO constants_versions (values, checksum) VALUES (%s, 'h1')""",
                  ('{"pay.support.shift": {"value": "10 000", "status": "Утверждено"}}',))
    client.post(f"/api/hr/candidates/{cid}", json={"stage": "trial", "trial_on": "2026-11-28"}, headers=hdr(1000))
    r = client.post(f"/api/hr/candidates/{cid}", json={"stage": "hired"}, headers=hdr(1000)).json()
    assert r["stage"] == "hired" and r["hired_role"] == "support"
    assert rows["87771234567"][1] == "В команде" and staff == [("Садыкова Айгерим", "Саппорт", True)]

    # входит в приложение с тем же телефоном — роль и зона уже стоят, HEAD не ждёт
    me = client.post("/api/register", json={"full_name": "Айгерим Садыкова", "phone": "8 (777) 123 45 67"}, headers=hdr(7777)).json()
    me = client.get("/api/me", headers=hdr(7777)).json()
    assert me["role_code"] == "support" and me["status"] == "active" and "mural" in me["zones"]
    assert client.get(f"/api/hr/candidates/{cid}", headers=hdr(1000)).json()["person_id"] == me["id"]
    # пробная смена — в ФОТ только потому, что приняли (HEAD 26.11)
    with db.pool.connection() as c:
        acc = c.execute("SELECT a.amount, a.detail FROM fin_accruals a JOIN fin_payees f ON f.id=a.payee_id WHERE f.person_id=%s", (me["id"],)).fetchall()
    assert len(acc) == 1 and float(acc[0]["amount"]) == 10000 and "Пробная смена 28.11" in acc[0]["detail"]
    assert client.get(f"/api/hr/candidates/{cid}", headers=hdr(1000)).json()["trial_paid"]
    # чужой телефон — как раньше, ждёт роль
    client.post("/api/register", json={"full_name": "Кто-то", "phone": "87000000000"}, headers=hdr(7778))
    assert client.get("/api/me", headers=hdr(7778)).json()["status"] == "pending"
    p = client.get("/api/head/pulse", headers=hdr(1000)).json()
    assert p["hr"] == {"new": 0, "waiting": 0}

    # знакомство (HEAD 26.11): принятый сначала читает правила роли и ТБ и принимает соглашение — до этого смены закрыты
    assert me["onboard"] == ["duties", "safety", "nda"]
    import pytest
    from fastapi import HTTPException
    from artgame import onboard, work
    with db.pool.connection() as c, pytest.raises(HTTPException) as ex:
        work.check_zone(c, me, "mural", 1)
    assert ex.value.status_code == 403 and "знакомство" in ex.value.detail
    ob = client.get("/api/onboard", headers=hdr(7777)).json()
    assert ob["required"] and [s["doc"] for s in ob["steps"]] == ["duties", "safety", "nda"] and ob["nda"]["draft"]
    assert client.post("/api/onboard/ack", json={"doc": "duties", "version": "app", "sha256": "abcd1234ef"}, headers=hdr(7777)).json()["pending"] == ["safety", "nda"]
    client.post("/api/onboard/ack", json={"doc": "safety", "version": "app", "sha256": "abcd1234ef"}, headers=hdr(7777))
    nda = {"doc": "nda", "version": ob["nda"]["version"], "sha256": ob["nda"]["sha256"], "full_name": "Садыкова Айгерим Маратовна", "agree": True}
    assert client.post("/api/onboard/ack", json={**nda, "sha256": "old-version-sha"}, headers=hdr(7777)).status_code == 409
    assert client.post("/api/onboard/ack", json={**nda, "agree": False}, headers=hdr(7777)).status_code == 400
    assert client.post("/api/onboard/ack", json=nda, headers=hdr(7777)).json()["pending"] == []
    assert client.get("/api/me", headers=hdr(7777)).json()["onboard"] == []
    with db.pool.connection() as c:
        row = c.execute("SELECT * FROM onboard_acks WHERE person_id=%s AND doc='nda'", (me["id"],)).fetchone()
    assert row["full_name"] == "Садыкова Айгерим Маратовна" and row["sha256"] == onboard.NDA_SHA and row["phone"]
    cd = client.get(f"/api/hr/candidates/{cid}", headers=hdr(1000)).json()["onboard"]
    assert cd["done"] and all(s["done"] for s in cd["steps"])
    # новая версия соглашения — принять заново; старые сотрудники без «отправить на ознакомление» не трогаем
    monkeypatch.setattr(onboard, "NDA_SHA", "v2sha")
    assert client.get("/api/me", headers=hdr(7777)).json()["onboard"] == ["nda"]
    with db.pool.connection() as c:
        c.execute("UPDATE people SET status='active', role_code='artist' WHERE tg_id=7778")
    assert client.get("/api/me", headers=hdr(7778)).json()["onboard"] == []
    pid = client.get("/api/me", headers=hdr(7778)).json()["id"]
    assert client.post(f"/api/onboard/send/{pid}", headers=hdr(7777)).status_code == 403
    assert client.post(f"/api/onboard/send/{pid}", headers=hdr(1000)).json()["ok"]
    assert client.get("/api/me", headers=hdr(7778)).json()["onboard"] == ["duties", "safety", "nda"]


def test_rejected_status_and_latin():
    assert hr.latin("Шынәсіл Әділет") == "shynasil-adilet"
    assert hr_sheets.phone("+7 (777) 123-45-67") == hr_sheets.phone("7771234567") == "87771234567"
    assert hr_sheets.status_of({"stage": "rejected", "self_refused": True}) == "Не актуален"
    assert hr_sheets.status_of({"stage": "rejected", "self_refused": False}) == "Не приглашать"


def test_delete_test_candidate(client, monkeypatch):
    """HEAD 28.11 «просто удали»: тестовая анкета — из приложения, строка базы очищается, папка — в корзину."""
    monkeypatch.setattr(drive, "Drive", FakeDrive)
    trashed, cleared = [], []
    monkeypatch.setattr(FakeDrive, "trash", lambda self, fid: trashed.append(fid), raising=False)
    monkeypatch.setattr(hr_sheets, "find_prior", lambda ph: None)
    monkeypatch.setattr(hr_sheets, "base_upsert", lambda sheet, c, lvl, url: 7)
    monkeypatch.setattr(hr_sheets, "base_clear", lambda sheet, ph: cleared.append((sheet, ph)) or 7)
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    tok = client.post("/api/hr/apply", json={"dir": "art", "answers": {**ANS, "full_name": "Данила", "phone": "89774100011"}}).json()["token"]
    client.post(f"/api/hr/c/{tok}/file", json={"kind": "photo", "data": PNG})
    client.post(f"/api/hr/c/{tok}/done")
    cid = client.get("/api/hr/candidates", headers=hdr(1000)).json()["items"][0]["id"]
    assert client.delete(f"/api/hr/candidates/{cid}", headers=hdr(5555)).status_code == 403
    assert client.delete(f"/api/hr/candidates/{cid}", headers=hdr(1000)).json() == {"ok": True, "left": []}
    assert client.get("/api/hr/candidates", headers=hdr(1000)).json()["items"] == []
    assert cleared == [("Художники", "89774100011")] and trashed and client.get(f"/api/hr/c/{tok}").status_code == 404
    with db.pool.connection() as c:
        assert c.execute("SELECT count(*) AS n FROM candidate_files").fetchone()["n"] == 0
