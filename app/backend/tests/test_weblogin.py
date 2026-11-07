"""Вход с компьютера (HEAD 06.11): код от бота → сессия; чужим и заблокированным — нет."""
import re

from artgame import notify
from conftest import hdr


def setup(c, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "SEND", lambda tg, text: sent.append((tg, text)))
    c.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    pid = c.post("/api/register", json={"full_name": "Ануар", "phone": "+7 (701) 111-22-33"}, headers=hdr(6000, username="anuar_mop")).json()["id"]
    c.post(f"/api/people/{pid}", json={"role_code": "mop", "status": "active", "zones": ["sales"]}, headers=hdr(1000))
    sent.clear()
    return sent, pid


def code_of(sent):
    return re.search(r"\d{6}", sent[-1][1]).group()


def test_login_by_phone(client, monkeypatch):
    sent, pid = setup(client, monkeypatch)
    r = client.post("/api/login/code", json={"who": "8 701 111 22 33"}).json()
    assert r["ok"] and sent and sent[-1][0] == 6000
    assert client.post("/api/login/verify", json={"who": "87011112233", "code": "000000" if code_of(sent) != "000000" else "111111"}).status_code == 400
    tok = client.post("/api/login/verify", json={"who": "+77011112233", "code": code_of(sent)}).json()["token"]
    auth = {"Authorization": f"Bearer {tok}"}
    me = client.get("/api/me", headers=auth).json()
    assert me["id"] == pid and me["role_code"] == "mop"
    assert client.post("/api/login/verify", json={"who": "+77011112233", "code": code_of(sent)}).status_code == 400   # код одноразовый
    assert client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    client.post("/api/logout", headers=auth)
    assert client.get("/api/me", headers=auth).status_code == 401


def test_login_by_username_and_limits(client, monkeypatch):
    sent, pid = setup(client, monkeypatch)
    client.post("/api/login/code", json={"who": "@Anuar_MOP"})
    assert len(sent) == 1
    client.post("/api/login/code", json={"who": "@anuar_mop"})   # повтор раньше минуты — нового кода нет
    assert len(sent) == 1
    good = code_of(sent)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        client.post("/api/login/verify", json={"who": "@anuar_mop", "code": bad})
    assert client.post("/api/login/verify", json={"who": "@anuar_mop", "code": good}).status_code == 400   # 5 ошибок — код сгорел
    # незнакомый — тот же ответ, без письма
    r = client.post("/api/login/code", json={"who": "+7 777 000 00 00"})
    assert r.status_code == 200 and len(sent) == 1
    # заблокированный не входит
    client.post(f"/api/people/{pid}", json={"status": "blocked"}, headers=hdr(1000))
    client.post("/api/login/code", json={"who": "@anuar_mop"})
    assert len(sent) == 1
