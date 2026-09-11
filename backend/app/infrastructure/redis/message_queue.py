"""RedisStreamMessageQueue — Redis Streams backed MessageQueue.

Delivery model
--------------
- ``publish()``  → XADD with approximate MAXLEN trimming.
- ``get()``      → XREADGROUP (new messages) with blocking timeout.
- ACK            → XACK immediately after successful deserialization.
- Recovery       → XAUTOCLAIM reclaims pending messages idle longer than
                   ``pending_idle_timeout_ms``; runs inside ``get()`` on a
                   time-gated cadence (``recovery_interval_seconds``).

Consumer groups
---------------
One consumer group per stream (``stream_name:workers``).  The group is created
lazily on first ``get()`` call via XGROUP CREATE … MKSTREAM so that the stream
and group exist before any consumer tries to read.

Invalid messages
----------------
If ``deserialize()`` returns ``None`` the message is still ACKed (ACK-and-skip)
and ``queue.Empty`` is raised so the caller can loop normally.

Thread safety
-------------
``redis-py`` ConnectionPool is thread-safe.  The ``_last_recovery`` dict is
guarded by a lock to prevent multiple threads accidentally triggering concurrent
recovery for the same topic.
"""
from __future__ import annotations

import queue
import socket
import threading
import time
from typing import Any

import redis.exceptions
import structlog

from backend.app.infrastructure.message_queue.base import MessageQueue
from backend.app.infrastructure.redis.config import RedisConfig
from backend.app.infrastructure.redis.connection import RedisConnectionManager
from backend.app.infrastructure.redis.metrics import RedisMetrics
from backend.app.infrastructure.redis.serialization import deserialize, serialize

logger = structlog.get_logger(__name__)

_FIELD = b"data"  # decode_responses=False → bytes keys in result dicts


class RedisStreamMessageQueue(MessageQueue):
    """Redis Streams backed MessageQueue with at-least-once delivery.

    Args:
        connection:    Shared Redis connection manager.
        config:        Redis configuration (stream names, consumer settings).
        metrics:       Shared metrics counter.
        consumer_name: Stable consumer identity for this process.
                       Defaults to the machine hostname.
    """

    def __init__(
        self,
        connection: RedisConnectionManager,
        config: RedisConfig,
        metrics: RedisMetrics,
        *,
        consumer_name: str | None = None,
    ) -> None:
        self._client = connection.client
        self._config = config
        self._metrics = metrics
        self._consumer_name = consumer_name or socket.gethostname()
        # topic → last recovery timestamp (monotonic)
        self._last_recovery: dict[str, float] = {}
        self._lock = threading.Lock()
        # tracks which (stream, group) pairs have already been initialised
        self._groups_initialised: set[tuple[str, str]] = set()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _stream(self, topic: str) -> str:
        return self._config.streams.stream_for_topic(topic)

    def _group(self, topic: str) -> str:
        return self._config.streams.consumer_group_for_topic(topic)

    def _ensure_group(self, stream: str, group: str) -> None:
        """Create consumer group if it does not yet exist (idempotent).

        Only issues the XGROUP CREATE command once per (stream, group) pair
        for the lifetime of this instance — avoids hammering Redis on every
        get() call.
        """
        key = (stream, group)
        if key in self._groups_initialised:
            return
        try:
            self._client.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("redis_consumer_group_created", stream=stream, group=group)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                logger.warning(
                    "redis_xgroup_create_error",
                    stream=stream,
                    group=group,
                    error=str(exc),
                )
        # Mark as initialised regardless — group either existed or was just created.
        self._groups_initialised.add(key)

    def _is_recovery_due(self, topic: str) -> bool:
        interval = self._config.consumer.recovery_interval_seconds
        with self._lock:
            last = self._last_recovery.get(topic, 0.0)
            if time.monotonic() - last >= interval:
                self._last_recovery[topic] = time.monotonic()
                return True
        return False

    def _try_recover_pending(self, topic: str, stream: str, group: str) -> Any | None:
        """Claim one idle pending message via XPENDING + XCLAIM (Redis 5.x compatible).

        XAUTOCLAIM requires Redis 6.2+. We use XPENDING to list idle messages
        and XCLAIM to take ownership, which works on Redis 5.0+.

        The `idle` filter parameter in xpending_range also requires Redis 6.2+.
        On Redis 5.x we fetch pending entries without the idle filter and skip
        any that haven't been idle long enough yet.
        """
        idle_ms = self._config.consumer.pending_idle_timeout_ms
        try:
            # XPENDING stream group - + count → list pending entries (no idle= filter,
            # Redis 5.x compatible). We manually check idle time below.
            pending = self._client.xpending_range(
                stream,
                group,
                min="-",
                max="+",
                count=1,
            )
            if not pending:
                return None

            entry = pending[0]
            msg_id = entry["message_id"]

            # Manual idle check — entry["time_since_delivered"] is in ms (Redis 5.x).
            if entry.get("time_since_delivered", 0) < idle_ms:
                return None

            # XCLAIM to take ownership of the message
            claimed = self._client.xclaim(
                stream,
                group,
                self._consumer_name,
                min_idle_time=idle_ms,
                message_ids=[msg_id],
            )
            if not claimed:
                return None

            fields = claimed[0][1]
            data_bytes = fields.get(_FIELD)
            obj = deserialize(topic, data_bytes)
            self._client.xack(stream, group, msg_id)
            self._metrics.record_ack()
            self._metrics.record_pending_recovered()
            if obj is None:
                self._metrics.record_processing_failure()
            return obj
        except Exception:
            logger.exception("redis_pending_recovery_failed", stream=stream)
            return None

    # ── MessageQueue interface ────────────────────────────────────────────────

    def publish(self, topic: str, message: Any) -> None:
        stream = self._stream(topic)
        try:
            data = serialize(topic, message)
            self._client.xadd(
                stream,
                {_FIELD: data},
                maxlen=self._config.streams.max_length,
                approximate=self._config.streams.approximate_trim,
            )
            self._metrics.record_publish()
        except Exception:
            logger.exception("redis_publish_failed", topic=topic)
            self._metrics.record_publish_failure()

    def get(self, topic: str, timeout: float | None = None) -> Any:
        """Consume the next message from a stream topic.

        Blocks up to ``timeout`` seconds (None = forever).
        Raises ``queue.Empty`` if the timeout elapses or the message is invalid.
        """
        stream = self._stream(topic)
        group = self._group(topic)
        self._ensure_group(stream, group)

        # Time-gated pending recovery — check before reading new messages.
        if self._is_recovery_due(topic):
            obj = self._try_recover_pending(topic, stream, group)
            if obj is not None:
                return obj

        # Translate Python timeout to Redis block milliseconds.
        if timeout is None:
            block_ms = 0          # block forever
        elif timeout <= 0:
            block_ms = None       # non-blocking
        else:
            block_ms = int(timeout * 1000)

        try:
            results = self._client.xreadgroup(
                group,
                self._consumer_name,
                {stream: ">"},
                count=1,
                block=block_ms,
            )
        except redis.exceptions.TimeoutError:
            # Socket timed out while blocking for a new message — normal when
            # no messages arrive within the socket timeout window.  Treat as
            # an empty result so the worker loops and checks the stop flag.
            raise queue.Empty
        except Exception:
            logger.exception("redis_xreadgroup_failed", topic=topic)
            self._metrics.record_connection_failure()
            raise queue.Empty

        if not results:
            raise queue.Empty

        self._metrics.record_stream_read()
        _stream_bytes, messages = results[0]
        msg_id, fields = messages[0]
        data_bytes = fields.get(_FIELD)

        obj = deserialize(topic, data_bytes)

        # ACK regardless — invalid messages are ACK-and-skipped.
        try:
            self._client.xack(stream, group, msg_id)
            self._metrics.record_ack()
        except Exception:
            logger.warning("redis_xack_failed", topic=topic, msg_id=msg_id)

        if obj is None:
            self._metrics.record_processing_failure()
            raise queue.Empty

        return obj

    def qsize(self, topic: str) -> int:
        """Approximate number of entries in the stream (not pending count)."""
        stream = self._stream(topic)
        try:
            return self._client.xlen(stream)
        except Exception:
            logger.exception("redis_xlen_failed", topic=topic)
            return 0
