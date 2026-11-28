"""«Учёба» МОП (HEAD 28.11): учебник и тесты. Верный ответ на телефон не уходит, ответы по человеку, глава засчитывается от 80 %."""
import json
import secrets

import pytest

from artgame import places, study
from artgame.config import settings
from conftest import hdr

KEY = secrets.token_hex(32)


@pytest.fixture
def book(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "content_key", KEY)
    monkeypatch.setattr(study, "DIR", tmp_path / "_study")
    src = tmp_path / "b.json"
    src.write_text(json.dumps({"mods": [{"n": "01", "title": "Роль", "img": "img/s01.jpg", "blocks": [
        {"t": "p", "x": "Пример по константам от 02.11.2026: 3 × 17 000"}]}], "tasks": []}, ensure_ascii=False), encoding="utf-8")
    q = tmp_path / "q.py"
    q.write_text('Q = {"01": [(1, "fact", "Сколько?", ["верно", "б", "в", "г"], "потому", "m01"), '
                 '(2, "case", "Как?", ["да", "нет", "может", "никогда"], "так", "m01")]}', encoding="utf-8")
    assert study.build(src, [q], KEY, "28.11.2026") == (1, 2)
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    for tg, role in [(2300, "mop"), (2000, "artist")]:
        pid = client.post("/api/register", json={"full_name": f"P{tg}"}, headers=hdr(tg)).json()["id"]
        client.post(f"/api/people/{pid}", json={"role_code": role, "zones": ["sales" if role == "mop" else "mural"]}, headers=hdr(1000))
    return client


def test_encrypted_and_konst_date(book):
    assert "Сколько".encode() not in (study.DIR / "mop_quiz.json.enc").read_bytes()
    b = book.get("/api/study/mop", headers=hdr(2300)).json()
    assert "по константам от 28.11.2026" in b["mods"][0]["blocks"][0]["x"]
    assert b["qcount"] == {"01": 2} and b["levels"][1] == "VIP МОП"
    assert book.get("/api/study/mop", headers=hdr(2000)).status_code == 403


def test_round_answer_progress(book):
    r = book.get("/api/study/mop/round?ch=01", headers=hdr(2300)).json()["q"]
    assert len(r) == 2 and r[0]["lvl"] == 1
    assert all("верно" not in json.dumps(o) or "k" in o for q in r for o in q["opts"])
    assert "why" not in r[0] and "a" not in r[0]
    q = r[0]
    wrong = next(o["k"] for o in q["opts"] if o["t"] != "верно")
    a = book.post("/api/study/mop/answer", json={"qid": q["id"], "k": wrong}, headers=hdr(2300)).json()
    assert a["ok"] is False and a["why"] == "потому"
    right = next(o["k"] for o in q["opts"] if o["t"] == "верно")
    assert a["right"] == right
    assert book.post("/api/study/mop/answer", json={"qid": q["id"], "k": right}, headers=hdr(2300)).json()["ok"] is True
    # ключи вариантов у каждого свои: чужой ключ не подходит
    assert book.post("/api/study/mop/answer", json={"qid": q["id"], "k": "0000000000"}, headers=hdr(2300)).status_code == 400
    me = book.get("/api/study/mop/me", headers=hdr(2300)).json()
    assert me["chapters"]["01"]["ok"] == 1 and not me["chapters"]["01"]["passed"] and me["points"] == 10
    q2 = r[1]
    k2 = next(o["k"] for o in q2["opts"] if o["t"] == "да")
    book.post("/api/study/mop/answer", json={"qid": q2["id"], "k": k2}, headers=hdr(2300))
    me = book.get("/api/study/mop/me", headers=hdr(2300)).json()
    assert me["chapters"]["01"]["passed"] and me["points"] == 30
    book.post("/api/study/mop/read", json={"ch": "01"}, headers=hdr(2300))
    t = book.get("/api/study/mop/team", headers=hdr(1000)).json()
    assert t["people"][0]["read"] == 1 and t["people"][0]["ok"] == 2
    assert book.get("/api/study/mop/team", headers=hdr(2300)).status_code == 403
