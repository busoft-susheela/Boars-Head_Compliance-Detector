"""RedisStateStore — Redis-backed compliance state persistence.

Stores each zone's state dict as a JSON string under a prefixed key.
Uses the shared RedisConnectionManager pool (no extra connections).

Key scheme
----------
    {key_prefix}:{camera_id}:{zone_id}
    e.g.  cv:state:handwash-camera-01:handwash_zone

TTL
---
Each key is written with an expiry (default 1 hour).  This prevents stale
state from a crashed session blocking a new one indefinitely.  The TTL is
reset on every ``set()`` call so an active session never expires mid-run.

Thread safety
-------------
All Redis client calls are thread-safe.  The ComplianceWorker serialises
access per zone (single thread), so no additional locking is needed here.
"""

from __future__ import annotations

import json

import structlog

from backend.app.infrastructure.state_store.base import StateStore

logger = structlog.get_logger(__name__)


class RedisStateStore(StateStore):
    """Redis-backed implementation of :class:`StateStore`.

    Args:
        connection:  Shared :class:`RedisConnectionManager` instance.
        key_prefix:  Namespace prefix for all state keys in Redis.
        ttl_seconds: Expiry for each key in seconds.  Reset on every write.
    """

    def __init__(
        self,
        connection,
        key_prefix: str = "cv:state",
        ttl_seconds: int = 3600,
    ) -> None:
        self._client = connection.client
        self._prefix = key_prefix
        self._ttl = ttl_seconds
        logger.info(
            "redis_state_store_initialized",
            key_prefix=key_prefix,
            ttl_seconds=ttl_seconds,
        )

    def get(self, key: str) -> dict | None:
        """Return the stored state dict, or ``None`` if absent or expired."""
        raw = self._client.get(self._make_key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception as exc:
            logger.error(
                "redis_state_store_decode_error",
                key=key,
                error=str(exc),
            )
            return None

    def set(self, key: str, value: dict) -> None:
        """Serialise ``value`` as JSON and persist under ``key``."""
        try:
            self._client.set(
                self._make_key(key),
                json.dumps(value),
                ex=self._ttl,
            )
        except Exception as exc:
            logger.error(
                "redis_state_store_write_error",
                key=key,
                error=str(exc),
            )

    def close(self) -> None:
        """No-op — connection pool is managed by RedisConnectionManager."""
        logger.debug("state_store_closed", backend="redis")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _make_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"
