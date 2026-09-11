"""YoloDetector — runs one Ultralytics YOLO model against one frame.

Responsibilities:
- Execute inference for a single (model, frame) pair.
- Apply the model-specific confidence threshold.
- Normalise Ultralytics result objects into the project's ``Detection`` type.
- Hide all Ultralytics-specific types from the rest of the pipeline.

Thread safety
-------------
Ultralytics YOLO objects are NOT documented as thread-safe for concurrent
``__call__`` invocations.  The ModelRegistry holds one YoloDetector per model
path.  The CPUInferenceWorker uses a single worker thread (``workers: 1`` by
default), so concurrent inference on the same model is avoided without extra
locking for the MVP.  If workers > 1 is ever configured, a per-detector lock
should be added here.
"""

from __future__ import annotations

import structlog
import numpy as np
from ultralytics import YOLO

from backend.app.inference.exceptions import InferenceRuntimeError
from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.models.detection import BoundingBox, Detection

logger = structlog.get_logger(__name__)


class YoloDetector:
    """Wraps a loaded YOLO model and normalises its output to ``Detection`` objects.

    Args:
        model: Pre-loaded ``ultralytics.YOLO`` instance (owned by the registry).
        spec:  The ModelSpec that describes this model's runtime settings.
    """

    def __init__(self, model: YOLO, spec: ModelSpec) -> None:
        self._model = model
        self._spec = spec

    @property
    def spec(self) -> ModelSpec:
        return self._spec

    def infer(self, frame: np.ndarray) -> list[Detection]:
        """Run inference (or tracking) and return normalised detections.

        When ``spec.tracker`` is set (e.g. ``"bytetrack.yaml"``), uses
        ``model.track()`` with ``persist=True`` so ByteTrack maintains state
        across frames.  Each ``Detection`` will carry a ``track_id`` from the
        tracker.

        When ``spec.tracker`` is None, falls back to plain ``model()`` inference
        with ``track_id=None`` on every detection.

        Args:
            frame: BGR numpy array in the **original frame** coordinate system.
                   The detector does NOT mutate the array.

        Returns:
            List of ``Detection`` objects.  Empty list if no objects exceed the
            configured confidence threshold.

        Raises:
            InferenceRuntimeError: If the underlying model call raises an unexpected error.
        """
        # Use presence_confidence_threshold (lower) for inference when configured —
        # catches anyone near the sink even if not actively washing.
        # The washing confidence gate is applied downstream in ObservationBuilder.
        infer_conf = (
            self._spec.presence_confidence_threshold
            if self._spec.presence_confidence_threshold is not None
            else self._spec.confidence_threshold
        )
        try:
            if self._spec.tracker:
                results = self._model.track(
                    frame,
                    persist=True,
                    tracker=self._spec.tracker,
                    imgsz=self._spec.image_size,
                    conf=infer_conf,
                    device=self._spec.device,
                    verbose=False,
                )
            else:
                results = self._model(
                    frame,
                    imgsz=self._spec.image_size,
                    conf=infer_conf,
                    device=self._spec.device,
                    verbose=False,
                )
        except Exception as exc:
            raise InferenceRuntimeError(self._spec.model_path, str(exc)) from exc

        detections: list[Detection] = []
        for result in results:
            names = result.names
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                track_id: int | None = None
                if box.is_track and box.id is not None:
                    track_id = int(box.id.item())
                detections.append(
                    Detection(
                        class_id=cls_id,
                        class_name=names.get(cls_id, str(cls_id)),
                        bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                        confidence=float(box.conf.item()),
                        use_case=self._spec.use_case,
                        track_id=track_id,
                    )
                )

        logger.debug(
            "inference_complete",
            use_case=self._spec.use_case,
            detection_count=len(detections),
            tracker=self._spec.tracker or "none",
        )
        return detections
