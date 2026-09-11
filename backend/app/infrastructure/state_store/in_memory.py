"""InMemoryStateStore — dict-backed compliance state, no external dependencies.

Thread safety
-------------
A single ``threading.Lock`` protects all dict operations.  For the current
single-worker-per-zone design, lock contention is minimal; the lock exists
to protect against accidental concurrent access if the architecture later
introduces a second worker.

Restart behaviour
-----------------
State is in-memory only.  On process restart all state is lost and every
camera/zone starts fresh from the UNKNOWN handwash state.  This is
acceptable for the MVP.  Switching to RedisStateStore (which implements
the same interface) would restore persistence without changing any caller.

StateStore must NOT store evidence (thumbnail bytes, NumPy arrays, etc.).
Callers are responsible for keeping state dicts small and JSON-serializable.
"""

from __future__ import annotations

import threading

import structlog

from .base import StateStore

logger = structlog.get_logger(__name__)


class InMemoryStateStore(StateStore):
    """Thread-safe in-memory implementation of :class:`StateStore`."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._closed = False

    def get(self, key: str) -> dict | None:
        with self._lock:
            self._assert_open()
            value = self._store.get(key)
            if value is not None:
                return dict(value)  # defensive copy — callers must not mutate the store
            return None

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            self._assert_open()
            self._store[key] = dict(value)  # store a copy so mutations don't bleed

    def close(self) -> None:
        with self._lock:
            self._store.clear()
            self._closed = True
        logger.debug("state_store_closed", backend="in_memory")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("StateStore is closed")
