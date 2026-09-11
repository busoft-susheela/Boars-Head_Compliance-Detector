"""BoundedBuffer — backpressure mechanism that prevents unbounded frame queuing.

Strategy "latest": when the buffer is full, the oldest (stale) frame is
discarded and the newest is retained.  For real-time CV this is preferable
to dropping the newest frame or blocking the producer.

Thread-safe: uses queue.Queue internally, safe for one producer + one consumer.
"""

import queue
from typing import Generic, TypeVar

T = TypeVar("T")


class BoundedBuffer(Generic[T]):
    def __init__(self, max_size: int = 1) -> None:
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size!r}")
        self._q: queue.Queue[T] = queue.Queue(maxsize=max_size)
        self._dropped: int = 0

    @property
    def dropped_count(self) -> int:
        """Total number of frames dropped due to the buffer being full."""
        return self._dropped

    @property
    def depth(self) -> int:
        """Current number of items waiting in the buffer."""
        return self._q.qsize()

    def put(self, item: T) -> None:
        """Add item.  If the buffer is full, evict the oldest item first."""
        while True:
            try:
                self._q.put_nowait(item)
                return
            except queue.Full:
                # Evict oldest item; if a concurrent consumer already drained
                # it, the Empty exception is silently ignored and we retry.
                try:
                    self._q.get_nowait()
                    self._dropped += 1
                except queue.Empty:
                    pass  # concurrent consumer; retry put

    def get(self, timeout: float | None = None) -> T:
        """Block until an item is available or timeout elapses."""
        return self._q.get(timeout=timeout)

    def get_nowait(self) -> T:
        """Non-blocking get; raises queue.Empty if buffer is empty."""
        return self._q.get_nowait()
