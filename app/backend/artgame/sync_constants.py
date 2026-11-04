"""Запускается таймером systemd каждые 5 минут: python -m artgame.sync_constants"""
from . import constants, db


def main():
    p = db.open_pool()
    values = constants.parse_rows(constants.fetch_rows())
    with p.connection() as conn:
        changed = constants.store_if_changed(conn, values)
        if changed:
            db.audit(conn, None, "constants_sync", data={"keys": len(values)})
    print(f"keys={len(values)} changed={changed}")


if __name__ == "__main__":
    main()
