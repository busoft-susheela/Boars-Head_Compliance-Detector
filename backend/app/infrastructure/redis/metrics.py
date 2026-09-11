"""Redis operational metrics — thread-safe counters.

Exposed through the /health endpoint alongside existing ingestion/inference
metrics rather than as a separate monitoring mechanism.
"""
from __future__ import annotations

import threading


class RedisMetrics:
    """Thread-safe counters for Redis stream and FrameStore operations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Connection
        self.connection_failures: int = 0

        # Stream publishing
        self.publish_total: int = 0
        self.publish_failure_total: int = 0

        # Stream reading / processing
        self.stream_read_total: int = 0
        self.stream_ack_total: int = 0
        self.stream_processing_failure_total: int = 0
        self.stream_pending_recovered: int = 0

        # FrameStore
        self.frame_store_put_total: int = 0
        self.frame_store_get_total: int = 0
        self.frame_store_miss_total: int = 0
        self.frame_store_expired_total: int = 0

    # ── Increment helpers ─────────────────────────────────────────────────────

    def record_publish(self) -> None:
        with self._lock:
            self.publish_total += 1

    def record_publish_failure(self) -> None:
        with self._lock:
            self.publish_failure_total += 1

    def record_stream_read(self) -> None:
        with self._lock:
            self.stream_read_total += 1

    def record_ack(self) -> None:
        with self._lock:
            self.stream_ack_total += 1

    def record_processing_failure(self) -> None:
        with self._lock:
            self.stream_processing_failure_total += 1

    def record_pending_recovered(self) -> None:
        with self._lock:
            self.stream_pending_recovered += 1

    def record_connection_failure(self) -> None:
        with self._lock:
            self.connection_failures += 1

    def record_frame_put(self) -> None:
        with self._lock:
            self.frame_store_put_total += 1

    def record_frame_get(self) -> None:
        with self._lock:
            self.frame_store_get_total += 1

    def record_frame_miss(self) -> None:
        with self._lock:
            self.frame_store_miss_total += 1

    def record_frame_expired(self) -> None:
        with self._lock:
            self.frame_store_expired_total += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connection_failures": self.connection_failures,
                "publish_total": self.publish_total,
                "publish_failure_total": self.publish_failure_total,
                "stream_read_total": self.stream_read_total,
                "stream_ack_total": self.stream_ack_total,
                "stream_processing_failure_total": self.stream_processing_failure_total,
                "stream_pending_recovered": self.stream_pending_recovered,
                "frame_store_put_total": self.frame_store_put_total,
                "frame_store_get_total": self.frame_store_get_total,
                "frame_store_miss_total": self.frame_store_miss_total,
                "frame_store_expired_total": self.frame_store_expired_total,
            }
