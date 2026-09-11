"""InMemoryMessageQueue — one queue.Queue per topic, for single-process deployments.

This is the MVP backend.  It is thread-safe and works directly from the sync
ingestion thread.  When the inference pipeline moves to asyncio, swap this for
an AsyncMessageQueue backed by asyncio.Queue without changing any producer or
consumer code.

Backpressure
------------
Each topic has a configurable max_size.  When the queue is full the oldest
message is evicted (latest-message strategy, same as BoundedBuffer) and the
drop counter is incremented.  This prevents unbounded memory growth when a
consumer falls behind.
"""

import queue
import threading
import structlog
from typing import Any

from .base import MessageQueue

logger = structlog.get_logger(__name__)


class InMemoryMessageQueue(MessageQueue):
    """Thread-safe, single-process MessageQueue backed by queue.Queue.

    Args:
        max_size_per_topic: Maximum messages held per topic before the oldest
                            is dropped.  0 = unbounded (not recommended).
    """

    def __init__(self, max_size_per_topic: int = 10) -> None:
        self._max_size = max_size_per_topic
        self._queues: dict[str, queue.Queue] = {}
        self._dropped: dict[str, int] = {}
        self._lock = threading.Lock()

    def _get_or_create(self, topic: str) -> queue.Queue:
        with self._lock:
            if topic not in self._queues:
                self._queues[topic] = queue.Queue(maxsize=self._max_size)
                self._dropped[topic] = 0
            return self._queues[topic]

    def publish(self, topic: str, message: Any) -> None:
        q = self._get_or_create(topic)
        while True:
            try:
                q.put_nowait(message)
                return
            except queue.Full:
                # Evict oldest; if a consumer already drained it, retry.
                try:
                    q.get_nowait()
                    with self._lock:
                        self._dropped[topic] += 1
                    logger.debug(
                        "message_queue_drop",
                        topic=topic,
                        total_dropped=self._dropped[topic],
                    )
                except queue.Empty:
                    pass  # concurrent consumer; retry put

    def get(self, topic: str, timeout: float | None = None) -> Any:
        q = self._get_or_create(topic)
        return q.get(timeout=timeout)

    def qsize(self, topic: str) -> int:
        q = self._get_or_create(topic)
        return q.qsize()

    def dropped_count(self, topic: str) -> int:
        """Total messages dropped for a topic due to capacity limits."""
        with self._lock:
            return self._dropped.get(topic, 0)
