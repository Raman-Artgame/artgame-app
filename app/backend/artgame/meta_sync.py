"""Запускается таймером systemd раз в ночь: python -m artgame.meta_sync"""
import sys

from . import db, meta


def main():
    db.open_pool()
    r = meta.sync()
    print(f"ok={r['ok']} ads={r.get('ads')} ig={r.get('ig')} errors={r['errors']}")
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
