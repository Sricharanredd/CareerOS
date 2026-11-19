"""Engine and session factory. MySQL 8.0 only — no fallback, no silent switching."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.core.config import get_settings


class DatabaseConfigurationError(RuntimeError):
    """Raised when the configured database violates a hard project constraint."""


def _validate_url(raw_url: str, *, is_test: bool) -> str:
    url = make_url(raw_url)
    if url.get_backend_name() != "mysql" or url.drivername != "mysql+pymysql":
        raise DatabaseConfigurationError(
            f"CareerOS requires mysql+pymysql, got '{url.drivername}'. SQLite and other "
            "engines are not supported."
        )
    database = url.database or ""
    if not database:
        raise DatabaseConfigurationError("DATABASE_URL must name a database")
    if is_test and not database.endswith("_test"):
        raise DatabaseConfigurationError(
            f"Test mode requires a schema ending in '_test' (got '{database}')."
        )
    if not is_test and database.endswith("_test"):
        raise DatabaseConfigurationError(
            f"Refusing to run the application against test schema '{database}'."
        )
    return raw_url


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    raw_url = _validate_url(settings.active_database_url(), is_test=settings.is_test)
    return create_engine(
        raw_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=5,
        future=True,
        echo=False,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False, future=True)


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one transaction per request.

    The session is exposed on ``request.state`` so the route class can commit it
    before the response is sent (see ``app.core.routing``).
    """
    session = get_session_factory()()
    request.state.db_session = session
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """For CLI commands and background work."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)")


def assert_mysql_8() -> str:
    engine = get_engine()
    if engine.dialect.name != "mysql":
        raise DatabaseConfigurationError("Only MySQL is supported at runtime.")
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT VERSION()"))
    match = _VERSION_RE.match(str(version))
    if not match or (int(match.group(1)), int(match.group(2))) < (8, 0):
        raise DatabaseConfigurationError(f"MySQL 8.0+ required, server reports '{version}'.")
    return str(version)


def database_status() -> dict[str, object]:
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.scalar(text("SELECT 1"))
        url = make_url(str(engine.url))
        return {"ok": True, "database": url.database, "host": url.host}
    except Exception as exc:  # pragma: no cover - readiness only
        return {"ok": False, "error": type(exc).__name__}


def reset_engine_cache() -> None:
    """Tests and CLI reconfiguration only."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
