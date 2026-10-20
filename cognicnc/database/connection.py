
"""SQLAlchemy engine, session factory, and database manager.

Supports both:
1. Existing AppConfig-based application access.
2. Direct SQLite paths for isolated integration tests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cognicnc.config import AppConfig

logger = logging.getLogger("cognicnc.database")

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None
_engine_key: Optional[str] = None


def _create_engine(db_path: Path, echo: bool = False) -> Engine:
    """Create an engine for a specific SQLite database file."""
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        echo=echo,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    logger.info("Database engine created: %s", db_path)
    return engine


def _set_cached_engine(engine: Engine, key: str) -> Engine:
    """Update the shared engine and session factory."""
    global _engine, _SessionFactory, _engine_key

    if _engine is not None and _engine is not engine:
        _engine.dispose()

    _engine = engine
    _SessionFactory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    _engine_key = key
    return engine


def get_engine(config: AppConfig) -> Engine:
    """Return the cached engine for the configured application database."""
    db_path = (
        Path(config.resolved_path("database")) / "cognicnc.sqlite"
    ).resolve()
    key = str(db_path)

    if _engine is None or _engine_key != key:
        return _set_cached_engine(_create_engine(db_path), key)

    return _engine


def get_session_factory(config: AppConfig) -> sessionmaker:
    """Return a session factory bound to the configured engine."""
    engine = get_engine(config)

    if _SessionFactory is None or _SessionFactory.kw.get("bind") is not engine:
        return _set_cached_engine(engine, str(engine.url.database)) and _SessionFactory

    return _SessionFactory


def get_session(config: AppConfig) -> Session:
    """Create a new session. The caller is responsible for closing it."""
    return get_session_factory(config)()


def reset_engine() -> None:
    """Dispose the cached engine and clear the global cache."""
    global _engine, _SessionFactory, _engine_key

    if _engine is not None:
        _engine.dispose()

    _engine = None
    _SessionFactory = None
    _engine_key = None
    logger.info("Database engine cache reset.")


class DatabaseManager:
    """Database manager compatible with integration tests and repositories."""

    def __init__(
        self,
        sqlite_path: str | Path,
        echo: bool = False,
    ) -> None:
        self.sqlite_path = Path(sqlite_path).resolve()
        self.engine = _create_engine(self.sqlite_path, echo=echo)
        self.SessionFactory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self._closed = False

    def create_tables(self) -> None:
        """Create all ORM tables for this database."""
        from cognicnc.database.models import Base

        Base.metadata.create_all(self.engine)
        logger.info("Database tables created: %s", self.sqlite_path)

    def get_session(self) -> Session:
        """Create a session for this database."""
        if self._closed:
            raise RuntimeError("DatabaseManager is closed.")
        return self.SessionFactory()

    def close(self) -> None:
        """Dispose this manager's engine."""
        if not self._closed:
            self.engine.dispose()
            self._closed = True
            logger.info("Database manager closed: %s", self.sqlite_path)

