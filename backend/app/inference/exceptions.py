"""Custom exceptions for the inference layer.

Hierarchy
---------
InferenceError
├── ModelConfigError        — invalid or missing configuration
│   ├── UnknownCameraError  — camera_id not found in config
│   ├── UnknownZoneError    — zone_id not found in config
│   └── UnknownModelError   — model name referenced by a zone is not defined
├── ModelLoadError          — weights file missing or runtime load failure
└── InferenceRuntimeError   — model raised an error during inference execution
"""

from __future__ import annotations


class InferenceError(Exception):
    """Base class for all inference-layer exceptions."""


class ModelConfigError(InferenceError):
    """Raised when the model/camera/zone configuration is invalid or incomplete."""


class UnknownCameraError(ModelConfigError):
    """Raised when a camera_id is not present in the configuration."""

    def __init__(self, camera_id: str, known: list[str]) -> None:
        self.camera_id = camera_id
        self.known = known
        super().__init__(
            f"Unknown camera_id {camera_id!r}. Known cameras: {known}"
        )


class UnknownZoneError(ModelConfigError):
    """Raised when a zone_id is not present in the configuration."""

    def __init__(self, zone_id: str, known: list[str]) -> None:
        self.zone_id = zone_id
        self.known = known
        super().__init__(
            f"Unknown zone_id {zone_id!r}. Known zones: {known}"
        )


class UnknownModelError(ModelConfigError):
    """Raised when a zone references a model name that is not defined under 'models:'."""

    def __init__(self, model_name: str, zone_id: str, known: list[str]) -> None:
        self.model_name = model_name
        self.zone_id = zone_id
        self.known = known
        super().__init__(
            f"Zone {zone_id!r} references model {model_name!r} which is not defined "
            f"in 'models:'. Known models: {known}"
        )


class ModelLoadError(InferenceError):
    """Raised when model weights cannot be found or the runtime fails to load them."""

    def __init__(self, model_path: str, reason: str) -> None:
        self.model_path = model_path
        self.reason = reason
        super().__init__(f"Failed to load model {model_path!r}: {reason}")


class InferenceRuntimeError(InferenceError):
    """Raised when the model raises an error during an inference call."""

    def __init__(self, model_path: str, reason: str) -> None:
        self.model_path = model_path
        self.reason = reason
        super().__init__(f"Inference failed for model {model_path!r}: {reason}")
