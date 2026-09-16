"""Tests for HandwashStateMachine and HandwashState."""

from datetime import datetime, timezone

import pytest

from backend.app.compliance.observation import Observation
from backend.app.compliance.state_machine import HandwashState, HandwashStateMachine

_T0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _obs(**kwargs) -> Observation:
    defaults = dict(
        camera_id="cam01",
        zone_id="zone_a",
        person_id=7,
        timestamp=_T0,
        frame_id=1,
        inside_sink_zone=True,
        hands_interacting=False,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


@pytest.fixture
def sm():
    return HandwashStateMachine()


# ── NOT_NEAR_SINK ─────────────────────────────────────────────────────────────

def test_not_near_sink_enters_sink(sm):
    result = sm.transition(HandwashState.NOT_NEAR_SINK, _obs(inside_sink_zone=True))
    assert result.new_state == HandwashState.NEAR_SINK_NOT_WASHING
    assert result.reason == "entered_sink_area"
    assert result.transitioned is True


def test_not_near_sink_stays_when_not_at_sink(sm):
    result = sm.transition(HandwashState.NOT_NEAR_SINK, _obs(inside_sink_zone=False))
    assert result.new_state == HandwashState.NOT_NEAR_SINK
    assert result.reason == "not_near_sink"
    assert result.transitioned is False


# ── NEAR_SINK_NOT_WASHING ─────────────────────────────────────────────────────

def test_near_sink_washing_confirmed(sm):
    result = sm.transition(HandwashState.NEAR_SINK_NOT_WASHING, _obs(hands_interacting=True))
    assert result.new_state == HandwashState.WASHING
    assert result.reason == "washing_confirmed"
    assert result.transitioned is True


def test_near_sink_stays_without_hands(sm):
    result = sm.transition(HandwashState.NEAR_SINK_NOT_WASHING, _obs(hands_interacting=False))
    assert result.new_state == HandwashState.NEAR_SINK_NOT_WASHING
    assert result.reason == "near_sink_not_washing"
    assert result.transitioned is False


def test_near_sink_exits_zone(sm):
    result = sm.transition(HandwashState.NEAR_SINK_NOT_WASHING, _obs(inside_sink_zone=False))
    assert result.new_state == HandwashState.NOT_NEAR_SINK
    assert result.reason == "left_sink_area"
    assert result.transitioned is True


# ── WASHING ───────────────────────────────────────────────────────────────────

def test_washing_stays_while_hands_interacting(sm):
    result = sm.transition(HandwashState.WASHING, _obs(hands_interacting=True))
    assert result.new_state == HandwashState.WASHING
    assert result.reason == "still_washing"
    assert result.transitioned is False


def test_washing_stops_when_hands_stop(sm):
    result = sm.transition(HandwashState.WASHING, _obs(hands_interacting=False))
    assert result.new_state == HandwashState.NEAR_SINK_NOT_WASHING
    assert result.reason == "washing_stopped"
    assert result.transitioned is True


def test_washing_exits_zone(sm):
    result = sm.transition(HandwashState.WASHING, _obs(inside_sink_zone=False))
    assert result.new_state == HandwashState.NOT_NEAR_SINK
    assert result.reason == "left_sink_area"
    assert result.transitioned is True


# ── Terminal states (WASHED / NOT_WASHED) ────────────────────────────────────

@pytest.mark.parametrize("terminal", [HandwashState.WASHED, HandwashState.NOT_WASHED])
def test_terminal_stays_while_still_at_sink(sm, terminal):
    """No new cycle starts while the person is still physically at the sink."""
    result = sm.transition(terminal, _obs(inside_sink_zone=True))
    assert result.new_state == terminal
    assert result.reason == "terminal_waiting_exit"
    assert result.transitioned is False


@pytest.mark.parametrize("terminal", [HandwashState.WASHED, HandwashState.NOT_WASHED])
def test_terminal_resets_when_person_leaves(sm, terminal):
    """Reset to NOT_NEAR_SINK only once the person has physically left."""
    result = sm.transition(terminal, _obs(inside_sink_zone=False))
    assert result.new_state == HandwashState.NOT_NEAR_SINK
    assert result.reason == "new_visit_after_terminal"
    assert result.transitioned is True


# ── StateTransitionResult metadata ───────────────────────────────────────────

def test_result_carries_person_id_and_timestamp(sm):
    result = sm.transition(HandwashState.NOT_NEAR_SINK, _obs(person_id=42, timestamp=_T0))
    assert result.person_id == 42
    assert result.timestamp == _T0


def test_result_previous_and_new_state(sm):
    result = sm.transition(HandwashState.NOT_NEAR_SINK, _obs(inside_sink_zone=True))
    assert result.previous_state == HandwashState.NOT_NEAR_SINK
    assert result.new_state == HandwashState.NEAR_SINK_NOT_WASHING
