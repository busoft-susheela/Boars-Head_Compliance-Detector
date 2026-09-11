"""Unit tests for YoloDetector — inference and output normalisation.

The underlying YOLO model is mocked so no real weights are required.
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.models.detection import BoundingBox, Detection
from backend.app.inference.yolo_detector import YoloDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(**overrides) -> ModelSpec:
    defaults = dict(
        use_case="handwashing",
        model_path="artifacts/yolo11n.pt",
        confidence_threshold=0.5,
        device="cpu",
        image_size=640,
    )
    defaults.update(overrides)
    return ModelSpec(**defaults)


def _fake_box(cls_id: int, conf: float, x1: float, y1: float, x2: float, y2: float):
    """Build a mock Ultralytics box tensor."""
    box = MagicMock()
    box.cls = MagicMock()
    box.cls.item.return_value = cls_id
    box.conf = MagicMock()
    box.conf.item.return_value = conf
    # Mimic Ultralytics tensor: box.xyxy[0].tolist() returns [x1,y1,x2,y2]
    coords = MagicMock()
    coords.tolist.return_value = [x1, y1, x2, y2]
    box.xyxy = [coords]
    return box


def _fake_result(boxes, names: dict):
    result = MagicMock()
    result.names = names
    result.boxes = boxes
    return result


def _make_detector(spec: ModelSpec | None = None) -> tuple[YoloDetector, MagicMock]:
    """Return a YoloDetector with a mocked YOLO model."""
    spec = spec or _spec()
    mock_model = MagicMock()
    detector = YoloDetector(model=mock_model, spec=spec)
    return detector, mock_model


class TestInferNormalisation:
    def test_single_detection_normalised(self):
        detector, mock_model = _make_detector()
        names = {0: "hand"}
        box = _fake_box(0, 0.85, 10.0, 20.0, 100.0, 200.0)
        mock_model.return_value = [_fake_result([box], names)]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.infer(frame)

        assert len(results) == 1
        d = results[0]
        assert d.class_id == 0
        assert d.class_name == "hand"
        assert d.confidence == pytest.approx(0.85)
        assert d.use_case == "handwashing"
        assert d.bbox == BoundingBox(x1=10.0, y1=20.0, x2=100.0, y2=200.0)

    def test_multiple_detections(self):
        detector, mock_model = _make_detector()
        names = {0: "hand", 1: "soap"}
        boxes = [
            _fake_box(0, 0.9, 0, 0, 50, 50),
            _fake_box(1, 0.7, 100, 100, 200, 200),
        ]
        mock_model.return_value = [_fake_result(boxes, names)]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.infer(frame)

        assert len(results) == 2
        assert {d.class_name for d in results} == {"hand", "soap"}

    def test_empty_detections(self):
        detector, mock_model = _make_detector()
        mock_model.return_value = [_fake_result([], {0: "hand"})]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.infer(frame)

        assert results == []

    def test_use_case_from_spec(self):
        detector, mock_model = _make_detector(_spec(use_case="ppe"))
        box = _fake_box(0, 0.8, 0, 0, 10, 10)
        mock_model.return_value = [_fake_result([box], {0: "helmet"})]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.infer(frame)

        assert results[0].use_case == "ppe"

    def test_model_called_with_spec_parameters(self):
        spec = _spec(image_size=320, device="cpu", confidence_threshold=0.6)
        detector, mock_model = _make_detector(spec)
        mock_model.return_value = [_fake_result([], {})]

        frame = np.zeros((320, 320, 3), dtype=np.uint8)
        detector.infer(frame)

        mock_model.assert_called_once_with(
            frame,
            imgsz=320,
            conf=0.6,
            device="cpu",
            verbose=False,
        )

    def test_unknown_class_id_uses_str(self):
        """When a class ID is not in names, fall back to str(class_id)."""
        detector, mock_model = _make_detector()
        box = _fake_box(99, 0.8, 0, 0, 10, 10)
        mock_model.return_value = [_fake_result([box], {})]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.infer(frame)

        assert results[0].class_name == "99"

    def test_runtime_error_propagates(self):
        detector, mock_model = _make_detector()
        mock_model.side_effect = RuntimeError("CUDA OOM")

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with pytest.raises(RuntimeError, match="CUDA OOM"):
            detector.infer(frame)


class TestDetectorDoesNotLeakUltralytics:
    def test_returns_detection_objects_not_raw_results(self):
        detector, mock_model = _make_detector()
        box = _fake_box(0, 0.8, 0, 0, 10, 10)
        mock_model.return_value = [_fake_result([box], {0: "hand"})]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.infer(frame)

        for d in results:
            assert isinstance(d, Detection)
            assert isinstance(d.bbox, BoundingBox)
