"""Запускается таймером systemd раз в ночь: python -m artgame.meta_sync"""
import sys

from . import adrules, db, meta


def main():
    db.open_pool()
    r = meta.sync()
    print(f"ok={r['ok']} ads={r.get('ads')} ig={r.get('ig')} hints={r.get('hints')} errors={r['errors']}")
    today = adrules._today()
    if today.weekday() == 0:        # понедельник: отчёт за прошлую неделю файлом на Диск
        try:
            print("report:", adrules.export_week(today))
        except Exception as e:  # noqa: BLE001
            print(f"report failed: {type(e).__name__}: {e}")
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
