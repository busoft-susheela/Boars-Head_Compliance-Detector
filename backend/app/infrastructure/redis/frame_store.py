"""RedisFrameStore — Redis-backed ephemeral frame storage.

Frames are JPEG-encoded and stored under per-camera keys with a TTL.
Redis handles expiry natively, so evict_expired() is a no-op — it returns 0
to satisfy the FrameStore interface without scanning the keyspace.

Key format: {prefix}:{camera_id}:{frame_id}

Thread safety
-------------
redis-py ConnectionPool is thread-safe; no additional lock is needed here.
"""
from __future__ import annotations

import cv2
import numpy as np
import structlog

from backend.app.infrastructure.frame_store.base import FrameStore
from backend.app.infrastructure.redis.connection import RedisConnectionManager
from backend.app.infrastructure.redis.keys import frame_key
from backend.app.infrastructure.redis.metrics import RedisMetrics

logger = structlog.get_logger(__name__)

_DEFAULT_JPEG_QUALITY = 85


class RedisFrameStore(FrameStore):
    """Redis-backed frame store with TTL eviction.

    Frames are JPEG-compressed before storing to reduce Redis memory.
    ``GETDEL`` is used for consume-on-read semantics (matches InMemoryFrameStore).

    Args:
        connection:   Shared Redis connection manager.
        metrics:      Shared metrics counter.
        camera_id:    Camera identifier (scopes frame keys to this camera).
        ttl_seconds:  How long a frame persists in Redis before automatic eviction.
        key_prefix:   Key namespace prefix (e.g. ``"cv:frame"``).
        jpeg_quality: JPEG compression quality 1–100.
    """

    def __init__(
        self,
        connection: RedisConnectionManager,
        metrics: RedisMetrics,
        *,
        camera_id: str,
        ttl_seconds: int = 30,
        key_prefix: str = "cv:frame",
        jpeg_quality: int = _DEFAULT_JPEG_QUALITY,
    ) -> None:
        self._client = connection.client
        self._metrics = metrics
        self._camera_id = camera_id
        self._ttl = ttl_seconds
        self._prefix = key_prefix
        self._jpeg_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

    def _key(self, frame_id: int) -> str:
        return frame_key(self._prefix, self._camera_id, frame_id)

    # ── FrameStore interface ──────────────────────────────────────────────────

    def put(self, frame_id: int, frame: np.ndarray) -> None:
        ok, buf = cv2.imencode(".jpg", frame, self._jpeg_params)
        if not ok:
            logger.error("redis_frame_encode_failed", frame_id=frame_id)
            return
        key = self._key(frame_id)
        try:
            self._client.set(key, buf.tobytes(), ex=self._ttl)
            self._metrics.record_frame_put()
        except Exception:
            logger.exception("redis_frame_put_failed", frame_id=frame_id)
            self._metrics.record_connection_failure()

    def get(self, frame_id: int) -> np.ndarray | None:
        key = self._key(frame_id)
        try:
            data = self._client.getdel(key)
        except Exception:
            logger.exception("redis_frame_get_failed", frame_id=frame_id)
            self._metrics.record_connection_failure()
            return None

        self._metrics.record_frame_get()
        if data is None:
            self._metrics.record_frame_miss()
            logger.debug("redis_frame_miss", frame_id=frame_id)
            return None

        buf = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            logger.error("redis_frame_decode_failed", frame_id=frame_id)
            self._metrics.record_frame_miss()
            return None
        return frame

    def evict_expired(self) -> int:
        """No-op — Redis TTL handles expiry automatically."""
        return 0

    def size(self) -> int:
        """Return number of live frame keys for this camera (SCAN-based)."""
        pattern = f"{self._prefix}:{self._camera_id}:*".encode()
        try:
            cursor = 0
            count = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception:
            logger.exception("redis_frame_size_failed")
            return 0
