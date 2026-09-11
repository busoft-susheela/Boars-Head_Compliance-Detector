"""Unit tests for YoloInferenceEngine — orchestration logic using fakes."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.app.inference.engine import YoloInferenceEngine, DETECTIONS_TOPIC
from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.models.detection import BoundingBox, Detection, DetectionEvent
from backend.app.inference.registry import ModelRegistry
from backend.app.inference.resolver.base import ModelResolver
from backend.app.inference.thumbnail import ThumbnailGenerator
from backend.app.infrastructure.frame_store.in_memory import InMemoryFrameStore
from backend.app.infrastructure.message_queue.in_memory import InMemoryMessageQueue
from backend.app.ingestion.models.frame_envelope import FrameEnvelope


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeResolver(ModelResolver):
    """Returns a fixed list of ModelSpecs."""
    def __init__(self, specs: list[ModelSpec]):
        self._specs = specs

    def resolve(self, camera_id: str, zone_id: str) -> list[ModelSpec]:
        return list(self._specs)


class FakeDetector:
    """Returns a fixed list of Detection objects."""
    def __init__(self, detections: list[Detection], spec: ModelSpec):
        self._detections = detections
        self.spec = spec

    def infer(self, frame) -> list[Detection]:
        return list(self._detections)


def _spec(use_case: str = "handwashing") -> ModelSpec:
    return ModelSpec(
        use_case=use_case,
        model_path=f"artifacts/{use_case}.pt",
        confidence_threshold=0.5,
        device="cpu",
        image_size=640,
    )


def _envelope(camera_id: str = "cam-01", frame_id: int = 1) -> FrameEnvelope:
    now = datetime.now(tz=timezone.utc)
    return FrameEnvelope(
        camera_id=camera_id,
        frame_id=frame_id,
        captured_at=now,
        received_at=now,
        topic="ingestion.frames",
    )


def _make_engine(
    zone_id: str = "handwash_zone",
    specs: list[ModelSpec] | None = None,
    fake_detections: list[Detection] | None = None,
) -> tuple[YoloInferenceEngine, InMemoryFrameStore, InMemoryMessageQueue, FakeDetector]:
    specs = specs or [_spec()]
    detections = fake_detections or []

    resolver = FakeResolver(specs)
    frame_store = InMemoryFrameStore(ttl_seconds=10.0)
    message_queue = InMemoryMessageQueue(max_size_per_topic=100)
    thumbnail_gen = ThumbnailGenerator(max_width=320, jpeg_quality=70)

    fake_detector = FakeDetector(detections, specs[0] if specs else _spec())

    mock_registry = MagicMock(spec=ModelRegistry)
    mock_registry.get.return_value = fake_detector

    engine = YoloInferenceEngine(
        zone_id=zone_id,
        resolver=resolver,
        registry=mock_registry,
        frame_store=frame_store,
        message_queue=message_queue,
        thumbnail_generator=thumbnail_gen,
    )
    return engine, frame_store, message_queue, fake_detector


class TestEngineProcess:
    def test_publishes_detection_event(self):
        engine, frame_store, mq, _ = _make_engine()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        env = _envelope(frame_id=1)
        frame_store.put(1, frame)

        engine.process(env)

        event: DetectionEvent = mq.get(DETECTIONS_TOPIC, timeout=1.0)
        assert isinstance(event, DetectionEvent)
        assert event.camera_id == "cam-01"
        assert event.zone_id == "handwash_zone"
        assert event.frame_id == 1

    def test_detection_event_contains_detections(self):
        det = Detection(
            class_id=0,
            class_name="hand",
            bbox=BoundingBox(0, 0, 50, 50),
            confidence=0.9,
            use_case="handwashing",
        )
        engine, frame_store, mq, _ = _make_engine(fake_detections=[det])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))

        engine.process(_envelope(frame_id=1))

        event: DetectionEvent = mq.get(DETECTIONS_TOPIC, timeout=1.0)
        assert len(event.detections) == 1
        assert event.detections[0].class_name == "hand"

    def test_empty_detections_still_published(self):
        engine, frame_store, mq, _ = _make_engine(fake_detections=[])
        frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))

        engine.process(_envelope(frame_id=1))

        event = mq.get(DETECTIONS_TOPIC, timeout=1.0)
        assert event.detections == ()

    def test_frame_store_miss_skips_inference(self):
        engine, frame_store, mq, _ = _make_engine()
        # Do NOT put any frame into the store

        engine.process(_envelope(frame_id=999))

        # Nothing should be published
        import queue as qmod
        with pytest.raises(qmod.Empty):
            mq.get(DETECTIONS_TOPIC, timeout=0.1)

    def test_thumbnail_included_in_event(self):
        engine, frame_store, mq, _ = _make_engine()
        frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))

        engine.process(_envelope(frame_id=1))

        event: DetectionEvent = mq.get(DETECTIONS_TOPIC, timeout=1.0)
        # Thumbnail should be bytes (JPEG encoded) or None
        if event.thumbnail is not None:
            assert isinstance(event.thumbnail, bytes)
            assert event.thumbnail[:3] == b"\xff\xd8\xff"

    def test_detections_sorted_deterministically(self):
        """Detections from multiple models must be sorted by use_case, class_id, -conf."""
        spec_a = _spec("aardvark")
        spec_b = _spec("zebra")

        det_a = Detection(
            class_id=1, class_name="tail", bbox=BoundingBox(0, 0, 1, 1),
            confidence=0.6, use_case="zebra",
        )
        det_b = Detection(
            class_id=0, class_name="ear", bbox=BoundingBox(0, 0, 1, 1),
            confidence=0.9, use_case="aardvark",
        )

        resolver = FakeResolver([spec_a, spec_b])
        frame_store = InMemoryFrameStore(ttl_seconds=10.0)
        mq = InMemoryMessageQueue(max_size_per_topic=100)

        # Registry returns different detectors for each spec
        registry = MagicMock(spec=ModelRegistry)
        def get_detector(spec):
            d = FakeDetector(
                [det_b] if spec.use_case == "aardvark" else [det_a],
                spec,
            )
            return d
        registry.get.side_effect = get_detector

        engine = YoloInferenceEngine(
            zone_id="z",
            resolver=resolver,
            registry=registry,
            frame_store=frame_store,
            message_queue=mq,
            thumbnail_generator=ThumbnailGenerator(),
        )
        frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))
        engine.process(_envelope(frame_id=1))

        event: DetectionEvent = mq.get(DETECTIONS_TOPIC, timeout=1.0)
        assert event.detections[0].use_case == "aardvark"
        assert event.detections[1].use_case == "zebra"

    def test_model_inference_failure_publishes_partial_result(self):
        """If a model raises RuntimeError, detections from that model are skipped."""
        spec = _spec("handwashing")
        resolver = FakeResolver([spec])
        frame_store = InMemoryFrameStore(ttl_seconds=10.0)
        mq = InMemoryMessageQueue(max_size_per_topic=100)

        failing_detector = MagicMock()
        failing_detector.spec = spec
        failing_detector.infer.side_effect = RuntimeError("OOM")

        registry = MagicMock(spec=ModelRegistry)
        registry.get.return_value = failing_detector

        engine = YoloInferenceEngine(
            zone_id="z",
            resolver=resolver,
            registry=registry,
            frame_store=frame_store,
            message_queue=mq,
            thumbnail_generator=ThumbnailGenerator(),
        )
        frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))
        engine.process(_envelope(frame_id=1))

        # Should still publish with empty detections (not crash)
        event: DetectionEvent = mq.get(DETECTIONS_TOPIC, timeout=1.0)
        assert event.detections == ()

    def test_resolve_error_does_not_publish(self):
        """If the resolver raises (unknown camera/zone), no event is published."""
        bad_resolver = MagicMock(spec=ModelResolver)
        bad_resolver.resolve.side_effect = KeyError("unknown zone")

        frame_store = InMemoryFrameStore(ttl_seconds=10.0)
        mq = InMemoryMessageQueue(max_size_per_topic=100)

        engine = YoloInferenceEngine(
            zone_id="bad",
            resolver=bad_resolver,
            registry=MagicMock(spec=ModelRegistry),
            frame_store=frame_store,
            message_queue=mq,
            thumbnail_generator=ThumbnailGenerator(),
        )
        frame_store.put(1, np.zeros((480, 640, 3), dtype=np.uint8))
        engine.process(_envelope(frame_id=1))

        import queue as qmod
        with pytest.raises(qmod.Empty):
            mq.get(DETECTIONS_TOPIC, timeout=0.1)
