"""StaticModelResolver — configuration-driven MVP resolver.

Reads the static model/zone/camera mapping from config at construction time
and returns the appropriate ModelSpec list for any camera+zone pair.

Configuration schema expected from config.yaml::

    cameras:
      handwash-camera-01:
        zones:
          - handwash_zone

    zones:
      handwash_zone:
        models:
          - handwashing.person
          - handwashing.sink
          - handwashing.hand

    models:
      handwashing:
        use_case: handwashing
        device: cpu
        image_size: 640
        person:
          path: artifacts/models/yolo11n.pt
          confidence: 0.25
        sink:
          path: artifacts/models/sink_detection.pt
          confidence: 0.50
        hand:
          path: artifacts/models/handwash_detection.pt
          confidence: 0.50

Validation
----------
The resolver validates the full configuration at construction time so that
configuration errors fail fast rather than appearing on the first real frame.
"""

from __future__ import annotations

import structlog

from backend.app.inference.exceptions import (
    ModelConfigError,
    UnknownCameraError,
    UnknownModelError,
    UnknownZoneError,
)

from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.resolver.base import ModelResolver

logger = structlog.get_logger(__name__)


class StaticModelResolver(ModelResolver):
    """Configuration-backed ModelResolver.  Thread-safe (read-only after init).

    Args:
        config: The top-level application configuration dict (as returned by
                ``config.loader.load_config()``).

    Raises:
        ModelConfigError:  If the configuration is structurally invalid.
        UnknownModelError: If a zone references a model name not defined in ``models:``.
    """

    def __init__(self, config: dict) -> None:
        self._specs = self._build_specs(config)
        # camera_id -> list[zone_id]  (preserves configured order)
        self._camera_zones = self._build_camera_zones(config)
        # zone_id -> list[ModelSpec]  (preserves configured order)
        self._zone_models = self._build_zone_models(config, self._specs)

        logger.debug(
            "static_resolver_ready",
            cameras=list(self._camera_zones.keys()),
            zones=list(self._zone_models.keys()),
        )

    # ------------------------------------------------------------------
    # ModelResolver interface
    # ------------------------------------------------------------------

    def resolve(self, camera_id: str, zone_id: str) -> list[ModelSpec]:
        """Return the ModelSpec list for this camera/zone pair.

        Raises:
            KeyError: If camera_id or zone_id are not in the configuration.
        """
        if camera_id not in self._camera_zones:
            raise UnknownCameraError(camera_id, list(self._camera_zones.keys()))
        if zone_id not in self._zone_models:
            raise UnknownZoneError(zone_id, list(self._zone_models.keys()))
        return list(self._zone_models[zone_id])  # defensive copy

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def zones_for_camera(self, camera_id: str) -> list[str]:
        """Return the ordered list of zone_ids configured for a camera.

        Raises:
            KeyError: If camera_id is unknown.
        """
        if camera_id not in self._camera_zones:
            raise UnknownCameraError(camera_id, list(self._camera_zones.keys()))
        return list(self._camera_zones[camera_id])

    # ------------------------------------------------------------------
    # Private builders — run once at construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_specs(config: dict) -> dict[str, ModelSpec]:
        """Build a mapping of model_name -> ModelSpec from config.

        Supports two config shapes:

        Flat (legacy)::

            models:
              handwashing:
                use_case: handwashing
                path: artifacts/models/handwash_detection.pt
                confidence: 0.5
                device: cpu
                image_size: 640

        Nested (current — all detectors grouped under one use-case)::

            models:
              handwashing:
                use_case: handwashing
                device: cpu
                image_size: 640
                person:
                  path: artifacts/models/yolo11n.pt
                  confidence: 0.25
                sink:
                  path: artifacts/models/sink_detection.pt
                  confidence: 0.50
                hand:
                  path: artifacts/models/handwash_detection.pt
                  confidence: 0.50

        Nested entries produce keys of the form ``"{use_case}.{sub_name}"``
        (e.g. ``"handwashing.person"``).  Shared ``device`` and ``image_size``
        are inherited from the parent and may be overridden per sub-model.
        """
        models_cfg = config.get("models", {})
        if not models_cfg:
            raise ModelConfigError("config.yaml must define at least one model under 'models:'")

        specs: dict[str, ModelSpec] = {}
        for name, mcfg in models_cfg.items():
            if "path" not in mcfg:
                # ── Nested use-case group ──────────────────────────────────
                use_case = mcfg.get("use_case", name)
                shared_device = mcfg.get("device", "cpu")
                shared_image_size = int(mcfg.get("image_size", 640))

                for sub_name, sub_cfg in mcfg.items():
                    if not isinstance(sub_cfg, dict) or "path" not in sub_cfg:
                        continue  # skip scalar keys (use_case, device, image_size)
                    spec_key = f"{name}.{sub_name}"
                    try:
                        presence_conf = sub_cfg.get("presence_confidence")
                        specs[spec_key] = ModelSpec(
                            use_case=use_case,
                            model_path=sub_cfg["path"],
                            confidence_threshold=float(sub_cfg.get("confidence", 0.5)),
                            device=sub_cfg.get("device", shared_device),
                            image_size=int(sub_cfg.get("image_size", shared_image_size)),
                            tracker=sub_cfg.get("tracker") or None,
                            presence_confidence_threshold=float(presence_conf) if presence_conf is not None else None,
                        )
                    except (KeyError, ValueError, TypeError) as exc:
                        raise ModelConfigError(f"Invalid model config for {spec_key!r}: {exc}") from exc
            else:
                # ── Flat single-model entry ────────────────────────────────
                try:
                    presence_conf = mcfg.get("presence_confidence")
                    specs[name] = ModelSpec(
                        use_case=mcfg.get("use_case", name),
                        model_path=mcfg["path"],
                        confidence_threshold=float(mcfg.get("confidence", 0.5)),
                        device=mcfg.get("device", "cpu"),
                        image_size=int(mcfg.get("image_size", 640)),
                        tracker=mcfg.get("tracker") or None,
                        presence_confidence_threshold=float(presence_conf) if presence_conf is not None else None,
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    raise ModelConfigError(f"Invalid model config for {name!r}: {exc}") from exc

        return specs

    @staticmethod
    def _build_camera_zones(config: dict) -> dict[str, list[str]]:
        """Build a mapping of camera_id -> list[zone_id] from config."""
        cameras_cfg = config.get("cameras", {})
        if not cameras_cfg:
            raise ModelConfigError("config.yaml must define at least one camera under 'cameras:'")

        camera_zones: dict[str, list[str]] = {}
        for cam_id, cam_cfg in cameras_cfg.items():
            zones = cam_cfg.get("zones", [])
            if not isinstance(zones, list):
                raise ModelConfigError(
                    f"cameras.{cam_id}.zones must be a list, got {type(zones).__name__}"
                )
            camera_zones[cam_id] = zones

        return camera_zones

    @staticmethod
    def _build_zone_models(
        config: dict,
        specs: dict[str, ModelSpec],
    ) -> dict[str, list[ModelSpec]]:
        """Build a mapping of zone_id -> list[ModelSpec] from config."""
        zones_cfg = config.get("zones", {})
        if not zones_cfg:
            raise ModelConfigError("config.yaml must define at least one zone under 'zones:'")

        zone_models: dict[str, list[ModelSpec]] = {}
        for zone_id, zone_cfg in zones_cfg.items():
            model_names = zone_cfg.get("models", [])
            if not isinstance(model_names, list):
                raise ModelConfigError(
                    f"zones.{zone_id}.models must be a list, got {type(model_names).__name__}"
                )
            resolved: list[ModelSpec] = []
            for model_name in model_names:
                if model_name not in specs:
                    raise UnknownModelError(model_name, zone_id, list(specs.keys()))
                resolved.append(specs[model_name])

            # Enforce uniqueness (same model listed twice in one zone)
            seen_paths: set[str] = set()
            deduped: list[ModelSpec] = []
            for spec in resolved:
                key = spec.normalised_path
                if key not in seen_paths:
                    seen_paths.add(key)
                    deduped.append(spec)

            zone_models[zone_id] = deduped

        return zone_models
