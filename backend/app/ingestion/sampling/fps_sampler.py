"""FpsSampler — time-based frame-rate limiter.

Prefer time-based sampling over frame_number % N so that the effective
processing rate is stable regardless of source FPS variation.
"""

import time

import structlog

from .base import Sampler

logger = structlog.get_logger(__name__)


class FpsSampler(Sampler):
    """Allows at most target_fps frames per second to pass through.

    Thread-safe for single-producer / single-consumer use (one ingestion
    thread calling should_process()).
    """

    def __init__(self, target_fps: float) -> None:
        if target_fps <= 0:
            logger.error("fps_sampler_invalid_target_fps", target_fps=target_fps)
            raise ValueError(f"target_fps must be > 0, got {target_fps!r}")
        self._interval = 1.0 / target_fps
        self._last_kept: float = 0.0
        self._frames_checked: int = 0
        self._frames_sampled: int = 0
        logger.info("fps_sampler_initialized", target_fps=target_fps, interval_seconds=round(self._interval, 4))

    @property
    def target_fps(self) -> float:
        return 1.0 / self._interval

    @property
    def frames_checked(self) -> int:
        return self._frames_checked

    @property
    def frames_sampled(self) -> int:
        return self._frames_sampled

    @property
    def frames_dropped(self) -> int:
        return self._frames_checked - self._frames_sampled

    def should_process(self) -> bool:
        self._frames_checked += 1
        now = time.monotonic()
        if now - self._last_kept >= self._interval:
            self._last_kept = now
            self._frames_sampled += 1
            return True
        return False

    def log_summary(self) -> None:
        logger.info(
            "fps_sampler_summary",
            target_fps=self.target_fps,
            frames_checked=self._frames_checked,
            frames_sampled=self._frames_sampled,
            frames_dropped=self.frames_dropped,
        )
