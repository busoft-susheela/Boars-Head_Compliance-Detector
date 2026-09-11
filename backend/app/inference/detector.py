"""YOLODetector — runs YOLO11n inference on a single frame."""

import time
from pathlib import Path

import numpy as np
import structlog
from ultralytics import YOLO

logger = structlog.get_logger(__name__)


class YOLODetector:
    def __init__(self, weights_path: str | Path):
        self._weights_path = str(weights_path)
        logger.info("yolo_detector_loading", weights_path=self._weights_path)
        t0 = time.monotonic()
        try:
            self._model = YOLO(self._weights_path)
        except Exception as exc:
            logger.error("yolo_detector_load_failed", weights_path=self._weights_path, error=str(exc))
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info("yolo_detector_ready", weights_path=self._weights_path, load_duration_ms=round(elapsed_ms, 1))

    def predict(self, frame: np.ndarray) -> list[dict]:
        """Return a list of detections: [{class_name, confidence, box}, ...]."""
        t0 = time.monotonic()
        results = self._model(frame, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                detections.append({
                    "class_name": r.names[int(box.cls)],
                    "confidence": float(box.conf),
                    "box": box.xyxy[0].tolist(),
                })
        elapsed_ms = (time.monotonic() - t0) * 1000
        if not detections:
            logger.info("yolo_predict_no_detections", weights_path=self._weights_path, duration_ms=round(elapsed_ms, 1))
        else:
            logger.info(
                "yolo_predict_done",
                weights_path=self._weights_path,
                detection_count=len(detections),
                duration_ms=round(elapsed_ms, 1),
                detections=[
                    {"class": d["class_name"], "confidence": round(d["confidence"], 2)}
                    for d in detections
                ],
            )
        return detections
