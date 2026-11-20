"""Две роли у одного человека (HEAD 08.11, «Оба способа»): «Я сейчас» + роль смены по объекту, ФОТ по ставке роли смены."""
import uuid

from artgame import db
from conftest import hdr
from test_files import JPEG
from test_production import VALS, Copying, team  # noqa: F401


def _shift(client, tg, zone, day, role=None):
    uid = str(uuid.uuid4())
    body = {"client_uid": uid, "object_id": 731, "zone_code": zone, "started_at": f"2026-11-{day:02d}T09:00:00+05:00", "photo_before": JPEG}
    if role:
        body["role"] = role
    s = client.post("/api/shifts/start", json=body, headers=hdr(tg)).json()
    client.post("/api/shifts/finish", json={"client_uid": uid, "ended_at": f"2026-11-{day:02d}T19:00:00+05:00", "area_m2": 5, "work_done": "Работа",
                                            "photo_after": JPEG}, headers=hdr(tg))
    return s


def test_dual_role(client, team):  # noqa: F811
    pid = client.post("/api/register", json={"full_name": "Оператор Саппорт"}, headers=hdr(6100)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "print_operator", "zones": ["print", "mural"]}, headers=hdr(1000))
    assert client.post(f"/api/people/{pid}", json={"extra_roles": ["nope"]}, headers=hdr(1000)).status_code == 400
    assert client.post(f"/api/people/{pid}", json={"extra_roles": ["support", "head", "print_operator"]}, headers=hdr(1000)).json()["extra_roles"] == ["support"]
    with db.pool.connection() as c:
        c.execute("UPDATE constants_versions SET values = values || '{\"pay.print.operator\": {\"value\": \"15000\", \"status\": \"Утверждено\", \"who\": \"head\"}}'::jsonb")
    me = client.get("/api/me", headers=hdr(6100)).json()
    assert me["role_code"] == "print_operator" and me["roles"] == ["print_operator", "support"]
    # «Я сейчас: Саппорт» — права и меню от саппорта; чужую роль сервер не даёт
    assert client.get("/api/me", headers={**hdr(6100), "X-Act-Role": "support"}).json()["role_code"] == "support"
    assert client.get("/api/me", headers={**hdr(6100), "X-Act-Role": "head"}).json()["role_code"] == "print_operator"
    assert client.get("/api/me", headers={**hdr(6100), "X-Act-Role": "artist"}).json()["role_code"] == "print_operator"
    # роль смены: по зоне объекта (роспись → саппорт, печать → оператор), либо выбранная
    assert _shift(client, 6100, "mural", 3)["role_code"] == "support"
    assert _shift(client, 6100, "print", 4)["role_code"] == "print_operator"
    assert _shift(client, 6100, "mural", 5, role="print_operator")["role_code"] == "print_operator"
    with db.pool.connection() as c:
        c.execute("UPDATE shifts SET status='approved' WHERE person_id=%s", (pid,))
    out = client.post("/api/fin/payroll/2026-11/compute", headers=hdr(1000)).json()
    row = next(r for r in out["rows"] if r["name"] == "Оператор Саппорт")
    piece = next(l for l in row["lines"] if l["kind"] == "piece")
    assert float(piece["amount"]) == 10000 + 15000 * 2 and "Саппорт 1" in piece["detail"]
    rate = client.get("/api/fin/my", headers=hdr(6100)).json()["rate"]
    assert {x["label"] for x in rate} >= {"Оператор настенного принтера · Смена 10 ч", "Саппорт · Смена 10 ч"}


def test_print_exam_rate(client, team):  # noqa: F811
    """HEAD 13.11 (Арслан): оператор после экзамена — pay.print.operator_exam с дня экзамена, саппортом — по-прежнему ставка саппорта."""
    pid = client.post("/api/register", json={"full_name": "Арслан Оператор"}, headers=hdr(6200)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "print_operator", "zones": ["print", "mural"], "extra_roles": ["support"]}, headers=hdr(1000))
    with db.pool.connection() as c:
        c.execute("""UPDATE constants_versions SET values = values || '{"pay.print.operator": {"value": "10000", "status": "Утверждено", "who": "head"},
                     "pay.print.operator_exam": {"value": "15000", "status": "Утверждено", "who": "head"}}'::jsonb""")
    assert client.post(f"/api/people/{pid}", json={"print_exam_on": "2026-11-04"}, headers=hdr(1000)).json()["print_exam_on"] == "2026-11-04"
    _shift(client, 6200, "print", 3)    # до экзамена — 10 000
    _shift(client, 6200, "print", 4)    # с дня экзамена — 15 000
    _shift(client, 6200, "mural", 5)    # саппорт — 10 000
    with db.pool.connection() as c:
        c.execute("UPDATE shifts SET status='approved' WHERE person_id=%s", (pid,))
    out = client.post("/api/fin/payroll/2026-11/compute", headers=hdr(1000)).json()
    row = next(r for r in out["rows"] if r["name"] == "Арслан Оператор")
    assert float(next(l for l in row["lines"] if l["kind"] == "piece")["amount"]) == 10000 + 15000 + 10000
    rate = {x["label"]: x["amount"] for x in client.get("/api/fin/my", headers=hdr(6200)).json()["rate"]}
    assert rate["Оператор настенного принтера · Смена 10 ч"] == 15000 and rate["Саппорт · Смена 10 ч"] == 10000, rate
    assert client.post(f"/api/people/{pid}", json={"no_print_exam": True}, headers=hdr(1000)).json()["print_exam_on"] is None


def test_exam_is_grow_item(client, team):  # noqa: F811
    """HEAD 13.11: пункт 1 пути «Оператор → Мастер» и дата экзамена в «Команде» — одно и то же."""
    pid = client.post("/api/register", json={"full_name": "Оператор Путь"}, headers=hdr(6300)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "print_operator", "zones": ["print"]}, headers=hdr(1000))
    # HEAD подтверждает пункт, который сотрудник сам не отмечал, и ставит дату
    marks = client.post("/api/grow/confirm", json={"person_id": pid, "path": "print_operator", "idx": 0, "ok": True, "exam_on": "2026-11-01"},
                        headers=hdr(1000)).json()["marks"]
    assert marks[0]["confirmed_at"]
    x = next(p for p in client.get("/api/grow/team", headers=hdr(1000)).json()["people"] if p["id"] == pid)
    assert x["print_exam_on"] == "2026-11-01"
    # снять в «Команде» — пункт тоже снимается; поставить дату в «Команде» — пункт подтверждён
    client.post(f"/api/people/{pid}", json={"no_print_exam": True}, headers=hdr(1000))
    x = next(p for p in client.get("/api/grow/team", headers=hdr(1000)).json()["people"] if p["id"] == pid)
    assert x["print_exam_on"] is None and not x["marks"][0]["confirmed_at"]
    client.post(f"/api/people/{pid}", json={"print_exam_on": "2026-11-03"}, headers=hdr(1000))
    x = next(p for p in client.get("/api/grow/team", headers=hdr(1000)).json()["people"] if p["id"] == pid)
    assert x["print_exam_on"] == "2026-11-03" and x["marks"][0]["confirmed_at"]


def test_person_hour_rate(client, team):  # noqa: F811
    """HEAD 15.11 («У Элины нужно поставить ставку 1200 в час»): личная ставка в час — смена = часы × ставка; 0 — снять."""
    pid = client.post("/api/register", json={"full_name": "Элина Почасовая"}, headers=hdr(6400)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "support", "zones": ["mural"]}, headers=hdr(1000))
    assert client.post(f"/api/people/{pid}", json={"hour_rate": 1200}, headers=hdr(1000)).json()["hour_rate"] == 1200
    assert client.post(f"/api/people/{pid}", json={"hour_rate": -5}, headers=hdr(1000)).status_code == 400
    assert next(p for p in client.get("/api/people", headers=hdr(1000)).json() if p["id"] == pid)["hour_rate"] == 1200
    _shift(client, 6400, "mural", 6)    # 10 ч
    with db.pool.connection() as c:
        c.execute("UPDATE shifts SET status='approved' WHERE person_id=%s", (pid,))
    row = next(r for r in client.post("/api/fin/payroll/2026-11/compute", headers=hdr(1000)).json()["rows"] if r["name"] == "Элина Почасовая")
    assert float(next(l for l in row["lines"] if l["kind"] == "piece")["amount"]) == 12000
    rate = {x["label"]: x["amount"] for x in client.get("/api/fin/my", headers=hdr(6400)).json()["rate"]}
    assert rate.get("Твоя ставка в час") == 1200 and not any(k.startswith("Смена ") for k in rate), rate
    assert client.post(f"/api/people/{pid}", json={"hour_rate": 0}, headers=hdr(1000)).json()["hour_rate"] is None


def test_live_shift_many_photos(client, team):  # noqa: F811
    """HEAD 16.11: «когда отчёты закидываем, можем только одну фотку прикрепить» — к обычной смене тоже, по client_uid смены."""
    s = _shift(client, 5000, "mural", 7)
    uid = s["client_uid"]
    for _ in range(2):
        r = client.post(f"/api/shifts/by-uid/{uid}/photos", json={"client_uid": str(uuid.uuid4()), "photo": JPEG}, headers=hdr(5000))
        assert r.status_code == 200, r.text
    assert r.json()["count"] == 2
    assert client.post(f"/api/shifts/by-uid/{uid}/photos", json={"client_uid": str(uuid.uuid4()), "photo": JPEG}, headers=hdr(2000)).status_code == 404
