"""End-to-end compliance integration tests.

No YOLO, camera, RTSP, GPU, or real model required.
Uses real in-memory infrastructure and synthetic DetectionEvents.

Tests the complete pipeline:
    DetectionEvent → ObservationBuilder → StateMachine
    → SpatioTemporalAnalyzer → HandwashRuleEvaluator
    → ComplianceRuleEngine → InMemoryStateStore + InMemoryMessageQueue

Detection conventions
---------------------
Frames with a "person" + "sink" + "handwash" detection (all same bbox) simulate
the person actively at the sink with their hand confirmed near it.
Empty detection frames simulate the person being absent — the engine synthesises
an absence observation that eventually triggers a zone exit.
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

# Reusable Detection objects — all share the same bbox so IoUTracker keeps a
# stable track_id and the spatial functions find hand/sink proximity.
_PERSON = Detection(class_id=0, class_name="person", bbox=_BBOX, confidence=0.9, use_case="hw")
_SINK   = Detection(class_id=1, class_name="sink",   bbox=_BBOX, confidence=0.9, use_case="hw")
_HAND   = Detection(class_id=2, class_name="handwash", bbox=_BBOX, confidence=0.9, use_case="hw")

# Full "at sink washing" frame: person tracked, sink detected, hand near sink.
_WASHING_DETS = (_PERSON, _SINK, _HAND)


def _t(seconds: float) -> datetime:
    return _BASE + timedelta(seconds=seconds)


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


def _build_pipeline(min_washing_seconds: float = 3.0) -> tuple:
    """Build the full compliance pipeline with predictable test parameters.

    Key choices:
    - confirmation_frames=1: one handwash detection immediately confirms washing
    - require_hand_movement=False: avoid movement-score dependency in tests
    - washing_hold_frames=2: small gap tolerance (real frames only)
    - Frames are sent 0.1 s apart (10 fps equivalent)
    """
    store = InMemoryStateStore()
    mq = InMemoryMessageQueue(max_size_per_topic=50)

    rule_config = HandwashRuleConfig(
        minimum_washing_duration_seconds=min_washing_seconds,
        absence_threshold_seconds=30.0,
        evidence_buffer_max=10,
        confirmation_frames=1,
        reset_after_no_detection_seconds=1.0,
        min_hands_for_washing=1,
        min_hand_movement=2.0,
        require_hand_movement=False,
        person_box_expand_x=0.15,
        person_box_expand_y=0.20,
        max_person_sink_distance=2.0,
        sink_horizontal_margin=0.30,
        sink_top_margin=1.50,
        sink_bottom_margin=0.20,
        session_cooldown_seconds=0.0,  # disable cooldown in tests
    )
    obs_builder = ObservationBuilder(
        hand_class="handwash",
        confirmation_frames=1,
        require_hand_movement=False,
        washing_hold_frames=2,
    )
    engine = ComplianceRuleEngine(
        state_store=store,
        tracker=IoUTracker(),
        observation_builder=obs_builder,
        state_machine=HandwashStateMachine(),
        temporal_analyzer=SpatioTemporalAnalyzer(),
        rule_evaluator=HandwashRuleEvaluator(config=rule_config),
        message_queue=mq,
    )
    return engine, store, mq


def _send_washing_frames(engine, n: int, start_frame: int = 1) -> int:
    """Send n frames of 'person at sink washing' 0.1 s apart.

    Returns the last frame_id sent.
    """
    for i in range(n):
        fid = start_frame + i
        engine.process(_event(fid, fid * 0.1, detections=_WASHING_DETS))
    return start_frame + n - 1


def _send_exit_frames(engine, n: int = 10, start_frame: int = 100) -> None:
    """Send n empty frames to let the absence synthesis trigger a zone exit.

    n must exceed _MAX_LOST_FRAMES (5) to guarantee inside_zone=False.
    """
    for i in range(n):
        fid = start_frame + i
        engine.process(_event(fid, fid * 0.1, detections=()))


# ── Violation confirmed ───────────────────────────────────────────────────────

class TestViolationConfirmed:
    """Person washes briefly then exits → one violation event."""

    def _setup_violation(self, min_seconds: float = 3.0):
        engine, store, mq = _build_pipeline(min_seconds)
        # 2 washing frames: zone entry (frame 1) + WASHING starts (frame 2)
        last = _send_washing_frames(engine, n=2, start_frame=1)
        # Exit: absence synthesis fires inside_zone=False after _MAX_LOST_FRAMES
        _send_exit_frames(engine, n=10, start_frame=last + 1)
        return engine, store, mq

    def test_violation_fires(self):
        _, _, mq = self._setup_violation()
        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 1
        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        assert alert.outcome == "violation"
        assert alert.camera_id == "cam01"

    def test_one_violation_per_episode(self):
        """Violation fires exactly once regardless of how many frames follow."""
        engine, _, mq = self._setup_violation()
        # Send more washing frames while person is in NOT_WASHED terminal state.
        # Terminal state suppresses new cycles while person is still at the sink.
        _send_washing_frames(engine, n=20, start_frame=200)
        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 1

    def test_evidence_published_with_violation(self):
        _, _, mq = self._setup_violation()
        assert mq.qsize(TOPIC_EVIDENCE_CAPTURE) == 1

    def test_evidence_group_id_matches_alert(self):
        _, _, mq = self._setup_violation()
        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        assert alert.group_id == evidence_event.group_id

    def test_evidence_items_are_immutable_tuple(self):
        _, _, mq = self._setup_violation()
        mq.get(TOPIC_COMPLIANCE_ALERT)
        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        assert isinstance(evidence_event.payload.items, tuple)


# ── Alert payload ─────────────────────────────────────────────────────────────

class TestAlertPayload:
    def test_alert_has_no_thumbnail_field(self):
        from backend.app.compliance.events import ComplianceEvent
        engine, _, mq = _build_pipeline()
        _send_washing_frames(engine, n=2)
        _send_exit_frames(engine, n=10, start_frame=10)
        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        assert isinstance(alert, ComplianceEvent)
        assert not hasattr(alert, "thumbnail")
        assert not hasattr(alert, "evidence")

    def test_alert_payload_has_required_fields(self):
        engine, _, mq = _build_pipeline()
        _send_washing_frames(engine, n=2)
        _send_exit_frames(engine, n=10, start_frame=10)
        alert = mq.get(TOPIC_COMPLIANCE_ALERT)
        assert alert.camera_id == "cam01"
        assert alert.zone_id == "handwash_zone"
        assert alert.outcome == "violation"
        assert alert.group_id is not None
        assert alert.rule_name == "handwash_compliance"


# ── Evidence comes from DetectionEvent thumbnail ──────────────────────────────

class TestFrameStoreIndependence:
    def test_evidence_thumbnails_come_from_detection_event(self):
        engine, _, mq = _build_pipeline()
        _send_washing_frames(engine, n=2)
        _send_exit_frames(engine, n=10, start_frame=10)
        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        thumbs = [item.thumbnail for item in evidence_event.payload.items]
        assert any(t == _THUMB for t in thumbs)


# ── Evidence buffer cap ───────────────────────────────────────────────────────

class TestEvidenceBufferCap:
    def test_evidence_respects_buffer_max(self):
        store = InMemoryStateStore()
        mq = InMemoryMessageQueue(max_size_per_topic=50)
        rule_config = HandwashRuleConfig(
            minimum_washing_duration_seconds=3.0,
            absence_threshold_seconds=30.0,
            evidence_buffer_max=3,
            confirmation_frames=1,
            reset_after_no_detection_seconds=1.0,
            min_hands_for_washing=1,
            min_hand_movement=2.0,
            require_hand_movement=False,
            person_box_expand_x=0.15,
            person_box_expand_y=0.20,
            max_person_sink_distance=2.0,
            sink_horizontal_margin=0.30,
            sink_top_margin=1.50,
            sink_bottom_margin=0.20,
            session_cooldown_seconds=0.0,  # disable cooldown in tests
        )
        obs_builder = ObservationBuilder(
            hand_class="handwash",
            confirmation_frames=1,
            require_hand_movement=False,
            washing_hold_frames=2,
        )
        engine = ComplianceRuleEngine(
            state_store=store,
            tracker=IoUTracker(),
            observation_builder=obs_builder,
            state_machine=HandwashStateMachine(),
            temporal_analyzer=SpatioTemporalAnalyzer(),
            rule_evaluator=HandwashRuleEvaluator(config=rule_config),
            message_queue=mq,
        )
        _send_washing_frames(engine, n=2)
        _send_exit_frames(engine, n=10, start_frame=10)
        mq.get(TOPIC_COMPLIANCE_ALERT)
        evidence_event = mq.get(TOPIC_EVIDENCE_CAPTURE)
        assert len(evidence_event.payload.items) <= 3


# ── Full compliant wash — no violation ───────────────────────────────────────

class TestFullHandwashLifecycle:
    def test_complete_compliant_wash_no_violation(self):
        """Person washes for > minimum duration → exits cleanly → no violation."""
        # min=3.0s, send 35 washing frames at 0.1s each = 3.5s of washing,
        # which exceeds the 3.0s minimum.
        engine, _, mq = _build_pipeline(min_washing_seconds=3.0)
        _send_washing_frames(engine, n=35, start_frame=1)
        _send_exit_frames(engine, n=10, start_frame=50)
        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 0
        assert mq.qsize(TOPIC_EVIDENCE_CAPTURE) == 0
