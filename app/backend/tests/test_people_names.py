"""HEAD 27.11: имена сотрудников — «Имя Фамилия» и никнейм; HEAD правит в «Команде», странные имена подсвечены."""
from conftest import hdr


def test_names_format_and_nickname(client):
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    pid = client.post("/api/register", json={"full_name": "Gleb Fokin"}, headers=hdr(2000)).json()["id"]
    row = lambda: next(x for x in client.get("/api/people", headers=hdr(1000)).json() if x["id"] == pid)
    assert row()["name_issue"] == "нет имени или фамилии отдельно"
    # HEAD правит сам: регистр выравнивается, показывается «Имя Фамилия», никнейм отдельно
    r = client.post(f"/api/people/{pid}", json={"first_name": " глеб ", "last_name": "ФОКИН", "nickname": " Foks "}, headers=hdr(1000))
    assert r.status_code == 200 and r.json()["full_name"] == "Глеб Фокин" and r.json()["nickname"] == "Foks"
    assert row()["name_issue"] == "" and row()["nickname"] == "Foks"
    assert client.post(f"/api/people/{pid}", json={"first_name": "Глеб", "last_name": ""}, headers=hdr(1000)).status_code == 422
    assert client.post(f"/api/people/{pid}", json={"nickname": ""}, headers=hdr(1000)).json()["nickname"] is None
    # сам человек в анкете: то же правило, двойная фамилия через дефис, латиница видна HEAD
    body = {"last_name": "салтыкова-щедрина", "first_name": "АННА", "birth_date": "1995-05-05", "phone": "+77011234567", "city": "Астана", "nickname": "Ann"}
    me = client.post("/api/profile", json=body, headers=hdr(2000)).json()
    assert me["full_name"] == "Анна Салтыкова-Щедрина" and me["nickname"] == "Ann"
    old = {k: v for k, v in body.items() if k != "nickname"}   # старая версия страницы: поля «Никнейм» в запросе нет
    assert client.post("/api/profile", json=old, headers=hdr(2000)).json()["nickname"] == "Ann"
    client.post("/api/profile", json={**body, "first_name": "Anna", "last_name": "Lee"}, headers=hdr(2000))
    assert row()["name_issue"] == "латиницей"
    assert client.post(f"/api/people/{pid}", json={"nickname": "x"}, headers=hdr(2000)).status_code == 403
