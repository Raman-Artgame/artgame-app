"""Отчёт таргетолога (HEAD 26.11: «в маркетинге для таргетолога возможность загрузить отчёт»; план и макет — «да доработаем»).

Агентство загружает свой отчёт (Excel, PDF или скрин) за период — файл идёт с телефона прямо на Диск
«06 МАРКЕТИНГ / 04 ОТЧЁТЫ / Таргет / ГГГГ-ММ», доступ к Диску не нужен. К отчёту приложение само ставит цифры за тот же
период: Meta (расход, переписки, объявления — из ночного сбора) и Битрикс (заявки и сделки площадки «Таргет Instagram»).
Если в отчёте указаны «потрачено» и «переписки», видно, сходятся ли они с кабинетом. HEAD: «Принято» или «Вернуть с вопросом».
Плановая цена переписки — только из «Значений» (mkt.cpl_plan), в коде цифр нет.
"""
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import ads, constants, db, drive, meta
from .adrules import REPORTS_FOLDER, _ad_rows, _calc
from .config import settings
from .files import MAX_BIG, links
from .projcard import _tell
from .work import active

router = APIRouter(prefix="/api")
UPLOAD_JOBS = {"target", "lead"}         # кроме HEAD: таргетолог и руководитель агентства
MATCH_PCT = 3                            # «сходится», если расход отчёта и Meta расходятся не больше чем на 3% (округления, курс, часы)
MIMES = ("image/", "application/pdf", "application/vnd", "text/csv", "application/octet-stream")
ST = {"pending": "у HEAD", "accepted": "принято", "returned": "вернул с вопросом"}


def _can_up(p: dict):
    ads._see(p)
    if p["role_code"] != "head" and p.get("mkt_job") not in UPLOAD_JOBS:
        raise HTTPException(403, "отчёт загружает таргетолог или руководитель агентства")


def _folder(d, when) -> str:
    return d.child(d.child(REPORTS_FOLDER, "Таргет"), f"{when.year}-{when.month:02d}")


def compare(conn, t0: date, t1: date, fresh: bool = False) -> dict:
    """Цифры приложения за период отчёта: Meta по объявлениям и Битрикс по площадке «Таргет Instagram»."""
    rows = [_calc(x) for x in _ad_rows(conn, t0, t1)]
    spend = round(sum(x["spend"] or 0 for x in rows), 2)
    chats = sum(x["results"] for x in rows)
    k = constants.latest(conn)
    plan = k.get("mkt.cpl_plan") if isinstance(k.get("mkt.cpl_plan"), (int, float)) and k.get("mkt.cpl_plan") > 0 else None
    ch = conn.execute("SELECT id FROM mkt_channels WHERE title=%s", (meta.CHANNEL,)).fetchone()
    by, _, err = ads.bx_by_channel(t0, t1 + timedelta(days=1), fresh)
    b = by.get(ch["id"], {}) if ch else {}
    best = sorted((x for x in rows if x["cpr"]), key=lambda x: x["cpr"])
    return {"currency": rows[0]["currency"] if rows else None, "spend": spend, "chats": chats,
            "cpr": round(spend / chats, 2) if chats else None, "plan": plan,
            "impressions": sum(x["impressions"] or 0 for x in rows), "clicks": sum(x["clicks"] or 0 for x in rows),
            "ads": [{f: x[f] for f in ("ad_id", "ad_name", "campaign_name", "spend", "results", "cpr", "ctr")} for x in (best + [x for x in rows if not x["cpr"]])[:12]],
            "bx": {"leads": b.get("leads", 0), "deals": b.get("deals", 0), "won": b.get("won", 0), "won_sum": float(b.get("won_sum", 0))},
            "bx_err": err, "has_meta": bool(rows)}


def verdict(r: dict, c: dict) -> list[str]:
    """Несколько фраз: сходится ли отчёт с кабинетом, цена переписки к плану, сколько переписок дошло до Битрикса."""
    out = []
    cur = c["currency"] or ""
    if not c["has_meta"]:
        out.append("За этот период в приложении нет данных Meta — сверить расход не с чем.")
    elif r["rep_spend"] is not None and c["spend"]:
        diff = (float(r["rep_spend"]) - c["spend"]) / c["spend"] * 100
        out.append(f"Расход в отчёте сходится с кабинетом Meta ({c['spend']:.0f} {cur})." if abs(diff) <= MATCH_PCT else
                   f"Расход в отчёте {float(r['rep_spend']):.0f}, в кабинете Meta {c['spend']:.0f} {cur} — разница {diff:+.0f}%. Спросить агентство.")
    cpr = (float(r["rep_spend"]) / r["rep_chats"]) if r["rep_spend"] and r["rep_chats"] else c["cpr"]
    if cpr and c["plan"]:
        over = (cpr - c["plan"]) / c["plan"] * 100
        out.append(f"Цена переписки {cpr:.2f} {cur}: " + (f"выше плана {c['plan']} на {over:.0f}%." if over > 0 else f"в плане ({c['plan']})."))
    elif cpr and not c["plan"]:
        out.append("Плановой цены переписки нет в «Значениях» (mkt.cpl_plan) — сравнить не с чем.")
    chats = r["rep_chats"] or c["chats"]
    if chats and not c["bx_err"]:
        out.append(f"Из {chats} переписок в Битриксе {c['bx']['leads']} заявок с площадки «{meta.CHANNEL}»"
                   + (f", сделок {c['bx']['deals']}, выиграно {c['bx']['won']}." if c["bx"]["deals"] else ".")
                   + (" Проверить, все ли переписки МОП заводит заявкой." if c["bx"]["leads"] * 2 < chats else ""))
    if c["bx_err"]:
        out.append(c["bx_err"])
    return out


def _files(conn, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    rows = {f["id"]: f for f in conn.execute("""SELECT f.*, pe.full_name AS by FROM files f JOIN people pe ON pe.id=f.uploaded_by
                                                WHERE f.id = ANY(%s) AND f.kind='doc' AND f.status='ready'""", (ids,)).fetchall()}
    return [links(rows[i]) for i in ids if i in rows]


def _out(conn, r: dict, full: bool = False) -> dict:
    out = {**{k: r[k] for k in ("id", "period_from", "period_to", "campaigns", "note", "status", "review_note", "reviewed_at", "created_at", "author_id")},
           "rep_spend": float(r["rep_spend"]) if r["rep_spend"] is not None else None, "rep_chats": r["rep_chats"],
           "author": r["author"], "status_ru": ST[r["status"]], "files": _files(conn, list(r["file_ids"] or []))}
    if full:
        c = compare(conn, r["period_from"], r["period_to"])
        out.update({"cmp": c, "verdict": verdict(r, c)})
    return out


class UpIn(BaseModel):
    client_uid: UUID
    name: str = Field(min_length=1, max_length=200)
    mime: str = Field(default="application/octet-stream", max_length=150)
    size: int = Field(gt=0, le=MAX_BIG)


@router.post("/mkt/adreports/uploads")
def upload_start(b: UpIn, request: Request, p: dict = Depends(active)):
    """Файл отчёта идёт с телефона прямо в Google, в «04 ОТЧЁТЫ / Таргет / ГГГГ-ММ»; сервер выдаёт ссылку."""
    _can_up(p)
    mime = b.mime or "application/octet-stream"
    if not mime.startswith(MIMES):
        raise HTTPException(400, "отчёт — Excel, PDF, CSV или скрин")
    origin = request.headers.get("origin") or settings.public_origin
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, status, uploaded_by, note)
                            VALUES (%s, 0, 'doc', %s, %s, %s, 'uploading', %s, 'adreport') ON CONFLICT (client_uid) DO NOTHING RETURNING *""",
                         (b.client_uid, b.name, mime, b.size, p["id"])).fetchone()
        if not f:
            f = conn.execute("SELECT * FROM files WHERE client_uid=%s AND uploaded_by=%s AND kind='doc'", (b.client_uid, p["id"])).fetchone()
            if not f:
                raise HTTPException(409, "повтори загрузку")
            if f["status"] == "ready":
                return {"file_id": f["id"], "done": True, "file": links({**f, "by": p["full_name"]})}
        try:
            d = drive.Drive()
            url = d.resumable(_folder(d, f["created_at"]), b.name, mime, b.size, origin)
        except Exception as ex:
            raise drive.fail(ex)
    return {"file_id": f["id"], "upload_url": url}


class UpDone(BaseModel):
    drive_id: str = Field(min_length=10, max_length=100)


@router.post("/mkt/adreports/uploads/{file_id}/done")
def upload_done(file_id: int, b: UpDone, p: dict = Depends(active)):
    _can_up(p)
    with db.pool.connection() as conn, conn.transaction():
        f = conn.execute("SELECT * FROM files WHERE id=%s AND uploaded_by=%s AND kind='doc' AND note='adreport'", (file_id, p["id"])).fetchone()
        if not f:
            raise HTTPException(404)
        if f["status"] != "ready":
            try:
                d = drive.Drive()
                m = d.meta(b.drive_id)
                folder = _folder(d, f["created_at"])
            except Exception as ex:
                raise drive.fail(ex)
            if folder not in m.get("parents", []) or int(m.get("size", -1)) != f["size"]:
                raise HTTPException(400, "file mismatch")
            f = conn.execute("UPDATE files SET drive_id=%s, status='ready', mime=%s WHERE id=%s RETURNING *",
                             (b.drive_id, m.get("mimeType") or f["mime"], file_id)).fetchone()
            db.audit(conn, p["id"], "file_add", "files", file_id, {"kind": "adreport"})
        return links({**f, "by": p["full_name"]})


SQL = "SELECT a.*, pe.full_name AS author FROM mkt_ad_reports a JOIN people pe ON pe.id=a.author_id"


@router.get("/mkt/adreports")
def reports_list(p: dict = Depends(active)):
    ads._see(p)
    with db.pool.connection() as conn:
        rows = conn.execute(SQL + " ORDER BY a.status<>'pending', a.created_at DESC LIMIT 40").fetchall()
        items = [_out(conn, r) for r in rows]
    return {"items": items, "can_upload": p["role_code"] == "head" or p.get("mkt_job") in UPLOAD_JOBS, "head": p["role_code"] == "head"}


@router.get("/mkt/adreports/{rid}")
def report_one(rid: int, p: dict = Depends(active)):
    ads._see(p)
    with db.pool.connection() as conn:
        r = conn.execute(SQL + " WHERE a.id=%s", (rid,)).fetchone()
        if not r:
            raise HTTPException(404)
        return _out(conn, r, full=True)


class ReportIn(BaseModel):
    period_from: date
    period_to: date
    campaigns: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)
    file_ids: list[int] = Field(min_length=1, max_length=10)
    rep_spend: float | None = Field(default=None, ge=0, le=10_000_000)
    rep_chats: int | None = Field(default=None, ge=0, le=1_000_000)


def _check(conn, b: ReportIn, p: dict):
    if b.period_to < b.period_from or (b.period_to - b.period_from).days > 186:
        raise HTTPException(400, "период: с какого по какое число, не больше полугода")
    n = conn.execute("SELECT count(*) AS n FROM files WHERE id = ANY(%s) AND kind='doc' AND status='ready' AND object_id=0",
                     (b.file_ids,)).fetchone()["n"]
    if n != len(set(b.file_ids)):
        raise HTTPException(400, "файл отчёта не найден — загрузи ещё раз")


@router.post("/mkt/adreports")
def report_add(b: ReportIn, p: dict = Depends(active)):
    _can_up(p)
    with db.pool.connection() as conn, conn.transaction():
        _check(conn, b, p)
        r = conn.execute("""INSERT INTO mkt_ad_reports (period_from, period_to, campaigns, note, file_ids, rep_spend, rep_chats, author_id)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                         (b.period_from, b.period_to, b.campaigns, b.note, b.file_ids, b.rep_spend, b.rep_chats, p["id"])).fetchone()
        db.audit(conn, p["id"], "mkt_adreport", "mkt_ad_reports", r["id"], {"from": str(b.period_from), "to": str(b.period_to)})
        return _out(conn, conn.execute(SQL + " WHERE a.id=%s", (r["id"],)).fetchone())


@router.post("/mkt/adreports/{rid}")
def report_edit(rid: int, b: ReportIn, p: dict = Depends(active)):
    """Возвращённый отчёт агентство дополняет и отправляет снова (снова «у HEAD»)."""
    _can_up(p)
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("SELECT * FROM mkt_ad_reports WHERE id=%s FOR UPDATE", (rid,)).fetchone()
        if not r:
            raise HTTPException(404)
        if r["status"] == "accepted":
            raise HTTPException(409, "принятый отчёт не правим")
        _check(conn, b, p)
        conn.execute("""UPDATE mkt_ad_reports SET period_from=%s, period_to=%s, campaigns=%s, note=%s, file_ids=%s, rep_spend=%s, rep_chats=%s,
                        status='pending', updated_at=now() WHERE id=%s""",
                     (b.period_from, b.period_to, b.campaigns, b.note, b.file_ids, b.rep_spend, b.rep_chats, rid))
        db.audit(conn, p["id"], "mkt_adreport_edit", "mkt_ad_reports", rid, {})
        return _out(conn, conn.execute(SQL + " WHERE a.id=%s", (rid,)).fetchone())


class ReviewIn(BaseModel):
    ok: bool
    note: str | None = Field(default=None, max_length=1000)


@router.post("/mkt/adreports/{rid}/review")
def report_review(rid: int, b: ReviewIn, p: dict = Depends(active)):
    if p["role_code"] != "head" or p.get("_view_as"):
        raise HTTPException(403, "отчёт принимает HEAD")
    if not b.ok and not (b.note or "").strip():
        raise HTTPException(400, "напиши вопрос агентству")
    with db.pool.connection() as conn, conn.transaction():
        r = conn.execute("SELECT * FROM mkt_ad_reports WHERE id=%s FOR UPDATE", (rid,)).fetchone()
        if not r:
            raise HTTPException(404)
        if r["status"] != "pending":
            raise HTTPException(409, "отчёт уже не ждёт решения")
        st = "accepted" if b.ok else "returned"
        conn.execute("UPDATE mkt_ad_reports SET status=%s, review_note=%s, reviewed_by=%s, reviewed_at=now(), updated_at=now() WHERE id=%s",
                     (st, (b.note or "").strip() or None, p["id"], rid))
        db.audit(conn, p["id"], "mkt_adreport_" + st, "mkt_ad_reports", rid, {"note": b.note})
        per = f"{r['period_from']:%d.%m}–{r['period_to']:%d.%m}"
        _tell(conn, r["author_id"], f"📊 Отчёт по рекламе {per}: HEAD — принято." if b.ok else
              f"📊 Отчёт по рекламе {per}: у HEAD вопрос — {b.note.strip()}. Ответь и отправь снова в «Маркетинг → Отчёты таргета».")
        return _out(conn, conn.execute(SQL + " WHERE a.id=%s", (rid,)).fetchone())
