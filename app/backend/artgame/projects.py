"""«Проекты» — общая вкладка (HEAD 06.11): кто где находится и сколько дней осталось до сдачи.

Проект = сделка воронки «1.1 Продажи РК» на стадии работ (UC_AV00QK, UC_BMKDS4) или перед стартом (FINAL_INVOICE).
Срок — поле «Срок клиенту» из расчёта (норма) или дни из договора; старт — день перевода в «В работе» (история стадий).
Ход работ — смены из приложения по объекту (shifts): сделано смен и м², кто был на объекте последние дни.
Видят все активные роли; сумму сделки — только МОП и HEAD.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from . import bx, db
from .work import active

router = APIRouter(prefix="/api")

WORK = ("UC_AV00QK", "UC_BMKDS4")
SOON = ("FINAL_INVOICE",)
F_DAYS = "UF_CRM_1753295493279"
SELECT = ["ID", "TITLE", "STAGE_ID", "ASSIGNED_BY_ID", "OPPORTUNITY", "DATE_MODIFY", bx.CITY, bx.AREA, bx.F_LEVEL, bx.F_SHIFTS,
          bx.F_CREW, bx.F_TERM, F_DAYS, bx.ADDR]


def _d(iso) -> date | None:
    try:
        return datetime.fromisoformat(str(iso)).date() if iso else None
    except ValueError:
        return None


def work_days(start: date, n: int) -> date:
    """n рабочих дней от старта (суббота и воскресенье не считаем)."""
    d, left = start, max(0, n)
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def _started(deal_id: int, fresh: bool) -> date | None:
    try:
        rows = bx._rows(bx.read("crm.stagehistory.list", {"entityTypeId": 2, "filter": {"OWNER_ID": deal_id}, "order": {"ID": "DESC"}}, fresh=fresh))
    except Exception:  # noqa: BLE001 — истории может не быть, тогда дата изменения сделки
        return None
    for h in rows:
        if h.get("STAGE_ID") in WORK:
            return _d(h.get("CREATED_TIME"))
    return None


def projects(p: dict, fresh: bool = False) -> dict:
    rows = bx.read_all("crm.deal.list", {"filter": {"CATEGORY_ID": [0], "STAGE_ID": list(WORK + SOON)}, "select": SELECT,
                                         "order": {"DATE_MODIFY": "DESC"}}, fresh=fresh)
    st = bx.stages()
    names = {u["id"]: u["name"] for u in bx.users()}
    see_sum = p["role_code"] in bx.BX_ROLES
    ids = [int(d["ID"]) for d in rows]
    done, who = {}, {}
    if ids:
        with db.pool.connection() as conn:
            for r in conn.execute("""SELECT object_id, count(*) AS n, coalesce(sum(area_m2), 0) AS m2, max(started_at) AS last
                                     FROM shifts WHERE object_id = ANY(%s) AND status <> 'rejected' GROUP BY object_id""", (ids,)).fetchall():
                done[r["object_id"]] = r
            for r in conn.execute("""SELECT DISTINCT s.object_id, pe.full_name FROM shifts s JOIN people pe ON pe.id = s.person_id
                                     WHERE s.object_id = ANY(%s) AND s.status <> 'rejected' AND s.started_at > now() - interval '4 days'
                                     ORDER BY s.object_id, pe.full_name""", (ids,)).fetchall():
                who.setdefault(r["object_id"], []).append(r["full_name"])
    today, out = date.today(), []
    for d in rows:
        did = int(d["ID"])
        working = d["STAGE_ID"] in WORK
        start = (_started(did, fresh) if working else None) or (_d(d.get("DATE_MODIFY")) if working else None)
        term = int(bx._num(d.get(bx.F_TERM))) or 0
        if not term:
            try:
                term = int(str(d.get(F_DAYS) or "0").split()[0])
            except ValueError:
                term = 0
        due = work_days(start, term) if start and term else None
        dn = done.get(did)
        shifts_norm = bx._num(d.get(bx.F_SHIFTS))
        shifts_done = int(dn["n"]) if dn else 0
        progress = min(100, round(shifts_done / shifts_norm * 100)) if shifts_norm else None
        left = (due - today).days if due else None
        state = ("soon" if not working else "late" if left is not None and left < 0 else "today" if left == 0
                 else "quiet" if dn and dn["last"] and (datetime.now(timezone.utc) - dn["last"]).days >= 3 else "idle" if not dn else "ok")
        out.append({"id": did, "title": d.get("TITLE") or "", "stage": d["STAGE_ID"], "stage_name": (st.get(d["STAGE_ID"]) or {}).get("name", d["STAGE_ID"]),
                    "working": working, "city": bx.city_name(d.get(bx.CITY)), "address": (d.get(bx.ADDR) or "").split("|")[0] if isinstance(d.get(bx.ADDR), str) else "",
                    "manager": names.get(int(d.get("ASSIGNED_BY_ID") or 0), ""), "area": bx._num(d.get(bx.AREA)),
                    "level": bx.LEVELS.get(bx.level_key(d.get(bx.F_LEVEL)), ""), "sum": bx._num(d.get("OPPORTUNITY")) if see_sum else None,
                    "norm": {"shifts": shifts_norm, "crew": bx._num(d.get(bx.F_CREW)), "term": term},
                    "start": start.isoformat() if start else None, "due": due.isoformat() if due else None, "left": left,
                    "done": {"shifts": shifts_done, "m2": float(dn["m2"]) if dn else 0, "last": dn["last"].isoformat() if dn and dn["last"] else None},
                    "progress": progress, "people": who.get(did, []), "state": state})
    order = {"late": 0, "today": 1, "quiet": 2, "idle": 3, "ok": 4, "soon": 5}
    out.sort(key=lambda x: (order[x["state"]], x["left"] if x["left"] is not None else 999))
    return {"projects": out, "today": today.isoformat(),
            "counts": {"work": sum(x["working"] for x in out), "soon": sum(not x["working"] for x in out),
                       "late": sum(x["state"] == "late" for x in out)}}


@router.get("/bx/projects")
def api_projects(fresh: int = 0, p: dict = Depends(active)):
    return projects(p, bool(fresh))
