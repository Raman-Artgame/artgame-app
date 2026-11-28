"""«Реклама» (HEAD 14.11): что реально приводит клиентов, а что сливает бюджет.

По каждой площадке за месяц: расход, заявки (лиды Битрикса), сколько стало сделками, сколько выиграно и на какую сумму,
цена заявки. Площадка лида: сама — по фразе из своей ссылки WhatsApp в первом сообщении клиента, или её ставит МОП
в карточке лида («И ссылка, и МОП»). В Битрикс не пишем — только читаем лиды и сделки.
"""
import re
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, db
from .work import active

router = APIRouter(prefix="/api")
SEE = {"marketer", "head"}
EDIT_JOBS = {"lead", "target"}          # кроме HEAD: руководитель отдела и таргетолог вносят расход и площадки
MOP = {"mop", "mop_vip", "head"}
CONVERTED = "CONVERTED"


def _see(p: dict):
    if p["role_code"] not in SEE:
        raise HTTPException(403, "«Реклама» — у маркетинга и HEAD")


def _edit(p: dict):
    _see(p)
    if p["role_code"] != "head" and p.get("mkt_job") not in EDIT_JOBS:
        raise HTTPException(403, "расход и площадки вносят HEAD, руководитель отдела и таргетолог")


def _norm(s: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", (s or "").lower().replace("ё", "е")).strip()


def channels(conn, only_active: bool = True) -> list[dict]:
    return conn.execute("SELECT id, title, phrase, paid, active, sort FROM mkt_channels" + (" WHERE active" if only_active else "") +
                        " ORDER BY sort, id").fetchall()


def detect(conn, text: str) -> int | None:
    """Площадка по первой фразе клиента: фраза из ссылки целиком есть в сообщении."""
    t = _norm(text)
    if not t:
        return None
    for c in channels(conn):
        ph = _norm(c["phrase"] or "")
        if ph and ph in t:
            return c["id"]
    return None


SITE = "https://artgame.kz"


def label_phrase(lid: int, channel_phrase: str | None) -> str:
    """Фраза кампании = фраза площадки + номер рекламы: клиент отправляет её как есть, по номеру узнаём кампанию."""
    return f"{(channel_phrase or 'Здравствуйте!').strip()} Реклама №{lid}."


def detect_label(conn, text: str) -> dict | None:
    m = re.search(r"реклама\s*№\s*(\d+)", (text or "").lower())
    return conn.execute("SELECT id, channel_id FROM mkt_labels WHERE id=%s", (int(m.group(1)),)).fetchone() if m else None


def auto_origin(lead_id: int, text: str) -> None:
    """Вызывается, когда приложение читает переписку лида: узнали площадку по фразе — запомнили. Отметку МОП не трогаем."""
    with db.pool.connection() as conn:
        if conn.execute("SELECT 1 FROM lead_origin WHERE lead_id=%s", (lead_id,)).fetchone():
            return
        lb = detect_label(conn, text)
        ch = lb["channel_id"] if lb else detect(conn, text)
        if ch:
            conn.execute("INSERT INTO lead_origin (lead_id, channel_id, label_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                         (lead_id, ch, lb["id"] if lb else None))


def origin_of(conn, lead_id: int) -> dict | None:
    return conn.execute("""SELECT o.channel_id, c.title, o.set_by IS NULL AS auto FROM lead_origin o JOIN mkt_channels c ON c.id=o.channel_id
                           WHERE o.lead_id=%s""", (lead_id,)).fetchone()


def _wa(conn) -> str:
    r = conn.execute("SELECT value FROM mkt_settings WHERE key='wa_phone'").fetchone()
    return r["value"] if r else ""


def _month(ym: str | None) -> tuple[str, date, date]:
    ym = ym or date.today().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", ym):
        raise HTTPException(400, "bad month")
    y, m = map(int, ym.split("-"))
    return ym, date(y, m, 1), date(y + m // 12, m % 12 + 1, 1)


@router.get("/mkt/channels")
def api_channels(p: dict = Depends(active)):
    """Список площадок — для «Рекламы» и для МОП («Откуда клиент» в лиде)."""
    if p["role_code"] not in SEE | MOP:
        raise HTTPException(403)
    with db.pool.connection() as conn:
        return channels(conn)


def bx_by_channel(t0: date, t1: date, fresh: bool = False) -> tuple[dict, int, str]:
    """Заявки (лиды Битрикса) за период и что из них стало сделками — по площадкам. Ключ None — площадка не отмечена."""
    err = ""
    try:
        leads = bx.read_all("crm.lead.list", {"filter": {">=DATE_CREATE": f"{t0}T00:00:00+05:00", "<DATE_CREATE": f"{t1}T00:00:00+05:00"},
                                              "select": ["ID", "STATUS_ID"]}, fresh=fresh)
    except HTTPException as e:
        leads, err = [], f"Битрикс не ответил ({e.detail}) — заявки и сделки не посчитаны"
    ids = [int(l["ID"]) for l in leads]
    conv = [int(l["ID"]) for l in leads if l.get("STATUS_ID") == CONVERTED]
    deals = []
    if conv and not err:
        try:
            for i in range(0, len(conv), 50):
                deals += bx.read_all("crm.deal.list", {"filter": {"LEAD_ID": conv[i:i + 50]},
                                                       "select": ["ID", "LEAD_ID", "OPPORTUNITY", "STAGE_SEMANTIC_ID"]}, fresh=fresh)
        except HTTPException as e:
            err = f"Битрикс не отдал сделки ({e.detail})"
    with db.pool.connection() as conn:
        org = {r["lead_id"]: r["channel_id"] for r in conn.execute("SELECT lead_id, channel_id FROM lead_origin WHERE lead_id = ANY(%s)", (ids,)).fetchall()}
    by: dict = {}
    for i in ids:
        by.setdefault(org.get(i), {"leads": 0, "deals": 0, "won": 0, "won_sum": 0.0})["leads"] += 1
    for d in deals:
        b = by.setdefault(org.get(int(d.get("LEAD_ID") or 0)), {"leads": 0, "deals": 0, "won": 0, "won_sum": 0.0})
        b["deals"] += 1
        if d.get("STAGE_SEMANTIC_ID") == "S":
            b["won"] += 1
            b["won_sum"] += bx._num(d.get("OPPORTUNITY"))
    return by, len(ids), err


@router.get("/mkt/ads")
def ads(ym: str | None = None, fresh: int = 0, p: dict = Depends(active)):
    _see(p)
    ym, t0, t1 = _month(ym)
    by, n_leads, err = bx_by_channel(t0, t1, bool(fresh))
    with db.pool.connection() as conn:
        chans = channels(conn, only_active=False)
        spend = {r["channel_id"]: r for r in conn.execute("SELECT * FROM mkt_spend WHERE ym=%s", (ym,)).fetchall()}
        wa = _wa(conn)
    rows = []
    for c in chans:
        s, b = spend.get(c["id"]), by.get(c["id"], {"leads": 0, "deals": 0, "won": 0, "won_sum": 0.0})
        amount = float(s["amount"]) if s else 0.0
        if not c["active"] and not amount and not b["leads"]:
            continue
        verdict = ""
        if c["paid"] and amount:
            verdict = "works" if b["won"] or b["deals"] else "weak" if b["leads"] else "burns"
        rows.append({**c, **b, "spend": amount, "spend_source": s["source"] if s else None, "spend_note": s["note"] if s else None,
                     "cpl": round(amount / b["leads"]) if amount and b["leads"] else None, "verdict": verdict,
                     "link": f"https://wa.me/{wa}?text={quote(c['phrase'])}" if wa and c["phrase"] else None})
    unknown = by.get(None, {"leads": 0, "deals": 0, "won": 0, "won_sum": 0.0})
    return {"ym": ym, "items": rows, "unknown": unknown, "total": {"leads": n_leads, "spend": sum(r["spend"] for r in rows)},
            "wa_phone": wa, "can_edit": p["role_code"] == "head" or p.get("mkt_job") in EDIT_JOBS, "err": err}


class SpendIn(BaseModel):
    channel_id: int
    ym: str = Field(pattern=r"^\d{4}-\d{2}$")
    amount: float = Field(ge=0, le=1e9)
    note: str | None = Field(default=None, max_length=300)


@router.post("/mkt/spend")
def spend_set(b: SpendIn, p: dict = Depends(active)):
    _edit(p)
    with db.pool.connection() as conn, conn.transaction():
        if not conn.execute("SELECT 1 FROM mkt_channels WHERE id=%s", (b.channel_id,)).fetchone():
            raise HTTPException(404)
        conn.execute("""INSERT INTO mkt_spend (channel_id, ym, amount, note, updated_by) VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (channel_id, ym) DO UPDATE SET amount=EXCLUDED.amount, note=EXCLUDED.note, source='manual',
                        updated_by=EXCLUDED.updated_by, updated_at=now()""", (b.channel_id, b.ym, b.amount, b.note, p["id"]))
        db.audit(conn, p["id"], "mkt_spend", "mkt_spend", b.channel_id, b.model_dump())
    return {"ok": True}


class ChannelIn(BaseModel):
    title: str = Field(min_length=2, max_length=60)
    phrase: str | None = Field(default=None, max_length=200)
    paid: bool = True
    active: bool = True


@router.post("/mkt/channels")
@router.post("/mkt/channels/{cid}")
def channel_save(b: ChannelIn, cid: int | None = None, p: dict = Depends(active)):
    """Площадку не удаляем — выключаем (active=false): история заявок и расходов остаётся."""
    _edit(p)
    ph = (b.phrase or "").strip() or None
    with db.pool.connection() as conn, conn.transaction():
        if conn.execute("SELECT 1 FROM mkt_channels WHERE lower(title)=lower(%s) AND id IS DISTINCT FROM %s", (b.title.strip(), cid)).fetchone():
            raise HTTPException(409, "такая площадка уже есть")
        if ph and any(_norm(ph) == _norm(c["phrase"] or "") and c["id"] != cid for c in channels(conn, only_active=False)):
            raise HTTPException(409, "эта фраза уже у другой площадки — заявки перепутаются")
        if cid:
            r = conn.execute("UPDATE mkt_channels SET title=%s, phrase=%s, paid=%s, active=%s WHERE id=%s RETURNING id",
                             (b.title.strip(), ph, b.paid, b.active, cid)).fetchone()
            if not r:
                raise HTTPException(404)
        else:
            r = conn.execute("INSERT INTO mkt_channels (title, phrase, paid, active) VALUES (%s,%s,%s,%s) RETURNING id",
                             (b.title.strip(), ph, b.paid, b.active)).fetchone()
        db.audit(conn, p["id"], "mkt_channel", "mkt_channels", r["id"], b.model_dump())
    return {"id": r["id"]}


class LabelIn(BaseModel):
    channel_id: int | None = None
    title: str | None = Field(default=None, min_length=2, max_length=80)
    active: bool = True


def _labels(conn, channel_id: int) -> list[dict]:
    wa = _wa(conn)
    ch = conn.execute("SELECT id, title, phrase FROM mkt_channels WHERE id=%s", (channel_id,)).fetchone()
    if not ch:
        raise HTTPException(404)
    src = re.sub(r"[^a-z0-9]+", "_", ch["title"].lower().translate(str.maketrans("абвгдежзийклмнопрстуфхцчшщыэюя", "abvgdegziyklmnoprstufhccss_eua"))).strip("_") or f"ch{ch['id']}"
    out = []
    for r in conn.execute("""SELECT l.id, l.title, l.active, (SELECT count(*) FROM lead_origin o WHERE o.label_id=l.id) AS leads
                             FROM mkt_labels l WHERE l.channel_id=%s ORDER BY l.active DESC, l.id DESC""", (channel_id,)).fetchall():
        ph = label_phrase(r["id"], ch["phrase"])
        out.append({**r, "phrase": ph, "wa_link": f"https://wa.me/{wa}?text={quote(ph)}" if wa else None,
                    "site_link": f"{SITE}/?utm_source={src}&utm_medium=cpc&utm_campaign=ag{r['id']}"})
    return out


@router.get("/mkt/labels")
def labels_get(channel_id: int, p: dict = Depends(active)):
    _see(p)
    with db.pool.connection() as conn:
        return _labels(conn, channel_id)


@router.post("/mkt/labels")
@router.post("/mkt/labels/{label_id}")
def label_save(b: LabelIn, label_id: int | None = None, p: dict = Depends(active)):
    """Метку не удаляем — выключаем: заявки, пришедшие по ней, остаются за кампанией."""
    _edit(p)
    with db.pool.connection() as conn, conn.transaction():
        if label_id:
            r = conn.execute("UPDATE mkt_labels SET active=%s, title=COALESCE(%s, title) WHERE id=%s RETURNING channel_id", (b.active, b.title, label_id)).fetchone()
            if not r:
                raise HTTPException(404)
        else:
            if not b.channel_id or not b.title:
                raise HTTPException(400, "назови кампанию")
            if not conn.execute("SELECT 1 FROM mkt_channels WHERE id=%s", (b.channel_id,)).fetchone():
                raise HTTPException(404)
            r = conn.execute("INSERT INTO mkt_labels (channel_id, title, created_by) VALUES (%s,%s,%s) RETURNING channel_id, id",
                             (b.channel_id, b.title.strip(), p["id"])).fetchone()
        db.audit(conn, p["id"], "mkt_label", "mkt_labels", label_id or r["id"], b.model_dump())
        return _labels(conn, r["channel_id"])


class PhoneIn(BaseModel):
    phone: str = Field(max_length=30)


@router.post("/mkt/wa_phone")
def wa_phone(b: PhoneIn, p: dict = Depends(active)):
    """Номер WhatsApp для заявок — по нему собираются ссылки площадок. Только цифры, с кодом страны."""
    _edit(p)
    digits = re.sub(r"\D", "", b.phone)
    if digits and not 10 <= len(digits) <= 15:
        raise HTTPException(400, "номер с кодом страны, например 7 705 123 45 67")
    with db.pool.connection() as conn, conn.transaction():
        conn.execute("INSERT INTO mkt_settings (key, value) VALUES ('wa_phone', %s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (digits,))
        db.audit(conn, p["id"], "mkt_wa_phone", "mkt_settings", None, {"phone": digits})
    return {"wa_phone": digits}


class OriginIn(BaseModel):
    channel_id: int


@router.post("/bx/leads/{lead_id}/origin")
def lead_origin_set(lead_id: int, b: OriginIn, p: dict = Depends(active)):
    """МОП отмечает, откуда клиент (звонки, сарафан — то, что ссылка не поймает). Его отметка главнее автоматической."""
    if p["role_code"] not in MOP:
        raise HTTPException(403, "площадку лида отмечает МОП")
    with db.pool.connection() as conn, conn.transaction():
        c = conn.execute("SELECT id, title FROM mkt_channels WHERE id=%s AND active", (b.channel_id,)).fetchone()
        if not c:
            raise HTTPException(404, "нет такой площадки")
        conn.execute("""INSERT INTO lead_origin (lead_id, channel_id, set_by) VALUES (%s,%s,%s)
                        ON CONFLICT (lead_id) DO UPDATE SET channel_id=EXCLUDED.channel_id, set_by=EXCLUDED.set_by, set_at=now()""",
                     (lead_id, b.channel_id, p["id"]))
        db.audit(conn, p["id"], "lead_origin", "lead", lead_id, {"channel": c["title"]})
    return {"channel_id": c["id"], "title": c["title"], "auto": False}
