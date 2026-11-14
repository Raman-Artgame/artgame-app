"""Ночные и длинные смены (HEAD 09.11): ночь 00:00–06:00 +pay.night % к часу, сверх нормы — по часовой ставке."""
from datetime import datetime, timedelta

from artgame.finance import TZ, night_hours, shift_pay

V = {"shift.hours": 10, "pay.artist.shift": 15000, "pay.artist.hour": 1500, "pay.night": 10, "pay.night.from": "0:00", "pay.night.to": "6:00"}


def t(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=TZ)


def test_night_hours():
    assert night_hours(V, t(7, 9), t(7, 19)) == 0
    assert night_hours(V, t(7, 18), t(8, 4)) == 4          # 00:00–04:00
    assert night_hours(V, t(7, 9), t(7, 9) + timedelta(hours=34)) == 6   # 34 ч: одна ночь целиком
    assert night_hours(V, t(7, 20), t(9, 7)) == 12          # две ночи
    assert night_hours({**V, "pay.night.from": "22:00"}, t(7, 21), t(7, 23)) == 1


def test_shift_pay_overtime_and_night():
    assert shift_pay(V, "artist", 10) == (15000, "")
    assert shift_pay(V, "artist", 5) == (7500, "")
    assert shift_pay(V, "artist", 34)[0] == 15000 + 24 * 1500            # сверх 10 ч — по часу
    assert shift_pay(V, "artist", 10, night=4)[0] == 15000 + 4 * 150     # ночь +10 % к часу
    assert shift_pay({**V, "pay.night": 0}, "artist", 10, night=4)[0] == 15000


def test_no_night_keys_no_night():
    assert night_hours({"pay.night": 10}, t(7, 18), t(8, 4)) == 0


def test_night_from_constants_into_payroll(client, monkeypatch):
    """12.11: время ночи в «Значениях» — строкой («22:00»); раньше vals() его отбрасывал и ночь в ФОТ не начислялась."""
    from psycopg.types.json import Jsonb

    from artgame import db
    from test_appeals import approved_shift, piece
    from test_finance import setup
    ids = setup(client, monkeypatch)
    with db.pool.connection() as c:
        row = c.execute("SELECT id, values FROM constants_versions ORDER BY id DESC LIMIT 1").fetchone()
        v = dict(row["values"])
        for k, x in {"pay.night": "10", "pay.night.from": "22:00", "pay.night.to": "06:00"}.items():
            v[k] = {"value": x, "status": "Утверждено", "who": "head"}
        c.execute("UPDATE constants_versions SET values=%s WHERE id=%s", (Jsonb(v), row["id"]))
    approved_shift(client, 2000, "2026-11-04T14:00:00+05:00", "2026-11-05T00:00:00+05:00")   # 10 ч, из них 2 ночных
    assert piece(client, "2026-11", ids[2000])["piece"][0] == 15000 + 2 * 150
