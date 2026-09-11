"""ModelSpec — immutable declaration of one trained model and its runtime settings.

ModelSpec is configuration/data only.  It is NOT:
- a loaded YOLO object
- runtime state
- a cache entry
- a worker

The same ModelSpec may be safely referenced by multiple inference requests because
it is frozen and validates its own fields at construction time.

Registry identity
-----------------
The ModelRegistry uses the *normalised absolute model path* as its cache key.
Two ModelSpec objects with different relative paths that resolve to the same
file are treated as the same model.  Normalisation is the registry's job;
ModelSpec stores the configured (possibly relative) path as-is.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_VALID_DEVICES = {"cpu", "cuda", "mps"}


@dataclass(frozen=True)
class ModelSpec:
    """Immutable declaration of one trained model.

    Attributes:
        use_case:             Short label identifying what this model detects
                              (e.g. ``"handwashing"``).  Used to tag detections.
        model_path:           Path to model weights file, relative to the working
                              directory or absolute.  Must be non-empty.
        confidence_threshold: Minimum detection confidence to retain, in [0, 1].
        device:               Runtime device string: ``"cpu"``, ``"cuda"``, or ``"mps"``.
        image_size:           Model input size in pixels (square).  Must be > 0.
    """

    use_case: str
    model_path: str
    confidence_threshold: float
    device: str
    image_size: int
    tracker: str | None = None  # e.g. "bytetrack.yaml"; None = IoUTracker only
    # When set, the model runs at this lower confidence for detection (presence),
    # while confidence_threshold is used downstream to gate hands_interacting=True.
    # Allows detecting people near the sink even when not actively washing.
    presence_confidence_threshold: float | None = None

    # __post_init__ runs after the frozen dataclass is created; it validates
    # without mutating (raises ValueError on invalid config).
    def __post_init__(self) -> None:
        if not self.use_case.strip():
            raise ValueError("ModelSpec.use_case must be non-empty")
        if not self.model_path.strip():
            raise ValueError("ModelSpec.model_path must be non-empty")
        if not (0.0 <= self.confidence_threshold <= 1.0):
            raise ValueError(
                f"ModelSpec.confidence_threshold must be in [0, 1], "
                f"got {self.confidence_threshold!r}"
            )
        if self.device not in _VALID_DEVICES:
            raise ValueError(
                f"ModelSpec.device must be one of {sorted(_VALID_DEVICES)}, "
                f"got {self.device!r}"
            )
        if self.image_size <= 0:
            raise ValueError(
                f"ModelSpec.image_size must be > 0, got {self.image_size!r}"
            )
        if self.presence_confidence_threshold is not None:
            if not (0.0 <= self.presence_confidence_threshold <= 1.0):
                raise ValueError(
                    f"ModelSpec.presence_confidence_threshold must be in [0, 1], "
                    f"got {self.presence_confidence_threshold!r}"
                )
            if self.presence_confidence_threshold > self.confidence_threshold:
                raise ValueError(
                    "ModelSpec.presence_confidence_threshold must be <= confidence_threshold "
                    f"(got {self.presence_confidence_threshold} > {self.confidence_threshold})"
                )

    @property
    def normalised_path(self) -> str:
        """Absolute, normalised path — used as the ModelRegistry cache key."""
        return os.path.normcase(os.path.abspath(self.model_path))
