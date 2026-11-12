"""Деньги сделки (HEAD 10.11.2026): «Поступило», «Долг», «Упущено» считает приложение, а не робот FIN03.

Робот FIN03 на сервере встал 09.11 16:42, и поступление по Айболиту (800 000) в сделке не посчиталось. Теперь итог — из базы:
- Поступило = оплаты клиента по сделке в журнале денег (из полей «Поступление 1–4», кнопкой «Внести оплату», вручную HEAD)
  − возвраты клиенту + поступления из полей сделки, которых в журнале нет (история до ноября 2026, она не меняется).
- Долг = сумма сделки − поступило, не меньше 0. У проигранной сделки долг 0, остаток — «Упущено». Переплата — сверх суммы.
- «Сумма без НДС» и «НДС» — от суммы сделки по ставке vat из «Значений», как считал FIN03 (сверено на 321 сделке 10.11).
В сделку пишем только изменившиеся поля и только там, где ARTGAME_PAY_PUSH=1 — в одной среде, при выключенном FIN03.
Ручная правка итогов в Битриксе через 15 минут возвращается к журналу. Старые сделки без денег, которых FIN03 не вёл,
не трогаем: иначе у давно оплаченных проектов без заполненных поступлений появится ложный долг.
"""
import time
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from . import bx, bxw, db, drive, finance
from .config import settings
from .deps import require_head
from .fin_bx import DESIGN, PAY, START, _day
from .work import active, with_receipt

router = APIRouter(prefix="/api")

F = {"received": "UF_CRM_ARTGAME_FIN03_RECEIVED", "debt": "UF_CRM_ARTGAME_FIN03_DEBT", "lost": "UF_CRM_ARTGAME_FIN03_LOST",
     "overpaid": "UF_CRM_ARTGAME_FIN03_OVERPAID", "net": "UF_CRM_ARTGAME_FIN03_NET", "vat": "UF_CRM_ARTGAME_FIN03_VAT"}
TITLE = {"received": "Поступило", "debt": "Долг", "lost": "Упущено", "overpaid": "Переплата", "net": "Сумма без НДС", "vat": "НДС"}
IN = ("client_payment", "design_prepay")          # приходы клиента; «refund» — возврат клиенту, вычитается
OWE = {"FINAL_INVOICE", "UC_AV00QK", "UC_BMKDS4"}  # счёт отправлен и дальше: долг есть, даже если оплат ещё нет
SELECT = ["ID", "TITLE", "CATEGORY_ID", "STAGE_ID", "STAGE_SEMANTIC_ID", "OPPORTUNITY", "CURRENCY_ID", "DATE_CREATE", "MOVED_TIME"] \
    + [f for _, a, d in PAY for f in (a, d)] + list(F.values())
PAGES = 40       # до 2000 сделок за проход (у bx.read_all потолок 500)
PAUSE = 0.5      # между записями в Битрикс: не больше двух запросов в секунду
# Оплату, которую внёс МОП, считаем сразу — со статусом «на сверке», пока HEAD не нажал ✓ (рекомендация 10.11:
# МОП не ждёт HEAD, чтобы начать работы; ошибку HEAD отменяет ✕). False — считать только после ✓ HEAD.
COUNT_UNCHECKED = True
TZ = ZoneInfo("Asia/Almaty")
CASH = "cash"                  # счёт «Наличные»: оплату можно внести без фото (HEAD 10.11)
TEST_DEAL = "Тестовая сделка — оплаты в неё не вносим, в деньгах приложения её нет"
HIST_FROM = date(2025, 1, 1)   # оплату задним числом вносим с 2025 года; до 01.11.2026 — в счёт «История»: в долг сделки, не в деньги ноября


def _cur(d: dict, key: str) -> float | None:
    """Что сейчас в поле итога сделки: число или None, если поле пустое."""
    v = str(d.get(F[key]) or "").split("|")[0].strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _fresh(d: dict) -> bool:
    """Сделка живая с начала учёта: создана или сдвинута по стадии с 01.11.2026."""
    return max(_day(d.get("DATE_CREATE")) or date.min, _day(d.get("MOVED_TIME")) or date.min) >= START


def _failed(d: dict) -> bool:
    """Сделка проиграна (любая стадия провала, в том числе «Другое» и «Игнор / отмена»)."""
    if d.get("STAGE_SEMANTIC_ID"):
        return d["STAGE_SEMANTIC_ID"] == "F"
    try:
        return (bx.stages().get(d.get("STAGE_ID")) or {}).get("semantic") in ("failure", "apology")
    except Exception:  # noqa: BLE001 — справочник стадий недоступен
        return str(d.get("STAGE_ID") or "").split(":")[-1] in ("LOSE", "APOLOGY")


def ledger(conn, ids=None) -> dict[int, dict]:
    """Оплаты клиента из журнала по сделкам: сумма (приходы − возвраты, без отменённых) и какие поступления 1–4 сделки
    журнал уже знает (в любом статусе: строку, которую HEAD отменил, из поля сделки обратно не считаем; поле без даты,
    которое заменили оплатой в приложении с датой и чеком, — тоже)."""
    q = ("SELECT deal_id, direction, amount, status, source, source_ref, checked_at FROM fin_ledger "
         "WHERE deal_id IS NOT NULL AND article_code = ANY(%s)")
    args = [list(IN) + ["refund"]]
    if ids is not None:
        q += " AND deal_id = ANY(%s)"
        args.append([int(i) for i in ids])
    out: dict[int, dict] = {}
    for r in conn.execute(q, args):
        x = out.setdefault(int(r["deal_id"]), {"sum": 0.0, "refs": set()})
        if r["source"] in ("bitrix", "app") and str(r["source_ref"] or "").startswith("deal:"):
            x["refs"].add(r["source_ref"])
        if r["status"] == "active" and (COUNT_UNCHECKED or r["source"] != "app" or r["checked_at"] is not None):
            x["sum"] += float(r["amount"]) * (1 if r["direction"] == "in" else -1)
    return out


def received(d: dict, led: dict | None) -> float:
    """Поступило: журнал + поступления из полей сделки, которых в журнале нет."""
    did, led = int(d["ID"]), led or {}
    total = led.get("sum", 0.0)
    for n, fa, _ in PAY:
        if f"deal:{did}:pay{n}" not in led.get("refs", ()):
            total += bx._money(d.get(fa))
    return round(total, 2)


def target(d: dict, led: dict | None, vat: float) -> dict:
    """Итоги сделки, как их должен видеть Битрикс."""
    opp, got = bx._money(d.get("OPPORTUNITY")), received(d, led)
    rest = round(max(0.0, opp - got), 2)
    lost = _failed(d)
    out = {"received": got, "debt": 0.0 if lost else rest, "lost": rest if lost else 0.0, "overpaid": round(max(0.0, got - opp), 2)}
    if vat:
        net = round(opp / (1 + vat / 100), 2)
        out.update(net=net, vat=round(opp - net, 2))
    return out


def managed(d: dict, led: dict | None) -> bool:
    """Чьи итоги ведём: в сделке есть деньги, FIN03 её уже вёл, или она живая с ноября и на стадии, где бывает долг."""
    if led or any(bx._money(d.get(a)) > 0 for _, a, _ in PAY):
        return True
    if any(_cur(d, k) is not None for k in ("received", "debt", "lost")):
        return True
    return _fresh(d) and (d.get("STAGE_SEMANTIC_ID") in ("S", "F") or d.get("STAGE_ID") in OWE)


def changes(d: dict, tgt: dict) -> dict:
    """Поля, которые надо переписать: значение другое. Пустое поле = 0; «без НДС» не заводим у старых сделок, где его нет."""
    out = {}
    for k, v in tgt.items():
        cur = _cur(d, k)
        if k in ("net", "vat") and cur is None and not _fresh(d):
            continue
        if round(cur or 0.0, 2) != round(v, 2):
            out[k] = v
    return out


def _money_str(v: float, cur: str) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{s}|{cur or 'KZT'}"


def _vat() -> float:
    try:
        return float(bx._vals().get("vat") or 0)
    except Exception:  # noqa: BLE001 — нет «Значений»: «без НДС» не трогаем, остальное считаем
        return 0.0


def _deals(ids: list[int] | None = None) -> list[dict]:
    """Сделки для сверки: все с изменениями с начала учёта + сделки с деньгами в журнале (их — по номерам)."""
    if ids is not None:
        out = []
        for i in range(0, len(ids), 50):
            out += bx.read_all("crm.deal.list", {"filter": {"ID": ids[i:i + 50]}, "select": SELECT}, fresh=True)
        return out
    out, start = [], 0
    params = {"filter": {"CATEGORY_ID": list(bx.CATEGORIES), ">=DATE_MODIFY": START.isoformat()}, "select": SELECT, "order": {"ID": "ASC"}}
    for _ in range(PAGES):
        j = bx.read("crm.deal.list", {**params, "start": start}, fresh=True)
        out += bx._rows(j)
        start = None if isinstance(j, list) else j.get("next")
        if start is None:
            break
    return out


def plan(conn, ids: list[int] | None = None) -> list[dict]:
    """Расхождения журнала и Битрикса по сделкам: [{deal, fields: {ключ: (в Битриксе, по журналу)}}]. Ничего не пишет."""
    led = ledger(conn, ids)
    deals = {int(d["ID"]): d for d in _deals(ids)}
    if ids is None:
        rest = sorted(set(led) - set(deals))
        deals.update({int(d["ID"]): d for d in (_deals(rest) if rest else [])})
    vat, out = _vat(), []
    for did in sorted(deals):
        d = deals[did]
        if int(d.get("CATEGORY_ID") or 0) not in bx.CATEGORIES or bx.is_test(d) or not managed(d, led.get(did)):
            continue   # тестовую сделку (1409, HEAD 11.11) не считаем и итоги в неё не пишем
        tgt = target(d, led.get(did), vat)
        diff = changes(d, tgt)
        if diff:
            # «Поступило» вписали в Битриксе руками, а приложение по сделке не знает ни одной оплаты (ни строки в журнале,
            # ни поля «Поступление»): не обнуляем, ждём оплату в приложении (1557, 1579, 1611 — 10.11). HEAD видит их в сверке.
            hold = did not in led and tgt["received"] == 0 and (_cur(d, "received") or 0.0) > 0
            out.append({"id": did, "title": d.get("TITLE") or "", "stage": d.get("STAGE_ID"), "currency": d.get("CURRENCY_ID") or "KZT",
                        "fields": {k: (_cur(d, k), v) for k, v in diff.items()}, "hold": hold})
    return out


def push(conn, ids: list[int] | None = None) -> dict:
    """Сверить и записать итоги в Битрикс (если ARTGAME_PAY_PUSH=1 и есть вебхук). Ошибка одной сделки не останавливает остальные."""
    todo = plan(conn, ids)
    on = settings.pay_push and bxw.enabled()
    done, errors = 0, []
    for x in todo if on else []:
        if x["hold"]:
            continue
        fields = {F[k]: _money_str(v, x["currency"]) for k, (_, v) in x["fields"].items()}
        log = {"fields": {TITLE[k]: [a, b] for k, (a, b) in x["fields"].items()}}
        try:
            bxw.CALL("crm.deal.update", {"id": x["id"], "fields": fields, "params": {"REGISTER_SONET_EVENT": "N"}})
            log["bx"], done = "ok", done + 1
        except Exception as ex:  # noqa: BLE001
            log["bx"], log["error"] = "error", str(ex)[:300]
            errors.append({"id": x["id"], "error": log["error"]})
        db.audit(conn, None, "deal_money_push", "deal", x["id"], log)
        if len(todo) > 1:
            time.sleep(PAUSE)
    if done:
        bx._cache.clear()
    return {"push": on, "diff": len(todo), "written": done, "errors": errors, "held": sum(1 for x in todo if x["hold"])}


def push_deal(deal_id: int) -> dict:
    """После оплаты или отмены в приложении — сразу итоги этой сделки (в фоне ответа, сбой Битрикса не ломает действие)."""
    if not (settings.pay_push and bxw.enabled()):
        return {"push": False}
    try:
        with db.pool.connection() as conn:
            return push(conn, [int(deal_id)])
    except Exception as ex:  # noqa: BLE001
        print(f"deal_money {deal_id}: {ex}")
        return {"error": str(ex)[:200]}


def card(d: dict) -> dict:
    """Деньги сделки для карточки и замка в приложении — по журналу, не по полям Битрикса: итоги, оплаты, история до ноября."""
    did = int(d["ID"])
    with db.pool.connection() as conn:
        led = ledger(conn, [did]).get(did)
        rows = conn.execute(
            """SELECT l.id, l.op_date, l.direction, l.amount, l.article_code, l.source, l.source_ref, l.status, l.checked_at, l.note,
                      l.receipt_file_id, l.account_code, ac.title AS account_title, pe.full_name AS author
               FROM fin_ledger l JOIN fin_accounts ac ON ac.code = l.account_code LEFT JOIN people pe ON pe.id = l.created_by
               WHERE l.deal_id = %s AND l.article_code = ANY(%s) ORDER BY l.op_date DESC, l.id DESC""", (did, list(IN) + ["refund"])).fetchall()
        # valid_until: счёт только для оплат по эту дату (ИП Артамонов — до 31.12.2026, HEAD 11.11); окно фильтрует по дате оплаты
        accounts = conn.execute("SELECT code, title, valid_until FROM fin_accounts WHERE active AND code <> 'hist' ORDER BY sort, code").fetchall()
    t = target(d, led, 0)
    refs = (led or {}).get("refs", ())
    undated = _undated(d)
    history = [{"n": n, "slot": n if f"deal:{did}:pay{n}" in undated else None, "date": str(_day(d.get(fd)) or ""),
                "amount": bx._money(d.get(fa))} for n, fa, fd in PAY if bx._money(d.get(fa)) > 0 and f"deal:{did}:pay{n}" not in refs]
    # slot — оплата из поля «Поступление N» без даты: у неё кнопка «Дата и чек» (заменить оплатой с датой и чеком, без двойного счёта);
    # строку импорта, которую заменили, не показываем — вместо неё оплата с датой и чеком; отменённую строку из поля тоже
    # (HEAD 11.11, ФОК: оплаты внесли заново с чеками — старые строки из полей убрать); в журнале и витрине она остаётся «отменено»
    owned = {r["source_ref"] for r in rows if r["source"] == "app" and r["source_ref"]}
    items = [with_receipt({**r, "amount": float(r["amount"]) * (1 if r["direction"] == "in" else -1), "op_date": str(r["op_date"]),
                           "on_check": _on_check(r),
                           "slot": undated.get(r["source_ref"]) if r["source"] == "bitrix" and r["status"] == "active" else None})
             for r in rows if not (r["source"] == "bitrix" and (r["source_ref"] in owned or r["status"] == "cancelled"))]
    return {"received": t["received"], "debt": t["debt"], "lost": t["lost"], "overpaid": t["overpaid"], "items": items, "history": history,
            "on_check": round(sum(x["amount"] for x in items if x["on_check"]), 2), "accounts": accounts, "count_unchecked": COUNT_UNCHECKED}


def _undated(d: dict) -> dict[str, int]:
    """Поля «Поступление N» сделки с суммой, но без даты: {'deal:<ID>:payN': N}."""
    return {f"deal:{int(d['ID'])}:pay{n}": n for n, fa, fd in PAY if bx._money(d.get(fa)) > 0 and _day(d.get(fd)) is None}


def _on_check(r: dict) -> bool:
    """Оплата, которую внёс МОП и HEAD ещё не сверил."""
    return r["source"] == "app" and r["status"] == "active" and r.get("checked_at") is None and r["article_code"] in IN


# ---------- «Внести оплату» в сделке (МОП — своя сделка, HEAD и «Вносит оплаты клиентов» — любая) ----------

def can_pay_any(p: dict) -> bool:
    """По любой сделке оплату вносят HEAD и те, кому HEAD поставил «Вносит оплаты клиентов» в «Команде» (HEAD 10.11: Анна)."""
    return p["role_code"] == "head" or bool(p.get("pays"))


def _deal_for_pay(p: dict, deal_id: int) -> dict:
    if not p.get("pays"):
        return bx._deal(p, deal_id, fresh=True)   # МОП — только своя сделка, HEAD — любая
    j = bx.read("crm.deal.get", {"id": deal_id}, fresh=True)
    d = j.get("result", j) if isinstance(j, dict) else None
    if not d or not d.get("ID"):
        raise HTTPException(404, "Сделка не найдена")
    return d


class PaymentIn(BaseModel):
    client_uid: UUID
    amount: float = Field(gt=0, le=10_000_000_000)
    op_date: date
    account: str = Field(min_length=1, max_length=40)
    receipt: str | None = Field(default=None, min_length=30, max_length=8_000_000)   # без фото — только наличные
    note: str | None = Field(default=None, max_length=300)
    slot: int | None = Field(default=None, ge=1, le=4)   # «Дата и чек»: эта оплата — «Поступление N» сделки без даты
    cash: bool = False   # наличными (для оплаты до ноября: счёт там «История», наличные — отметкой)


def _income_receipt(conn, p: dict, name: str, data_url: str, deal_id: int) -> int:
    if not data_url.startswith(("data:image/jpeg;base64,", "data:image/png;base64,")):
        raise HTTPException(400, "Чек — фото jpeg или png")
    try:
        drive_id = drive.save_income_receipt(conn, name, data_url, deal_id)
    except Exception as ex:  # Диск недоступен — запись останется в очереди телефона и уйдёт позже
        raise drive.fail(ex)
    data, mime = drive.decode_data_url(data_url)
    # object_id 0: чек оплаты клиента не попадает в файлы объекта, которые видит команда на площадке
    return conn.execute("""INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by)
                           VALUES (gen_random_uuid(), 0, 'receipt', %s, %s, %s, %s, %s) RETURNING id""",
                        (name, mime, len(data), drive_id, p["id"])).fetchone()["id"]


@router.post("/bx/deals/{deal_id}/payment")
def add_payment(deal_id: int, b: PaymentIn, bg: BackgroundTasks, p: dict = Depends(active)):
    """Оплата клиента с фото чека → журнал денег (сразу в «Поступило»), чек — в папку сделки «Приходы чеки», HEAD сверяет.
    Оплата до 01.11.2026 (нашли задним числом) — в счёт «История»: долг сделки уменьшает, в деньги ноября не входит.
    slot — «Дата и чек» к полю «Поступление N» без даты (Анна 09–10.11): оплата заменяет поле, поле больше не считается.
    Наличные (HEAD 10.11): фото расписки по желанию, без фото HEAD сверяет сам; безналичные — только с фото чека или выписки."""
    d = _deal_for_pay(p, deal_id)
    cat = int(d.get("CATEGORY_ID") or 0)
    if cat not in bx.CATEGORIES:
        raise HTTPException(400, "оплату вносим по сделкам «Продажи РК» и «Дизайн РК»")
    if bx.is_test(d):
        raise HTTPException(400, TEST_DEAL)
    today = datetime.now(TZ).date()
    if not HIST_FROM <= b.op_date <= today:
        raise HTTPException(400, f"дата оплаты — с {HIST_FROM:%d.%m.%Y} по сегодня")
    hist = b.op_date < START
    ref = f"deal:{deal_id}:pay{b.slot}" if b.slot else None
    with db.pool.connection() as conn, conn.transaction():
        dup = conn.execute("SELECT * FROM fin_ledger WHERE client_uid=%s", (b.client_uid,)).fetchone()
        if dup:   # повтор из офлайн-очереди телефона
            return {"ok": True, "row": with_receipt(dup)}
        account = "hist" if hist else b.account
        acc = conn.execute("SELECT title, valid_until FROM fin_accounts WHERE code=%s AND active", (account,)).fetchone()
        if (b.account == "hist" and not hist) or not acc:
            raise HTTPException(400, "нет такого счёта")
        if acc["valid_until"] and b.op_date > acc["valid_until"]:
            raise HTTPException(400, f"на счёт «{acc['title']}» — только оплаты по {acc['valid_until']:%d.%m.%Y}")
        cash = account == CASH or (hist and (b.cash or b.account == CASH))
        if not b.receipt and not cash:
            raise HTTPException(400, "нужно фото чека или выписки; без фото — только оплата наличными")
        if ref:
            if ref not in _undated(d):
                raise HTTPException(400, f"у «Поступление {b.slot}» в сделке нет суммы без даты")
            known = conn.execute("SELECT source, status FROM fin_ledger WHERE source IN ('bitrix','app') AND source_ref=%s FOR UPDATE",
                                 (ref,)).fetchall()
            if any(r["source"] == "app" for r in known):
                raise HTTPException(409, "дату и чек к этой оплате уже внесли")
            if known and not any(r["status"] == "active" for r in known):
                raise HTTPException(409, "эту оплату HEAD отменил в журнале")
            # приход, который импорт поставил днём, когда увидел поле, — отменяем: вместо него оплата с датой и чеком
            conn.execute("UPDATE fin_ledger SET status='cancelled' WHERE source='bitrix' AND source_ref=%s AND status='active'", (ref,))
        title = str(d.get("TITLE") or f"сделка {deal_id}")[:80]
        fid = _income_receipt(conn, p, f"{b.op_date} приход {b.amount:.0f} {title}".replace("/", "-"), b.receipt, deal_id) if b.receipt else None
        note = " · ".join(x for x in (title, f"внёс {p['full_name']}", "до ноября" if hist else "", "наличными" if hist and cash else "",
                                      f"вместо «Поступление {b.slot}» без даты" if ref else "", (b.note or "").strip()) if x)
        row = finance.add_ledger(conn, p, client_uid=b.client_uid, op_date=b.op_date, account=account, direction="in", amount=b.amount,
                                 article="design_prepay" if cat == DESIGN else "client_payment", period=f"{b.op_date:%Y-%m}",
                                 deal_id=deal_id, note=note[:500], receipt_file_id=fid, source="app", source_ref=ref)
        if p["role_code"] == "head" and not p.get("_view_as"):   # оплата, которую внёс сам HEAD, сверять не нужно
            row = conn.execute("UPDATE fin_ledger SET checked_at=now(), checked_by=%s WHERE id=%s RETURNING *", (p["id"], row["id"])).fetchone()
        db.audit(conn, p["id"], "client_payment_add", "deal", deal_id,
                 {"amount": b.amount, "ledger": row["id"], "account": account, **({"slot": b.slot} if ref else {}),
                  **({"cash": True} if cash else {}), **({} if b.receipt else {"receipt": None})})
    bg.add_task(push_deal, deal_id)
    return {"ok": True, "row": with_receipt(row), "pay": card(d)}


def _brief(d: dict, st: dict | None = None, names: dict | None = None) -> dict:
    """Сделка коротко для «Оплат»: номер, название, стадия, сумма, МОП."""
    st = bx.stages() if st is None else st
    names = {u["id"]: u["name"] for u in bx.users()} if names is None else names
    return {"id": int(d["ID"]), "title": str(d.get("TITLE") or ""),
            "stage_name": (st.get(d.get("STAGE_ID")) or {}).get("name", d.get("STAGE_ID") or ""), "sum": bx._num(d.get("OPPORTUNITY")),
            "manager": names.get(int(d.get("ASSIGNED_BY_ID") or 0), ""), "category": int(d.get("CATEGORY_ID") or 0)}


@router.get("/pay/deals")
def pay_find(q: str = "", p: dict = Depends(active)):
    """«Оплаты» (HEAD 10.11): сделка по номеру или части названия — для тех, кто вносит оплаты по любой сделке."""
    if not can_pay_any(p):
        raise HTTPException(403, "оплаты по любой сделке вносят HEAD и те, кому он поставил галочку в «Команде»")
    q = q.strip()[:60]
    if len(q) < 2 and not q.isdigit():
        return []
    flt = {"CATEGORY_ID": list(bx.CATEGORIES), **({"ID": [int(q)]} if q.isdigit() else {"%TITLE": q})}
    rows = bx._rows(bx.read("crm.deal.list", {"filter": flt, "order": {"ID": "DESC"},
                                              "select": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "ASSIGNED_BY_ID", "CATEGORY_ID"]}, fresh=True))
    st, names = bx.stages(), {u["id"]: u["name"] for u in bx.users()}
    return [_brief(d, st, names) for d in rows if not bx.is_test(d)][:12]


@router.get("/pay/deals/{deal_id}")
def pay_deal(deal_id: int, p: dict = Depends(active)):
    if not can_pay_any(p):
        raise HTTPException(403, "оплаты по любой сделке вносят HEAD и те, кому он поставил галочку в «Команде»")
    d = _deal_for_pay(p, deal_id)
    if int(d.get("CATEGORY_ID") or 0) not in bx.CATEGORIES:
        raise HTTPException(400, "оплату вносим по сделкам «Продажи РК» и «Дизайн РК»")
    if bx.is_test(d):
        raise HTTPException(400, TEST_DEAL)
    return {**_brief(d), "pay": card(d)}


@router.get("/fin/payments/check")
def to_check(p: dict = Depends(require_head)):
    """Оплаты клиентов, которые внесли МОП и HEAD ещё не сверил (в «Проверке» и в Пульте)."""
    with db.pool.connection() as conn:
        rows = conn.execute(
            """SELECT l.id, l.op_date, l.amount, l.deal_id, l.note, l.receipt_file_id, l.created_at, ac.title AS account_title,
                      pe.full_name AS author
               FROM fin_ledger l JOIN fin_accounts ac ON ac.code = l.account_code LEFT JOIN people pe ON pe.id = l.created_by
               WHERE l.source = 'app' AND l.status = 'active' AND l.checked_at IS NULL AND l.article_code = ANY(%s)
               ORDER BY l.created_at""", (list(IN),)).fetchall()
    return [with_receipt({**r, "amount": float(r["amount"]), "op_date": str(r["op_date"])}) for r in rows]


@router.post("/fin/ledger/{item_id}/check")
def check_payment(item_id: int, bg: BackgroundTasks, p: dict = Depends(require_head)):
    """HEAD сверил оплату с чеком и выпиской — ✓. Ошибочную — ✕ (отмена строки журнала, итог сделки пересчитается)."""
    with db.pool.connection() as conn, conn.transaction():
        row = conn.execute("""UPDATE fin_ledger SET checked_at=now(), checked_by=%s
                              WHERE id=%s AND status='active' AND checked_at IS NULL AND article_code = ANY(%s) RETURNING *""",
                           (p["id"], item_id, list(IN))).fetchone()
        if not row:
            raise HTTPException(409, "уже сверено, отменено или это не оплата клиента")
        db.audit(conn, p["id"], "client_payment_check", "fin_ledger", item_id, {"deal": row["deal_id"], "amount": float(row["amount"])})
    if not COUNT_UNCHECKED and row["deal_id"]:
        bg.add_task(push_deal, int(row["deal_id"]))
    return {"ok": True}


@router.get("/fin/deal-money")
def check(p: dict = Depends(require_head)):
    """Сверка для HEAD: где итоги в Битриксе расходятся с журналом приложения (до включения записи и после)."""
    with db.pool.connection() as conn:
        rows = plan(conn)
    return {"push": bool(settings.pay_push and bxw.enabled()), "count": len(rows), "held": sum(1 for r in rows if r["hold"]),
            "rows": [{**r, "fields": {TITLE[k]: {"bitrix": a, "app": b} for k, (a, b) in r["fields"].items()}} for r in rows]}
