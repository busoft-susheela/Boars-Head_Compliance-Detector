"""InMemoryFrameStore — dict-backed ephemeral frame storage with TTL eviction.

Frames are stored in a plain dict keyed by frame_id.  Each entry records its
insertion time so that frames not consumed within the TTL can be evicted.

Eviction strategy
-----------------
- On every put() call, evict_expired() is called first.
  This ensures memory stays bounded without a background thread.
- On get(), the frame is removed immediately (consumed).
- If the consumer never reads a frame (e.g. inference is stopped), it expires
  naturally on the next put() cycle.

Thread safety
-------------
A single threading.Lock protects all dict operations.  The ingestion thread
writes; the inference thread reads.  Lock contention is minimal because each
critical section is short (no I/O, no heavy computation).
"""

import threading
import time
from dataclasses import dataclass

import numpy as np
import structlog

from .base import FrameStore

logger = structlog.get_logger(__name__)


@dataclass
class _Entry:
    frame: np.ndarray
    inserted_at: float   # time.monotonic() timestamp


class InMemoryFrameStore(FrameStore):
    """Thread-safe in-memory frame store.

    Args:
        ttl_seconds: Frames not consumed within this many seconds are evicted.
    """

    def __init__(self, ttl_seconds: float = 5.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds!r}")
        self._ttl = ttl_seconds
        self._store: dict[int, _Entry] = {}
        self._lock = threading.Lock()
        self._evicted_total: int = 0

    @property
    def evicted_total(self) -> int:
        """Total frames evicted due to TTL expiry (never consumed)."""
        return self._evicted_total

    def put(self, frame_id: int, frame: np.ndarray) -> None:
        expired = self.evict_expired()
        if expired:
            logger.debug("frame_store_eviction", count=expired, ttl=self._ttl)
        with self._lock:
            self._store[frame_id] = _Entry(frame=frame, inserted_at=time.monotonic())

    def get(self, frame_id: int) -> np.ndarray | None:
        with self._lock:
            entry = self._store.pop(frame_id, None)
        return entry.frame if entry is not None else None

    def evict_expired(self) -> int:
        cutoff = time.monotonic() - self._ttl
        with self._lock:
            expired_ids = [
                fid for fid, entry in self._store.items()
                if entry.inserted_at < cutoff
            ]
            for fid in expired_ids:
                del self._store[fid]
            self._evicted_total += len(expired_ids)
        return len(expired_ids)

    def size(self) -> int:
        with self._lock:
            return len(self._store)
