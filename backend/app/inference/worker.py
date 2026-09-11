"""CPUInferenceWorker — bounded threading worker consuming FrameEnvelopes.

This worker:
1. Runs in a dedicated background thread (consistent with the ingestion service).
2. Consumes FrameEnvelopes from the MessageQueue (blocking get with timeout).
3. Passes each envelope to YoloInferenceEngine.process() for a full inference cycle.
4. Handles per-frame errors gracefully so a bad frame never kills the worker.
5. Stops cleanly when stop() is called or the application shuts down.

Backpressure
------------
The InMemoryMessageQueue already enforces a bounded topic queue (drop-oldest
strategy).  The worker adds a second boundary: it processes one frame at a time
in a single thread (``workers: 1``).  If inference is slower than ingestion, the
MessageQueue drops old envelopes — the worker always processes the freshest
available frame.

Startup sequencing
------------------
The worker does NOT start consuming until ``start()`` is called explicitly.
``main.py`` should call ``registry.get(spec)`` (eager model loading + warm-up)
BEFORE starting the worker so that the first real frame does not experience
model-loading latency.

Lifecycle
---------
    worker.start()   → begins background thread
    worker.stop()    → signals thread to exit; join in caller
    worker.join(t)   → waits up to t seconds for clean exit
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timezone

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from backend.app.inference.engine import YoloInferenceEngine
from backend.app.inference.health.metrics import InferenceMetrics
from backend.app.infrastructure.message_queue.base import MessageQueue
from backend.app.ingestion.models.frame_envelope import FrameEnvelope

logger = structlog.get_logger(__name__)

_GET_TIMEOUT = 1.0  # seconds; controls shutdown responsiveness


class CPUInferenceWorker:
    """Single-threaded, bounded inference worker.

    Args:
        engine:        :class:`YoloInferenceEngine` that processes each envelope.
        message_queue: Source of :class:`FrameEnvelope` messages.
        input_topic:   MessageQueue topic to consume from.
        metrics:       Optional metrics tracker; created if not provided.
    """

    def __init__(
        self,
        engine: YoloInferenceEngine,
        message_queue: MessageQueue,
        input_topic: str = "ingestion.frames",
        metrics: InferenceMetrics | None = None,
    ) -> None:
        self._engine = engine
        self._message_queue = message_queue
        self._input_topic = input_topic
        self._metrics = metrics or InferenceMetrics()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def metrics(self) -> InferenceMetrics:
        return self._metrics

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background consumer thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("inference_worker_already_running")
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="inference-worker", daemon=True
        )
        self._thread.start()
        self._metrics.set("worker_running", True)
        logger.info("inference_worker_started", topic=self._input_topic)

    def stop(self) -> None:
        """Signal the worker thread to stop after the current frame."""
        logger.info("inference_worker_stop_requested")
        self._stop.set()

    def join(self, timeout: float = 5.0) -> None:
        """Wait for the worker thread to exit."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._metrics.set("worker_running", False)
        logger.info("inference_worker_stopped")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _run(self) -> None:
        logger.info("inference_worker_running", topic=self._input_topic)
        while not self._stop.is_set():
            try:
                envelope: FrameEnvelope = self._message_queue.get(
                    self._input_topic, timeout=_GET_TIMEOUT
                )
            except queue.Empty:
                # Timeout — check stop flag and loop.
                continue
            except Exception as exc:
                logger.error("inference_queue_error", error=str(exc))
                continue

            self._metrics.increment("frames_received_total")
            self._process(envelope)

        logger.info("inference_worker_loop_exited")

    def _process(self, envelope: FrameEnvelope) -> None:
        """Delegate to engine; catch and log all per-frame errors."""
        clear_contextvars()
        bind_contextvars(
            correlation_id=envelope.correlation_id,
            camera_id=envelope.camera_id,
            frame_id=envelope.frame_id,
        )
        t0 = time.monotonic()
        try:
            self._engine.process(envelope)
            self._metrics.increment("frames_processed_total")
            self._metrics.set("last_processed_at", datetime.now(tz=timezone.utc))
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "inference_worker_unhandled_error",
                camera_id=envelope.camera_id,
                frame_id=envelope.frame_id,
                duration_ms=round(elapsed_ms, 1),
                error=str(exc),
            )
