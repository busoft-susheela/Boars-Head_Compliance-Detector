"""Tests for HandwashRuleEvaluator — no YOLO, camera, or queue required."""

import uuid
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
    at_sink_duration: float = 0.0,
    current_state: str = HandwashState.NEAR_SINK_NOT_WASHING.name,
) -> TemporalMetrics:
    return TemporalMetrics(
        at_sink_duration=at_sink_duration,
        washing_duration=washing_duration,
        sequence_valid=True,
        continuity_valid=True,
        observation_count=1,
        current_state=current_state,
        last_gap_seconds=0.2,
        positive_frames=0,
        no_detection_frames=0,
        hand_movement_score=0.0,
    )


def _person_state(current_state: str = HandwashState.NEAR_SINK_NOT_WASHING.name) -> dict:
    ps = initial_person_state(_PID, _BASE)
    ps["current_state"] = current_state
    return ps


def _config(min_seconds: float = 20.0) -> HandwashRuleConfig:
    return HandwashRuleConfig(
        minimum_washing_duration_seconds=min_seconds,
        absence_threshold_seconds=30.0,
        evidence_buffer_max=10,
        confirmation_frames=3,
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
        session_cooldown_seconds=0.0,  # disable cooldown so tests don't wait
    )


@pytest.fixture
def evaluator():
    return HandwashRuleEvaluator(config=_config())


# ── NEAR_SINK_NOT_WASHING — no outcome yet ────────────────────────────────────

def test_person_near_sink_no_outcome_on_first_frame(evaluator):
    """First frame at sink — debounce not met, no group, no outcome."""
    ps = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)
    result = evaluator.evaluate(
        person_state=ps, metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(0), thumbnail=_THUMB, frame_id=1,
    )
    assert result.outcome is None
    assert result.evidence is None
    # Debounce not crossed yet — no group opened
    assert result.person_state.get("group_id") is None


def test_group_id_minted_after_debounce(evaluator):
    """Group ID is minted once _MIN_SINK_ENTRY_FRAMES consecutive frames are seen."""
    ps = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)
    # Frame 1 — debounce count = 1, still under threshold
    r1 = evaluator.evaluate(
        person_state=ps, metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(0), thumbnail=_THUMB, frame_id=1,
    )
    assert r1.person_state.get("group_id") is None

    # Frame 2 — debounce threshold crossed, group opened
    r2 = evaluator.evaluate(
        person_state=r1.person_state, metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(1), thumbnail=_THUMB, frame_id=2,
    )
    assert r2.person_state.get("group_id") is not None


def test_group_id_stable_across_frames(evaluator):
    """Same group_id is reused on all subsequent NEAR_SINK_NOT_WASHING frames."""
    ps = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)
    for fid in range(1, 4):
        r = evaluator.evaluate(
            person_state=ps, metrics=_metrics(),
            camera_id=_CAM, zone_id=_ZONE,
            timestamp=_t(fid), thumbnail=_THUMB, frame_id=fid,
        )
        ps = r.person_state

    group_id = ps["group_id"]
    assert group_id is not None

    r = evaluator.evaluate(
        person_state=ps, metrics=_metrics(),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(4), thumbnail=_THUMB, frame_id=4,
    )
    assert r.person_state["group_id"] == group_id


# ── WASHING — buffer preserved, no outcome ───────────────────────────────────

def test_person_washing_no_outcome(evaluator):
    """Person actively washing — no outcome, buffer accumulates frames."""
    ps = _person_state(HandwashState.WASHING.name)
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(washing_duration=5.0, current_state=HandwashState.WASHING.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(5), thumbnail=_THUMB, frame_id=5,
    )
    assert result.outcome is None
    assert result.evidence is None


def test_washing_preserves_group_id(evaluator):
    """Transitioning to WASHING must NOT clear the evidence group."""
    ps = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)
    # Open a group via NEAR_SINK_NOT_WASHING (2 frames to pass debounce)
    for fid in (1, 2):
        r = evaluator.evaluate(
            person_state=ps, metrics=_metrics(),
            camera_id=_CAM, zone_id=_ZONE,
            timestamp=_t(fid), thumbnail=_THUMB, frame_id=fid,
        )
        ps = r.person_state
    group_id = ps["group_id"]
    assert group_id is not None

    # Transition to WASHING
    ps_washing = dict(ps)
    ps_washing["current_state"] = HandwashState.WASHING.name
    r_washing = evaluator.evaluate(
        person_state=ps_washing,
        metrics=_metrics(washing_duration=1.0, current_state=HandwashState.WASHING.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(3), thumbnail=_THUMB, frame_id=3,
    )
    # Group must be preserved (buffer is kept open through WASHING)
    assert r_washing.person_state["group_id"] == group_id
    assert r_washing.outcome is None


# ── Zone exit — violation on insufficient washing ────────────────────────────

def _state_with_group(current_state: str) -> dict:
    """Return a person_state dict that already has an open evidence group."""
    ps = _person_state(current_state)
    ps["group_id"] = str(uuid.uuid4())
    ps["absence_started_at"] = _BASE.isoformat()
    return ps


def test_violation_on_zone_exit_insufficient_washing(evaluator):
    """Person exits after < minimum washing → outcome='violation'."""
    # Run through normal entry flow so the evaluator has a populated buffer.
    ps = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)
    for fid in (1, 2):
        r = evaluator.evaluate(
            person_state=ps, metrics=_metrics(),
            camera_id=_CAM, zone_id=_ZONE,
            timestamp=_t(fid), thumbnail=_THUMB, frame_id=fid,
        )
        ps = r.person_state
    ps = dict(ps)
    ps["current_state"] = HandwashState.NOT_NEAR_SINK.name
    # First exit frame: opens cooldown window, no outcome yet.
    r1 = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(washing_duration=5.0, current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(10), thumbnail=_THUMB, frame_id=10,
    )
    assert r1.outcome is None  # cooldown pending
    # Second exit frame after cooldown elapsed (session_cooldown_seconds=0.0).
    result = evaluator.evaluate(
        person_state=r1.person_state,
        metrics=_metrics(washing_duration=5.0, current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(10.1), thumbnail=_THUMB, frame_id=11,
    )
    assert result.outcome == "violation"
    assert result.evidence is not None


def test_no_violation_on_zone_exit_compliant_washing(evaluator):
    """Person exits after >= minimum washing → compliant, no violation."""
    ps = _state_with_group(HandwashState.NOT_NEAR_SINK.name)
    # First exit: cooldown pending.
    r1 = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(washing_duration=25.0, current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(30), thumbnail=_THUMB, frame_id=30,
    )
    assert r1.outcome is None
    # Second exit after cooldown: evaluates as compliant.
    result = evaluator.evaluate(
        person_state=r1.person_state,
        metrics=_metrics(washing_duration=25.0, current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(30.1), thumbnail=_THUMB, frame_id=31,
    )
    assert result.outcome is None
    assert result.evidence is None


def test_violation_evidence_carries_group_id(evaluator):
    """Frozen evidence must carry the same group_id as the person state."""
    # Run through normal entry flow so the evaluator opens and populates a buffer.
    ps = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)
    for fid in (1, 2):
        r = evaluator.evaluate(
            person_state=ps, metrics=_metrics(),
            camera_id=_CAM, zone_id=_ZONE,
            timestamp=_t(fid), thumbnail=_THUMB, frame_id=fid,
        )
        ps = r.person_state
    expected_group = ps["group_id"]
    ps = dict(ps)
    ps["current_state"] = HandwashState.NOT_NEAR_SINK.name
    # First exit: cooldown pending.
    r1 = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(washing_duration=5.0, current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(10), thumbnail=_THUMB, frame_id=10,
    )
    # Second exit after cooldown: confirms violation.
    result = evaluator.evaluate(
        person_state=r1.person_state,
        metrics=_metrics(washing_duration=5.0, current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(10.1), thumbnail=_THUMB, frame_id=11,
    )
    assert result.evidence.group_id == expected_group


def test_idempotency_no_repeat_violation(evaluator):
    """Once violation_confirmed=True, subsequent zone-exit calls return None."""
    ps = _state_with_group(HandwashState.NOT_NEAR_SINK.name)
    ps["violation_confirmed"] = True

    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(washing_duration=5.0, current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(10), thumbnail=_THUMB, frame_id=10,
    )
    assert result.outcome is None


def test_zone_exit_without_group_and_zero_metrics_is_noop(evaluator):
    """Exit with no group and no accumulated time → nothing evaluated, no crash."""
    ps = _person_state(HandwashState.NOT_NEAR_SINK.name)
    result = evaluator.evaluate(
        person_state=ps,
        metrics=_metrics(washing_duration=0.0, at_sink_duration=0.0,
                         current_state=HandwashState.NOT_NEAR_SINK.name),
        camera_id=_CAM, zone_id=_ZONE,
        timestamp=_t(0), thumbnail=None, frame_id=1,
    )
    assert result.outcome is None


# ── Zone isolation ────────────────────────────────────────────────────────────

def test_different_zones_have_independent_buffers():
    """Two zones on the same camera must not share evidence buffers."""
    evaluator = HandwashRuleEvaluator(config=_config())

    ps_a = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)
    ps_b = _person_state(HandwashState.NEAR_SINK_NOT_WASHING.name)

    # Two frames each to pass the debounce and open a group
    for fid in (1, 2):
        r = evaluator.evaluate(
            person_state=ps_a, metrics=_metrics(),
            camera_id=_CAM, zone_id="zone_a",
            timestamp=_t(fid), thumbnail=_THUMB, frame_id=fid,
        )
        ps_a = r.person_state

    for fid in (1, 2):
        r = evaluator.evaluate(
            person_state=ps_b, metrics=_metrics(),
            camera_id=_CAM, zone_id="zone_b",
            timestamp=_t(fid), thumbnail=_THUMB, frame_id=fid,
        )
        ps_b = r.person_state

    assert ps_a["group_id"] is not None
    assert ps_b["group_id"] is not None
    assert ps_a["group_id"] != ps_b["group_id"]


# ── HandwashRuleConfig validation ─────────────────────────────────────────────

def _minimal_config(**overrides) -> dict:
    base = dict(
        minimum_washing_duration_seconds=20.0,
        absence_threshold_seconds=30.0,
        evidence_buffer_max=10,
        confirmation_frames=3,
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
    )
    base.update(overrides)
    return base


def test_config_rejects_zero_min_duration():
    with pytest.raises(ValueError):
        HandwashRuleConfig(**_minimal_config(minimum_washing_duration_seconds=0))


def test_config_rejects_zero_buffer_max():
    with pytest.raises(ValueError):
        HandwashRuleConfig(**_minimal_config(evidence_buffer_max=0))


def test_config_rejects_zero_confirmation_frames():
    with pytest.raises(ValueError):
        HandwashRuleConfig(**_minimal_config(confirmation_frames=0))


def test_config_from_config_nested():
    """from_config reads from compliance.handwash.* nested structure."""
    cfg = {
        "handwash": {
            "minimum_washing_duration_seconds": 30.0,
            "evidence_buffer_max": 5,
        },
    }
    rc = HandwashRuleConfig.from_config(cfg)
    assert rc.minimum_washing_duration_seconds == 30.0
    assert rc.evidence_buffer_max == 5
    # Defaults kick in for everything else
    assert rc.confirmation_frames == 3
