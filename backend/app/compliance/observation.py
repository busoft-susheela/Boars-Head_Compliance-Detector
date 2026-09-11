"""Observation — the domain view of "what is happening" in a frame.

Responsibility: Convert multi-model detection outputs (person, sink, hand)
into domain Observations that the state machine and temporal analyzer understand.

The ObservationBuilder answers "What is happening?" — not "Is it compliant?"

Multi-model processing pipeline (per frame)
------------------------------------------

  All detections (from DetectionEvent)
       |
       +── person detections (class_name == person_class, have track_id)
       |       |
       |       v
       |   IoUTracker passthrough (ByteTrack IDs already set)
       |
       +── sink detections (class_name == sink_class)
       |
       +── hand detections (class_name == hand_class / trigger_class)

  For each tracked person:
    1. assign_person_to_sink()     → sink_index
    2. For each hand:
         point_inside_expanded_box() → belongs_to_person?
       Nearest-person assignment for each hand.
    3. hand_is_near_sink()         → hand_near_sink
    4. Movement history update     → movement_score (EMA)
    5. washing_evidence = has_hand AND near_sink AND (moving OR not require_hand_movement)
    6. positive_frames / no_detection_frames update
    7. hands_interacting = positive_frames >= confirmation_frames
    8. inside_sink_zone = hand_near_sink (hand physically at the sink)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

import structlog

from backend.app.compliance.spatial import (
    assign_person_to_sink,
    box_center,
    hand_is_near_sink,
    point_distance,
    point_inside_expanded_box,
)
from backend.app.compliance.tracker import Track
from backend.app.inference.models.detection import BoundingBox, Detection

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Observation dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    """Domain observation for one tracked person in one frame.

    All boolean fields default to ``False`` when the relevant evidence is
    absent.  ``None`` means "information unavailable" — distinct from
    ``False`` (observed and not present).

    Attributes:
        camera_id:            Source camera.
        zone_id:              Zone within the camera.
        person_id:            Stable track ID (ByteTrack or IoUTracker).
        timestamp:            Frame capture time.
        frame_id:             Monotonic frame counter.
        inside_sink_zone:     True when the person's hand is near their
                              assigned sink.  Maps to ``hand_near_sink`` in
                              the reference script; drives state machine
                              zone-entry/exit transitions.
        hands_interacting:    True when washing is *confirmed* — i.e.
                              ``positive_frames >= confirmation_frames``.
                              Unlike the original single-model design where
                              this meant "raw handwash class detected", here
                              it signals temporal confirmation.
        hand_near_sink:       Raw per-frame flag (hand spatially near sink),
                              before temporal confirmation.
        hand_count:           Number of hands associated with this person.
        hand_movement_score:  Exponential-moving-average of hand displacement
                              (pixels/frame).
        positive_frames:      Consecutive frames with washing evidence.
        no_detection_frames:  Consecutive frames without washing evidence.
        water_detected:       Not used in multi-model design; kept for
                              interface compatibility (always False).
        soap_detected:        Not used in multi-model design; kept for
                              interface compatibility (always False).
        track_bbox:           Person bounding box in original frame coords.
        is_synthetic:         True when synthesised for a person not seen
                              this frame (absence inference).
    """

    camera_id: str
    zone_id: str
    person_id: int
    timestamp: datetime
    frame_id: int
    inside_sink_zone: bool
    hands_interacting: bool
    hand_near_sink: bool = False
    hand_count: int = 0
    hand_movement_score: float = 0.0
    positive_frames: int = 0
    no_detection_frames: int = 0
    water_detected: bool = False
    soap_detected: bool = False
    track_bbox: BoundingBox | None = None
    is_synthetic: bool = False


# ---------------------------------------------------------------------------
# ObservationBuilder
# ---------------------------------------------------------------------------

class ObservationBuilder:
    """Converts multi-model detections into domain Observations.

    Stateful: maintains per-person movement history and confirmation
    frame counts across calls.  One instance per compliance worker.

    Args:
        person_class:           YOLO class name for people (e.g. "person").
        sink_class:             YOLO class name for sinks (e.g. "sink").
        hand_class:             YOLO class name for hands / washing activity
                                (trigger_class, e.g. "hand_washing").
        person_box_expand_x:    Horizontal expansion ratio for hand→person
                                association (PERSON_BOX_EXPAND_X).
        person_box_expand_y:    Vertical expansion ratio (PERSON_BOX_EXPAND_Y).
        max_person_sink_distance: Max normalised distance for person→sink
                                  assignment (MAX_PERSON_SINK_DISTANCE).
        sink_horizontal_margin: Sink proximity zone horizontal margin.
        sink_top_margin:        Sink proximity zone top margin.
        sink_bottom_margin:     Sink proximity zone bottom margin.
        min_hands_for_washing:  Minimum associated hands required.
        min_hand_movement:      Minimum EMA movement score to count as moving.
        require_hand_movement:  If True, movement is required for washing evidence.
        confirmation_frames:    Consecutive positive frames before hands_interacting=True.
        reset_after_no_detection_seconds: Seconds without hand-near-sink before
                                          treating person as having left the zone.
        movement_history_size:  Rolling window size for hand center history.
    """

    def __init__(
        self,
        person_class: str = "person",
        sink_class: str = "sink",
        hand_class: str = "hand_washing",
        person_box_expand_x: float = 0.15,
        person_box_expand_y: float = 0.20,
        max_person_sink_distance: float = 2.0,
        sink_horizontal_margin: float = 0.30,
        sink_top_margin: float = 1.50,
        sink_bottom_margin: float = 0.20,
        min_hands_for_washing: int = 1,
        min_hand_movement: float = 2.0,
        require_hand_movement: bool = True,
        confirmation_frames: int = 3,
        reset_after_no_detection_seconds: float = 1.0,
        movement_history_size: int = 12,
    ) -> None:
        self._person_class = person_class
        self._sink_class = sink_class
        self._hand_class = hand_class
        self._person_box_expand_x = person_box_expand_x
        self._person_box_expand_y = person_box_expand_y
        self._max_sink_distance = max_person_sink_distance
        self._sink_h_margin = sink_horizontal_margin
        self._sink_top_margin = sink_top_margin
        self._sink_bottom_margin = sink_bottom_margin
        self._min_hands = min_hands_for_washing
        self._min_movement = min_hand_movement
        self._require_movement = require_hand_movement
        self._confirm_frames = confirmation_frames
        self._reset_seconds = reset_after_no_detection_seconds
        self._movement_history_size = movement_history_size

        # Per-person tracking state (keyed by track_id / person_id).
        # This state is lightweight and intentionally separate from the
        # StateStore — it resets when the worker restarts and does not
        # need to survive process restarts.
        self._tracking: dict[int, dict] = {}

        logger.info(
            "observation_builder_initialized",
            person_class=person_class,
            sink_class=sink_class,
            hand_class=hand_class,
            confirmation_frames=confirmation_frames,
            require_hand_movement=require_hand_movement,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        camera_id: str,
        zone_id: str,
        frame_id: int,
        timestamp: datetime,
        tracks: list[Track],
        all_detections: list[Detection] | None = None,
    ) -> list[Observation]:
        """Build one Observation per active person track.

        Args:
            camera_id:       Camera source identifier.
            zone_id:         Zone identifier.
            frame_id:        Current frame counter.
            timestamp:       Frame capture time.
            tracks:          Active person tracks (from the Tracker).
            all_class_names: All class names present this frame (unused;
                             kept for interface compatibility).
            all_detections:  All raw Detection objects from all models.
                             Required to extract sink and hand detections.
        """
        all_detections = all_detections or []

        # ── Split detections by model role ───────────────────────────────────
        sink_dets = [
            d for d in all_detections
            if d.class_name == self._sink_class
        ]
        hand_dets = [
            d for d in all_detections
            if d.class_name == self._hand_class
        ]

        # ── Convert to simple tuples for spatial functions ───────────────────
        sink_boxes: list[tuple[tuple[int, int, int, int], float]] = [
            (
                (int(d.bbox.x1), int(d.bbox.y1), int(d.bbox.x2), int(d.bbox.y2)),
                d.confidence,
            )
            for d in sink_dets
        ]

        # ── Hand→Person assignment ───────────────────────────────────────────
        # A hand belongs to the nearest person whose expanded bbox contains
        # the hand center.
        person_hand_assignments: dict[int, list[tuple[tuple[int, int, int, int], float]]] = {
            t.track_id: [] for t in tracks
        }
        for hand_det in hand_dets:
            hbox = (
                int(hand_det.bbox.x1), int(hand_det.bbox.y1),
                int(hand_det.bbox.x2), int(hand_det.bbox.y2),
            )
            hand_center = box_center(hbox)
            best_pid: int | None = None
            best_dist = float("inf")
            for track in tracks:
                pbox = (
                    int(track.detection.bbox.x1), int(track.detection.bbox.y1),
                    int(track.detection.bbox.x2), int(track.detection.bbox.y2),
                )
                if not point_inside_expanded_box(
                    hand_center, pbox,
                    self._person_box_expand_x, self._person_box_expand_y,
                ):
                    continue
                dist = point_distance(hand_center, box_center(pbox))
                if dist < best_dist:
                    best_dist = dist
                    best_pid = track.track_id
            if best_pid is not None:
                person_hand_assignments[best_pid].append((hbox, hand_det.confidence))

        # ── Build one Observation per person track ───────────────────────────
        observations: list[Observation] = []
        for track in tracks:
            person_id = track.track_id
            pbox = (
                int(track.detection.bbox.x1), int(track.detection.bbox.y1),
                int(track.detection.bbox.x2), int(track.detection.bbox.y2),
            )

            # Ensure tracking state entry exists.
            state = self._get_or_create(person_id)
            state["last_seen_at"] = timestamp

            # ── Sink assignment ──────────────────────────────────────────────
            sink_index = assign_person_to_sink(
                pbox, sink_boxes, self._max_sink_distance
            )
            state["sink_index"] = sink_index

            # ── Hand-to-sink proximity ───────────────────────────────────────
            assigned_hands = person_hand_assignments.get(person_id, [])
            hand_near_sink = False
            hand_centers: list[tuple[int, int]] = []

            for hbox, _ in assigned_hands:
                hand_centers.append(box_center(hbox))
                if sink_index is not None:
                    sink_box, _ = sink_boxes[sink_index]
                    if hand_is_near_sink(
                        hbox, sink_box,
                        self._sink_h_margin,
                        self._sink_top_margin,
                        self._sink_bottom_margin,
                    ):
                        hand_near_sink = True

            # ── Hand movement (EMA) ──────────────────────────────────────────
            if hand_centers:
                avg_x = sum(c[0] for c in hand_centers) / len(hand_centers)
                avg_y = sum(c[1] for c in hand_centers) / len(hand_centers)
                current_center = (int(avg_x), int(avg_y))
                history: deque = state["movement_history"]
                history.append(current_center)
                if len(history) >= 2:
                    movement = point_distance(history[-1], history[-2])
                    state["movement_score"] = (
                        0.8 * state["movement_score"] + 0.2 * movement
                    )
            else:
                state["movement_score"] *= 0.8

            movement_score: float = state["movement_score"]

            # ── Washing evidence ─────────────────────────────────────────────
            has_enough_hands = len(assigned_hands) >= self._min_hands
            is_moving = movement_score >= self._min_movement

            if self._require_movement:
                washing_evidence = has_enough_hands and hand_near_sink and is_moving
            else:
                washing_evidence = has_enough_hands and hand_near_sink

            # ── Temporal confirmation ────────────────────────────────────────
            if washing_evidence:
                state["positive_frames"] += 1
                state["no_detection_frames"] = 0
            else:
                state["positive_frames"] = 0
                state["no_detection_frames"] += 1

            # ── Reset check (person left sink area) ─────────────────────────
            # If the hand has been away from the sink long enough, treat the
            # person as having exited the sink zone for state-machine purposes.
            inside_sink_zone = hand_near_sink
            if not hand_near_sink and state.get("last_hand_near_sink_at") is not None:
                elapsed = (timestamp - state["last_hand_near_sink_at"]).total_seconds()
                if elapsed >= self._reset_seconds:
                    # Persist the exit — downstream rule evaluator handles
                    # the WASHED/NOT_WASHED decision.
                    inside_sink_zone = False
                else:
                    # Within grace period — still treat as "at sink" to absorb
                    # brief detection gaps.
                    inside_sink_zone = True

            if hand_near_sink:
                state["last_hand_near_sink_at"] = timestamp

            # ── Confirmed washing ────────────────────────────────────────────
            confirmed_washing = state["positive_frames"] >= self._confirm_frames

            observations.append(Observation(
                camera_id=camera_id,
                zone_id=zone_id,
                person_id=person_id,
                timestamp=timestamp,
                frame_id=frame_id,
                inside_sink_zone=inside_sink_zone,
                hands_interacting=confirmed_washing,
                hand_near_sink=hand_near_sink,
                hand_count=len(assigned_hands),
                hand_movement_score=movement_score,
                positive_frames=state["positive_frames"],
                no_detection_frames=state["no_detection_frames"],
                track_bbox=track.detection.bbox,
            ))

        logger.info(
            "observations_built",
            camera_id=camera_id,
            zone_id=zone_id,
            frame_id=frame_id,
            track_count=len(tracks),
            observation_count=len(observations),
            sink_count=len(sink_boxes),
            hand_count=len(hand_dets),
        )
        return observations

    def evict_stale(
        self,
        now: datetime,
        stale_threshold_seconds: float = 3.0,
    ) -> None:
        """Remove tracking state for persons not seen for ``stale_threshold_seconds``.

        Call once per frame after ``build()``.  Persons whose ``last_seen_at``
        timestamp is older than the threshold are evicted (mirrors the reference
        script's ``frame_number - last_seen_frame > source_fps * 3`` check).

        Args:
            now:                     Current frame timestamp.
            stale_threshold_seconds: Evict after this many seconds of absence.
        """
        to_remove = [
            pid for pid, state in self._tracking.items()
            if state.get("last_seen_at") is not None
            and (now - state["last_seen_at"]).total_seconds() > stale_threshold_seconds
        ]
        for pid in to_remove:
            del self._tracking[pid]
            logger.debug("observation_builder_evicted_stale", person_id=pid)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_create(self, person_id: int) -> dict:
        if person_id not in self._tracking:
            self._tracking[person_id] = {
                "movement_history": deque(maxlen=self._movement_history_size),
                "movement_score": 0.0,
                "positive_frames": 0,
                "no_detection_frames": 0,
                "sink_index": None,
                "last_hand_near_sink_at": None,
                "last_seen_at": None,
            }
        return self._tracking[person_id]
