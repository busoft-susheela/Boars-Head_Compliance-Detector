"""ComplianceWorker — background thread consuming inference.detections.

Responsibility: thread lifecycle only.

The worker pulls DetectionEvents from the MessageQueue topic
``inference.detections`` and delegates each one to ComplianceRuleEngine.

Design mirrors CPUInferenceWorker:
  - ``start()`` / ``stop()`` / ``join()`` interface
  - ``threading.Event`` for cooperative shutdown
  - Timeout-based ``get()`` so the thread wakes periodically to check
    the stop event even when the queue is idle
"""

from __future__ import annotations

import queue
import threading

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from backend.app.compliance.engine import ComplianceRuleEngine
from backend.app.compliance.metrics import ComplianceMetrics
from backend.app.inference.models.detection import DetectionEvent
from backend.app.infrastructure.message_queue.base import MessageQueue

logger = structlog.get_logger(__name__)

_DETECTION_TOPIC = "inference.detections"
_QUEUE_TIMEOUT = 1.0  # seconds — controls shutdown responsiveness


class ComplianceWorker:
    """Background thread that feeds DetectionEvents to ComplianceRuleEngine.

    Args:
        engine:        Compliance orchestrator to call for each event.
        message_queue: Source of DetectionEvents (``inference.detections``).
        metrics:       Shared metrics instance; uses engine's own if None.
    """

    def __init__(
        self,
        engine: ComplianceRuleEngine,
        message_queue: MessageQueue,
        metrics: ComplianceMetrics | None = None,
    ) -> None:
        self._engine = engine
        self._mq = message_queue
        self._metrics = metrics or engine._metrics
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def metrics(self) -> ComplianceMetrics:
        return self._metrics

    def start(self) -> None:
        """Start the worker thread.  No-op if already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="compliance_worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("compliance_worker_started")

    def stop(self) -> None:
        """Signal the worker thread to stop after the current event."""
        self._stop_event.set()
        logger.info("compliance_worker_stop_requested")

    def join(self, timeout: float = 5.0) -> None:
        """Wait for the worker thread to finish.

        Args:
            timeout: Maximum seconds to wait.
        """
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def _run(self) -> None:
        logger.debug("compliance_worker_running")
        while not self._stop_event.is_set():
            try:
                event: DetectionEvent = self._mq.get(
                    _DETECTION_TOPIC, timeout=_QUEUE_TIMEOUT
                )
            except queue.Empty:
                continue
            except Exception:
                logger.exception("compliance_worker_queue_error")
                continue

            clear_contextvars()
            bind_contextvars(
                correlation_id=event.correlation_id,
                camera_id=event.camera_id,
                frame_id=event.frame_id,
            )
            try:
                self._engine.process(event)
            except Exception:
                logger.exception(
                    "compliance_worker_unhandled_error",
                    camera_id=getattr(event, "camera_id", None),
                    frame_id=getattr(event, "frame_id", None),
                )

        # ── Drain any remaining queued events before flushing ─────────────────
        while True:
            try:
                event = self._mq.get(_DETECTION_TOPIC, timeout=0)
                clear_contextvars()
                bind_contextvars(
                    correlation_id=event.correlation_id,
                    camera_id=event.camera_id,
                    frame_id=event.frame_id,
                )
                self._engine.process(event)
            except queue.Empty:
                break
            except Exception:
                logger.exception("compliance_worker_drain_error")
                break

        # ── Finalise any persons still mid-visit when the stream ended ────────
        clear_contextvars()
        self._engine.flush()

        logger.debug("compliance_worker_stopped")
