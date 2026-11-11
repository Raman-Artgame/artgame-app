"""«Мой путь» на сервере (HEAD 11.11): сотрудник отмечает пункт, наставник своей ветки подтверждает или возвращает, HEAD видит всех."""
from conftest import hdr
from test_production import VALS, Copying, team  # noqa: F401


def test_marks_and_mentor(client, team):  # noqa: F811
    sup, lead, art = team[2000], team[3000], team[5000]
    # художник отмечает пункт 0 — ждёт наставника
    m = client.post("/api/grow/my", json={"path": "artist", "idx": 0, "on": True}, headers=hdr(5000)).json()["marks"]
    assert m[0]["idx"] == 0 and m[0]["marked_at"] and not m[0]["confirmed_at"]
    assert client.post("/api/grow/my", json={"path": "nope", "idx": 0, "on": True}, headers=hdr(5000)).status_code == 400
    # саппорт не наставник художника; сам себя не подтверждает
    assert client.post("/api/grow/confirm", json={"person_id": art, "path": "artist", "idx": 0, "ok": True}, headers=hdr(2000)).status_code == 403
    assert client.post("/api/grow/confirm", json={"person_id": art, "path": "artist", "idx": 0, "ok": True}, headers=hdr(5000)).status_code == 403
    # Главный видит саппорта и художника (не себя), подтверждает
    t = client.get("/api/grow/team", headers=hdr(3000)).json()["people"]
    assert sorted(x["id"] for x in t) == sorted([sup, art])
    assert client.post("/api/grow/confirm", json={"person_id": art, "path": "lead_artist", "idx": 0, "ok": True}, headers=hdr(3000)).status_code == 403   # путь Главных — не его ветка
    c = client.post("/api/grow/confirm", json={"person_id": art, "path": "artist", "idx": 0, "ok": True}, headers=hdr(3000)).json()["marks"]
    assert c[0]["confirmed_name"] == "P3000"
    # подтверждённое сам не снять
    assert client.post("/api/grow/my", json={"path": "artist", "idx": 0, "on": False}, headers=hdr(5000)).status_code == 400
    # возврат с комментарием: отметки нет, комментарий виден
    client.post("/api/grow/my", json={"path": "artist", "idx": 1, "on": True}, headers=hdr(5000))
    r = client.post("/api/grow/confirm", json={"person_id": art, "path": "artist", "idx": 1, "ok": False, "note": "ещё 3 смены"}, headers=hdr(3000)).json()["marks"]
    assert [(x["idx"], bool(x["marked_at"]), x["note"]) for x in r] == [(0, True, None), (1, False, "ещё 3 смены")]
    # перенос из телефона — только если на сервере пусто
    assert client.post("/api/grow/my/import", json={"path": "artist", "idx": [5]}, headers=hdr(5000)).json()["marks"][-1]["idx"] == 1
    assert [x["idx"] for x in client.post("/api/grow/my/import", json={"path": "support", "idx": [0, 2]}, headers=hdr(2000)).json()["marks"]] == [0, 2]
    # HEAD видит всех, у художника — 1 подтверждён
    h = {x["id"]: x for x in client.get("/api/grow/team", headers=hdr(1000)).json()["people"]}
    assert set(h) == {sup, lead, art} and sum(1 for x in h[art]["marks"] if x["confirmed_at"]) == 1
    # художнику «Путь команды» пуст
    assert client.get("/api/grow/team", headers=hdr(5000)).json() == {"people": []}
