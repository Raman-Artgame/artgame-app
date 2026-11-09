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
