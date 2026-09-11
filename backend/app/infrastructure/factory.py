"""Infrastructure factory — selects memory vs Redis backends from config.

Call ``build_frame_store()`` and ``build_message_queue()`` from the app
lifespan.  Both functions read the ``runtime`` section of the loaded config dict
and instantiate either the in-memory or Redis-backed implementation.

Redis is only constructed when explicitly configured:
    runtime:
      message_queue_backend: redis   # or: memory
      frame_store_backend:   redis   # or: memory

If the ``runtime`` section is absent the factory defaults to in-memory so
existing deployments are unaffected.

Connection pool singleton
-------------------------
Both Redis-backed components share a single ``RedisConnectionManager`` via
``RedisConnectionManager.get_shared()``.  No matter how many times the factory
functions are called, only one ConnectionPool is created per Redis URL.
``RedisMetrics`` is similarly shared so counters accumulate across all
components.
"""
from __future__ import annotations

import structlog

from backend.app.infrastructure.frame_store.base import FrameStore
from backend.app.infrastructure.frame_store.in_memory import InMemoryFrameStore
from backend.app.infrastructure.message_queue.base import MessageQueue
from backend.app.infrastructure.message_queue.in_memory import InMemoryMessageQueue
from backend.app.infrastructure.state_store.base import StateStore
from backend.app.infrastructure.state_store.in_memory import InMemoryStateStore

logger = structlog.get_logger(__name__)

# Shared Redis infrastructure — created once, reused by every component.
_redis_metrics: "RedisMetrics | None" = None  # type: ignore[name-defined]


def _get_redis_infra(cfg: dict):
    """Return (RedisConnectionManager, RedisMetrics) singletons for this process."""
    global _redis_metrics
    from backend.app.infrastructure.redis.config import RedisConfig
    from backend.app.infrastructure.redis.connection import RedisConnectionManager
    from backend.app.infrastructure.redis.metrics import RedisMetrics

    redis_cfg = RedisConfig.from_cfg(cfg.get("redis", {}))
    connection = RedisConnectionManager.get_shared(redis_cfg)   # one pool per URL
    if _redis_metrics is None:
        _redis_metrics = RedisMetrics()
    return redis_cfg, connection, _redis_metrics


def build_frame_store(
    cfg: dict,
    *,
    camera_id: str,
    frame_ttl_seconds: float = 5.0,
) -> FrameStore:
    """Build and return a FrameStore according to ``runtime.frame_store_backend``.

    Args:
        cfg:               Full loaded config dict.
        camera_id:         Camera identifier (required by the Redis key scheme).
        frame_ttl_seconds: TTL used when the in-memory backend is selected.
                           The Redis backend uses ``redis.frame_store.ttl_seconds``.

    Returns:
        Configured FrameStore implementation.
    """
    runtime = cfg.get("runtime", {})
    backend = runtime.get("frame_store_backend", "memory").lower()

    if backend == "redis":
        from backend.app.infrastructure.redis.frame_store import RedisFrameStore

        redis_cfg, connection, metrics = _get_redis_infra(cfg)
        logger.info("frame_store_backend", backend="redis", camera_id=camera_id)
        return RedisFrameStore(
            connection=connection,
            metrics=metrics,
            camera_id=camera_id,
            ttl_seconds=redis_cfg.frame_store.ttl_seconds,
            key_prefix=redis_cfg.frame_store.key_prefix,
        )

    logger.info("frame_store_backend", backend="memory")
    return InMemoryFrameStore(ttl_seconds=frame_ttl_seconds)


def build_message_queue(
    cfg: dict,
    *,
    max_size_per_topic: int = 10,
) -> MessageQueue:
    """Build and return a MessageQueue according to ``runtime.message_queue_backend``.

    Args:
        cfg:                Full loaded config dict.
        max_size_per_topic: Capacity per topic used when the in-memory backend
                            is selected.

    Returns:
        Configured MessageQueue implementation.
    """
    runtime = cfg.get("runtime", {})
    backend = runtime.get("message_queue_backend", "memory").lower()

    if backend == "redis":
        from backend.app.infrastructure.redis.message_queue import RedisStreamMessageQueue

        redis_cfg, connection, metrics = _get_redis_infra(cfg)
        logger.info("message_queue_backend", backend="redis")
        return RedisStreamMessageQueue(
            connection=connection,
            config=redis_cfg,
            metrics=metrics,
        )

    logger.info("message_queue_backend", backend="memory")
    return InMemoryMessageQueue(max_size_per_topic=max_size_per_topic)


def build_state_store(cfg: dict) -> StateStore:
    """Build and return a StateStore according to ``state_store.backend``.

    Args:
        cfg: Full loaded config dict.

    Returns:
        Configured StateStore implementation.
    """
    ss_cfg = cfg.get("state_store", {})
    backend = ss_cfg.get("backend", "in_memory").lower()

    if backend == "redis":
        from backend.app.infrastructure.state_store.redis_store import RedisStateStore

        redis_cfg, connection, _ = _get_redis_infra(cfg)
        key_prefix = ss_cfg.get("key_prefix", "cv:state")
        ttl_seconds = int(ss_cfg.get("ttl_seconds", 3600))
        logger.info("state_store_backend", backend="redis", key_prefix=key_prefix, ttl_seconds=ttl_seconds)
        return RedisStateStore(
            connection=connection,
            key_prefix=key_prefix,
            ttl_seconds=ttl_seconds,
        )

    logger.info("state_store_backend", backend="in_memory")
    return InMemoryStateStore()
