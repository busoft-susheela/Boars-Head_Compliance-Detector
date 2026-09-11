"""TemporalMetrics — typed output of the SpatioTemporalAnalyzer.

Responsibility: carry temporal measurements only.  No compliance decisions.

Duration fields are in seconds derived from wall-clock observation timestamps.
Frame-count fields (positive_frames, no_detection_frames) are raw frame counts
tracked by the ObservationBuilder across the lifetime of one sink visit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalMetrics:
    """Temporal measurements for one person's handwash episode.

    Attributes:
        at_sink_duration:         Total seconds in NEAR_SINK_NOT_WASHING state.
        washing_duration:         Total seconds in WASHING state (includes
                                  ongoing washing if current state is WASHING).
        sequence_valid:           Always True in multi-model design; kept for
                                  interface compatibility.
        continuity_valid:         False if a suspiciously large time gap was
                                  detected between consecutive observations.
        observation_count:        Total observations processed for this person.
        current_state:            Name of the HandwashState at this measurement.
        last_gap_seconds:         Seconds since the previous observation.
        positive_frames:          Consecutive frames with washing evidence
                                  (hand near sink + movement if required).
        no_detection_frames:      Consecutive frames without washing evidence.
        hand_movement_score:      Current EMA movement score (pixels/frame).
    """

    # Wall-clock duration fields
    at_sink_duration: float
    washing_duration: float

    # Validity / continuity
    sequence_valid: bool
    continuity_valid: bool

    # Observation metadata
    observation_count: int
    current_state: str
    last_gap_seconds: float

    # Frame-based fields from ObservationBuilder
    positive_frames: int
    no_detection_frames: int
    hand_movement_score: float
