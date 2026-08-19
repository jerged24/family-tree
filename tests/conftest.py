"""Shared pytest fixtures: isolated in-memory SQLite sessions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models  # noqa: F401  (registers mappers on Base.metadata)
from backend.app.config import settings
from backend.app.models.base import Base

FIXTURES = Path(__file__).parent / "fixtures"


def _new_session() -> Session:
    """A fresh, independent in-memory database with foreign keys enforced."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection == one in-memory DB
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture
def db() -> Session:
    session = _new_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def new_session() -> Callable[[], Session]:
    """Factory for additional independent sessions (e.g. round-trip re-import)."""
    return _new_session


@pytest.fixture
def sample_ged() -> str:
    return (FIXTURES / "sample_551.ged").read_text(encoding="utf-8")


@pytest.fixture
def client():
    """A FastAPI TestClient wired to an isolated in-memory database.

    The TestClient is created without a ``with`` block so the app lifespan (which
    would init the real file DB) does not run; the schema comes from this fixture's
    in-memory engine instead, injected via a ``get_db`` dependency override.
    """
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.main import app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        test_client = TestClient(app)
        test_client.post("/admin/login", json={"password": settings.admin_password})
        yield test_client
    finally:
        app.dependency_overrides.clear()
