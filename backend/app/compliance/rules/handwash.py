"""HandwashRuleEvaluator — applies the handwash compliance rule.

Responsibility: "Is it compliant?" — rule decision only.

Violation trigger (multi-model design)
---------------------------------------
The violation is triggered when a person **exits the sink area** without
having accumulated the minimum washing duration.  This mirrors the reference
script's exit logic:

    if not near_sink and entered_sink_frame is not None and no_detection_frames >= reset_frames:
        if washing_duration < MIN_WASHING_DURATION:
            → NOT_WASHED  (violation)
        else:
            → WASHED      (compliant)

State lifecycle
---------------

    NOT_NEAR_SINK  (no group active)
         |  person's hand reaches the sink
         v
    NEAR_SINK_NOT_WASHING  (evidence group opened)
         |  positive_frames crosses threshold
         v
    WASHING                (still in group — washing timer running)
         |
    person exits (state transitions to NOT_NEAR_SINK)
         |
         +── washing_seconds >= MIN_WASHING_DURATION ?
         |        YES → state = WASHED     (group discarded, no alert)
         |        NO  → state = NOT_WASHED (VIOLATION — group frozen & published)
         v

If the person starts washing mid-visit and then exits:
  The same exit check applies using accumulated washing_seconds.

Idempotency
-----------
Once a violation has been confirmed (violation_confirmed=True), subsequent
frames for the same episode return outcome=None.  One alert per group_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from backend.app.compliance.evidence.buffer import EvidenceBuffer
from backend.app.compliance.evidence.models import EvidenceItem, EvidencePayload
from backend.app.compliance.rules.base import RuleEvaluationResult, RuleEvaluator
from backend.app.compliance.rules.config import HandwashRuleConfig
from backend.app.compliance.state_machine import HandwashState
from backend.app.compliance.temporal.models import TemporalMetrics
from backend.app.compliance.action_log import write_action_log
from backend.app.compliance.video_time import video_time_str

logger = structlog.get_logger(__name__)

# Debounce: require this many consecutive frames at the sink before opening
# an evidence group.  Prevents a brief tracker re-ID gap from producing a
# false-positive absence event.
_MIN_SINK_ENTRY_FRAMES = 2

# States where the person is actively washing.
_WASHING_STATES = frozenset({HandwashState.WASHING})

# States where the person is at the sink (washing or not).
_AT_SINK_STATES = frozenset({
    HandwashState.NEAR_SINK_NOT_WASHING,
    HandwashState.WASHING,
})


class HandwashRuleEvaluator(RuleEvaluator):
    """Evaluates the handwash compliance rule for one person+zone combination.

    Maintains in-memory evidence buffers keyed by (camera_id, zone_id, person_id).
    Buffers are NOT persisted — they are temporary until discarded or frozen.

    Args:
        config: Validated rule parameters.
    """

    def __init__(self, config: HandwashRuleConfig) -> None:
        self._config = config
        self._buffers: dict[tuple[str, str, int], EvidenceBuffer] = {}

    def evaluate(
        self,
        person_state: dict,
        metrics: TemporalMetrics,
        camera_id: str,
        zone_id: str,
        timestamp: datetime,
        thumbnail: bytes | None,
        frame_id: int,
        source_fps: float = 0.0,
    ) -> RuleEvaluationResult:
        """Apply the handwash rule for one frame observation.

        Returns a RuleEvaluationResult with the updated person state dict,
        optional outcome ("violation"), and optional frozen evidence payload.
        """
        state = dict(person_state)
        current_state = HandwashState[state["current_state"]]
        person_id: int = state["person_id"]
        buf_key = (camera_id, zone_id, person_id)

        # ── Person exited sink area → evaluate washing outcome ────────────────
        if current_state == HandwashState.NOT_NEAR_SINK:
            return self._handle_zone_exit(
                state, buf_key, camera_id, zone_id, person_id,
                timestamp, frame_id, metrics, source_fps,
            )

        # ── Person is actively washing → discard any unconfirmed group ───────
        if current_state == HandwashState.WASHING:
            # Log every 5-second washing milestone (matches reference script behaviour).
            milestone = int(metrics.washing_duration // 5) * 5
            last_milestone = state.get("washing_duration_logged", 0)
            if milestone >= 5 and milestone > last_milestone:
                state["washing_duration_logged"] = milestone
                write_action_log(
                    person_id=person_id,
                    action=f"WASHING - {milestone} SECONDS",
                    frame_number=frame_id,
                    fps=source_fps,
                    state=HandwashState.WASHING.name,
                    extra=f"Current duration: {metrics.washing_duration:.2f}s",
                )
            self._handle_washing_active(state, buf_key)
            return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)

        # ── Person at sink but not washing → build/continue absence group ────
        if current_state == HandwashState.NEAR_SINK_NOT_WASHING:
            return self._handle_near_sink_not_washing(
                state, buf_key, camera_id, zone_id, person_id,
                timestamp, thumbnail, frame_id, source_fps,
            )

        # ── Terminal states (WASHED / NOT_WASHED) — idempotent ───────────────
        return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_zone_exit(
        self,
        state: dict,
        buf_key: tuple,
        camera_id: str,
        zone_id: str,
        person_id: int,
        timestamp: datetime,
        frame_id: int,
        metrics: TemporalMetrics,
        source_fps: float = 0.0,
    ) -> RuleEvaluationResult:
        """Person exited the sink zone."""
        if state.get("violation_confirmed", False):
            # Already confirmed in a previous frame — stay idempotent.
            state["consecutive_absence_frames"] = 0
            return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)

        group_id = state.get("group_id")

        if group_id is None:
            # No active evidence group.
            # This happens when the buffer was discarded while the person was actively
            # washing (WASHING state) — they exited without transitioning back to
            # NEAR_SINK_NOT_WASHING first.  We must still evaluate washing duration
            # so the visit doesn't silently disappear with no verdict.
            if metrics.washing_duration == 0.0 and metrics.at_sink_duration == 0.0:
                # Person never approached the sink — nothing to evaluate.
                _reset_visit(state)
                return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)
            # Fall through to evaluate accumulated washing_seconds (no evidence buffer).

        washing_seconds = metrics.washing_duration
        min_duration = self._config.minimum_washing_duration_seconds

        vt = video_time_str(frame_id, source_fps)

        total_visit_seconds = metrics.at_sink_duration + washing_seconds

        if washing_seconds >= min_duration:
            # ── Compliant exit ───────────────────────────────────────────────
            state["current_state"] = HandwashState.WASHED.name
            self._discard_buffer(buf_key, state, reason="compliant_exit")
            logger.info(
                "action_log",
                action="WASHED",
                person_id=person_id,
                video_time=vt,
                detail=f"Duration: {washing_seconds:.2f}s (>= {min_duration}s required)",
                camera_id=camera_id,
                zone_id=zone_id,
                frame_id=frame_id,
                washing_seconds=round(washing_seconds, 2),
            )
            write_action_log(
                person_id=person_id,
                action="WASHED",
                frame_number=frame_id,
                fps=source_fps,
                state=HandwashState.WASHED.name,
                extra=f"Duration: {washing_seconds:.2f}s (>= {min_duration}s required)",
            )
            write_action_log(
                person_id=person_id,
                action="LEFT SINK AREA",
                frame_number=frame_id,
                fps=source_fps,
                state=HandwashState.WASHED.name,
            )
            write_action_log(
                person_id=person_id,
                action="PROCESS COMPLETE",
                frame_number=frame_id,
                fps=source_fps,
                state=HandwashState.WASHED.name,
                result="COMPLIANT",
                extra=(
                    f"Total: {total_visit_seconds:.2f}s "
                    f"(Washing: {washing_seconds:.2f}s, "
                    f"At Sink: {metrics.at_sink_duration:.2f}s)"
                ),
            )
            _reset_visit(state)
            return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)

        # ── Non-compliant exit → violation ───────────────────────────────────
        state["current_state"] = HandwashState.NOT_WASHED.name
        buf = self._buffers.get(buf_key)
        result = self._confirm_violation(state, buf_key, buf, timestamp, person_id, frame_id, source_fps)
        logger.info(
            "action_log",
            action="NOT WASHED",
            person_id=person_id,
            video_time=vt,
            detail=f"Duration: {washing_seconds:.2f}s (< {min_duration}s required)",
            camera_id=camera_id,
            zone_id=zone_id,
            frame_id=frame_id,
            washing_seconds=round(washing_seconds, 2),
            required_seconds=min_duration,
        )
        write_action_log(
            person_id=person_id,
            action="NOT WASHED",
            frame_number=frame_id,
            fps=source_fps,
            state=HandwashState.NOT_WASHED.name,
            extra=f"Duration: {washing_seconds:.2f}s (< {min_duration}s required)",
        )
        write_action_log(
            person_id=person_id,
            action="LEFT SINK AREA",
            frame_number=frame_id,
            fps=source_fps,
            state=HandwashState.NOT_WASHED.name,
        )
        write_action_log(
            person_id=person_id,
            action="PROCESS COMPLETE",
            frame_number=frame_id,
            fps=source_fps,
            state=HandwashState.NOT_WASHED.name,
            result="VIOLATION",
            extra=(
                f"Total: {total_visit_seconds:.2f}s "
                f"(Washing: {washing_seconds:.2f}s / {min_duration:.1f}s required, "
                f"At Sink: {metrics.at_sink_duration:.2f}s)"
            ),
        )
        _reset_visit(state)
        return result

    def _handle_washing_active(self, state: dict, buf_key: tuple) -> None:
        """Person is confirmed washing — discard any unconfirmed absence group."""
        if state.get("group_id") and not state.get("violation_confirmed", False):
            self._discard_buffer(buf_key, state, reason="washing_resumed")
        state["consecutive_absence_frames"] = 0

    def _handle_near_sink_not_washing(
        self,
        state: dict,
        buf_key: tuple,
        camera_id: str,
        zone_id: str,
        person_id: int,
        timestamp: datetime,
        thumbnail: bytes | None,
        frame_id: int,
        source_fps: float = 0.0,
    ) -> RuleEvaluationResult:
        """Person is at the sink but not confirmed washing — build evidence group."""
        if state.get("violation_confirmed", False):
            return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)

        # Debounce: wait for a few consecutive sink-entry frames before opening a group.
        if not state.get("group_id"):
            count = state.get("consecutive_absence_frames", 0) + 1
            state["consecutive_absence_frames"] = count
            if count < _MIN_SINK_ENTRY_FRAMES:
                return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)

            group_id = str(uuid.uuid4())
            state["group_id"] = group_id
            state["absence_started_at"] = _fmt(timestamp)
            self._buffers[buf_key] = EvidenceBuffer(
                max_items=self._config.evidence_buffer_max,
                group_id=group_id,
                camera_id=camera_id,
                zone_id=zone_id,
            )
            logger.info(
                "action_log",
                action="ENTERED SINK AREA",
                person_id=person_id,
                video_time=video_time_str(frame_id, source_fps),
                camera_id=camera_id,
                zone_id=zone_id,
                frame_id=frame_id,
                group_id=group_id,
            )

        # Buffer this frame's thumbnail.
        buf = self._buffers.get(buf_key)
        if buf is not None and not buf.frozen:
            buf.add(EvidenceItem(
                frame_id=frame_id,
                timestamp=timestamp,
                thumbnail=thumbnail,
                camera_id=camera_id,
                zone_id=zone_id,
                person_id=person_id,
            ))

        return RuleEvaluationResult(person_state=state, outcome=None, evidence=None)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _confirm_violation(
        self,
        state: dict,
        buf_key: tuple,
        buf: EvidenceBuffer | None,
        timestamp: datetime,
        person_id: int,
        frame_id: int = 0,
        source_fps: float = 0.0,
    ) -> RuleEvaluationResult:
        """Freeze the evidence buffer and return a violation result."""
        state["violation_confirmed"] = True
        frozen: EvidencePayload | None = None
        if buf is not None and not buf.frozen:
            frozen = buf.freeze()

        logger.info(
            "violation_confirmed",
            action=f"VIOLATION: Person {person_id} left the sink without washing enough",
            camera_id=buf_key[0],
            zone_id=buf_key[1],
            person_id=person_id,
            group_id=state.get("group_id"),
            evidence_count=len(frozen.items) if frozen else 0,
        )
        write_action_log(
            person_id=person_id,
            action="VIOLATION",
            frame_number=frame_id,
            fps=source_fps,
            state=HandwashState.NOT_WASHED.name,
            result="VIOLATION",
            extra=f"Evidence frames: {len(frozen.items) if frozen else 0} | Group: {state.get('group_id')}",
        )
        return RuleEvaluationResult(
            person_state=state,
            outcome="violation",
            evidence=frozen,
        )

    def _discard_buffer(self, buf_key: tuple, state: dict, reason: str) -> None:
        """Discard the active evidence buffer and reset group tracking."""
        buf = self._buffers.pop(buf_key, None)
        if buf is not None:
            buf.discard()
            _reason_text = {
                "washing_resumed":  "person confirmed washing — no violation",
                "compliant_exit":   "person washed for sufficient duration — compliant",
            }.get(reason, reason)
            logger.info(
                "evidence_group_discarded",
                action=f"Person {buf_key[2]} absence group cleared: {_reason_text}",
                camera_id=buf_key[0],
                zone_id=buf_key[1],
                person_id=buf_key[2],
                group_id=state.get("group_id"),
                reason=reason,
            )
        state["group_id"] = None
        state["absence_started_at"] = None
        state["violation_confirmed"] = False
        state["consecutive_absence_frames"] = 0


def _reset_visit(state: dict) -> None:
    """Clear per-visit counters after a zone exit."""
    state["consecutive_absence_frames"] = 0
    state["washing_duration_logged"] = 0
    state["washing_seconds"] = 0.0
    state["at_sink_seconds"] = 0.0


def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
