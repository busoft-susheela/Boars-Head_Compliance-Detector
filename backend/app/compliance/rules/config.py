"""HandwashRuleConfig — typed, validated configuration for the handwash rule.

Validated at construction so that misconfiguration causes a clear error at
startup rather than a silent runtime failure.

Config.yaml sections consumed
------------------------------
compliance.handwash.*      — duration thresholds, evidence buffer
compliance.washing.*       — confirmation frames, movement thresholds
compliance.association.*   — spatial thresholds for person/hand/sink linking
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HandwashRuleConfig:
    """Rule parameters for the handwash compliance evaluator.

    Duration / threshold attributes
    --------------------------------
    minimum_washing_duration_seconds:
        Person must accumulate at least this many seconds of confirmed
        WASHING state to be considered compliant on exit.
    absence_threshold_seconds:
        Grace period — kept for backward compatibility; not used in the
        multi-model evaluator which triggers on zone-exit instead.
    evidence_buffer_max:
        Maximum thumbnails buffered per violation episode (ring-buffer).

    Temporal confirmation attributes
    ---------------------------------
    confirmation_frames:
        Consecutive positive frames required before hands_interacting=True
        (DETECTION_CONFIRMATION_FRAMES in the reference script).
    reset_after_no_detection_seconds:
        Seconds without hand-near-sink evidence before treating the person
        as having left the sink zone (RESET_AFTER_NO_DETECTION_SECONDS).

    Movement attributes
    -------------------
    min_hands_for_washing:
        Minimum associated hand detections required (MIN_HANDS_FOR_WASHING).
    min_hand_movement:
        Minimum EMA movement score (pixels/frame) to count as active washing
        (MIN_HAND_MOVEMENT).
    require_hand_movement:
        If True, movement is a required condition for washing evidence
        (REQUIRE_HAND_MOVEMENT).

    Spatial association attributes
    --------------------------------
    person_box_expand_x / _y:
        Fractional expansion applied to the person bbox when assigning hands
        (PERSON_BOX_EXPAND_X / Y).
    max_person_sink_distance:
        Maximum normalised person-to-sink distance for assignment
        (MAX_PERSON_SINK_DISTANCE).
    sink_horizontal_margin / top_margin / bottom_margin:
        Margins around the sink box used for hand-proximity check
        (SINK_HORIZONTAL_MARGIN / TOP_MARGIN / BOTTOM_MARGIN).
    """

    # ── Duration / thresholds ──────────────────────────────────────────────
    minimum_washing_duration_seconds: float
    absence_threshold_seconds: float
    evidence_buffer_max: int

    # ── Temporal confirmation ──────────────────────────────────────────────
    confirmation_frames: int
    reset_after_no_detection_seconds: float

    # ── Movement ──────────────────────────────────────────────────────────
    min_hands_for_washing: int
    min_hand_movement: float
    require_hand_movement: bool

    # ── Spatial association ────────────────────────────────────────────────
    person_box_expand_x: float
    person_box_expand_y: float
    max_person_sink_distance: float
    sink_horizontal_margin: float
    sink_top_margin: float
    sink_bottom_margin: float

    def __post_init__(self) -> None:
        if self.minimum_washing_duration_seconds <= 0:
            raise ValueError(
                f"minimum_washing_duration_seconds must be > 0, "
                f"got {self.minimum_washing_duration_seconds}"
            )
        if self.evidence_buffer_max < 1:
            raise ValueError(
                f"evidence_buffer_max must be >= 1, got {self.evidence_buffer_max}"
            )
        if self.confirmation_frames < 1:
            raise ValueError(
                f"confirmation_frames must be >= 1, got {self.confirmation_frames}"
            )
        if self.min_hands_for_washing < 1:
            raise ValueError(
                f"min_hands_for_washing must be >= 1, got {self.min_hands_for_washing}"
            )

    @classmethod
    def from_config(cls, compliance_cfg: dict) -> "HandwashRuleConfig":
        """Construct from the ``compliance`` section of config.yaml."""
        hw = compliance_cfg.get("handwash", {})
        washing = compliance_cfg.get("washing", {})
        assoc = compliance_cfg.get("association", {})

        return cls(
            # Duration / thresholds
            minimum_washing_duration_seconds=float(
                hw.get("minimum_washing_duration_seconds", 5.0)
            ),
            absence_threshold_seconds=float(
                hw.get("absence_threshold_seconds", 5.0)
            ),
            evidence_buffer_max=int(hw.get("evidence_buffer_max", 10)),

            # Temporal confirmation (compliance.washing.*)
            confirmation_frames=int(
                washing.get("confirmation_frames", 3)
            ),
            reset_after_no_detection_seconds=float(
                washing.get("reset_after_no_detection_seconds", 1.0)
            ),

            # Movement (compliance.washing.*)
            min_hands_for_washing=int(
                washing.get("min_hands", 1)
            ),
            min_hand_movement=float(
                washing.get("min_hand_movement", 2.0)
            ),
            require_hand_movement=bool(
                washing.get("require_hand_movement", True)
            ),

            # Spatial association (compliance.association.*)
            person_box_expand_x=float(
                assoc.get("person_box_expand_x", 0.15)
            ),
            person_box_expand_y=float(
                assoc.get("person_box_expand_y", 0.20)
            ),
            max_person_sink_distance=float(
                assoc.get("max_person_sink_distance", 2.0)
            ),
            sink_horizontal_margin=float(
                assoc.get("sink_horizontal_margin", 0.30)
            ),
            sink_top_margin=float(
                assoc.get("sink_top_margin", 1.50)
            ),
            sink_bottom_margin=float(
                assoc.get("sink_bottom_margin", 0.20)
            ),
        )
