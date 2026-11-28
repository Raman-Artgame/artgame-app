"""Учебник и тесты в «Учёбе» (HEAD 28.11): учебник МОП — раздел приложения, а не страница во фрейме; банк вопросов по главам.

Содержимое зашифровано (репо публичный): places/_study/<книга>_book.json.enc — главы, задачи; <книга>_quiz.json.enc — вопросы
с ответами и разбором. Папка с «_» — по подписанной ссылке места её не отдать (places.place_file). Картинки глав берутся
из места книги (img/sNN.jpg) по его подписанной ссылке — поле img_base.

Ответы проверяет сервер: варианты приходят перемешанными, у каждого свой ключ (подпись человек + вопрос + номер варианта),
верный вариант на телефон не уходит. Каждый ответ — строка study_answers; вопрос «освоен», если последний ответ верный.
Глава засчитана, если освоено от PASS всех её вопросов. Ошибка возвращается в раунд на следующий день.

Уровни вопросов — ступени роста МОП («Мой путь»): 1 МОП, 2 VIP МОП, 3 Руководитель продаж. Очки — верные ответы × вес
уровня; это только счёт знаний, игровых наград и ключей game.* здесь нет (ждут «да» HEAD по геймификации).
"""
import hashlib
import hmac
import json
import random
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .places import PLACES, ROOT, allowed, decrypt, token
from .work import active

router = APIRouter(prefix="/api/study")

DIR = ROOT / "_study"
# книга → место, у которого она берёт картинки, и лестница уровней
BOOKS = {"mop": {"place": "mop", "levels": ["МОП", "VIP МОП", "Руководитель продаж"], "roles": PLACES["mop"]["roles"]}}
WEIGHT = {1: 10, 2: 20, 3: 30}
PASS = 0.8
ROUND = 10


@lru_cache(maxsize=8)
def _load(name: str, mtime: float) -> dict:
    return json.loads(decrypt((DIR / f"{name}.json.enc").read_bytes(), f"_study/{name}.json"))


def load(name: str) -> dict:
    f = DIR / f"{name}.json.enc"
    if not f.exists():
        raise HTTPException(404, "учебник не загружен")
    return _load(name, f.stat().st_mtime)


def _book(p: dict, book: str) -> dict:
    b = BOOKS.get(book)
    if not b:
        raise HTTPException(404)
    if p["role_code"] not in b["roles"] and not set(p.get("roles") or []) & b["roles"]:
        raise HTTPException(403, "учебник не для твоей роли")
    return b


def _key(pid: int, qid: str, i: int) -> str:
    sk = hashlib.sha256(("study:" + (settings.content_key or "dev")).encode()).digest()
    return hmac.new(sk, f"{pid}:{qid}:{i}".encode(), hashlib.sha256).hexdigest()[:10]


def _stats(conn, pid: int, book: str) -> dict:
    """Последний ответ на каждый вопрос: {qid: (ok, at)}."""
    rows = conn.execute("""SELECT DISTINCT ON (qid) qid, ok, at FROM study_answers WHERE person_id = %s AND book = %s
                           ORDER BY qid, at DESC""", (pid, book)).fetchall()
    return {r["qid"]: (r["ok"], r["at"]) for r in rows}


def _rank(p: dict) -> int:
    return 2 if p["role_code"] == "mop_vip" else 1


@router.get("/{book}")
def get_book(book: str, p: dict = Depends(active)):
    b = _book(p, book)
    data = load(f"{book}_book")
    quiz = load(f"{book}_quiz")["q"]
    count = {}
    for q in quiz:
        count[q["ch"]] = count.get(q["ch"], 0) + 1
    place = b["place"]
    base = f"/api/p/{place}/{token(p['id'], place)}/" if allowed(p, place) else ""
    return {**data, "img_base": base, "levels": b["levels"], "qcount": count, "pass": PASS}


@router.get("/{book}/me")
def my_progress(book: str, p: dict = Depends(active)):
    b = _book(p, book)
    quiz = load(f"{book}_quiz")["q"]
    with db.pool.connection() as conn:
        st = _stats(conn, p["id"], book)
        read = [r["ch"] for r in conn.execute("SELECT ch FROM study_read WHERE person_id = %s AND book = %s", (p["id"], book))]
        total = conn.execute("SELECT count(*) AS n, count(*) FILTER (WHERE ok) AS ok FROM study_answers WHERE person_id = %s AND book = %s",
                             (p["id"], book)).fetchone()
    chs, points, due = {}, 0, 0
    today = datetime.now(timezone.utc) - timedelta(hours=18)
    for q in quiz:
        c = chs.setdefault(q["ch"], {"total": 0, "ok": 0, "wrong": 0, "lv": {}})
        c["total"] += 1
        lv = c["lv"].setdefault(str(q["lvl"]), [0, 0])
        lv[1] += 1
        s = st.get(q["id"])
        if s and s[0]:
            c["ok"] += 1
            lv[0] += 1
            points += WEIGHT.get(q["lvl"], 10)
        elif s:
            c["wrong"] += 1
            if s[1] < today:
                due += 1
    for c in chs.values():
        c["passed"] = c["total"] > 0 and c["ok"] >= PASS * c["total"]
    return {"read": read, "chapters": chs, "points": points, "due": due, "answers": total["n"], "right": total["ok"],
            "rank": _rank(p), "levels": b["levels"]}


@router.get("/{book}/round")
def get_round(book: str, ch: str = "", mode: str = "", p: dict = Depends(active)):
    """Раунд из ROUND вопросов. ch — глава; mode=due — ошибки прошлых дней по всем главам; mode=all — вся глава подряд."""
    _book(p, book)
    quiz = load(f"{book}_quiz")["q"]
    with db.pool.connection() as conn:
        st = _stats(conn, p["id"], book)
    today = datetime.now(timezone.utc) - timedelta(hours=18)
    if mode == "due":
        pool = [q for q in quiz if q["id"] in st and not st[q["id"]][0] and st[q["id"]][1] < today]
    else:
        pool = [q for q in quiz if not ch or q["ch"] == ch]
    rnd = random.Random()
    # сначала новые и старые ошибки, потом освоенные; внутри — от простого уровня к сложному
    def order(q):
        s = st.get(q["id"])
        return (0 if not s else 1 if not s[0] else 2, q["lvl"], rnd.random())
    pool.sort(key=order)
    if mode != "all":
        pool = pool[:ROUND]
    out = []
    for q in pool:
        opts = [{"k": _key(p["id"], q["id"], i), "t": t} for i, t in enumerate(q["opts"])]
        rnd.shuffle(opts)
        s = st.get(q["id"])
        out.append({"id": q["id"], "ch": q["ch"], "lvl": q["lvl"], "kind": q["kind"], "q": q["q"], "opts": opts,
                    "seen": None if not s else ("ok" if s[0] else "wrong")})
    return {"q": out}


class Answer(BaseModel):
    qid: str = Field(max_length=40)
    k: str = Field(max_length=20)


@router.post("/{book}/answer")
def answer(book: str, a: Answer, p: dict = Depends(active)):
    _book(p, book)
    q = next((x for x in load(f"{book}_quiz")["q"] if x["id"] == a.qid), None)
    if not q:
        raise HTTPException(404, "нет такого вопроса")
    keys = [_key(p["id"], q["id"], i) for i in range(len(q["opts"]))]
    if a.k not in keys:
        raise HTTPException(400, "вариант не найден — обнови раунд")
    ok = a.k == keys[0]
    with db.pool.connection() as conn:
        conn.execute("INSERT INTO study_answers (person_id, book, qid, ch, lvl, ok) VALUES (%s, %s, %s, %s, %s, %s)",
                     (p["id"], book, q["id"], q["ch"], q["lvl"], ok))
    return {"ok": ok, "right": keys[0], "why": q.get("why", ""), "ref": q.get("ref", ""), "points": WEIGHT.get(q["lvl"], 10) if ok else 0}


class Read(BaseModel):
    ch: str = Field(max_length=8, pattern=r"^\d{2}$")


@router.post("/{book}/read")
def mark_read(book: str, r: Read, p: dict = Depends(active)):
    _book(p, book)
    with db.pool.connection() as conn:
        conn.execute("""INSERT INTO study_read (person_id, book, ch) VALUES (%s, %s, %s)
                        ON CONFLICT (person_id, book, ch) DO NOTHING""", (p["id"], book, r.ch))
    return {"ok": True}


@router.get("/{book}/team")
def team(book: str, p: dict = Depends(active)):
    """HEAD: кто сколько прочитал и освоил."""
    if p["role_code"] != "head":
        raise HTTPException(403, "только HEAD")
    b = _book(p, book)
    n = len(load(f"{book}_quiz")["q"])
    with db.pool.connection() as conn:
        rows = conn.execute("""
            SELECT pe.id, pe.full_name, pe.role_code,
                   (SELECT count(*) FROM study_read r WHERE r.person_id = pe.id AND r.book = %(b)s) AS read,
                   (SELECT count(*) FROM (SELECT DISTINCT ON (qid) ok FROM study_answers a WHERE a.person_id = pe.id AND a.book = %(b)s
                                          ORDER BY qid, at DESC) s WHERE s.ok) AS ok,
                   (SELECT max(at) FROM study_answers a WHERE a.person_id = pe.id AND a.book = %(b)s) AS last
            FROM people pe WHERE pe.status = 'active' AND (pe.role_code = ANY(%(r)s) OR pe.extra_roles && %(r)s)
            ORDER BY pe.full_name""", {"b": book, "r": list(b["roles"] - {"head"})}).fetchall()
    return {"total": n, "people": [{"id": r["id"], "name": r["full_name"], "role": r["role_code"], "read": r["read"], "ok": r["ok"],
                                     "last": r["last"].isoformat() if r["last"] else None} for r in rows]}


# ---------- сборка (локально, с ключом) ----------

def build(book_json: Path, quiz_py: list[Path], key: str, konst: str) -> tuple[int, int]:
    """Главы из D места (book_json) + вопросы из файлов Q[глава] = [(уровень, вид, вопрос, [верный, …], почему, якорь)]."""
    from .places import encrypt
    d = json.loads(book_json.read_text(encoding="utf-8"))
    txt = json.dumps(d, ensure_ascii=False)
    txt = re.sub(r"по константам от \d\d\.\d\d\.2026", f"по константам от {konst}", txt)
    d = json.loads(txt)
    qs = []
    for f in quiz_py:
        ns: dict = {}
        exec(compile(f.read_text(encoding="utf-8"), str(f), "exec"), ns)
        for ch, items in ns["Q"].items():
            for n, (lvl, kind, q, opts, why, ref) in enumerate(items, 1):
                assert len(opts) == 4 and len(set(opts)) == 4, (ch, n, q)
                qs.append({"id": f"{ch}-{n:02d}", "ch": ch, "lvl": lvl, "kind": kind, "q": q, "opts": opts, "why": why, "ref": ref})
    DIR.mkdir(exist_ok=True)
    (DIR / "mop_book.json.enc").write_bytes(encrypt(json.dumps(d, ensure_ascii=False).encode(), "_study/mop_book.json", key))
    (DIR / "mop_quiz.json.enc").write_bytes(encrypt(json.dumps({"q": qs}, ensure_ascii=False).encode(), "_study/mop_quiz.json", key))
    return len(d.get("mods", [])), len(qs)


if __name__ == "__main__":
    import os
    import sys
    k = os.environ.get("ARTGAME_CONTENT_KEY", "")
    print(build(Path(sys.argv[1]), [Path(x) for x in sys.argv[3:]], k, sys.argv[2]))
