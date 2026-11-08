"""«Написать обращение» (HEAD 08.11): сотрудник пишет — HEAD видит в «Пульте», отвечает, человек видит ответ."""
from conftest import hdr
from test_production import VALS, Copying, team  # noqa: F401


def test_feedback(client, team):  # noqa: F811
    r = client.post("/api/feedback", json={"kind": "bug", "text": "Не грузится фото", "place": "Смена"}, headers=hdr(2000)).json()
    assert r["status"] == "new" and r["role_code"] == "support"
    assert client.post("/api/feedback", json={"kind": "nope", "text": "x x x"}, headers=hdr(2000)).status_code == 422
    assert client.get("/api/feedback", headers=hdr(2000)).status_code == 403                   # чужие — только HEAD
    pulse = client.get("/api/head/pulse", headers=hdr(1000)).json()
    assert [f["text"] for f in pulse["feedback"]] == ["Не грузится фото"]
    assert client.post(f"/api/feedback/{r['id']}", json={"status": "done"}, headers=hdr(3000)).status_code == 403
    a = client.post(f"/api/feedback/{r['id']}", json={"status": "done", "answer": "Починили"}, headers=hdr(1000)).json()
    assert a["status"] == "done" and a["answer"] == "Починили"
    my = client.get("/api/feedback/my", headers=hdr(2000)).json()["items"]
    assert my[0]["answer"] == "Починили" and client.get("/api/feedback/my", headers=hdr(3000)).json()["items"] == []
    assert client.get("/api/head/pulse", headers=hdr(1000)).json()["feedback"] == []
