import time

import pytest

from artgame.telegram import InitDataError, verify_init_data
from conftest import TOKEN, make_init_data


def test_valid():
    u = verify_init_data(make_init_data({"id": 5, "username": "a"}), TOKEN, 3600)
    assert u["id"] == 5


def test_wrong_token():
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data({"id": 5}, token="999:other"), TOKEN, 3600)


def test_tampered():
    d = make_init_data({"id": 5}).replace("%22id%22%3A5", "%22id%22%3A6")
    with pytest.raises(InitDataError):
        verify_init_data(d, TOKEN, 3600)


def test_expired():
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data({"id": 5}, auth_date=int(time.time()) - 7200), TOKEN, 3600)


def test_no_token_configured():
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data({"id": 5}), "", 3600)
