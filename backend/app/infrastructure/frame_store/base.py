"""FrameStore — ephemeral pixel storage, separate from queue messages.

Keeping raw frames out of the MessageQueue serves two goals:
  1. Queue messages stay small (a FrameEnvelope is ~200 bytes vs. several MB
     for a 1080p BGR frame).
  2. The store can be swapped independently — shared-memory, Redis, or an S3
     presigned URL scheme — without touching the queue contract.

Lifecycle
---------
put()  — called by the publisher immediately after sampling.
get()  — called by the consumer (inference); consumes (removes) the frame.
         Returns None if the frame has already been evicted or was never stored.
evict_expired() — removes frames that have exceeded the TTL without being
                  read; prevents memory growth when a consumer falls behind.
"""

from abc import ABC, abstractmethod

import numpy as np


class FrameStore(ABC):
    @abstractmethod
    def put(self, frame_id: int, frame: np.ndarray) -> None:
        """Store a raw frame under frame_id.

        Overwrites any existing entry for the same frame_id.
        Implementations should also call evict_expired() here to bound memory.
        """

    @abstractmethod
    def get(self, frame_id: int) -> np.ndarray | None:
        """Consume and return the frame for frame_id, or None if not found.

        The frame is removed from the store on retrieval (consume semantics).
        """

    @abstractmethod
    def evict_expired(self) -> int:
        """Remove all frames that have exceeded their TTL.

        Returns:
            Number of frames evicted.
        """

    @abstractmethod
    def size(self) -> int:
        """Return the number of frames currently held in the store."""
