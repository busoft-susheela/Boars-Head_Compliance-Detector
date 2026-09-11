"""Tests for ComplianceRuleEngine — mocked dependencies, no YOLO/camera."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.compliance.engine import ComplianceRuleEngine
from backend.app.compliance.events import (
    TOPIC_COMPLIANCE_ALERT,
    TOPIC_EVIDENCE_CAPTURE,
    ComplianceEvent,
    EvidenceCaptureEvent,
)
from backend.app.compliance.evidence.models import EvidenceItem, EvidencePayload
from backend.app.compliance.metrics import ComplianceMetrics
from backend.app.compliance.rules.base import RuleEvaluationResult
from backend.app.compliance.state_machine import HandwashState, StateTransitionResult
from backend.app.compliance.temporal.models import TemporalMetrics
from backend.app.inference.models.detection import BoundingBox, Detection, DetectionEvent
from backend.app.infrastructure.state_store.in_memory import InMemoryStateStore
from backend.app.infrastructure.message_queue.in_memory import InMemoryMessageQueue

_T0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
_THUMB = b"\xff\xd8" + b"\x00" * 4


def _detection_event(frame_id: int = 1, detections=()) -> DetectionEvent:
    return DetectionEvent(
        camera_id="cam01",
        zone_id="zone_a",
        frame_id=frame_id,
        captured_at=_T0,
        processed_at=_T0,
        detections=tuple(detections),
        thumbnail=_THUMB,
    )


def _build_engine(
    state_store=None,
    rule_evaluator=None,
    message_queue=None,
):
    """Build a ComplianceRuleEngine with real infrastructure but mocked domain."""
    state_store = state_store or InMemoryStateStore()
    message_queue = message_queue or InMemoryMessageQueue()

    tracker = MagicMock()
    tracker.update.return_value = []  # no tracks by default

    obs_builder = MagicMock()
    obs_builder.build.return_value = []  # no observations by default

    state_machine = MagicMock()
    temporal_analyzer = MagicMock()

    if rule_evaluator is None:
        rule_evaluator = MagicMock()
        rule_evaluator.evaluate.return_value = RuleEvaluationResult(
            person_state={"person_id": 7, "current_state": "AT_SINK"},
            outcome=None,
            evidence=None,
        )

    metrics = ComplianceMetrics()

    engine = ComplianceRuleEngine(
        state_store=state_store,
        tracker=tracker,
        observation_builder=obs_builder,
        state_machine=state_machine,
        temporal_analyzer=temporal_analyzer,
        rule_evaluator=rule_evaluator,
        message_queue=message_queue,
        metrics=metrics,
    )
    # Expose inner mocks for assertions
    engine._test_tracker = tracker
    engine._test_obs_builder = obs_builder
    engine._test_state_machine = state_machine
    engine._test_temporal = temporal_analyzer
    engine._test_rule_evaluator = rule_evaluator
    return engine, state_store, message_queue, metrics


class TestComplianceRuleEngine:
    def test_no_observations_skips_evaluation(self):
        engine, store, mq, metrics = _build_engine()
        engine.process(_detection_event())
        engine._test_rule_evaluator.evaluate.assert_not_called()
        assert metrics.snapshot()["evaluations_total"] == 1  # process was called

    def test_state_loaded_and_persisted(self):
        """State must be fetched before and written after evaluation."""
        from backend.app.compliance.observation import Observation

        obs = Observation(
            camera_id="cam01", zone_id="zone_a", person_id=7,
            timestamp=_T0, frame_id=1,
            inside_sink_zone=True, water_detected=False,
            soap_detected=False, hands_interacting=False,
            track_bbox=None,
        )

        engine, store, mq, metrics = _build_engine()
        engine._test_obs_builder.build.return_value = [obs]
        engine._test_state_machine.transition.return_value = StateTransitionResult(
            previous_state=HandwashState.UNKNOWN,
            new_state=HandwashState.AT_SINK,
            timestamp=_T0,
            person_id=7,
            transitioned=True,
            sequence_valid=True,
            reason="test",
        )
        engine._test_temporal.update_and_analyze.return_value = (
            {"person_id": 7, "current_state": "AT_SINK"},
            TemporalMetrics(0, 0, 0, 0, 0, True, True, 1, "AT_SINK", 0.0),
        )
        engine._test_rule_evaluator.evaluate.return_value = RuleEvaluationResult(
            person_state={"person_id": 7, "current_state": "AT_SINK"},
            outcome=None,
            evidence=None,
        )

        engine.process(_detection_event())

        # State should be persisted in store
        from backend.app.infrastructure.state_store.base import make_state_key
        zone_state = store.get(make_state_key("cam01", "zone_a"))
        assert zone_state is not None
        assert "persons" in zone_state
        assert "7" in zone_state["persons"]

    def test_no_alert_when_outcome_is_none(self):
        from backend.app.compliance.observation import Observation

        obs = Observation(
            camera_id="cam01", zone_id="zone_a", person_id=7,
            timestamp=_T0, frame_id=1,
            inside_sink_zone=True, water_detected=False,
            soap_detected=False, hands_interacting=False,
            track_bbox=None,
        )

        engine, store, mq, metrics = _build_engine()
        engine._test_obs_builder.build.return_value = [obs]
        engine._test_state_machine.transition.return_value = StateTransitionResult(
            previous_state=HandwashState.UNKNOWN, new_state=HandwashState.AT_SINK,
            timestamp=_T0, person_id=7, transitioned=True,
            sequence_valid=True, reason="test",
        )
        engine._test_temporal.update_and_analyze.return_value = (
            {"person_id": 7, "current_state": "AT_SINK"},
            TemporalMetrics(0, 0, 0, 0, 0, True, True, 1, "AT_SINK", 0.0),
        )
        engine._test_rule_evaluator.evaluate.return_value = RuleEvaluationResult(
            person_state={"person_id": 7, "current_state": "AT_SINK"},
            outcome=None,
            evidence=None,
        )

        engine.process(_detection_event())
        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 0
        assert mq.qsize(TOPIC_EVIDENCE_CAPTURE) == 0

    def test_alert_and_evidence_published_on_violation(self):
        from backend.app.compliance.observation import Observation

        obs = Observation(
            camera_id="cam01", zone_id="zone_a", person_id=7,
            timestamp=_T0, frame_id=1,
            inside_sink_zone=True, water_detected=False,
            soap_detected=False, hands_interacting=False,
            track_bbox=None,
        )
        evidence = EvidencePayload(
            group_id="g-001",
            camera_id="cam01",
            zone_id="zone_a",
            items=(EvidenceItem(
                frame_id=1, timestamp=_T0, thumbnail=_THUMB,
                camera_id="cam01", zone_id="zone_a", person_id=7,
            ),),
        )

        engine, store, mq, metrics = _build_engine()
        engine._test_obs_builder.build.return_value = [obs]
        engine._test_state_machine.transition.return_value = StateTransitionResult(
            previous_state=HandwashState.AT_SINK, new_state=HandwashState.AT_SINK,
            timestamp=_T0, person_id=7, transitioned=False,
            sequence_valid=True, reason="test",
        )
        engine._test_temporal.update_and_analyze.return_value = (
            {"person_id": 7, "current_state": "AT_SINK",
             "group_id": "g-001", "violation_confirmed": True},
            TemporalMetrics(0, 0, 0, 0, 0, True, True, 1, "AT_SINK", 0.0),
        )
        engine._test_rule_evaluator.evaluate.return_value = RuleEvaluationResult(
            person_state={
                "person_id": 7, "current_state": "AT_SINK",
                "group_id": "g-001", "violation_confirmed": True,
            },
            outcome="violation",
            evidence=evidence,
        )

        engine.process(_detection_event())

        assert mq.qsize(TOPIC_COMPLIANCE_ALERT) == 1
        assert mq.qsize(TOPIC_EVIDENCE_CAPTURE) == 1
        assert metrics.snapshot()["violations_total"] == 1

    def test_evaluation_failure_increments_failure_counter(self):
        engine, store, mq, metrics = _build_engine()
        # Make obs_builder raise to simulate failure
        engine._test_obs_builder.build.side_effect = RuntimeError("boom")
        # But we need at least one observation trigger — override tracker too
        from backend.app.compliance.observation import Observation
        obs = Observation(
            camera_id="cam01", zone_id="zone_a", person_id=7,
            timestamp=_T0, frame_id=1,
            inside_sink_zone=True, water_detected=False,
            soap_detected=False, hands_interacting=False,
            track_bbox=None,
        )
        # Let the builder raise after tracker returns something
        engine._test_tracker.update.return_value = [MagicMock()]

        engine.process(_detection_event())
        assert metrics.snapshot()["evaluation_failures_total"] == 1
