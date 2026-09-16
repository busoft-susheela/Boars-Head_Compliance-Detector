"""ComplianceRuleEngine — thin orchestrator for the compliance pipeline.

Responsibility: orchestrate, persist, publish — NOT decide compliance.

Flow per DetectionEvent (multi-model)
--------------------------------------

    DetectionEvent  (contains person + sink + hand detections)
         |
         +── filter person detections (class_name == person_class)
         |
         v
    IoUTracker.update(person_detections)   → list[Track]
         |
         v
    ObservationBuilder.build(tracks, all_detections)
         |   (performs person→sink assignment, hand→person, movement tracking)
         v
    list[Observation]  (one per tracked person)
         |
         v
    For each Observation:
         |
         v
    StateStore.get(zone_key)              → zone_state dict
         |
         v
    HandwashStateMachine.transition()     → StateTransitionResult
         |
         v
    SpatioTemporalAnalyzer.update_and_analyze()  → (person_state, TemporalMetrics)
         |
         v
    HandwashRuleEvaluator.evaluate()      → RuleEvaluationResult
         |
         v
    StateStore.set(zone_key, updated_zone_state)
         |
         +--> outcome == "violation"?
                 |
                 v
             MessageQueue.publish(TOPIC_COMPLIANCE_ALERT, ComplianceEvent)
             MessageQueue.publish(TOPIC_EVIDENCE_CAPTURE, EvidenceCaptureEvent)

    ObservationBuilder.evict_stale(now)
         (remove tracking state for persons absent > 3 s)

State structure in StateStore
-------------------------------
Key:   make_state_key(camera_id, zone_id)
Value: {
    "persons": {
        "<person_id>": { ... per-person state dict ... }
    }
}
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import structlog

from backend.app.compliance.events import (
    TOPIC_COMPLIANCE_ALERT,
    TOPIC_EVIDENCE_CAPTURE,
    ComplianceEvent,
    EvidenceCaptureEvent,
)
from backend.app.compliance.metrics import ComplianceMetrics
from backend.app.compliance.observation import Observation, ObservationBuilder
from backend.app.compliance.rules.base import RuleEvaluator
from backend.app.compliance.state_machine import HandwashState, HandwashStateMachine
from backend.app.compliance.temporal.analyzer import (
    SpatioTemporalAnalyzer,
    initial_person_state,
)
from backend.app.compliance.tracker import Tracker
from backend.app.compliance.action_log import write_action_log
from backend.app.compliance.video_time import video_time_str
from backend.app.inference.models.detection import Detection, DetectionEvent
from backend.app.infrastructure.message_queue.base import MessageQueue
from backend.app.infrastructure.state_store.base import StateStore, make_state_key

logger = structlog.get_logger(__name__)

# Frame-count fallback for synthetic zone-exit when source_fps is unavailable.
_MAX_LOST_FRAMES = 5

# Seconds without a real detection before a synthetic observation treats the
# person as having left the zone.  Must match ObservationBuilder's
# reset_after_no_detection_seconds (default 1.0 s) so that the two code paths
# use the same effective window and don't disagree about zone membership.
_ZONE_EXIT_GRACE_SECONDS = 1.0

# Stale person state is evicted from the ObservationBuilder after this many
# seconds without any detection (mirrors reference script's source_fps * 3).
_STALE_EVICTION_SECONDS = 3.0


class ComplianceRuleEngine:
    """Orchestrates the per-frame compliance evaluation pipeline.

    Stateless with respect to compliance rules — all mutable state lives
    in the StateStore or the RuleEvaluator's in-memory evidence buffers.

    Args:
        state_store:         Persistence backend for compliance state.
        tracker:             Object identity tracker (IoUTracker or ByteTrack).
        observation_builder: Converts multi-model detections to domain Observations.
        state_machine:       Deterministic state transition computer.
        temporal_analyzer:   Updates state durations and computes TemporalMetrics.
        rule_evaluator:      Applies compliance rules, manages evidence buffers.
        message_queue:       For publishing ComplianceEvent / EvidenceCaptureEvent.
        person_class:        Detection class_name used to identify person detections.
        metrics:             Optional metrics recorder; uses a no-op if None.
    """

    def __init__(
        self,
        state_store: StateStore,
        tracker: Tracker,
        observation_builder: ObservationBuilder,
        state_machine: HandwashStateMachine,
        temporal_analyzer: SpatioTemporalAnalyzer,
        rule_evaluator: RuleEvaluator,
        message_queue: MessageQueue,
        person_class: str = "person",
        metrics: ComplianceMetrics | None = None,
    ) -> None:
        self._store = state_store
        self._tracker = tracker
        self._obs_builder = observation_builder
        self._state_machine = state_machine
        self._temporal = temporal_analyzer
        self._evaluator = rule_evaluator
        self._mq = message_queue
        self._person_class = person_class
        self._metrics = metrics or ComplianceMetrics()
        # Tracks every (camera_id, zone_id) pair seen during processing so that
        # flush() knows which zones to finalise on stream end.
        self._known_zones: dict[str, tuple[str, str, float]] = {}
        # zone_key → (camera_id, zone_id, last_source_fps)
        self._last_event_timestamp: datetime | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, event: DetectionEvent) -> None:
        """Process one DetectionEvent through the full compliance pipeline."""
        t0 = time.monotonic()
        zone_key = make_state_key(event.camera_id, event.zone_id)
        self._known_zones[zone_key] = (event.camera_id, event.zone_id, event.source_fps)
        self._last_event_timestamp = event.captured_at
        try:
            self._process(event)
            self._metrics.record_evaluation(time.monotonic() - t0)
        except Exception:
            self._metrics.record_evaluation_failure()
            logger.exception(
                "compliance_engine_error",
                camera_id=event.camera_id,
                zone_id=event.zone_id,
                frame_id=event.frame_id,
            )

    def flush(self) -> None:
        """Force zone-exit evaluation for all persons still in non-resting states.

        Call once when the stream ends so that every in-progress visit is
        finalised (WASHED or NOT_WASHED) rather than silently discarded.
        """
        for zone_key, (camera_id, zone_id, source_fps) in list(self._known_zones.items()):
            zone_state = self._store.get(zone_key)
            if not zone_state:
                continue
            persons = zone_state.get("persons", {})
            if not persons:
                continue

            # Compute a frame_id far enough beyond the last seen frame that
            # frames_lost > _MAX_LOST_FRAMES for every person — triggering
            # inside_zone=False on the first (and only) synthetic observation.
            max_frame = max(
                (int(p.get("last_frame_id", 0)) for p in persons.values()),
                default=0,
            )
            flush_frame_id = max(max_frame + _MAX_LOST_FRAMES + 1, 1)
            flush_ts = self._last_event_timestamp or datetime.now(tz=timezone.utc)

            flush_event = DetectionEvent(
                camera_id=camera_id,
                zone_id=zone_id,
                frame_id=flush_frame_id,
                captured_at=flush_ts,
                processed_at=flush_ts,
                detections=(),
                thumbnail=None,
                correlation_id="stream_flush",
                source_fps=source_fps,
            )
            logger.info(
                "compliance_engine_flush",
                camera_id=camera_id,
                zone_id=zone_id,
                flush_frame_id=flush_frame_id,
                pending_persons=len(persons),
            )
            try:
                self._process(flush_event)
            except Exception:
                logger.exception(
                    "compliance_engine_flush_error",
                    camera_id=camera_id,
                    zone_id=zone_id,
                )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process(self, event: DetectionEvent) -> None:
        camera_id = event.camera_id
        zone_id = event.zone_id
        timestamp = event.captured_at
        frame_id = event.frame_id
        thumbnail = event.thumbnail
        source_fps = event.source_fps
        all_detections: list[Detection] = list(event.detections)

        # ── Filter person detections for the tracker ─────────────────────────
        # Only person detections carry ByteTrack IDs; sink and hand detections
        # do not need tracking — they are associated spatially each frame.
        person_detections = [
            d for d in all_detections
            if d.class_name == self._person_class
        ]

        # ── Track: assign stable person IDs ─────────────────────────────────
        tracks = self._tracker.update(person_detections, timestamp)

        # ── Build domain observations ────────────────────────────────────────
        # ObservationBuilder receives ALL detections so it can extract sink
        # and hand detections for spatial association internally.
        observations: list[Observation] = self._obs_builder.build(
            camera_id=camera_id,
            zone_id=zone_id,
            frame_id=frame_id,
            timestamp=timestamp,
            tracks=tracks,
            all_detections=all_detections,
        )

        # ── Evict stale per-person tracking state ────────────────────────────
        # Mirrors "REMOVE OLD PERSON STATES" in the reference script.
        self._obs_builder.evict_stale(
            now=timestamp,
            stale_threshold_seconds=_STALE_EVICTION_SECONDS,
        )

        # ── Load zone state ──────────────────────────────────────────────────
        zone_key = make_state_key(camera_id, zone_id)
        zone_state = self._store.get(zone_key) or {"persons": {}}
        self._metrics.record_state_store_get()

        # ── Supplement: absence observations for previously-tracked persons ──
        # Persons whose ByteTrack ID was not matched this frame may still be
        # in the zone — synthesise a NOT_NEAR_SINK / lost observation so the
        # state machine can transition them toward NOT_NEAR_SINK gracefully.
        current_person_ids = {obs.person_id for obs in observations}
        for str_pid, p_state in zone_state["persons"].items():
            pid = int(str_pid)
            if pid in current_person_ids:
                continue
            current_hs = HandwashState[p_state["current_state"]]
            if current_hs in (
                HandwashState.NOT_NEAR_SINK,
                HandwashState.WASHED,
                HandwashState.NOT_WASHED,
            ):
                # NOT_NEAR_SINK persons with a pending session exit still need
                # processing so the session cooldown can tick and the violation
                # can eventually be confirmed.
                if not (
                    current_hs == HandwashState.NOT_NEAR_SINK
                    and p_state.get("pending_exit_at")
                ):
                    continue  # true resting state — no synthetic obs needed

            last_frame = p_state.get("last_frame_id", frame_id - 1)
            frames_lost = frame_id - last_frame

            if frames_lost < 0:
                # Stale state from a previous session — skip.
                logger.info(
                    "stale_person_state_skipped",
                    camera_id=camera_id,
                    zone_id=zone_id,
                    frame_id=frame_id,
                    person_id=pid,
                    last_frame_id=last_frame,
                )
                continue

            # Use time-based threshold (matching ObservationBuilder grace period)
            # so both code paths agree on when a person has left the zone.
            # Fall back to frame count when source_fps is unavailable.
            if source_fps > 0:
                inside_zone = (frames_lost / source_fps) <= _ZONE_EXIT_GRACE_SECONDS
            else:
                inside_zone = frames_lost <= _MAX_LOST_FRAMES
            logger.info(
                "absence_observation_synthesized",
                action=(
                    f"Person {pid} not visible for {frames_lost} frame(s) — "
                    f"assumed {'still at sink' if inside_zone else 'left the zone'}"
                ),
                camera_id=camera_id,
                zone_id=zone_id,
                frame_id=frame_id,
                person_id=pid,
                frames_lost=frames_lost,
                inside_zone=inside_zone,
            )
            observations.append(Observation(
                camera_id=camera_id,
                zone_id=zone_id,
                person_id=pid,
                timestamp=timestamp,
                frame_id=frame_id,
                inside_sink_zone=inside_zone,
                hands_interacting=False,
                is_synthetic=True,
            ))

        if not observations:
            logger.info(
                "compliance_no_observations",
                action="No persons detected in frame — nothing to evaluate",
                camera_id=camera_id,
                zone_id=zone_id,
                frame_id=frame_id,
            )
            return

        # ── Per-person evaluation loop ───────────────────────────────────────
        for obs in observations:
            person_id = obs.person_id
            person_state = zone_state["persons"].get(str(person_id))
            if person_state is None:
                person_state = initial_person_state(person_id, timestamp)

            # Update last_frame_id for real (non-synthetic) observations.
            if person_id in current_person_ids:
                person_state["last_frame_id"] = frame_id

            # ── State machine ────────────────────────────────────────────────
            current_hs = HandwashState[person_state["current_state"]]
            transition = self._state_machine.transition(current_hs, obs)

            # ── Reset stale violation state on new sink visit ─────────────────
            # violation_confirmed=True persists in Redis across restarts (TTL
            # 3600 s).  It must be cleared whenever a person begins a new visit
            # so that _handle_zone_exit / _handle_near_sink_not_washing are not
            # blocked by a flag from a previous session.
            #
            # "new_visit_after_terminal" fires only when Redis stored NOT_WASHED.
            # "entered_sink_area" fires regardless — it is the definitive signal
            # that a new visit has begun (NOT_NEAR_SINK → NEAR_SINK_NOT_WASHING).
            if transition.reason in ("new_visit_after_terminal", "entered_sink_area"):
                # A session continuation is valid only when (a) there is a
                # pending_exit_at timestamp AND (b) the evaluator has an active
                # in-memory buffer for this person.  Condition (b) rules out
                # stale Redis state from a previous process restart: that state
                # has pending_exit_at set but no corresponding in-memory buffer,
                # so we reset cleanly instead of carrying over stale metrics.
                is_session_continuation = (
                    bool(person_state.get("pending_exit_at"))
                    and self._evaluator.has_active_session(camera_id, zone_id, person_id)
                )
                if not is_session_continuation:
                    last_frame_id = person_state.get("last_frame_id", -1)
                    person_state = initial_person_state(person_id, timestamp)
                    person_state["last_frame_id"] = last_frame_id

            vt = video_time_str(frame_id, source_fps)
            if transition.transitioned:
                # Map state-machine reasons to the reference script's action names.
                # "left_sink_area" is intentionally absent: the rule evaluator logs
                # it AFTER the WASHED/NOT WASHED verdict to preserve correct ordering.
                _ACTION_NAMES = {
                    "entered_sink_area":       "ENTERED SINK AREA",
                    "washing_confirmed":        "WASHING STARTED",
                    "washing_stopped":          "NEAR SINK - NOT WASHING",
                    "new_visit_after_terminal": "ENTERED SINK AREA",
                }
                action_name = _ACTION_NAMES.get(transition.reason, transition.reason.upper())
                logger.info(
                    "action_log",
                    action=action_name,
                    person_id=person_id,
                    video_time=vt,
                    previous_state=transition.previous_state.name,
                    new_state=transition.new_state.name,
                    camera_id=camera_id,
                    zone_id=zone_id,
                    frame_id=frame_id,
                )
                # Skip action_log for left_sink_area — rule evaluator owns that line.
                if transition.reason != "left_sink_area":
                    write_action_log(
                        person_id=person_id,
                        action=action_name,
                        frame_number=frame_id,
                        fps=source_fps,
                        state=transition.new_state.name,
                    )
            else:
                logger.debug(
                    "state_no_change",
                    person_id=person_id,
                    state=transition.new_state.name,
                    reason=transition.reason,
                    video_time=vt,
                    frame_id=frame_id,
                )

            # ── Temporal analysis ────────────────────────────────────────────
            updated_person_state, metrics = self._temporal.update_and_analyze(
                person_state,
                transition,
                observation_positive_frames=obs.positive_frames,
                observation_no_detection_frames=obs.no_detection_frames,
                observation_movement_score=obs.hand_movement_score,
            )

            # ── Rule evaluation ──────────────────────────────────────────────
            evidence_thumbnail = None if (obs.is_synthetic and not obs.inside_sink_zone) else thumbnail
            result = self._evaluator.evaluate(
                person_state=updated_person_state,
                metrics=metrics,
                camera_id=camera_id,
                zone_id=zone_id,
                timestamp=timestamp,
                thumbnail=evidence_thumbnail,
                frame_id=frame_id,
                source_fps=source_fps,
                detections=event.detections,
                frame_shape=event.frame_shape,
            )

            zone_state["persons"][str(person_id)] = result.person_state

            # ── Publish violation ────────────────────────────────────────────
            if result.outcome == "violation":
                self._metrics.record_violation()
                group_id = result.person_state.get("group_id", "unknown")
                self._publish_violation(
                    camera_id=camera_id,
                    zone_id=zone_id,
                    person_id=person_id,
                    timestamp=timestamp,
                    group_id=group_id,
                    evidence=result.evidence,
                )

        # ── Persist updated zone state ───────────────────────────────────────
        self._store.set(zone_key, zone_state)
        self._metrics.record_state_store_set()

    def _publish_violation(
        self,
        camera_id: str,
        zone_id: str,
        person_id: int,
        timestamp,
        group_id: str,
        evidence,
    ) -> None:
        """Publish EvidenceCaptureEvent then ComplianceEvent.

        Evidence is published first so that the PersistenceWorker can drain it
        into its pending-evidence map before the compliance alert triggers
        processing — avoiding a race where the worker looks for evidence that
        hasn't been enqueued yet.
        """
        # ── Publish evidence first (so it arrives before the alert) ──────────
        if evidence is not None:
            evidence_event = EvidenceCaptureEvent(
                group_id=group_id,
                camera_id=camera_id,
                zone_id=zone_id,
                payload=evidence,
                timestamp=timestamp,
            )
            try:
                self._mq.publish(TOPIC_EVIDENCE_CAPTURE, evidence_event)
                logger.info(
                    "evidence_event_published",
                    action=f"Evidence package saved — {len(evidence.items)} thumbnail(s) for group {group_id}",
                    camera_id=camera_id,
                    zone_id=zone_id,
                    group_id=group_id,
                    evidence_count=len(evidence.items),
                )
            except Exception:
                self._metrics.record_evidence_publish_failure()
                logger.exception(
                    "evidence_event_publish_failed",
                    camera_id=camera_id,
                    zone_id=zone_id,
                    group_id=group_id,
                )

        # ── Publish compliance alert (after evidence is enqueued) ─────────────
        compliance_event = ComplianceEvent(
            camera_id=camera_id,
            zone_id=zone_id,
            person_id=person_id,
            timestamp=timestamp,
            outcome="violation",
            rule_name="handwash_compliance",
            group_id=group_id,
        )
        try:
            self._mq.publish(TOPIC_COMPLIANCE_ALERT, compliance_event)
            logger.info(
                "compliance_event_published",
                action=f"VIOLATION ALERT published — person {person_id} did not wash hands",
                camera_id=camera_id,
                zone_id=zone_id,
                person_id=person_id,
                group_id=group_id,
                outcome="violation",
            )
        except Exception:
            logger.exception(
                "compliance_event_publish_failed",
                camera_id=camera_id,
                zone_id=zone_id,
                group_id=group_id,
            )
