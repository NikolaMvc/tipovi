"""SQLAlchemy engine / session setup. Works with both PostgreSQL (production)
and SQLite (zero-config local dev / tests)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from backend.config import settings

_url = settings.DATABASE_URL
# Normalize the bare "postgresql://" form (e.g. from Railway) to the psycopg2 driver.
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg2://", 1)
elif _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}

engine = create_engine(_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables directly (used for SQLite/dev; production uses Alembic)."""
    import backend.models.models  # noqa: F401  (register models)
    Base.metadata.create_all(bind=engine)
