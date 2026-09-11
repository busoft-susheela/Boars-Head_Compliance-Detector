"""Tests for SpatioTemporalAnalyzer and initial_person_state."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.compliance.state_machine import HandwashState, StateTransitionResult
from backend.app.compliance.temporal.analyzer import (
    SpatioTemporalAnalyzer,
    initial_person_state,
)
from backend.app.compliance.temporal.models import TemporalMetrics

_BASE = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _t(seconds: float) -> datetime:
    return _BASE + timedelta(seconds=seconds)


def _transition(
    prev: HandwashState,
    new: HandwashState,
    timestamp: datetime,
    person_id: int = 7,
    sequence_valid: bool = True,
) -> StateTransitionResult:
    return StateTransitionResult(
        previous_state=prev,
        new_state=new,
        timestamp=timestamp,
        person_id=person_id,
        transitioned=(prev != new),
        sequence_valid=sequence_valid,
        reason="test",
    )


@pytest.fixture
def analyzer():
    return SpatioTemporalAnalyzer(max_gap_seconds=10.0)


@pytest.fixture
def person_state():
    return initial_person_state(person_id=7, timestamp=_t(0))


# ── initial_person_state ─────────────────────────────────────────────────────

def test_initial_state_defaults(person_state):
    assert person_state["person_id"] == 7
    assert person_state["current_state"] == HandwashState.UNKNOWN.name
    assert person_state["observation_count"] == 0
    assert person_state["sequence_valid"] is True
    assert person_state["washing_seconds"] == 0.0


# ── Duration accumulation ─────────────────────────────────────────────────────

def test_unknown_to_at_sink_then_washing_accumulates_at_sink(analyzer, person_state):
    # UNKNOWN → AT_SINK at t=0
    t1 = _t(0)
    tr1 = _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, t1)
    state, _ = analyzer.update_and_analyze(person_state, tr1)

    # AT_SINK → WASHING at t=3  (3 seconds at sink)
    t2 = _t(3)
    tr2 = _transition(HandwashState.AT_SINK, HandwashState.WASHING, t2)
    state, metrics = analyzer.update_and_analyze(state, tr2)

    assert metrics.at_sink_duration == pytest.approx(3.0)
    assert metrics.washing_duration == pytest.approx(0.0)  # just transitioned in
    assert metrics.current_state == HandwashState.WASHING.name


def test_washing_duration_accumulates_from_timestamps(analyzer, person_state):
    """Use synthetic timestamps — must NOT use frame count."""
    # UNKNOWN → AT_SINK at t=0
    state, _ = analyzer.update_and_analyze(
        person_state, _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, _t(0))
    )
    # AT_SINK → WASHING at t=3
    state, _ = analyzer.update_and_analyze(
        state, _transition(HandwashState.AT_SINK, HandwashState.WASHING, _t(3))
    )
    # WASHING stays at t=8  (5 seconds elapsed in WASHING so far)
    state, metrics = analyzer.update_and_analyze(
        state, _transition(HandwashState.WASHING, HandwashState.WASHING, _t(8))
    )
    # WASHING → RINSING at t=31  (total 28 seconds washing: 8-3=5 ongoing + finalized)
    state, metrics = analyzer.update_and_analyze(
        state, _transition(HandwashState.WASHING, HandwashState.RINSING, _t(31))
    )
    # washing_seconds should be finalized: 31 - 3 = 28 seconds
    assert metrics.washing_duration == pytest.approx(28.0)
    assert metrics.rinsing_duration == pytest.approx(0.0)


def test_full_lifecycle_durations(analyzer, person_state):
    """
    t=0   UNKNOWN → AT_SINK
    t=3   AT_SINK → WATER_ON
    t=5   WATER_ON → SOAP_APPLIED
    t=8   SOAP_APPLIED → WASHING
    t=31  WASHING → RINSING
    t=33  RINSING → COMPLETED
    """
    state, _ = analyzer.update_and_analyze(
        person_state, _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, _t(0))
    )
    state, _ = analyzer.update_and_analyze(
        state, _transition(HandwashState.AT_SINK, HandwashState.WATER_ON, _t(3))
    )
    state, _ = analyzer.update_and_analyze(
        state, _transition(HandwashState.WATER_ON, HandwashState.SOAP_APPLIED, _t(5))
    )
    state, _ = analyzer.update_and_analyze(
        state, _transition(HandwashState.SOAP_APPLIED, HandwashState.WASHING, _t(8))
    )
    state, _ = analyzer.update_and_analyze(
        state, _transition(HandwashState.WASHING, HandwashState.RINSING, _t(31))
    )
    state, metrics = analyzer.update_and_analyze(
        state, _transition(HandwashState.RINSING, HandwashState.COMPLETED, _t(33))
    )

    assert metrics.at_sink_duration == pytest.approx(3.0)     # t=0..3
    assert metrics.water_on_duration == pytest.approx(2.0)    # t=3..5
    assert metrics.soap_applied_duration == pytest.approx(3.0) # t=5..8
    assert metrics.washing_duration == pytest.approx(23.0)    # t=8..31
    assert metrics.rinsing_duration == pytest.approx(2.0)     # t=31..33


def test_observation_count_increments(analyzer, person_state):
    state, metrics = analyzer.update_and_analyze(
        person_state, _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, _t(0))
    )
    assert metrics.observation_count == 1
    state, metrics = analyzer.update_and_analyze(
        state, _transition(HandwashState.AT_SINK, HandwashState.AT_SINK, _t(1))
    )
    assert metrics.observation_count == 2


# ── Sequence validity ─────────────────────────────────────────────────────────

def test_sequence_valid_degrades_and_stays_false(analyzer, person_state):
    # Valid transition
    state, metrics = analyzer.update_and_analyze(
        person_state,
        _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, _t(0), sequence_valid=True),
    )
    assert metrics.sequence_valid is True

    # Invalid transition (soap before water)
    state, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.AT_SINK, HandwashState.SOAP_APPLIED, _t(1), sequence_valid=False),
    )
    assert metrics.sequence_valid is False

    # Valid transition after — sequence_valid stays False
    state, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.SOAP_APPLIED, HandwashState.WASHING, _t(2), sequence_valid=True),
    )
    assert metrics.sequence_valid is False


# ── Continuity ────────────────────────────────────────────────────────────────

def test_continuity_valid_when_gap_within_threshold(analyzer, person_state):
    state, _ = analyzer.update_and_analyze(
        person_state, _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, _t(0))
    )
    _, metrics = analyzer.update_and_analyze(
        state, _transition(HandwashState.AT_SINK, HandwashState.AT_SINK, _t(5))
    )
    assert metrics.continuity_valid is True


def test_continuity_invalid_when_gap_exceeds_threshold(analyzer, person_state):
    state, _ = analyzer.update_and_analyze(
        person_state, _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, _t(0))
    )
    _, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.AT_SINK, HandwashState.AT_SINK, _t(15)),  # 15s gap > 10s threshold
    )
    assert metrics.continuity_valid is False


# ── Ongoing current state adds to metrics ─────────────────────────────────────

def test_ongoing_washing_included_in_metrics(analyzer, person_state):
    """If current state is WASHING, ongoing time must be reflected in washing_duration."""
    state, _ = analyzer.update_and_analyze(
        person_state, _transition(HandwashState.UNKNOWN, HandwashState.AT_SINK, _t(0))
    )
    state, _ = analyzer.update_and_analyze(
        state, _transition(HandwashState.AT_SINK, HandwashState.WASHING, _t(3))
    )
    # Same-state observation at t=13 — 10 seconds of WASHING ongoing
    state, metrics = analyzer.update_and_analyze(
        state, _transition(HandwashState.WASHING, HandwashState.WASHING, _t(13))
    )
    # 13 - 3 = 10 seconds of WASHING accumulated
    assert metrics.washing_duration == pytest.approx(10.0)
