"""InferenceMetrics — thread-safe counters and state for the inference layer."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class InferenceMetrics:
    """Mutable metrics for the inference worker.  All mutations are lock-protected."""

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    frames_received_total: int = 0
    frames_processed_total: int = 0
    frame_store_miss_total: int = 0
    inference_total: int = 0
    inference_failures_total: int = 0
    thumbnail_failures_total: int = 0
    last_processed_at: datetime | None = None
    worker_running: bool = False

    def increment(self, field_name: str, by: int = 1) -> None:
        with self._lock:
            current = getattr(self, field_name)
            object.__setattr__(self, field_name, current + by)

    def set(self, field_name: str, value) -> None:
        with self._lock:
            object.__setattr__(self, field_name, value)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "frames_received_total": self.frames_received_total,
                "frames_processed_total": self.frames_processed_total,
                "frame_store_miss_total": self.frame_store_miss_total,
                "inference_total": self.inference_total,
                "inference_failures_total": self.inference_failures_total,
                "thumbnail_failures_total": self.thumbnail_failures_total,
                "last_processed_at": (
                    self.last_processed_at.isoformat() if self.last_processed_at else None
                ),
                "worker_running": self.worker_running,
            }
