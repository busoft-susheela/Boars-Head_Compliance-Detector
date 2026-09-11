"""FrameEnvelope — lightweight routing message that travels through the MessageQueue.

The raw frame (np.ndarray) is NOT carried here.  It lives in FrameStore, keyed
by frame_id.  Downstream components retrieve it from the store after dequeuing
the envelope.  This keeps queue messages small regardless of frame resolution.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FrameEnvelope:
    """Immutable message published to the MessageQueue after a frame is sampled.

    Attributes:
        camera_id:   Source camera identifier.
        frame_id:    Monotonically increasing counter per camera_id.
                     Use this key to retrieve the raw frame from FrameStore.
        captured_at: Best approximation of capture time at the source.
        received_at: Wall-clock time when the ingestion service received the frame.
        topic:       The MessageQueue topic this envelope was published to.
    """

    camera_id: str
    frame_id: int
    captured_at: datetime
    received_at: datetime
    topic: str
    correlation_id: str = ""
    session_id: str = ""
    source_fps: float = 0.0   # native FPS of the source video; 0 = unknown
