"""ModelLoader — the single point responsible for loading model weights.

Only this module imports from ``ultralytics``.  No other inference component
should instantiate ``YOLO(...)`` directly.  This keeps the downstream pipeline
runtime-agnostic: switching from Ultralytics to ONNX Runtime or OpenVINO only
requires changing this file and its Detector implementation.

Extension points
----------------
Add additional ``load()`` implementations or dispatch on ``spec.model_path``
suffix (``.onnx``, ``.xml``) when new runtimes are needed.  The return type
(``ultralytics.YOLO``) is an internal detail hidden behind the ``YoloDetector``
which the registry stores, not exposed to the rest of the application.
"""

from __future__ import annotations

import time

import structlog
from ultralytics import YOLO

from backend.app.inference.exceptions import ModelLoadError
from backend.app.inference.model_spec import ModelSpec

logger = structlog.get_logger(__name__)


class ModelLoader:
    """Loads model weights into an Ultralytics YOLO runtime object.

    This class is intentionally thin — its only job is ``YOLO(path)``.
    Caching, warm-up, and Detector wrapping are the registry's responsibility.
    """

    def load(self, spec: ModelSpec) -> YOLO:
        """Load model weights from ``spec.model_path``.

        Args:
            spec: Immutable model declaration.

        Returns:
            Loaded ``ultralytics.YOLO`` object, ready for inference.

        Raises:
            ModelLoadError: If the model file does not exist or the runtime fails to load it.
        """
        logger.info(
            "model_loading",
            use_case=spec.use_case,
            model_path=spec.model_path,
            device=spec.device,
        )
        t0 = time.monotonic()
        try:
            model = YOLO(spec.model_path)
        except Exception as exc:
            logger.error(
                "model_load_failed",
                use_case=spec.use_case,
                model_path=spec.model_path,
                error=str(exc),
            )
            raise ModelLoadError(spec.model_path, str(exc)) from exc

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "model_loaded",
            use_case=spec.use_case,
            model_path=spec.model_path,
            load_duration_ms=round(elapsed_ms, 1),
            class_names=list(model.names.values()) if hasattr(model, "names") else [],
        )
        return model
