"""Integration tests for CPUInferenceWorker — end-to-end with fakes.

Tests cover:
- Full end-to-end flow: FrameEnvelope → DetectionEvent
- Frame expiration (FrameStore TTL miss)
- Model failure (partial result published)
- Queue backpressure (bounded queue does not grow unbounded)
- Graceful shutdown (worker exits cleanly)
"""

import queue
import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.app.inference.engine import YoloInferenceEngine, DETECTIONS_TOPIC
from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.models.detection import BoundingBox, Detection, DetectionEvent
from backend.app.inference.registry import ModelRegistry
from backend.app.inference.resolver.base import ModelResolver
from backend.app.inference.thumbnail import ThumbnailGenerator
from backend.app.inference.worker import CPUInferenceWorker
from backend.app.infrastructure.frame_store.in_memory import InMemoryFrameStore
from backend.app.infrastructure.message_queue.in_memory import InMemoryMessageQueue
from backend.app.ingestion.models.frame_envelope import FrameEnvelope


# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------

class FakeResolver(ModelResolver):
    def __init__(self, specs: list[ModelSpec]):
        self._specs = specs

    def resolve(self, camera_id: str, zone_id: str) -> list[ModelSpec]:
        return list(self._specs)


def _spec(use_case: str = "handwashing") -> ModelSpec:
    return ModelSpec(
        use_case=use_case,
        model_path=f"artifacts/{use_case}.pt",
        confidence_threshold=0.5,
        device="cpu",
        image_size=640,
    )


def _envelope(frame_id: int, camera_id: str = "cam-01") -> FrameEnvelope:
    now = datetime.now(tz=timezone.utc)
    return FrameEnvelope(
        camera_id=camera_id,
        frame_id=frame_id,
        captured_at=now,
        received_at=now,
        topic="ingestion.frames",
    )


def _build_stack(
    detections: list[Detection] | None = None,
    detector_raises: Exception | None = None,
) -> tuple[CPUInferenceWorker, InMemoryFrameStore, InMemoryMessageQueue]:
    """Build the full inference stack with a fake detector."""
    spec = _spec()
    frame_store = InMemoryFrameStore(ttl_seconds=5.0)
    mq = InMemoryMessageQueue(max_size_per_topic=50)

    fake_detector = MagicMock()
    fake_detector.spec = spec
    if detector_raises:
        fake_detector.infer.side_effect = detector_raises
    else:
        fake_detector.infer.return_value = detections or []

    registry = MagicMock(spec=ModelRegistry)
    registry.get.return_value = fake_detector

    engine = YoloInferenceEngine(
        zone_id="handwash_zone",
        resolver=FakeResolver([spec]),
        registry=registry,
        frame_store=frame_store,
        message_queue=mq,
        thumbnail_generator=ThumbnailGenerator(max_width=160),
    )
    worker = CPUInferenceWorker(engine=engine, message_queue=mq)
    return worker, frame_store, mq


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_frame_envelope_produces_detection_event(self):
        worker, frame_store, mq = _build_stack()
        worker.start()
        try:
            frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))
            mq.publish("ingestion.frames", _envelope(frame_id=1))

            event = mq.get(DETECTIONS_TOPIC, timeout=5.0)
            assert isinstance(event, DetectionEvent)
            assert event.frame_id == 1
            assert event.camera_id == "cam-01"
        finally:
            worker.stop()
            worker.join(timeout=3.0)

    def test_detection_event_contains_correct_detections(self):
        det = Detection(
            class_id=0, class_name="hand",
            bbox=BoundingBox(0, 0, 50, 50),
            confidence=0.9, use_case="handwashing",
        )
        worker, frame_store, mq = _build_stack(detections=[det])
        worker.start()
        try:
            frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))
            mq.publish("ingestion.frames", _envelope(frame_id=1))

            event: DetectionEvent = mq.get(DETECTIONS_TOPIC, timeout=5.0)
            assert len(event.detections) == 1
            assert event.detections[0].class_name == "hand"
        finally:
            worker.stop()
            worker.join(timeout=3.0)


class TestFrameExpiration:
    def test_frame_store_miss_does_not_crash_worker(self):
        """Worker must continue after a FrameStore miss, not raise or exit."""
        worker, frame_store, mq = _build_stack()
        worker.start()
        try:
            # Publish envelope WITHOUT storing the frame
            mq.publish("ingestion.frames", _envelope(frame_id=999))
            time.sleep(0.3)  # Give worker time to process

            # Worker should still be alive
            assert worker._thread is not None and worker._thread.is_alive()

            # Subsequent frames with valid store entries should still work
            frame_store.put(2, np.zeros((480, 640, 3), dtype=np.uint8))
            mq.publish("ingestion.frames", _envelope(frame_id=2))
            event = mq.get(DETECTIONS_TOPIC, timeout=5.0)
            assert event.frame_id == 2
        finally:
            worker.stop()
            worker.join(timeout=3.0)


class TestModelFailure:
    def test_model_failure_publishes_partial_result(self):
        """When the detector raises RuntimeError, worker still publishes DetectionEvent."""
        worker, frame_store, mq = _build_stack(
            detector_raises=RuntimeError("Inference OOM")
        )
        worker.start()
        try:
            frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))
            mq.publish("ingestion.frames", _envelope(frame_id=1))

            event: DetectionEvent = mq.get(DETECTIONS_TOPIC, timeout=5.0)
            # Empty detections, not a crash
            assert event.detections == ()
        finally:
            worker.stop()
            worker.join(timeout=3.0)

    def test_worker_continues_after_model_failure(self):
        """Worker should process subsequent frames after a model failure."""
        call_count = [0]
        original_side_effect = [RuntimeError("fail"), None]

        def sometimes_fail(frame):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                raise RuntimeError("First call fails")
            return []

        spec = _spec()
        frame_store = InMemoryFrameStore(ttl_seconds=5.0)
        mq = InMemoryMessageQueue(max_size_per_topic=50)

        fake_detector = MagicMock()
        fake_detector.spec = spec
        fake_detector.infer.side_effect = sometimes_fail

        registry = MagicMock(spec=ModelRegistry)
        registry.get.return_value = fake_detector

        engine = YoloInferenceEngine(
            zone_id="z",
            resolver=FakeResolver([spec]),
            registry=registry,
            frame_store=frame_store,
            message_queue=mq,
            thumbnail_generator=ThumbnailGenerator(),
        )
        worker = CPUInferenceWorker(engine=engine, message_queue=mq)
        worker.start()
        try:
            frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))
            frame_store.put(2, np.zeros((480, 640, 3), dtype=np.uint8))
            mq.publish("ingestion.frames", _envelope(frame_id=1))
            mq.publish("ingestion.frames", _envelope(frame_id=2))

            # Should receive two events (both published despite first model failure)
            ev1 = mq.get(DETECTIONS_TOPIC, timeout=5.0)
            ev2 = mq.get(DETECTIONS_TOPIC, timeout=5.0)
            assert {ev1.frame_id, ev2.frame_id} == {1, 2}
        finally:
            worker.stop()
            worker.join(timeout=3.0)


class TestBackpressure:
    def test_queue_stays_bounded_under_fast_ingestion(self):
        """Flooding the input queue faster than inference must not exhaust memory."""
        worker, frame_store, mq = _build_stack()
        # Don't start the worker — we test the queue size alone
        max_topic_size = 50  # from _build_stack's InMemoryMessageQueue

        for i in range(200):
            frame_store.put(i, np.zeros((480, 640, 3), dtype=np.uint8))
            mq.publish("ingestion.frames", _envelope(frame_id=i))

        # Queue size must not exceed configured max
        assert mq.qsize("ingestion.frames") <= max_topic_size
        # Some messages must have been dropped (200 > 50)
        assert mq.dropped_count("ingestion.frames") > 0


class TestGracefulShutdown:
    def test_worker_exits_cleanly_on_stop(self):
        worker, _, _ = _build_stack()
        worker.start()
        assert worker._thread is not None and worker._thread.is_alive()

        worker.stop()
        worker.join(timeout=3.0)

        assert not worker._thread.is_alive()

    def test_worker_stops_even_when_queue_is_empty(self):
        """stop() must work when there are no pending messages."""
        worker, _, _ = _build_stack()
        worker.start()
        time.sleep(0.1)  # Let worker block on empty queue
        worker.stop()
        worker.join(timeout=3.0)

        assert not worker._thread.is_alive()

    def test_metrics_worker_running_false_after_join(self):
        worker, _, _ = _build_stack()
        worker.start()
        worker.stop()
        worker.join(timeout=3.0)

        assert not worker.metrics.worker_running
