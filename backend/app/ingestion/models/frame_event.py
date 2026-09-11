"""FrameEvent — strongly typed event representing one sampled frame."""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass(frozen=True)
class FrameEvent:
    """Immutable event published downstream after a frame passes validation and sampling.

    Attributes:
        camera_id:    Identifies the source camera.  Monotonically stable per source.
        frame_id:     Monotonically increasing counter per camera_id.
        captured_at:  Best approximation of when the frame was captured at the source.
                      For RTSP this is the ingestion receive time (camera timestamps
                      are not reliably available over RTSP without SDP metadata).
                      For video files this tracks playback position.
        received_at:  Wall-clock time when the ingestion service received the frame.
        frame:        Raw BGR numpy array from OpenCV.  The field is excluded from
                      equality checks and hashing because numpy arrays are mutable
                      and unhashable; content equality is not required for routing.
    """

    camera_id: str
    frame_id: int
    captured_at: datetime
    received_at: datetime
    frame: np.ndarray = field(compare=False, hash=False, repr=False)
    correlation_id: str = ""
    session_id: str = ""
    source_fps: float = 0.0   # native FPS of the source video; 0 = unknown
