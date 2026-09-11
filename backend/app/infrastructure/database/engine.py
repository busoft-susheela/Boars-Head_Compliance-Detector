"""SQLAlchemy engine + thread-safe session factory.

Design notes
------------
- Uses psycopg2 (sync driver) — matches the threading model of the rest of the
  application.  No async driver is introduced.
- ``scoped_session`` provides a thread-local session so each worker thread gets
  its own connection; no session sharing across threads.
- ``pool_pre_ping=True`` detects stale connections and reconnects automatically.
- ``Database.session()`` is a context-manager that commits on exit and rolls
  back on exception; always call ``scoped_session.remove()`` in the finally
  block to return the connection to the pool.
- A module-level singleton is enforced via ``get_database()`` / ``close_database()``.
  Direct ``Database(...)`` construction is still allowed for isolated tests.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Generator

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker

logger = structlog.get_logger(__name__)

# ── Singleton state ───────────────────────────────────────────────────────────
_instance: Database | None = None
_lock = threading.Lock()


def build_database_url() -> str:
    """Build a psycopg2 URL from individual POSTGRES_* env vars.

    Falls back to DATABASE_URL if individual vars are not set.
    Raises RuntimeError if neither are available.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5433")
    user = os.environ.get("POSTGRES_USERNAME", "Postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "bh_cv")

    # URL-encode common special characters in the password.
    password = password.replace("%", "%25").replace("@", "%40").replace("#", "%23")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


class Database:
    """Encapsulates engine creation, session factory, and pool lifecycle.

    Args:
        url:             SQLAlchemy database URL.
        pool_max_size:   Maximum number of pooled connections.
        timeout_seconds: Connection acquisition timeout.
    """

    def __init__(
        self,
        url: str,
        pool_max_size: int = 10,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._engine = create_engine(
            url,
            pool_size=pool_max_size,
            pool_pre_ping=True,
            pool_timeout=timeout_seconds,
            connect_args={"connect_timeout": max(1, int(timeout_seconds))},
            future=True,
        )
        self._session_factory: scoped_session = scoped_session(
            sessionmaker(bind=self._engine, expire_on_commit=False)
        )
        logger.info("database_engine_created", pool_max_size=pool_max_size)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Provide a transactional session for one unit of work.

        Commits on clean exit, rolls back on any exception, and always
        removes the thread-local session when done.
        """
        sess: Session = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            self._session_factory.remove()

    def check_health(self) -> bool:
        """Return True if the database connection is alive (SELECT 1)."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            logger.warning("database_health_check_failed")
            return False

    def close(self) -> None:
        """Dispose the connection pool on shutdown."""
        self._session_factory.remove()
        self._engine.dispose()
        logger.info("database_pool_disposed")


# ── Module-level singleton helpers ────────────────────────────────────────────

def get_database(
    url: str,
    pool_max_size: int = 10,
    timeout_seconds: float = 10.0,
) -> "Database":
    """Return the process-wide ``Database`` singleton, creating it on first call.

    Subsequent calls return the same instance regardless of the arguments
    passed — the pool is created once and shared for the lifetime of the
    process.  Use ``close_database()`` during shutdown to dispose the pool.
    """
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = Database(
                    url=url,
                    pool_max_size=pool_max_size,
                    timeout_seconds=timeout_seconds,
                )
    return _instance


def close_database() -> None:
    """Close the singleton ``Database`` and reset it so the next call to
    ``get_database()`` creates a fresh pool (useful for clean shutdown and
    test teardown).
    """
    global _instance
    with _lock:
        if _instance is not None:
            _instance.close()
            _instance = None
