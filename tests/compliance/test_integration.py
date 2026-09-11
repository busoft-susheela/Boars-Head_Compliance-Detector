"""End-to-end compliance integration tests.

No YOLO, camera, RTSP, GPU, or real model required.
Uses real in-memory infrastructure and synthetic DetectionEvents.

Tests the complete pipeline:
    DetectionEvent → ObservationBuilder → StateMachine
    → SpatioTemporalAnalyzer → HandwashRuleEvaluator
    → ComplianceRuleEngine → InMemoryStateStore + InMemoryMessageQueue

Detection class conventions in tests
--------------------------------------
"person"   — non-trigger class; represents a person visible at the sink
             but NOT actively washing.  ObservationBuilder sets
             hands_interacting=False for this class.
"handwash" — trigger class; represents active handwashing.
             ObservationBuilder sets hands_interacting=True.

Both classes share the same bounding box so that IoUTracker keeps a
stable track_id across detection-class changes (simulating a multi-class
model where one track can transition from "person" to "handwash").
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.compliance.engine import ComplianceRuleEngine
from backend.app.compliance.events import (
    TOPIC_COMPLIANCE_ALERT,
    TOPIC_EVIDENCE_CAPTURE,
)
from backend.app.compliance.observation import ObservationBuilder
from backend.app.compliance.rules.config import HandwashRuleConfig
from backend.app.compliance.rules.handwash import HandwashRuleEvaluator
from backend.app.compliance.state_machine import HandwashStateMachine
from backend.app.compliance.temporal.analyzer import SpatioTemporalAnalyzer
from backend.app.compliance.tracker import IoUTracker
from backend.app.inference.models.detection import BoundingBox, Detection, DetectionEvent
from backend.app.infrastructure.message_queue.in_memory import InMemoryMessageQueue
from backend.app.infrastructure.state_store.in_memory import InMemoryStateStore

_BASE = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
_THUMB = b"\xff\xd8\xff" + b"\x00" * 10
_BBOX = BoundingBox(x1=100, y1=100, x2=200, y2=200)


def _t(seconds: float) -> datetime:
    return _BASE + timedelta(seconds=seconds)


def _det(class_name: str = "person") -> Detection:
    """Build a Detection in the sink area."""
    return Detection(
        class_id=0 if class_name == "person" else 1,
        class_name=class_name,
        bbox=_BBOX,
        confidence=0.9,
        use_case="handwashing",
    )


def _event(
    frame_id: int,
    seconds: float,
    detections: tuple = (),
    thumbnail: bytes | None = _THUMB,
) -> DetectionEvent:
    return DetectionEvent(
        camera_id="cam01",
        zone_id="handwash_zone",
        frame_id=frame_id,
        captured_at=_t(seconds),
        processed_at=_t(seconds),
        detections=detections,
        thumbnail=thumbnail,
    )


def _build_pipeline(absence_threshold: float = 20.0) -> tuple:
    store = InMemoryStateStore()
    mq = InMemoryMessageQueue(max_size_per_topic=50)
    rule_config = HandwashRuleConfig(
        minimum_washing_duration_seconds=20.0,
        absence_threshold_seconds=absence_threshold,
        require_soap=False,
        require_water=False,
        require_sequence=False,
        require_completion=False,
        evidence_buffer_max=10,
    )
    engine = ComplianceRuleEngine(
        state_store=store,
        tracker=IoUTracker(),
        observation_builder=ObservationBuilder(trigger_class="handwash"),
        state_machine=HandwashStateMachine(),
        temporal_analyzer=SpatioTemporalAnalyzer(),
        rule_evaluator=HandwashRuleEvaluator(config=rule_config),
        message_queue=mq,
    )
    return engine, store, mq


def _run_absence_frames(engine, n_frames: int, start_frame: int = 1) -> None:
    """Send n_frames of 'person at sink without washing' (1 second apart)."""
    for i in range(n_frames):
        fid = start_frame + i
        engine.process(_event(
            frame_id=fid,
            seconds=float(fid),
            detections=(_det("person"),),  # present but not washing
        ))


# ── Compliance resumes before violation ───────────────────────────────────────

class TestComplianceResumes:
    """Person at sink without washing → then starts washing → NO violation."""

    def test_no_violation_when_washing_resumes_within_threshold(self):
        engine, store, mq = _build_pipeline(absence_threshold=20.0)

        # Frames 1-5: person at sink but not washing (absence building)
        _run_absence_frames(engine, n_frames=5, start_frame=1)

        # Frame 6: person starts washing → compliance resumes
        engine.process(_event(
            frame_id=6, seconds=6.0,
            detections=(_det("handwash"),),
        ))

        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 0
        assert mq.qsize(TOPIC_EVIDENCE_CAPTURE) == 0

    def test_no_evidence_published_when_compliance_resumes(self):
        engine, store, mq = _build_pipeline(absence_threshold=20.0)

        _run_absence_frames(engine, n_frames=10, start_frame=1)

        engine.process(_event(
            frame_id=11, seconds=11.0,
            detections=(_det("handwash"),),
        ))

        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 0
        assert mq.qsize(TOPIC_EVIDENCE_CAPTURE) == 0


# ── Violation confirmed ───────────────────────────────────────────────────────

class TestViolationConfirmed:
    """Person at sink without washing beyond threshold → one violation event."""

    def test_violation_after_threshold(self):
        engine, store, mq = _build_pipeline(absence_threshold=5.0)

        # 7 frames at 1-second intervals — person at sink, never washes (5s threshold)
        _run_absence_frames(engine, n_frames=7, start_frame=1)

        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 1
        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        assert alert.outcome == "violation"
        assert alert.camera_id == "cam01"

    def test_one_violation_per_episode(self):
        """Violation fires exactly once regardless of how many frames follow."""
        engine, store, mq = _build_pipeline(absence_threshold=5.0)

        _run_absence_frames(engine, n_frames=20, start_frame=1)

        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 1

    def test_evidence_published_with_violation(self):
        engine, store, mq = _build_pipeline(absence_threshold=5.0)

        _run_absence_frames(engine, n_frames=7, start_frame=1)

        assert mq.qsize(TOPIC_EVIDENCE_CAPTURE) == 1

    def test_evidence_group_id_matches_alert(self):
        engine, store, mq = _build_pipeline(absence_threshold=5.0)

        _run_absence_frames(engine, n_frames=7, start_frame=1)

        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        assert alert.group_id == evidence_event.group_id

    def test_evidence_items_are_immutable_tuple(self):
        engine, store, mq = _build_pipeline(absence_threshold=5.0)

        _run_absence_frames(engine, n_frames=7, start_frame=1)

        mq.get(TOPIC_COMPLIANCE_ALERT)
        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        assert isinstance(evidence_event.payload.items, tuple)


# ── Alert payload is lightweight ──────────────────────────────────────────────

class TestAlertPayload:
    def test_alert_has_no_thumbnail_field(self):
        """ComplianceEvent must NOT contain thumbnails."""
        from backend.app.compliance.events import ComplianceEvent

        engine, store, mq = _build_pipeline(absence_threshold=5.0)
        _run_absence_frames(engine, n_frames=7, start_frame=1)

        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        assert isinstance(alert, ComplianceEvent)
        assert not hasattr(alert, "thumbnail")
        assert not hasattr(alert, "evidence")

    def test_alert_payload_has_required_fields(self):
        engine, store, mq = _build_pipeline(absence_threshold=5.0)
        _run_absence_frames(engine, n_frames=7, start_frame=1)

        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        assert alert.camera_id == "cam01"
        assert alert.zone_id == "handwash_zone"
        assert alert.outcome == "violation"
        assert alert.group_id is not None
        assert alert.rule_name == "handwash_compliance"


# ── FrameStore independence ───────────────────────────────────────────────────

class TestFrameStoreIndependence:
    """Evidence payload must rely on DetectionEvent.thumbnail, not FrameStore."""

    def test_evidence_thumbnails_come_from_detection_event(self):
        """Pipeline has no FrameStore — evidence still populated from DetectionEvent."""
        engine, store, mq = _build_pipeline(absence_threshold=5.0)

        _run_absence_frames(engine, n_frames=7, start_frame=1)

        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        thumbs = [item.thumbnail for item in evidence_event.payload.items]
        assert any(t == _THUMB for t in thumbs)


# ── Evidence buffer cap ───────────────────────────────────────────────────────

class TestEvidenceBufferCap:
    def test_evidence_respects_buffer_max(self):
        """Evidence payload must not exceed evidence_buffer_max items."""
        store = InMemoryStateStore()
        mq = InMemoryMessageQueue(max_size_per_topic=50)
        rule_config = HandwashRuleConfig(
            minimum_washing_duration_seconds=20.0,
            absence_threshold_seconds=5.0,
            require_soap=False, require_water=False,
            require_sequence=False, require_completion=False,
            evidence_buffer_max=3,  # small cap
        )
        engine = ComplianceRuleEngine(
            state_store=store,
            tracker=IoUTracker(),
            observation_builder=ObservationBuilder(trigger_class="handwash"),
            state_machine=HandwashStateMachine(),
            temporal_analyzer=SpatioTemporalAnalyzer(),
            rule_evaluator=HandwashRuleEvaluator(config=rule_config),
            message_queue=mq,
        )

        _run_absence_frames_on(engine, n_frames=20, start_frame=1)

        mq.get(TOPIC_COMPLIANCE_ALERT)
        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        assert len(evidence_event.payload.items) <= 3


def _run_absence_frames_on(engine, n_frames: int, start_frame: int = 1) -> None:
    for i in range(n_frames):
        fid = start_frame + i
        engine.process(_event(
            frame_id=fid,
            seconds=float(fid),
            detections=(_det("person"),),
        ))


# ── Full handwash lifecycle ───────────────────────────────────────────────────

class TestFullHandwashLifecycle:
    """End-to-end: person at sink, washes, completes — no violation."""

    def test_complete_compliant_wash_no_violation(self):
        engine, store, mq = _build_pipeline(absence_threshold=5.0)

        # Person at sink (1 frame)
        engine.process(_event(1, 1.0, detections=(_det("person"),)))
        # Person washes (7 frames, 7 seconds → well above threshold)
        for i in range(7):
            engine.process(_event(i + 2, float(i + 2), detections=(_det("handwash"),)))

        # No violation because person was washing, not absent
        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 0
