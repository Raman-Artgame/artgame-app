"""Объекты из Битрикса (только чтение). Таймер каждые 10 минут: python -m artgame.sync_objects

Сделка воронки 0 «1.1 Продажи РК» на этапе «Отправка счета/договора» (FINAL_INVOICE) и дальше → объект в приложении
и папка на Диске с подпапками. WON → объект «done». Сумму сделки не забираем (художникам не видно).
"""
import httpx

from . import db, drive
from .config import settings

CATEGORY = 0
ACTIVE = ("FINAL_INVOICE", "UC_AV00QK", "UC_BMKDS4")
DONE = ("WON",)


def fetch_deals() -> list[dict]:
    url = settings.bitrix_read_url.rstrip("/") + "/crm.deal.list.json"
    out, start = [], 0
    while start is not None:
        r = httpx.post(url, timeout=60, json={
            "filter": {"CATEGORY_ID": CATEGORY, "STAGE_ID": list(ACTIVE + DONE)},
            "select": ["ID", "TITLE", "STAGE_ID", "CATEGORY_ID"], "start": start})
        r.raise_for_status()
        j = r.json()
        out += j.get("result", [])
        start = j.get("next")
    return out


def upsert(conn, deals: list[dict]) -> list[int]:
    """Возвращает ID новых объектов."""
    new = []
    for d in deals:
        status = "done" if d["STAGE_ID"] in DONE else "active"
        row = conn.execute(
            """INSERT INTO objects (id, title, bitrix_stage, bitrix_category, status, synced_at)
               VALUES (%s,%s,%s,%s,%s,now())
               ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, bitrix_stage=EXCLUDED.bitrix_stage,
                   status=CASE WHEN objects.status='archived' THEN 'archived' ELSE EXCLUDED.status END, synced_at=now()
               RETURNING (xmax = 0) AS inserted""",
            (int(d["ID"]), d["TITLE"].strip(), d["STAGE_ID"], int(d["CATEGORY_ID"]), status)).fetchone()
        if row["inserted"]:
            new.append(int(d["ID"]))
    return new


def main():
    if not settings.bitrix_read_url:
        print("ARTGAME_BITRIX_READ_URL не задан — пропуск")
        return
    p = db.open_pool()
    deals = fetch_deals()
    with p.connection() as conn:
        new = upsert(conn, deals)
        made = 0
        for o in conn.execute("SELECT * FROM objects WHERE status='active' AND id<>0 AND (drive_folder IS NULL OR folders='{}')").fetchall():
            try:
                drive.ensure_folders(conn, o)
                made += 1
            except Exception as ex:
                print(f"folder {o['id']}: {ex}")
        if new:
            db.audit(conn, None, "objects_sync", data={"new": new})
    print(f"deals={len(deals)} new={len(new)} folders={made}")


if __name__ == "__main__":
    main()
