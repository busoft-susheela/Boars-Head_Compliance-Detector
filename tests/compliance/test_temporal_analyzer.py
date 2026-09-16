"""Tests for SpatioTemporalAnalyzer and initial_person_state."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.compliance.state_machine import HandwashState, StateTransitionResult
from backend.app.compliance.temporal.analyzer import (
    SpatioTemporalAnalyzer,
    initial_person_state,
)

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


# ── initial_person_state ──────────────────────────────────────────────────────

def test_initial_state_defaults(person_state):
    assert person_state["person_id"] == 7
    assert person_state["current_state"] == HandwashState.NOT_NEAR_SINK.name
    assert person_state["observation_count"] == 0
    assert person_state["sequence_valid"] is True
    assert person_state["washing_seconds"] == 0.0
    assert person_state["at_sink_seconds"] == 0.0


# ── Duration accumulation ─────────────────────────────────────────────────────

def test_entry_then_washing_accumulates_at_sink(analyzer, person_state):
    # NOT_NEAR_SINK → NEAR_SINK_NOT_WASHING at t=0
    tr1 = _transition(HandwashState.NOT_NEAR_SINK, HandwashState.NEAR_SINK_NOT_WASHING, _t(0))
    state, _ = analyzer.update_and_analyze(person_state, tr1)

    # NEAR_SINK_NOT_WASHING → WASHING at t=3  (3 seconds at sink)
    tr2 = _transition(HandwashState.NEAR_SINK_NOT_WASHING, HandwashState.WASHING, _t(3))
    state, metrics = analyzer.update_and_analyze(state, tr2)

    assert metrics.at_sink_duration == pytest.approx(3.0)
    assert metrics.washing_duration == pytest.approx(0.0)  # just transitioned in
    assert metrics.current_state == HandwashState.WASHING.name


def test_washing_duration_accumulates_from_timestamps(analyzer, person_state):
    """Duration is driven by wall-clock timestamps, not frame count."""
    # Enter sink at t=0
    state, _ = analyzer.update_and_analyze(
        person_state,
        _transition(HandwashState.NOT_NEAR_SINK, HandwashState.NEAR_SINK_NOT_WASHING, _t(0)),
    )
    # Washing confirmed at t=3
    state, _ = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.NEAR_SINK_NOT_WASHING, HandwashState.WASHING, _t(3)),
    )
    # Still WASHING at t=8 (no transition, ongoing)
    state, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.WASHING, HandwashState.WASHING, _t(8)),
    )
    # WASHING → NEAR_SINK_NOT_WASHING at t=31 (28 seconds of washing finalized)
    state, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.WASHING, HandwashState.NEAR_SINK_NOT_WASHING, _t(31)),
    )
    assert metrics.washing_duration == pytest.approx(28.0)
    assert metrics.at_sink_duration == pytest.approx(3.0)   # only the initial entry phase


def test_full_lifecycle_durations(analyzer, person_state):
    """
    t=0   NOT_NEAR_SINK → NEAR_SINK_NOT_WASHING
    t=3   NEAR_SINK_NOT_WASHING → WASHING
    t=31  WASHING → NOT_NEAR_SINK  (exit, 28 s washing)
    """
    state, _ = analyzer.update_and_analyze(
        person_state,
        _transition(HandwashState.NOT_NEAR_SINK, HandwashState.NEAR_SINK_NOT_WASHING, _t(0)),
    )
    state, _ = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.NEAR_SINK_NOT_WASHING, HandwashState.WASHING, _t(3)),
    )
    state, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.WASHING, HandwashState.NOT_NEAR_SINK, _t(31)),
    )

    assert metrics.at_sink_duration == pytest.approx(3.0)   # t=0..3
    assert metrics.washing_duration == pytest.approx(28.0)  # t=3..31


def test_observation_count_increments(analyzer, person_state):
    state, metrics = analyzer.update_and_analyze(
        person_state,
        _transition(HandwashState.NOT_NEAR_SINK, HandwashState.NEAR_SINK_NOT_WASHING, _t(0)),
    )
    assert metrics.observation_count == 1
    _, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.NEAR_SINK_NOT_WASHING, HandwashState.NEAR_SINK_NOT_WASHING, _t(1)),
    )
    assert metrics.observation_count == 2


# ── Continuity ────────────────────────────────────────────────────────────────

def test_continuity_valid_when_gap_within_threshold(analyzer, person_state):
    state, _ = analyzer.update_and_analyze(
        person_state,
        _transition(HandwashState.NOT_NEAR_SINK, HandwashState.NEAR_SINK_NOT_WASHING, _t(0)),
    )
    _, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.NEAR_SINK_NOT_WASHING, HandwashState.NEAR_SINK_NOT_WASHING, _t(5)),
    )
    assert metrics.continuity_valid is True


def test_continuity_invalid_when_gap_exceeds_threshold(analyzer, person_state):
    state, _ = analyzer.update_and_analyze(
        person_state,
        _transition(HandwashState.NOT_NEAR_SINK, HandwashState.NEAR_SINK_NOT_WASHING, _t(0)),
    )
    _, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.NEAR_SINK_NOT_WASHING, HandwashState.NEAR_SINK_NOT_WASHING, _t(15)),
    )
    assert metrics.continuity_valid is False


# ── Ongoing current state adds to metrics ─────────────────────────────────────

def test_ongoing_washing_included_in_metrics(analyzer, person_state):
    """Ongoing WASHING time must be included in washing_duration even without a transition."""
    state, _ = analyzer.update_and_analyze(
        person_state,
        _transition(HandwashState.NOT_NEAR_SINK, HandwashState.NEAR_SINK_NOT_WASHING, _t(0)),
    )
    state, _ = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.NEAR_SINK_NOT_WASHING, HandwashState.WASHING, _t(3)),
    )
    # Same-state observation at t=13 — 10 seconds of WASHING ongoing
    _, metrics = analyzer.update_and_analyze(
        state,
        _transition(HandwashState.WASHING, HandwashState.WASHING, _t(13)),
    )
    assert metrics.washing_duration == pytest.approx(10.0)
