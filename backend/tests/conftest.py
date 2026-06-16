"""Test fixtures: route the whole test session at a throwaway SQLite DB.

Must set DATABASE_URL before any backend module imports the engine."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/tipovi_test.db")
os.environ.setdefault("RUN_WORKER_IN_API", "false")
os.environ.setdefault("RUN_SCRAPE_ON_STARTUP", "false")

import pytest

from backend.models import init_db, SessionLocal
from backend.models.models import Match, Prediction, MyTip, Result


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture
def db_session():
    db = SessionLocal()
    # clean slate
    for model in (MyTip, Result, Prediction, Match):
        db.query(model).delete()
    db.commit()
    try:
        yield db
    finally:
        db.close()
