"""ModelRegistry — caches one YoloDetector per unique model path.

The registry owns the model lifecycle.  It is responsible for:

1. Loading a model exactly once (even under concurrent first-request pressure).
2. Warming up each model immediately after loading (optional, config-driven).
3. Returning the cached detector for every subsequent request.

Thread safety
-------------
A ``threading.Lock`` per model path ensures that even if two workers race to
request the same model for the first time, only one YOLO load occurs.  After
loading, the lock is released and all subsequent calls return immediately from
the cache without acquiring a lock.

Warm-up
-------
Warm-up runs one synthetic forward pass with a dummy black frame sized to the
model's configured ``image_size``.  This amortises JIT/initialisation costs
before real frames arrive.  Warm-up failures are logged but do not prevent the
model from being registered — inference may still work even if warm-up is slow
or returns unexpected results.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import structlog

from backend.app.inference.loader import ModelLoader
from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.yolo_detector import YoloDetector

logger = structlog.get_logger(__name__)


class ModelRegistry:
    """Thread-safe cache of one :class:`YoloDetector` per normalised model path.

    Args:
        loader:  :class:`ModelLoader` used to load weights on first access.
        warmup:  If ``True``, run a warm-up forward pass after loading.
    """

    def __init__(self, loader: ModelLoader, warmup: bool = True) -> None:
        self._loader = loader
        self._warmup = warmup
        self._cache: dict[str, YoloDetector] = {}
        # One lock per model key prevents double-loading under concurrent first access.
        self._key_locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()  # protects _key_locks dict itself

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, spec: ModelSpec) -> YoloDetector:
        """Return the :class:`YoloDetector` for this spec, loading it if necessary.

        Guaranteed to load each model exactly once, even under concurrent
        first-access pressure.

        Args:
            spec: Immutable model declaration.  Registry key is ``spec.normalised_path``.

        Returns:
            Cached or freshly-loaded :class:`YoloDetector`.

        Raises:
            RuntimeError: If model loading fails.
        """
        key = spec.normalised_path

        # Fast path: already cached (no lock needed — dict reads are safe in CPython).
        if key in self._cache:
            return self._cache[key]

        # Slow path: acquire per-key lock to serialise first load.
        lock = self._get_or_create_lock(key)
        with lock:
            # Double-check after acquiring — another thread may have loaded it.
            if key in self._cache:
                return self._cache[key]

            detector = self._load_and_warm(spec)
            self._cache[key] = detector
            return detector

    def close(self) -> None:
        """Release internal resources.  Call during application shutdown."""
        self._cache.clear()
        logger.debug("model_registry_closed")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_create_lock(self, key: str) -> threading.Lock:
        with self._meta_lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def _load_and_warm(self, spec: ModelSpec) -> YoloDetector:
        t_load = time.monotonic()
        model = self._loader.load(spec)
        load_ms = (time.monotonic() - t_load) * 1000

        detector = YoloDetector(model=model, spec=spec)

        if self._warmup:
            self._run_warmup(detector, spec, load_ms)
        else:
            logger.info(
                "model_ready_no_warmup",
                use_case=spec.use_case,
                model_path=spec.model_path,
                load_duration_ms=round(load_ms, 1),
            )

        return detector

    @staticmethod
    def _run_warmup(detector: YoloDetector, spec: ModelSpec, load_ms: float) -> None:
        dummy = np.zeros((spec.image_size, spec.image_size, 3), dtype=np.uint8)
        t_warm = time.monotonic()
        try:
            detector.infer(dummy)
            warm_ms = (time.monotonic() - t_warm) * 1000
            logger.info(
                "model_ready",
                use_case=spec.use_case,
                model_path=spec.model_path,
                load_duration_ms=round(load_ms, 1),
                warmup_duration_ms=round(warm_ms, 1),
            )
        except Exception as exc:
            warm_ms = (time.monotonic() - t_warm) * 1000
            logger.warning(
                "model_warmup_failed",
                use_case=spec.use_case,
                model_path=spec.model_path,
                warmup_duration_ms=round(warm_ms, 1),
                error=str(exc),
            )
