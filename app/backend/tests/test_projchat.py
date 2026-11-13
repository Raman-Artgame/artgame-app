"""Чат проекта (HEAD 13.11): сам у проекта на «Выполнении»; видят кто на объекте, ГИП, МОП и все HEAD; бот молчит."""
from conftest import hdr
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401

from artgame import db, dm


def test_project_chat(client, team, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(dm, "SEND", lambda tg, text: sent.append((tg, text)))
    mop = client.post("/api/register", json={"full_name": "МОП Анна"}, headers=hdr(7000)).json()["id"]
    client.post(f"/api/people/{mop}", json={"role_code": "mop"}, headers=hdr(1000))
    with db.pool.connection() as c:
        c.execute("UPDATE people SET bitrix_user_id=77 WHERE id=%s", (mop,))
        c.execute("UPDATE objects SET mop_bx_id=77 WHERE id=731")
        c.execute("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (900, 'Старый', 'Астана', 'WON')")
    # художник ещё не на объекте — чата не видит
    assert client.get("/api/pchat/list", headers=hdr(5000)).json()["chats"] == []
    assert client.get("/api/pchat/731", headers=hdr(5000)).status_code == 404
    assert client.post("/api/objects/731/crew", json={"person_id": team[5000]}, headers=hdr(1000)).status_code == 200
    # HEAD и МОП видят сразу, без кнопки «создать»; закрытый без сообщений — нет
    assert [x["id"] for x in client.get("/api/pchat/list", headers=hdr(1000)).json()["chats"]] == [731]
    assert [x["id"] for x in client.get("/api/pchat/list", headers=hdr(7000)).json()["chats"]] == [731]
    client.post("/api/pchat/731", json={"text": "Завтра грунт, в 9 на объекте"}, headers=hdr(7000))
    # непрочитанное — на вкладке «Чат»
    assert client.get("/api/dm/unread", headers=hdr(5000)).json() == {"n": 1}
    assert client.get("/api/dm/list", headers=hdr(5000)).json()["projects"][0]["unread"] == 1
    r = client.post("/api/pchat/731", json={"photo": JPEG}, headers=hdr(5000))
    assert r.status_code == 200
    d = client.get("/api/pchat/731", headers=hdr(1000)).json()
    assert [(x["name"], x["text"], bool(x["photo"])) for x in d["items"]] == [("МОП Анна", "Завтра грунт, в 9 на объекте", False), ("P5000", None, True)]
    assert {m["full_name"]: m["why"] for m in d["members"]} == {"HEAD": "head", "P5000": "crew", "МОП Анна": "mop"}
    assert client.get("/api/dm/unread", headers=hdr(5000)).json() == {"n": 0}   # ответил — прочитал
    assert client.get("/api/dm/unread", headers=hdr(7000)).json() == {"n": 1}   # МОП видит фото как новое
    # поддержка (не на объекте) не видит
    assert client.get("/api/pchat/731", headers=hdr(2000)).status_code == 404
    # сняли с объекта — выпал; сделка ушла дальше — только чтение
    client.post("/api/objects/731/crew", json={"person_id": team[5000], "on": False}, headers=hdr(1000))
    assert client.get("/api/pchat/731", headers=hdr(5000)).status_code == 404
    with db.pool.connection() as c:
        c.execute("UPDATE objects SET bitrix_stage='WON' WHERE id=731")
    assert client.get("/api/pchat/list", headers=hdr(1000)).json()["chats"][0]["open"] is False
    assert client.post("/api/pchat/731", json={"text": "x"}, headers=hdr(1000)).status_code == 409
    assert [t for t in sent if "Завтра" in t[1] or "фото" in t[1]] == []   # бот о чате молчит
