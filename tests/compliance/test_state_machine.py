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
        water_detected=False,
        soap_detected=False,
        hands_interacting=False,
        track_bbox=None,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


@pytest.fixture
def sm():
    return HandwashStateMachine()


# ── Person leaving zone always → UNKNOWN ─────────────────────────────────────

@pytest.mark.parametrize("state", list(HandwashState))
def test_leaves_zone_resets_to_unknown(sm, state):
    obs = _obs(inside_sink_zone=False)
    result = sm.transition(state, obs)
    assert result.new_state == HandwashState.UNKNOWN
    assert result.reason == "left_zone"


# ── UNKNOWN ───────────────────────────────────────────────────────────────────

def test_unknown_person_detected_becomes_at_sink(sm):
    obs = _obs()
    result = sm.transition(HandwashState.UNKNOWN, obs)
    assert result.new_state == HandwashState.AT_SINK
    assert result.transitioned is True


# ── AT_SINK ───────────────────────────────────────────────────────────────────

def test_at_sink_water_detected_becomes_water_on(sm):
    obs = _obs(water_detected=True)
    result = sm.transition(HandwashState.AT_SINK, obs)
    assert result.new_state == HandwashState.WATER_ON


def test_at_sink_soap_detected_becomes_soap_applied(sm):
    obs = _obs(soap_detected=True)
    result = sm.transition(HandwashState.AT_SINK, obs)
    assert result.new_state == HandwashState.SOAP_APPLIED


def test_at_sink_hands_interacting_becomes_washing(sm):
    obs = _obs(hands_interacting=True)
    result = sm.transition(HandwashState.AT_SINK, obs)
    assert result.new_state == HandwashState.WASHING


def test_at_sink_no_activity_stays(sm):
    obs = _obs()
    result = sm.transition(HandwashState.AT_SINK, obs)
    assert result.new_state == HandwashState.AT_SINK
    assert result.transitioned is False


# ── WATER_ON ─────────────────────────────────────────────────────────────────

def test_water_on_soap_becomes_soap_applied(sm):
    obs = _obs(water_detected=True, soap_detected=True)
    result = sm.transition(HandwashState.WATER_ON, obs)
    assert result.new_state == HandwashState.SOAP_APPLIED


def test_water_on_hands_interacting_becomes_washing(sm):
    obs = _obs(water_detected=True, hands_interacting=True)
    result = sm.transition(HandwashState.WATER_ON, obs)
    assert result.new_state == HandwashState.WASHING


def test_water_on_stays_when_only_water(sm):
    obs = _obs(water_detected=True)
    result = sm.transition(HandwashState.WATER_ON, obs)
    assert result.new_state == HandwashState.WATER_ON
    assert result.transitioned is False


# ── SOAP_APPLIED ─────────────────────────────────────────────────────────────

def test_soap_applied_hands_interacting_becomes_washing(sm):
    obs = _obs(soap_detected=True, hands_interacting=True)
    result = sm.transition(HandwashState.SOAP_APPLIED, obs)
    assert result.new_state == HandwashState.WASHING


def test_soap_applied_stays_without_hands(sm):
    obs = _obs(soap_detected=True)
    result = sm.transition(HandwashState.SOAP_APPLIED, obs)
    assert result.new_state == HandwashState.SOAP_APPLIED
    assert result.transitioned is False


# ── WASHING ───────────────────────────────────────────────────────────────────

def test_washing_stays_while_hands_interacting(sm):
    obs = _obs(hands_interacting=True, water_detected=True)
    result = sm.transition(HandwashState.WASHING, obs)
    assert result.new_state == HandwashState.WASHING
    assert result.transitioned is False


def test_washing_no_hands_becomes_rinsing(sm):
    obs = _obs(hands_interacting=False, water_detected=False)
    result = sm.transition(HandwashState.WASHING, obs)
    assert result.new_state == HandwashState.RINSING


def test_washing_no_hands_water_on_becomes_rinsing(sm):
    obs = _obs(hands_interacting=False, water_detected=True)
    result = sm.transition(HandwashState.WASHING, obs)
    assert result.new_state == HandwashState.RINSING


# ── RINSING ───────────────────────────────────────────────────────────────────

def test_rinsing_no_water_becomes_completed(sm):
    obs = _obs(water_detected=False, hands_interacting=False)
    result = sm.transition(HandwashState.RINSING, obs)
    assert result.new_state == HandwashState.COMPLETED


def test_rinsing_hands_interacting_back_to_washing(sm):
    obs = _obs(hands_interacting=True)
    result = sm.transition(HandwashState.RINSING, obs)
    assert result.new_state == HandwashState.WASHING


def test_rinsing_water_on_stays(sm):
    obs = _obs(water_detected=True, hands_interacting=False)
    result = sm.transition(HandwashState.RINSING, obs)
    assert result.new_state == HandwashState.RINSING


# ── COMPLETED ────────────────────────────────────────────────────────────────

def test_completed_stays_completed(sm):
    obs = _obs()
    result = sm.transition(HandwashState.COMPLETED, obs)
    assert result.new_state == HandwashState.COMPLETED
    assert result.transitioned is False


# ── Sequence validation ───────────────────────────────────────────────────────

def test_soap_before_water_flags_sequence_invalid(sm):
    """Soap applied directly from AT_SINK without water → sequence_valid=False."""
    obs = _obs(soap_detected=True, water_detected=False)
    result = sm.transition(HandwashState.AT_SINK, obs)
    assert result.new_state == HandwashState.SOAP_APPLIED
    assert result.sequence_valid is False


def test_soap_after_water_is_valid(sm):
    obs = _obs(soap_detected=True, water_detected=True)
    result = sm.transition(HandwashState.WATER_ON, obs)
    assert result.sequence_valid is True


# ── StateTransitionResult metadata ───────────────────────────────────────────

def test_result_carries_person_id_and_timestamp(sm):
    obs = _obs(person_id=42, timestamp=_T0)
    result = sm.transition(HandwashState.UNKNOWN, obs)
    assert result.person_id == 42
    assert result.timestamp == _T0


def test_result_previous_and_new_state(sm):
    obs = _obs()
    result = sm.transition(HandwashState.UNKNOWN, obs)
    assert result.previous_state == HandwashState.UNKNOWN
    assert result.new_state == HandwashState.AT_SINK
