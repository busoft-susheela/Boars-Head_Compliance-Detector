"""SpatioTemporalAnalyzer — derives temporal metrics from state history.

Responsibility: "For how long?" — duration measurement only.

The analyzer updates the per-person state dict and computes TemporalMetrics
from the latest state transition.  It does NOT decide compliance.

State dict schema (per-person, stored in StateStore zone dict)
--------------------------------------------------------------
{
    "person_id":                int,
    "current_state":            str,    # HandwashState.name
    "state_started_at":         str,    # UTC ISO-8601
    "last_seen_at":             str,    # UTC ISO-8601
    "observation_count":        int,
    "sequence_valid":           bool,
    "at_sink_seconds":          float,  # accumulated NEAR_SINK_NOT_WASHING time
    "washing_seconds":          float,  # accumulated WASHING time
    "last_frame_id":            int,    # last real (non-synthetic) frame seen
    "consecutive_absence_frames": int,  # kept for evaluator debounce
    # Frame-based metrics — updated from ObservationBuilder each frame:
    "positive_frames":          int,
    "no_detection_frames":      int,
    "hand_movement_score":      float,
}

Continuity check
----------------
If the gap between the last observation and the current transition exceeds
`max_gap_seconds`, `continuity_valid` is set to False in TemporalMetrics.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from backend.app.compliance.state_machine import HandwashState, StateTransitionResult
from backend.app.compliance.temporal.models import TemporalMetrics

logger = structlog.get_logger(__name__)

# Field name in person state dict for each HandwashState's accumulated seconds.
_STATE_SECONDS_KEY: dict[HandwashState, str | None] = {
    HandwashState.NOT_NEAR_SINK:          None,   # not at sink — not tracked
    HandwashState.NEAR_SINK_NOT_WASHING:  "at_sink_seconds",
    HandwashState.WASHING:                "washing_seconds",
    HandwashState.WASHED:                 None,   # terminal
    HandwashState.NOT_WASHED:             None,   # terminal
}

_DEFAULT_MAX_GAP_SECONDS = 10.0


def initial_person_state(person_id: int, timestamp: datetime) -> dict:
    """Return the starting state dict for a newly observed person."""
    ts = _fmt(timestamp)
    return {
        "person_id":                  person_id,
        "current_state":              HandwashState.NOT_NEAR_SINK.name,
        "state_started_at":           ts,
        "last_seen_at":               ts,
        "observation_count":          0,
        "sequence_valid":             True,
        "at_sink_seconds":            0.0,
        "washing_seconds":            0.0,
        "last_frame_id":              -1,
        "consecutive_absence_frames": 0,
        # Frame-based fields populated from ObservationBuilder each frame.
        "positive_frames":            0,
        "no_detection_frames":        0,
        "hand_movement_score":        0.0,
        # Milestone tracking — last logged 5-second washing milestone (int).
        "washing_duration_logged":    0,
    }


class SpatioTemporalAnalyzer:
    """Updates per-person state and computes TemporalMetrics.

    Args:
        max_gap_seconds: Time gap threshold for continuity detection.
    """

    def __init__(self, max_gap_seconds: float = _DEFAULT_MAX_GAP_SECONDS) -> None:
        self._max_gap = max_gap_seconds
        logger.info(
            "spatio_temporal_analyzer_initialized",
            max_gap_seconds=max_gap_seconds,
        )

    def update_and_analyze(
        self,
        person_state: dict,
        transition: StateTransitionResult,
        observation_positive_frames: int = 0,
        observation_no_detection_frames: int = 0,
        observation_movement_score: float = 0.0,
    ) -> tuple[dict, TemporalMetrics]:
        """Apply *transition* to *person_state* and return updated state + metrics.

        Args:
            person_state:                    Current serialisable person state dict.
            transition:                      Result of HandwashStateMachine.transition().
            observation_positive_frames:     positive_frames from the Observation.
            observation_no_detection_frames: no_detection_frames from the Observation.
            observation_movement_score:      hand_movement_score from the Observation.

        Returns:
            ``(updated_person_state, TemporalMetrics)``
        """
        state = dict(person_state)  # work on a copy

        now = transition.timestamp
        prev_state = transition.previous_state
        new_state = transition.new_state

        # ── Continuity gap ───────────────────────────────────────────────────
        last_seen = _parse(state["last_seen_at"])
        last_gap = (now - last_seen).total_seconds()
        continuity_valid = last_gap <= self._max_gap
        if not continuity_valid:
            logger.info(
                "temporal_continuity_gap_detected",
                person_id=state["person_id"],
                last_gap_seconds=round(last_gap, 3),
                max_gap_seconds=self._max_gap,
            )

        # ── Finalise duration of the outgoing state ──────────────────────────
        if transition.transitioned:
            started_at = _parse(state["state_started_at"])
            duration = max(0.0, (now - started_at).total_seconds())
            key = _STATE_SECONDS_KEY.get(prev_state)
            if key is not None:
                state[key] = state.get(key, 0.0) + duration
                logger.debug(
                    "state_duration_finalized",
                    person_id=state["person_id"],
                    state=prev_state.name,
                    duration_seconds=round(duration, 3),
                )
            state["state_started_at"] = _fmt(now)
            state["current_state"] = new_state.name
            logger.info(
                "person_state_transitioned",
                person_id=state["person_id"],
                previous_state=prev_state.name,
                new_state=new_state.name,
                state_duration_seconds=round(duration, 3),
            )

        # ── Update frame-based counters from Observation ─────────────────────
        state["positive_frames"]       = observation_positive_frames
        state["no_detection_frames"]   = observation_no_detection_frames
        state["hand_movement_score"]   = observation_movement_score

        state["last_seen_at"]      = _fmt(now)
        state["observation_count"] = state.get("observation_count", 0) + 1

        metrics = self._compute_metrics(state, now, continuity_valid, last_gap)
        return state, metrics

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_metrics(
        state: dict,
        now: datetime,
        continuity_valid: bool,
        last_gap: float,
    ) -> TemporalMetrics:
        """Derive TemporalMetrics from the (already updated) state dict."""
        current = HandwashState[state["current_state"]]
        state_started_at = _parse(state["state_started_at"])
        ongoing = max(0.0, (now - state_started_at).total_seconds())

        def _total(field: str, state_enum: HandwashState) -> float:
            base = state.get(field, 0.0)
            return base + (ongoing if current == state_enum else 0.0)

        return TemporalMetrics(
            at_sink_duration=_total("at_sink_seconds", HandwashState.NEAR_SINK_NOT_WASHING),
            washing_duration=_total("washing_seconds", HandwashState.WASHING),
            sequence_valid=state.get("sequence_valid", True),
            continuity_valid=continuity_valid,
            observation_count=state.get("observation_count", 0),
            current_state=current.name,
            last_gap_seconds=last_gap,
            positive_frames=state.get("positive_frames", 0),
            no_detection_frames=state.get("no_detection_frames", 0),
            hand_movement_score=state.get("hand_movement_score", 0.0),
        )


def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
