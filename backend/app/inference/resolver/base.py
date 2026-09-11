"""ModelResolver — abstract interface for model selection.

The resolver answers exactly one question:

    Which models apply to this camera and zone?

It must NOT load models, run inference, access FrameStore, publish events,
or generate thumbnails.  Those are separate responsibilities.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.inference.model_spec import ModelSpec


class ModelResolver(ABC):
    """Backend-independent abstraction for resolving models per camera/zone."""

    @abstractmethod
    def resolve(self, camera_id: str, zone_id: str) -> list[ModelSpec]:
        """Return the ordered list of ModelSpecs that apply to a camera/zone pair.

        Args:
            camera_id: Source camera identifier.
            zone_id:   Zone within the camera (one camera may have multiple zones).

        Returns:
            List of ModelSpec objects, ordered as configured.  May be empty if
            the zone intentionally has no models configured.

        Raises:
            UnknownCameraError: If camera_id is not in the configuration.
            UnknownZoneError:   If zone_id is not in the configuration.
        """
