"""IngestionMetrics — observable health state for the ingestion service.

Written by the ingestion thread; read by the FastAPI health endpoint.
All counter mutations use a lock so that reads from another thread always
see a consistent snapshot.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IngestionMetrics:
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    # Connection state
    stream_connected: bool = False
    last_frame_received_at: datetime | None = None

    # Counters
    frames_received_total: int = 0
    frames_sampled_total: int = 0
    frames_dropped_total: int = 0
    invalid_frames_total: int = 0
    reconnect_count: int = 0

    def snapshot(self) -> dict:
        """Return a thread-safe copy of all metrics as a plain dict."""
        with self._lock:
            return {
                "stream_connected": self.stream_connected,
                "last_frame_received_at": (
                    self.last_frame_received_at.isoformat()
                    if self.last_frame_received_at
                    else None
                ),
                "frames_received_total": self.frames_received_total,
                "frames_sampled_total": self.frames_sampled_total,
                "frames_dropped_total": self.frames_dropped_total,
                "invalid_frames_total": self.invalid_frames_total,
                "reconnect_count": self.reconnect_count,
            }

    def increment(self, field_name: str, by: int = 1) -> None:
        with self._lock:
            setattr(self, field_name, getattr(self, field_name) + by)

    def set(self, field_name: str, value) -> None:
        with self._lock:
            setattr(self, field_name, value)
