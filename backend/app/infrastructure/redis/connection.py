"""RedisConnectionManager — centralised connection pool for all Redis components.

One pool per process.  All RedisFrameStore and RedisStreamMessageQueue instances
share this manager rather than each creating their own connections.

Requirements (from redisstream.md §16)
---------------------------------------
- One configurable connection pool per process.
- Sync mode (matches threading model of the rest of the application).
- Explicit socket/connect/read timeouts.
- Health check via PING.
- Graceful close.
- Configuration-driven Redis URL.
- Optional username/password (encoded in the URL).
- Credentials never logged.

Singleton
---------
Use ``RedisConnectionManager.get_shared(config)`` to obtain the process-wide
instance for a given Redis URL.  All components (RedisFrameStore,
RedisStreamMessageQueue) must call this instead of constructing their own
manager, so the application shares exactly one ConnectionPool per Redis server.

Call ``RedisConnectionManager.reset_shared()`` in tests to get a clean slate
between test cases.
"""
from __future__ import annotations

import threading

import redis
import structlog

from backend.app.infrastructure.redis.config import RedisConfig

logger = structlog.get_logger(__name__)

# Process-level registry: Redis URL → manager instance.
_instances: dict[str, "RedisConnectionManager"] = {}
_registry_lock = threading.Lock()


class RedisConnectionManager:
    """Owns and vends the application-wide Redis connection pool.

    Args:
        config: Typed Redis configuration.
    """

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._pool = redis.ConnectionPool.from_url(
            config.url,
            socket_timeout=config.socket_timeout_seconds,
            socket_connect_timeout=config.socket_connect_timeout_seconds,
            decode_responses=False,  # We manage encoding ourselves.
            max_connections=20,
            protocol=2,  # Force RESP2; compatible with Redis 5.x+ (RESP3 requires Redis 6+)
        )
        # One shared client backed by the pool.
        self._client: redis.Redis = redis.Redis(connection_pool=self._pool)
        logger.info("redis_connection_manager_created", url=_redact(config.url))

    # ── Singleton access ──────────────────────────────────────────────────────

    @classmethod
    def get_shared(cls, config: RedisConfig) -> "RedisConnectionManager":
        """Return the process-wide shared instance for the given Redis URL.

        Creates a new manager on first call for this URL; returns the cached
        instance on every subsequent call.  Thread-safe.
        """
        with _registry_lock:
            if config.url not in _instances:
                _instances[config.url] = cls(config)
            return _instances[config.url]

    @classmethod
    def reset_shared(cls) -> None:
        """Remove all cached instances (for use in tests only)."""
        with _registry_lock:
            _instances.clear()

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def client(self) -> redis.Redis:
        """Return the shared Redis client (thread-safe)."""
        return self._client

    def check_health(self) -> bool:
        """Return True if Redis responds to PING."""
        try:
            return self._client.ping()
        except Exception:
            logger.warning("redis_health_check_failed")
            return False

    def close(self) -> None:
        """Disconnect all connections in the pool."""
        try:
            self._pool.disconnect()
            logger.info("redis_connection_pool_closed")
        except Exception:
            logger.exception("redis_connection_pool_close_error")


def _redact(url: str) -> str:
    """Strip password from a Redis URL for safe logging."""
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        if parsed.password:
            return url.replace(f":{parsed.password}@", ":***@")
    except Exception:
        pass
    return url
