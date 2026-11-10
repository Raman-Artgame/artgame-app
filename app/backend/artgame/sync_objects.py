"""Объекты из Битрикса (только чтение, через шлюз ARTGAME). Таймер каждые 10 минут: python -m artgame.sync_objects

Сделка воронки 0 «1.1 Продажи РК» на этапе «Отправка счета/договора» (FINAL_INVOICE) и дальше → объект в приложении
и папка на Диске с подпапками. WON → объект «done». Сумму сделки не забираем (художникам не видно).
"""
import json

import httpx

from . import db, drive
from .config import settings

CATEGORY = 0
ACTIVE = ("FINAL_INVOICE", "UC_AV00QK", "UC_BMKDS4")
DONE = ("WON",)
WORK = "UC_AV00QK"   # «Выполнение проекта»: только такие сделки можно выбрать для смен, трат и сборов (HEAD 08.11)
FOLDER_FIELD = "UF_CRM_ARTGAME_PROJECT_FOLDER_ID"
# Условия объекта для смены (HEAD 08.11 — заполняет МОП, команда видит без выбора): сложность, площадь, адрес
F_LEVEL, F_AREA, F_ADDR = "UF_CRM_ARTGAME_COMPLEXITY", "UF_CRM_ARTGAME_AREA_M2", "UF_CRM_1755520919823"  # папку сделки уже создаёт DRIVE01 — берём её, не плодим вторую


class Gateway:
    """Чтение Битрикса через шлюз ARTGAME (MCP, инструмент bitrix_read) по localhost. Своего ключа Битрикса у приложения нет."""

    def __init__(self, url: str, token: str = ""):
        self.url, self.sid, self.n = url, None, 0
        self.h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if token:
            self.h["Authorization"] = f"Bearer {token}"

    def _post(self, method: str, params: dict | None = None, notify: bool = False):
        body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self.n += 1
            body["id"] = self.n
        h = dict(self.h, **({"Mcp-Session-Id": self.sid} if self.sid else {}))
        r = httpx.post(self.url, json=body, headers=h, timeout=60)
        r.raise_for_status()
        self.sid = r.headers.get("mcp-session-id", self.sid)
        if notify:
            return None
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            msgs = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
            msg = next(m for m in msgs if m.get("id") == body["id"])
        else:
            msg = r.json()
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg["result"]

    def open(self):
        self._post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                  "clientInfo": {"name": "artgame-app", "version": "1"}})
        self._post("notifications/initialized", notify=True)
        return self

    def bitrix_read(self, method: str, params: dict):
        res = self._post("tools/call", {"name": "bitrix_read", "arguments": {"method": method, "params": params}})
        if res.get("isError"):
            raise RuntimeError(res)
        if "structuredContent" in res:
            data = res["structuredContent"]
            data = data.get("result", data) if isinstance(data, dict) and set(data) == {"result"} else data
        else:
            data = json.loads(res["content"][0]["text"])
        return data


def fetch_deals() -> list[dict]:
    if settings.gateway_url:
        rd = Gateway(settings.gateway_url, settings.gateway_token).open().bitrix_read
    else:
        from .bx import _webhook_read as rd   # шлюз не настроен — читаем вебхуком приложения
    out, start = [], 0
    while start is not None:
        j = rd("crm.deal.list", {
            "filter": {"CATEGORY_ID": CATEGORY, "STAGE_ID": list(ACTIVE + DONE)},
            "select": ["ID", "TITLE", "STAGE_ID", "CATEGORY_ID", FOLDER_FIELD, F_LEVEL, F_AREA, F_ADDR, "OPPORTUNITY"], "start": start})
        if isinstance(j, list):  # шлюз может вернуть сразу список
            out += j
            break
        out += j.get("result", [])
        start = j.get("next")
    return out


def split_title(deal_id: str, title: str) -> tuple[str, str | None]:
    """«525 · РЕСТОРАН ВОК — ШЫМКЕНТ» → («РЕСТОРАН ВОК», «ШЫМКЕНТ»). Номер в название не дублируем."""
    t = title.strip()
    for pre in (f"{deal_id} ·", f"{deal_id}·", f"№{deal_id}", f"{deal_id} "):
        if t.startswith(pre):
            t = t[len(pre):].strip(" ·-")
            break
    name, sep, city = t.rpartition(" — ")
    return (name.strip(), city.strip() or None) if sep and name.strip() else (t, None)


def _area(v) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        return None


def upsert(conn, deals: list[dict]) -> list[int]:
    """Возвращает ID новых объектов. Сумма сделки не хранится: только оценка сложности по ней (promo.guess_level)."""
    from . import constants as consts
    from .promo import guess_level, parse_geo
    v = consts.latest(conn)
    new = []
    for d in deals:
        status = "done" if d["STAGE_ID"] in DONE else "active"
        title, city = split_title(d["ID"], d["TITLE"])
        addr = d.get(F_ADDR)
        geo = parse_geo(addr)
        addr = (addr.split("|")[0].strip() or None) if isinstance(addr, str) else None
        guess = guess_level(v, _area(d.get(F_AREA)), d.get("OPPORTUNITY"))
        row = conn.execute(
            """INSERT INTO objects (id, title, city, bitrix_stage, bitrix_category, status, drive_folder, synced_at, level, area_m2, address, geo, level_guess)
               VALUES (%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, city=EXCLUDED.city, bitrix_stage=EXCLUDED.bitrix_stage,
                   level=EXCLUDED.level, area_m2=EXCLUDED.area_m2, address=EXCLUDED.address, geo=EXCLUDED.geo, level_guess=EXCLUDED.level_guess,
                   drive_folder=coalesce(objects.drive_folder, EXCLUDED.drive_folder),
                   status=CASE WHEN objects.status='archived' THEN 'archived' ELSE EXCLUDED.status END, synced_at=now(),
                   left_work_at=CASE WHEN objects.bitrix_stage='UC_AV00QK' AND EXCLUDED.bitrix_stage<>'UC_AV00QK' THEN now()
                                     ELSE objects.left_work_at END
               RETURNING (xmax = 0) AS inserted""",
            (int(d["ID"]), title, city, d["STAGE_ID"], int(d["CATEGORY_ID"]), status, d.get(FOLDER_FIELD) or None,
             str(d.get(F_LEVEL) or "") or None, _area(d.get(F_AREA)), addr, geo, guess)).fetchone()
        if row["inserted"]:
            new.append(int(d["ID"]))
    return new


def main():
    if not settings.gateway_url and not settings.bitrix_webhook:
        print("нет ни шлюза (ARTGAME_GATEWAY_URL), ни вебхука (ARTGAME_BITRIX_WEBHOOK) — пропуск")
        return
    p = db.open_pool()
    deals = fetch_deals()
    with p.connection() as conn:
        new = upsert(conn, deals)
        made = 0
        for o in conn.execute("SELECT * FROM objects WHERE status='active' AND id<>0 AND folders='{}'").fetchall():
            try:
                drive.ensure_folders(conn, o)
                made += 1
            except Exception as ex:
                print(f"folder {o['id']}: {ex}")
        # эскизы из «ДИЗАЙН» сделки на Диске — для живой карточки (объекты в работе, не чаще раза в 30 мин)
        from .promo import sync_designs
        got = 0
        for o in conn.execute("""SELECT * FROM objects WHERE status='active' AND id<>0 AND drive_folder IS NOT NULL
                                 AND (design_synced_at IS NULL OR design_synced_at < now() - interval '30 minutes')
                                 ORDER BY (bitrix_stage=%s) DESC LIMIT 30""", (WORK,)).fetchall():
            try:
                got += sync_designs(conn, o)
            except Exception as ex:
                print(f"designs {o['id']}: {ex}")
        if new:
            db.audit(conn, None, "objects_sync", data={"new": new})
    print(f"deals={len(deals)} new={len(new)} folders={made} designs+={got}")


if __name__ == "__main__":
    main()
