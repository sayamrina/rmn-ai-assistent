from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import dates
from app.db import Database
from app.main import create_app

# a fixed Thursday, so weekdays and lead times are reproducible
TODAY = date(2026, 10, 22)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(dates, "today", lambda: TODAY)


@pytest.fixture
def db():
    return Database(":memory:", ref_day=TODAY)


@pytest.fixture
def client(db):
    return TestClient(create_app(db=db, client=None))


def next_weekday(weekday: int) -> date:
    return TODAY + timedelta(days=(weekday - TODAY.weekday()) % 7 or 7)
