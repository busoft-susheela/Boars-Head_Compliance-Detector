"""StateStore — generic key/value state persistence interface.

The store is deliberately unaware of:
  handwashing, compliance, YOLO, ByteTrack, detections

It stores plain dicts (JSON-serializable values) keyed by a string.
This keeps the future path to a Redis or DynamoDB backend open without
changing any business-layer code.

Concurrency note
----------------
For the current single-process deployment the calling worker serialises
access per camera/zone, so concurrent get+set races do not occur.  A
future Redis backend must use atomic compare-and-swap or optimistic
locking if multiple workers are introduced.

Key convention
--------------
Use ``make_state_key(camera_id, zone_id)`` to build consistent keys.
Do not concatenate strings ad-hoc throughout the codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


def make_state_key(camera_id: str, zone_id: str) -> str:
    """Return a deterministic, opaque state key for a camera/zone pair."""
    return f"{camera_id}:{zone_id}"


class StateStore(ABC):
    """Backend-independent interface for compliance state persistence."""

    @abstractmethod
    def get(self, key: str) -> dict | None:
        """Return the stored state dict, or ``None`` if the key is absent."""

    @abstractmethod
    def set(self, key: str, value: dict) -> None:
        """Persist ``value`` under ``key``, overwriting any previous value."""

    @abstractmethod
    def close(self) -> None:
        """Release resources.  Call during application shutdown."""
