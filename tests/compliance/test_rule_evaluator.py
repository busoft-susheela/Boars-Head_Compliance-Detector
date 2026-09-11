"""Tests for HandwashRuleEvaluator — no YOLO, camera, or queue required."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.compliance.rules.config import HandwashRuleConfig
from backend.app.compliance.rules.handwash import HandwashRuleEvaluator
from backend.app.compliance.state_machine import HandwashState
from backend.app.compliance.temporal.analyzer import initial_person_state
from backend.app.compliance.temporal.models import TemporalMetrics

_BASE = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
_THUMB = b"\xff\xd8\xff" + b"\x00" * 5
_CAM = "cam01"
_ZONE = "zone_a"
_PID = 7


def _t(seconds: float) -> datetime:
    return _BASE + timedelta(seconds=seconds)


def _metrics(
    washing_duration: float = 0.0,
    current_state: str = HandwashState.AT_SINK.name,
    sequence_valid: bool = True,
    continuity_valid: bool = True,
) -> TemporalMetrics:
    return TemporalMetrics(
        at_sink_duration=0.0,
        water_on_duration=0.0,
        soap_applied_duration=0.0,
        washing_duration=washing_duration,
        rinsing_duration=0.0,
        sequence_valid=sequence_valid,
        continuity_valid=continuity_valid,
        observation_count=1,
        current_state=current_state,
        last_gap_seconds=0.2,
    )


def _person_state(current_state: str = HandwashState.AT_SINK.name) -> dict:
    ps = initial_person_state(_PID, _BASE)
    ps["current_state"] = current_state
    return ps


def _config(absence_threshold: float = 20.0) -> HandwashRuleConfig:
    return HandwashRuleConfig(
        minimum_washing_duration_seconds=20.0,
        absence_threshold_seconds=absence_threshold,
        require_soap=False,
        require_water=False,
        require_sequence=False,
        require_completion=False,
        evidence_buffer_max=10,
    )


@pytest.fixture
def evaluator():
    return HandwashRuleEvaluator(config=_config())


# ── No absence yet ────────────────────────────────────────────────────────────

def test_person_at_sink_no_outcome_initially(evaluator):
    """First frame at sink — no violation yet."""
    ps = _person_state(HandwashState.AT_SINK.name)
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(current_state=HandwashState.AT_SINK.name),
        camera_id=_CAM,
        zone_id=_ZONE,
        timestamp=_t(0),
        thumbnail=_THUMB,
        frame_id=1,
    )
    assert result.outcome is None
    assert result.evidence is None


def test_person_washing_no_outcome(evaluator):
    """Person actively washing — no violation."""
    ps = _person_state(HandwashState.WASHING.name)
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(washing_duration=23.0, current_state=HandwashState.WASHING.name),
        camera_id=_CAM,
        zone_id=_ZONE,
        timestamp=_t(23),
        thumbnail=_THUMB,
        frame_id=10,
    )
    assert result.outcome is None


# ── Absence group lifecycle ───────────────────────────────────────────────────

def test_group_id_minted_on_first_absence_frame(evaluator):
    ps = _person_state(HandwashState.AT_SINK.name)
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(),
        camera_id=_CAM,
        zone_id=_ZONE,
        timestamp=_t(0),
        thumbnail=_THUMB,
        frame_id=1,
    )
    assert result.person_state.get("group_id") is not None


def test_group_id_stable_across_frames(evaluator):
    """Same group_id must be reused on subsequent absence frames."""
    ps = _person_state(HandwashState.AT_SINK.name)

    result1 = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(0), thumbnail=_THUMB, frame_id=1,
    )
    group_id_1 = result1.person_state["group_id"]

    result2 = evaluator.evaluate(
        person_state=result1.person_state,
        metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(5), thumbnail=_THUMB, frame_id=2,
    )
    assert result2.person_state["group_id"] == group_id_1


def test_compliance_resumes_clears_group(evaluator):
    """If person starts washing, the absence group is discarded."""
    ps = _person_state(HandwashState.AT_SINK.name)
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(0), thumbnail=_THUMB, frame_id=1,
    )
    assert result.person_state["group_id"] is not None

    # Now person transitions to WASHING
    ps_washing = dict(result.person_state)
    ps_washing["current_state"] = HandwashState.WASHING.name
    result2 = evaluator.evaluate(
        person_state=ps_washing,
        metrics=_metrics(washing_duration=1.0, current_state=HandwashState.WASHING.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(1), thumbnail=_THUMB, frame_id=2,
    )
    assert result2.outcome is None
    assert result2.person_state["group_id"] is None


# ── Violation confirmation ────────────────────────────────────────────────────

def test_violation_confirmed_when_threshold_reached(evaluator):
    """After absence_threshold_seconds the evaluator returns outcome='violation'."""
    ps = _person_state(HandwashState.AT_SINK.name)

    # Build absence to just under threshold
    for i in range(19):
        result = evaluator.evaluate(
            person_state=ps,
            metrics=_metrics(),
            camera_id=_CAM, zone_id=_ZONE,
            timestamp=_t(i), thumbnail=_THUMB, frame_id=i,
        )
        ps = result.person_state
        assert result.outcome is None, f"Unexpected violation at t={i}"

    # At or beyond threshold (t=20 >= 20)
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(20), thumbnail=_THUMB, frame_id=20,
    )
    assert result.outcome == "violation"
    assert result.evidence is not None


def test_violation_evidence_contains_group_id(evaluator):
    ps = _person_state(HandwashState.AT_SINK.name)
    for i in range(20):
        result = evaluator.evaluate(
            person_state=ps,
            metrics=_metrics(),
            camera_id=_CAM, zone_id=_ZONE,
            timestamp=_t(i), thumbnail=_THUMB, frame_id=i,
        )
        ps = result.person_state
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(20), thumbnail=_THUMB, frame_id=20,
    )
    assert result.evidence.group_id == ps["group_id"]


def test_idempotency_no_repeat_violation(evaluator):
    """Subsequent frames after confirmed violation must NOT produce a second outcome."""
    ps = _person_state(HandwashState.AT_SINK.name)
    for i in range(21):
        result = evaluator.evaluate(
            person_state=ps,
            metrics=_metrics(),
            camera_id=_CAM, zone_id=_ZONE,
            timestamp=_t(i), thumbnail=_THUMB, frame_id=i,
        )
        ps = result.person_state

    # Frame 21 — violation already confirmed; must return None
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(21), thumbnail=_THUMB, frame_id=21,
    )
    assert result.outcome is None


# ── Zone isolation ────────────────────────────────────────────────────────────

def test_different_zones_have_independent_buffers():
    """Two zones on the same camera must not share evidence buffers."""
    evaluator = HandwashRuleEvaluator(config=_config(absence_threshold=5.0))

    ps_a = _person_state(HandwashState.AT_SINK.name)
    ps_b = _person_state(HandwashState.AT_SINK.name)

    for i in range(5):
        result_a = evaluator.evaluate(
            person_state=ps_a, metrics=_metrics(),
            camera_id=_CAM, zone_id="zone_a",
            timestamp=_t(i), thumbnail=_THUMB, frame_id=i,
        )
        ps_a = result_a.person_state

    for i in range(5):
        result_b = evaluator.evaluate(
            person_state=ps_b, metrics=_metrics(),
            camera_id=_CAM, zone_id="zone_b",
            timestamp=_t(i), thumbnail=_THUMB, frame_id=i,
        )
        ps_b = result_b.person_state

    # Zone A and B must have different group_ids
    assert ps_a["group_id"] != ps_b["group_id"]


# ── Zone exit ────────────────────────────────────────────────────────────────

def test_zone_exit_clears_unconfirmed_group(evaluator):
    ps = _person_state(HandwashState.AT_SINK.name)
    result = evaluator.evaluate(
        person_state=ps, metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(0), thumbnail=_THUMB, frame_id=1,
    )
    assert result.person_state["group_id"] is not None

    # Person leaves zone
    ps_unknown = dict(result.person_state)
    ps_unknown["current_state"] = HandwashState.UNKNOWN.name
    result2 = evaluator.evaluate(
        person_state=ps_unknown,
        metrics=_metrics(current_state=HandwashState.UNKNOWN.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(1), thumbnail=_THUMB, frame_id=2,
    )
    assert result2.outcome is None
    assert result2.person_state["group_id"] is None


# ── HandwashRuleConfig validation ─────────────────────────────────────────────

def test_config_rejects_zero_min_duration():
    with pytest.raises(ValueError):
        HandwashRuleConfig(
            minimum_washing_duration_seconds=0,
            absence_threshold_seconds=20,
            require_soap=False,
            require_water=False,
            require_sequence=False,
            require_completion=False,
            evidence_buffer_max=10,
        )


def test_config_rejects_zero_absence_threshold():
    with pytest.raises(ValueError):
        HandwashRuleConfig(
            minimum_washing_duration_seconds=20,
            absence_threshold_seconds=0,
            require_soap=False,
            require_water=False,
            require_sequence=False,
            require_completion=False,
            evidence_buffer_max=10,
        )


def test_config_rejects_zero_buffer_max():
    with pytest.raises(ValueError):
        HandwashRuleConfig(
            minimum_washing_duration_seconds=20,
            absence_threshold_seconds=20,
            require_soap=False,
            require_water=False,
            require_sequence=False,
            require_completion=False,
            evidence_buffer_max=0,
        )


def test_config_from_config_flat():
    cfg = {"min_seconds": 30.0, "evidence_buffer_max": 5}
    rc = HandwashRuleConfig.from_config(cfg)
    assert rc.minimum_washing_duration_seconds == 30.0
    assert rc.absence_threshold_seconds == 30.0
    assert rc.evidence_buffer_max == 5
