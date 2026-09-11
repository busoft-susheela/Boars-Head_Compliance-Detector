"""TemporalAnalyzer — confirms a violation only after sustained evidence."""

import time


class TemporalAnalyzer:
    def __init__(self, min_seconds: float, debounce_frames: int):
        self.min_seconds = min_seconds
        self.debounce_frames = debounce_frames
        self._violation_start: float | None = None
        self._debounce_count = 0

    def observe(self, is_violation: bool) -> bool:
        """Return True when a confirmed violation should be raised."""
        if is_violation:
            now = time.monotonic()
            if self._violation_start is None:
                self._violation_start = now
            elapsed = now - self._violation_start
            self._debounce_count += 1
            if elapsed >= self.min_seconds and self._debounce_count >= self.debounce_frames:
                return True
        else:
            self._violation_start = None
            self._debounce_count = 0
        return False
