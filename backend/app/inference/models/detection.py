"""Detection data models — the typed output of the inference layer.

Coordinate convention
---------------------
BoundingBox uses pixel coordinates in the **original frame** coordinate system:
- Origin: top-left corner of the frame (0, 0)
- x1, y1: top-left corner of the detection (inclusive)
- x2, y2: bottom-right corner of the detection (exclusive)
- Values are floats (as returned by the model runtime; callers may round as needed)

DetectionEvent
--------------
The event published to the MessageQueue after inference completes for one frame.
It is self-contained: thumbnail bytes are embedded so downstream consumers never
need to retrieve the original (ephemeral) frame from FrameStore.

Detections are stored in a tuple sorted by (use_case, class_id, confidence desc)
to guarantee deterministic ordering regardless of model execution order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BoundingBox:
    """Pixel-space bounding box in the original frame coordinate system.

    Attributes:
        x1: Left edge (inclusive), float pixels from left.
        y1: Top edge (inclusive), float pixels from top.
        x2: Right edge (exclusive), float pixels from left.
        y2: Bottom edge (exclusive), float pixels from top.
    """

    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class Detection:
    """Typed result for a single detected object.

    Attributes:
        class_id:   Integer class index from the model's class list.
        class_name: Human-readable class label from the model.
        bbox:       Bounding box in original frame pixel coordinates.
        confidence: Detection confidence in [0.0, 1.0].
        use_case:   Identifies which model/use-case produced this detection.
                    Critical when multiple models run against the same frame.
    """

    class_id: int
    class_name: str
    bbox: BoundingBox
    confidence: float
    use_case: str
    track_id: int | None = None  # set by ByteTrack; None when IoUTracker is used


@dataclass(frozen=True)
class DetectionEvent:
    """Message published to the MessageQueue after inference completes for a frame.

    Attributes:
        camera_id:    Source camera identifier (propagated from FrameEnvelope).
        zone_id:      Zone within the camera that was evaluated.
        frame_id:     Monotonically increasing frame identifier per camera.
        captured_at:  Best approximation of capture time at source.
        processed_at: Wall-clock time when inference completed.
        detections:   All detections from all models, sorted deterministically.
                      Empty tuple if no objects were detected (always published).
        thumbnail:    Small JPEG evidence bytes captured while the frame was live.
                      None if thumbnail generation was disabled or failed.
    """

    camera_id: str
    zone_id: str
    frame_id: int
    captured_at: datetime
    processed_at: datetime
    detections: tuple[Detection, ...]
    thumbnail: bytes | None
    correlation_id: str = ""
    source_fps: float = 0.0   # native FPS of the source video; propagated from FrameEnvelope
