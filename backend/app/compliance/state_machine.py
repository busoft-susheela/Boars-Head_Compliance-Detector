"""HandwashStateMachine — deterministic per-person state transitions.

Responsibility: "What state is this person in?" — state transitions only.

The machine is deterministic: given a current state and one Observation
it always returns the same next state.  It does NOT:
  - calculate durations
  - evaluate compliance rules
  - access the StateStore
  - publish events

State model
-----------

    NOT_NEAR_SINK ──► NEAR_SINK_NOT_WASHING ──► WASHING
                              ▲                     │
                              └─────────────────────┘  (washing stops)

    NEAR_SINK_NOT_WASHING ──► NOT_NEAR_SINK   (person exits sink area)
    WASHING               ──► NOT_NEAR_SINK   (person exits sink area)

    NOT_NEAR_SINK is also the start state for a newly detected person.

    WASHED / NOT_WASHED are terminal states set by the RuleEvaluator on
    zone exit — the state machine transitions to NOT_NEAR_SINK on exit and
    the evaluator upgrades the state based on washing duration.

Mapping from original reference-script action_state
----------------------------------------------------
    NOT_NEAR_SINK       ↔  "NOT_NEAR_SINK"
    NEAR_SINK_NOT_WASHING ↔ "NEAR_SINK_NOT_WASHING"
    WASHING             ↔  "WASHING"
    WASHED              ↔  "WASHED"        (set by RuleEvaluator)
    NOT_WASHED          ↔  "NOT_WASHED"    (set by RuleEvaluator / violation)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

import structlog

from backend.app.compliance.observation import Observation

logger = structlog.get_logger(__name__)


class HandwashState(Enum):
    NOT_NEAR_SINK = auto()          # person not near any sink (or newly detected)
    NEAR_SINK_NOT_WASHING = auto()  # person's hand is at the sink; washing not yet confirmed
    WASHING = auto()                # confirmed active washing (positive_frames threshold crossed)
    WASHED = auto()                 # terminal: person left after sufficient washing duration
    NOT_WASHED = auto()             # terminal: person left without sufficient washing (violation)


@dataclass(frozen=True)
class StateTransitionResult:
    """Outcome of one state machine step.

    Attributes:
        previous_state:  State before this observation.
        new_state:       State after applying the observation.
        timestamp:       Observation timestamp (from the frame).
        person_id:       Track ID of the observed person.
        transitioned:    True if the state actually changed.
        sequence_valid:  Always True in the multi-model design (kept for
                         interface compatibility with the temporal analyzer).
        reason:          Human-readable description of what drove the transition.
    """

    previous_state: HandwashState
    new_state: HandwashState
    timestamp: datetime
    person_id: int
    transitioned: bool
    sequence_valid: bool
    reason: str


class HandwashStateMachine:
    """Deterministic state machine for one camera/zone.

    Stateless — the caller supplies the current state and receives the next
    state in the result.  Persistent state lives in the StateStore, not here.
    """

    def transition(
        self,
        current_state: HandwashState,
        observation: Observation,
    ) -> StateTransitionResult:
        """Compute the next state given current state and one observation.

        Driving signals from Observation:
            inside_sink_zone  — hand is near the person's assigned sink
                                (raw spatial proximity, within grace period)
            hands_interacting — washing confirmed (positive_frames >= threshold)

        Args:
            current_state: State before this frame.
            observation:   Domain observation derived from the current frame.

        Returns:
            :class:`StateTransitionResult` describing the transition.
        """
        next_state, reason = self._next(current_state, observation)
        transitioned = next_state != current_state

        if transitioned:
            logger.info(
                "state_machine_transition",
                person_id=observation.person_id,
                camera_id=observation.camera_id,
                zone_id=observation.zone_id,
                frame_id=observation.frame_id,
                previous_state=current_state.name,
                new_state=next_state.name,
                reason=reason,
            )
        else:
            logger.debug(
                "state_machine_no_transition",
                person_id=observation.person_id,
                frame_id=observation.frame_id,
                current_state=current_state.name,
                reason=reason,
            )

        return StateTransitionResult(
            previous_state=current_state,
            new_state=next_state,
            timestamp=observation.timestamp,
            person_id=observation.person_id,
            transitioned=transitioned,
            sequence_valid=True,   # not applicable in multi-model design
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _next(
        state: HandwashState,
        obs: Observation,
    ) -> tuple[HandwashState, str]:
        """Core transition table."""

        # ── Terminal states reset only once the person leaves the sink ──────
        # Stay in the terminal state while the person is still at the sink so
        # that the engine does not open a new violation cycle for the same
        # physical visit.  The reset to NOT_NEAR_SINK fires only when they
        # actually leave (inside_sink_zone=False), after which a genuine
        # re-entry will trigger entered_sink_area for the next visit.
        if state in (HandwashState.WASHED, HandwashState.NOT_WASHED):
            if not obs.inside_sink_zone:
                return HandwashState.NOT_NEAR_SINK, "new_visit_after_terminal"
            return state, "terminal_waiting_exit"

        # ── Person exits sink area → reset to NOT_NEAR_SINK ──────────────────
        # inside_sink_zone=False means the hand has been away from the sink
        # long enough to have exceeded the grace period.
        if not obs.inside_sink_zone:
            if state == HandwashState.NOT_NEAR_SINK:
                return HandwashState.NOT_NEAR_SINK, "not_near_sink"
            return HandwashState.NOT_NEAR_SINK, "left_sink_area"

        # ── Person's hand is at the sink ─────────────────────────────────────
        if state == HandwashState.NOT_NEAR_SINK:
            return HandwashState.NEAR_SINK_NOT_WASHING, "entered_sink_area"

        if state == HandwashState.NEAR_SINK_NOT_WASHING:
            if obs.hands_interacting:
                return HandwashState.WASHING, "washing_confirmed"
            return HandwashState.NEAR_SINK_NOT_WASHING, "near_sink_not_washing"

        if state == HandwashState.WASHING:
            if not obs.hands_interacting:
                # positive_frames reset — washing evidence lost.
                return HandwashState.NEAR_SINK_NOT_WASHING, "washing_stopped"
            return HandwashState.WASHING, "still_washing"

        return state, "no_transition"
