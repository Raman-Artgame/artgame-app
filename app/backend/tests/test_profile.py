"""Анкета «Мои данные» (HEAD 09.11): человек сам заполняет ФИО, дату рождения и т. д.; имя в приложении — из анкеты."""
from conftest import hdr

OK = {"last_name": "Жұмаділдина", "first_name": "Малика", "birth_date": "1999-12-16", "phone": "+7 777 987 70 99", "city": "Астана",
      "emergency_name": "Мама", "emergency_phone": "+77001112233", "clothes_size": "M"}


def test_profile(client):
    client.post("/api/register", json={"full_name": "malika_tg"}, headers=hdr(7300))
    assert client.get("/api/me", headers=hdr(7300)).json()["profile_at"] is None
    me = client.post("/api/profile", json=OK, headers=hdr(7300)).json()
    assert me["full_name"] == "Малика Жұмаділдина" and me["profile_at"] and me["phone"] == "+77779877099" and me["birth_date"] == "1999-12-16"
    assert client.post("/api/profile", json={**OK, "first_name": "M4lika"}, headers=hdr(7300)).status_code == 422
    assert client.post("/api/profile", json={**OK, "birth_date": "2020-01-01"}, headers=hdr(7300)).status_code == 422
    assert client.post("/api/profile", json={**OK, "phone": "123"}, headers=hdr(7300)).status_code == 422
    client.post("/api/register", json={"full_name": "HEAD"}, headers=hdr(1000))
    row = next(x for x in client.get("/api/people", headers=hdr(1000)).json() if x["full_name"] == "Малика Жұмаділдина")
    assert row["emergency_phone"] == "+77001112233" and row["clothes_size"] == "M"
