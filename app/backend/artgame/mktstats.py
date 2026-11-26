"""«Итоги» маркетинга (HEAD 26.11: «чтобы у меня и у Кристины была статистика работы, что залетело, что нет и в каком направлении двигаться»).

Вышедшая публикация плана связывается с постом Instagram по ссылке («Вышло» со ссылкой → код поста /p/…, /reel/… →
mkt_ig_media.permalink, ночной сбор Meta). Дальше — просмотры, охват, реакции и заявки по рубрикам и форматам и вывод
«куда двигаться» простыми правилами. Нормы и рубрики пока только список (HEAD: «свяжем, когда будет полноценный маркетолог»).
Недельный вывод агентства («Отчёт Instagram», норма из mkt_norms) пишут руками здесь же — цифры считает приложение.
"""
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .marketing import KINDS, _mkt
from .work import active

router = APIRouter(prefix="/api")
SEE_JOBS = {"lead"}                      # кроме HEAD — руководитель агентства (Кристина)
WRITE_JOBS = {None, "lead", "smm"}       # недельный вывод пишут руководитель и контент
CODE = re.compile(r"instagram\.com/(?:[\w.]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)")
MIN_POSTS = 2                            # рубрику с одной публикацией не хвалим и не ругаем — это случайность


def ig_code(url: str | None) -> str | None:
    m = CODE.search(url or "")
    return m.group(1) if m else None


def _see(p: dict):
    _mkt(p)
    if p["role_code"] != "head" and p.get("mkt_job") not in SEE_JOBS:
        raise HTTPException(403, "итоги видят HEAD и руководитель агентства")


def _n(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _group(rows: list[dict], key: str) -> list[dict]:
    out = {}
    for r in rows:
        g = out.setdefault(r[key] or "", {"title": r[key] or "", "posts": 0, "linked": 0, "views": 0, "reach": 0, "acts": 0, "leads": 0,
                                           "good": 0, "weak": 0, "best": None})
        g["posts"] += 1
        g["leads"] += r["leads"] or 0
        g["good"] += r["result"] == "good"
        g["weak"] += r["result"] == "weak"
        if r["views"] is not None:
            g["linked"] += 1
            g["views"] += r["views"]
            g["reach"] += r["reach"] or 0
            g["acts"] += r["acts"] or 0
            if not g["best"] or r["views"] > g["best"]["views"]:
                g["best"] = {"id": r["id"], "title": r["title"], "url": r["url"], "views": r["views"]}
    for g in out.values():
        g["views_avg"] = round(g["views"] / g["linked"]) if g["linked"] else None
        g["er"] = round(g["acts"] / g["reach"] * 100, 1) if g["reach"] else None   # реакции на 100 охваченных
    return sorted(out.values(), key=lambda g: (g["views_avg"] is None, -(g["views_avg"] or 0), -g["posts"]))


def advice(rows: list[dict], by_rubric: list[dict], by_kind: list[dict], idle: list[str], outside: int) -> list[str]:
    """Вывод «куда двигаться»: несколько фраз по цифрам, без оценок там, где данных мало."""
    out = []
    linked = [r for r in rows if r["views"] is not None]
    nolink = len(rows) - len(linked)
    if not rows:
        return ["За период ничего не вышло — сначала план и публикации, потом выводы."]
    if nolink:
        out.append(f"У {nolink} из {len(rows)} вышедших публикаций нет ссылки на Instagram или сбор Meta их ещё не видел — "
                   "без ссылки цифры не считаются. Вставляйте ссылку в «Вышло».")
    avg = sum(r["views"] for r in linked) / len(linked) if linked else 0
    ok = [g for g in by_rubric if g["title"] and g["linked"] >= MIN_POSTS]
    if avg and ok:
        top = ok[0]
        if top["views_avg"] >= avg * 1.2:
            out.append(f"Лучше всего смотрят «{top['title']}»: в среднем {_n(top['views_avg'])} просмотров, в {top['views_avg'] / avg:.1f} раза "
                       "выше среднего. Ставить чаще.")
        low = ok[-1]
        if low is not top and low["views_avg"] <= avg * 0.6:
            out.append(f"«{low['title']}» ниже среднего ({_n(low['views_avg'])} против {_n(round(avg))}): менять подачу (первые секунды, обложку, "
                       "подпись) или ставить реже.")
    if len(linked) and len(linked) < 5:
        out.append(f"Связанных с Instagram публикаций пока {len(linked)} — выводы предварительные, через пару недель будет точнее.")
    kinds = [g for g in by_kind if g["linked"] >= MIN_POSTS]
    if len(kinds) >= 2 and kinds[0]["views_avg"] and kinds[-1]["views_avg"] and kinds[0]["views_avg"] >= kinds[-1]["views_avg"] * 1.5:
        out.append(f"Формат «{kinds[0]['title']}» набирает в {kinds[0]['views_avg'] / kinds[-1]['views_avg']:.1f} раза больше, чем «{kinds[-1]['title']}».")
    leads = sorted((g for g in by_rubric if g["title"] and g["leads"]), key=lambda g: -g["leads"])
    if leads:
        out.append(f"Заявки приносит «{leads[0]['title']}» — {leads[0]['leads']}. Это важнее просмотров: держать рубрику в каждой неделе.")
    noru = sum(1 for r in rows if not r["rubric"])
    if noru:
        out.append(f"{noru} публикаций без рубрики — их не видно в разбивке. Рубрику ставьте в публикации.")
    if idle:
        out.append("За период не выходило: " + ", ".join(f"«{t}»" for t in idle) + ".")
    if outside:
        out.append(f"В Instagram вышло {outside} постов мимо плана (без утверждения в приложении).")
    return out


@router.get("/mkt/stats")
def stats(days: int = 30, p: dict = Depends(active)):
    """Итоги за последние `days` дней (7–180) по вышедшим публикациям плана."""
    _see(p)
    days = max(7, min(days, 180))
    t1 = date.today() + timedelta(days=1)
    t0 = t1 - timedelta(days=days)
    with db.pool.connection() as conn:
        posts = conn.execute("""SELECT m.id, m.title, m.kind, m.url, m.views AS views_hand, m.leads, m.result, m.published_at, rb.title AS rubric
                                FROM mkt_posts m LEFT JOIN mkt_rubrics rb ON rb.id=m.rubric_id
                                WHERE m.status='published' AND coalesce(m.published_at::date, m.plan_date) >= %s
                                  AND coalesce(m.published_at::date, m.plan_date) < %s""", (t0, t1)).fetchall()
        media = conn.execute("""SELECT id, kind, permalink, views, reach, likes, comments, saved, shares, posted_at FROM mkt_ig_media
                                WHERE posted_at >= %s""", (datetime.combine(t0 - timedelta(days=14), datetime.min.time(), timezone.utc),)).fetchall()
        rubrics = [r["title"] for r in conn.execute("SELECT title FROM mkt_rubrics WHERE NOT project ORDER BY sort, id").fetchall()]
        weeks = conn.execute("""SELECT r.week, r.worked, r.next_step, pe.full_name AS author, r.updated_at FROM mkt_reports r
                                JOIN people pe ON pe.id=r.author_id ORDER BY r.week DESC LIMIT 8""").fetchall()
    by_code = {ig_code(m["permalink"]): m for m in media if ig_code(m["permalink"])}
    rows, used = [], set()
    for x in posts:
        m = by_code.get(ig_code(x["url"]))
        if m:
            used.add(m["id"])
        views = m["views"] if m and m["views"] is not None else x["views_hand"]
        rows.append({"id": x["id"], "title": x["title"], "kind": KINDS.get(x["kind"], x["kind"]), "url": x["url"], "rubric": x["rubric"],
                     "leads": x["leads"], "result": x["result"], "linked": bool(m), "views": views,
                     "reach": m["reach"] if m else None,
                     "acts": sum((m[k] or 0) for k in ("likes", "comments", "saved", "shares")) if m else None})
    outside = sum(1 for m in media if m["id"] not in used and m["kind"] != "STORY" and m["posted_at"]
                  and t0 <= m["posted_at"].date() < t1)
    by_rubric, by_kind = _group(rows, "rubric"), _group(rows, "kind")
    done = {r["rubric"] for r in rows}
    idle = [t for t in rubrics if t not in done]
    seen = sorted((r for r in rows if r["views"] is not None), key=lambda r: -r["views"])
    return {"from": t0, "to": t1 - timedelta(days=1), "days": days,
            "totals": {"posts": len(rows), "linked": sum(r["linked"] for r in rows), "views": sum(r["views"] or 0 for r in rows),
                       "reach": sum(r["reach"] or 0 for r in rows), "leads": sum(r["leads"] or 0 for r in rows), "outside": outside},
            "by_rubric": by_rubric, "by_kind": by_kind, "top": seen[:5], "weak": seen[-3:][::-1] if len(seen) > 5 else [],
            "advice": advice(rows, by_rubric, by_kind, idle, outside), "weeks": weeks,
            "this_week": _monday(date.today()), "can_write": p["role_code"] == "head" or p.get("mkt_job") in WRITE_JOBS}


class ReportIn(BaseModel):
    week: date | None = None                       # любой день недели; по умолчанию — прошлая неделя
    worked: str = Field(min_length=3, max_length=2000)
    next_step: str = Field(min_length=3, max_length=2000)


@router.post("/mkt/reports")
def report_put(b: ReportIn, p: dict = Depends(active)):
    """Недельный вывод агентства (норма «Отчёт Instagram»): что сработало и что делаем дальше. Одна запись на неделю, правится."""
    _mkt(p)
    if p["role_code"] != "head" and p.get("mkt_job") not in WRITE_JOBS:
        raise HTTPException(403, "недельный вывод пишет руководитель или контент")
    week = _monday(b.week or date.today() - timedelta(days=7))
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("""INSERT INTO mkt_reports (week, worked, next_step, author_id) VALUES (%s,%s,%s,%s)
                            ON CONFLICT (week) DO UPDATE SET worked=EXCLUDED.worked, next_step=EXCLUDED.next_step,
                                                             author_id=EXCLUDED.author_id, updated_at=now()
                            RETURNING id, week""", (week, b.worked.strip(), b.next_step.strip(), p["id"])).fetchone()
        db.audit(conn, p["id"], "mkt_report", "mkt_reports", r["id"], {"week": str(week)})
    return {"ok": True, "week": r["week"]}
