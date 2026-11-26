"""«Итоги» маркетинга (HEAD 26.11): публикация плана ↔ пост Instagram по ссылке, разбивка по рубрикам и форматам,
вывод «куда двигаться», недельный вывод агентства и нормы «Ролики видеографа» / «Отчёт Instagram»."""
from datetime import date, datetime, timedelta, timezone

from artgame import db
from artgame.mktstats import ig_code
from conftest import hdr
from test_marketing import team  # noqa: F401


def _pub(client, title, kind, rubric, url, views=None, leads=None):
    d = str(date.today() - timedelta(days=3))
    p = client.post("/api/mkt/posts", json={"title": title, "kind": kind, "plan_date": d, "rubric_id": rubric, "caption": "т"}, headers=hdr(1000)).json()
    assert p["rubric_id"] == rubric
    client.post(f"/api/mkt/posts/{p['id']}/submit", headers=hdr(1000))
    client.post(f"/api/mkt/posts/{p['id']}/review", json={"approve": True}, headers=hdr(1000))
    assert client.post(f"/api/mkt/posts/{p['id']}/published", json={"url": url}, headers=hdr(1000)).json()["status"] == "published"
    if leads is not None:
        client.post(f"/api/mkt/posts/{p['id']}/result", json={"result": "good", "leads": leads, "views": views}, headers=hdr(1000))
    return p["id"]


def test_ig_code():
    assert ig_code("https://www.instagram.com/reel/DAbc_12-x/?igsh=xyz") == "DAbc_12-x"
    assert ig_code("https://instagram.com/artgame.kz/p/Q1w2/") == "Q1w2"
    assert ig_code("https://tiktok.com/@a/video/1") is None and ig_code(None) is None


def test_stats_by_rubric_and_advice(client, team):  # noqa: F811
    with db.pool.connection() as c:
        rub = {r["title"]: r["id"] for r in c.execute("SELECT id, title FROM mkt_rubrics").fetchall()}
        now = datetime.now(timezone.utc) - timedelta(days=3)
        for i, (code, kind, views) in enumerate([("R1", "REELS", 9000), ("R2", "REELS", 7000), ("H1", "FEED", 900), ("H2", "FEED", 700),
                                                 ("X9", "REELS", 300)]):
            c.execute("""INSERT INTO mkt_ig_media (id, kind, permalink, posted_at, views, reach, likes, comments, saved, shares)
                         VALUES (%s,%s,%s,%s,%s,%s,10,2,3,1)""", (f"m{i}", kind, f"https://www.instagram.com/{'reel' if kind == 'REELS' else 'p'}/{code}/", now, views, views // 2))
    _pub(client, "Роспись кафе", "reels", rub["Процесс росписи"], "https://www.instagram.com/reel/R1/?igsh=a")
    _pub(client, "Роспись школы", "reels", rub["Процесс росписи"], "https://instagram.com/reel/R2", views=7000, leads=3)
    _pub(client, "Вакансия", "post", rub["HR"], "https://www.instagram.com/p/H1/")
    _pub(client, "Вакансия 2", "post", rub["HR"], "https://www.instagram.com/p/H2/")
    _pub(client, "Без ссылки", "post", None, None)
    # кто видит: HEAD и руководитель; маркетолог без роли руководителя и художник — нет
    assert client.get("/api/mkt/stats", headers=hdr(2000)).status_code == 403
    assert client.get("/api/mkt/stats", headers=hdr(3000)).status_code == 403
    s = client.get("/api/mkt/stats?days=30", headers=hdr(1000)).json()
    assert s["totals"]["posts"] == 5 and s["totals"]["linked"] == 4 and s["totals"]["leads"] == 3 and s["totals"]["outside"] == 1
    r = {g["title"]: g for g in s["by_rubric"]}
    assert r["Процесс росписи"]["views_avg"] == 8000 and r["Процесс росписи"]["best"]["title"] == "Роспись кафе"
    assert r["HR"]["views_avg"] == 800 and s["by_rubric"][0]["title"] == "Процесс росписи"
    assert s["top"][0]["title"] == "Роспись кафе"
    text = " ".join(s["advice"])
    assert "Лучше всего смотрят «Процесс росписи»" in text and "«HR» ниже среднего" in text
    assert "Заявки приносит «Процесс росписи» — 3" in text and "без рубрики" in text and "нет ссылки" in text
    assert "мимо плана" in text and "«Эксперт»" in text           # рубрика без публикаций
    assert "Рилс" in text                                          # рилс набирают больше постов


def test_weekly_report_and_new_norms(client, team):  # noqa: F811
    pid = client.post("/api/register", json={"full_name": "Видеограф"}, headers=hdr(2400)).json()["id"]
    client.post(f"/api/people/{pid}", json={"role_code": "marketer", "zones": ["marketing"], "mkt_job": "video"}, headers=hdr(1000))
    lead = client.post("/api/register", json={"full_name": "Кристина"}, headers=hdr(2100)).json()["id"]
    client.post(f"/api/people/{lead}", json={"role_code": "marketer", "zones": ["marketing"], "mkt_job": "lead"}, headers=hdr(1000))
    body = {"worked": "Рилс процесса — 9 тыс.", "next_step": "Ещё два процесса и отзыв"}
    assert client.post("/api/mkt/reports", json=body, headers=hdr(2400)).status_code == 403     # видеограф не пишет
    assert client.post("/api/mkt/reports", json=body, headers=hdr(2100)).json()["ok"]
    w = client.post("/api/mkt/reports", json={**body, "next_step": "Два процесса"}, headers=hdr(2100)).json()["week"]   # та же неделя — правка
    s = client.get("/api/mkt/stats", headers=hdr(2100)).json()
    assert len(s["weeks"]) == 1 and s["weeks"][0]["next_step"] == "Два процесса" and str(s["weeks"][0]["week"]) == w
    today = date.today()
    with db.pool.connection() as c:
        c.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, drive_id, uploaded_by)
                     VALUES (gen_random_uuid(), 0, 'pub', 'r.mp4', 'video/mp4', 1, 'ready', 'dv1', %s)""", (pid,))
    client.post("/api/mkt/shoots", json={"title": "Объект", "shoot_date": str(today)}, headers=hdr(2400))
    norms = {n["kind"]: n for n in client.get(f"/api/mkt/posts?ym={today:%Y-%m}", headers=hdr(1000)).json()["norms"]}
    assert norms["video"]["per_month"] == 8 and norms["video"]["planned"] == 1 and norms["video"]["done"] == 1
    want = 1 if date.fromisoformat(w).month == today.month else 0
    assert norms["ig_report"]["per_month"] == 4 and norms["ig_report"]["done"] == want
