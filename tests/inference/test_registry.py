"""Unit tests for ModelRegistry — caching, warm-up, and thread safety."""

import threading
import time
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from backend.app.inference.loader import ModelLoader
from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.registry import ModelRegistry
from backend.app.inference.yolo_detector import YoloDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(path: str = "artifacts/yolo11n.pt", use_case: str = "handwashing") -> ModelSpec:
    return ModelSpec(
        use_case=use_case,
        model_path=path,
        confidence_threshold=0.5,
        device="cpu",
        image_size=640,
    )


def _make_registry(warmup: bool = False) -> tuple[ModelRegistry, MagicMock]:
    """Return a registry with a mocked loader."""
    mock_loader = MagicMock(spec=ModelLoader)
    mock_loader.load.return_value = MagicMock()  # fake YOLO object
    registry = ModelRegistry(loader=mock_loader, warmup=warmup)
    return registry, mock_loader


class TestRegistryGet:
    def test_first_get_loads_model(self):
        registry, mock_loader = _make_registry()
        spec = _spec()
        detector = registry.get(spec)
        mock_loader.load.assert_called_once_with(spec)
        assert isinstance(detector, YoloDetector)

    def test_second_get_returns_same_instance(self):
        registry, mock_loader = _make_registry()
        spec = _spec()
        d1 = registry.get(spec)
        d2 = registry.get(spec)
        assert d1 is d2
        # Model should only be loaded once
        mock_loader.load.assert_called_once()

    def test_different_specs_different_detectors(self):
        registry, mock_loader = _make_registry()
        spec_a = _spec("artifacts/yolo11n.pt", "handwashing")
        spec_b = _spec("artifacts/ppe.pt", "ppe")
        d_a = registry.get(spec_a)
        d_b = registry.get(spec_b)
        assert d_a is not d_b
        assert mock_loader.load.call_count == 2

    def test_same_normalised_path_shares_detector(self):
        """Relative vs absolute path to the same file → same detector."""
        registry, mock_loader = _make_registry()
        import os
        abs_path = os.path.abspath("artifacts/yolo11n.pt")
        spec_rel = _spec("artifacts/yolo11n.pt")
        spec_abs = _spec(abs_path)
        d_rel = registry.get(spec_rel)
        d_abs = registry.get(spec_abs)
        assert d_rel is d_abs
        mock_loader.load.assert_called_once()


class TestRegistryWarmup:
    def test_warmup_runs_after_load(self):
        """With warmup=True, the detector's infer() is called once during loading."""
        mock_loader = MagicMock(spec=ModelLoader)
        mock_model = MagicMock()
        # Model returns empty results for warm-up
        mock_model.return_value = [MagicMock(boxes=[], names={})]
        mock_loader.load.return_value = mock_model

        registry = ModelRegistry(loader=mock_loader, warmup=True)
        spec = _spec()
        registry.get(spec)

        # The mock model should have been called once (warm-up)
        mock_model.assert_called_once()

    def test_warmup_disabled_model_not_called(self):
        mock_loader = MagicMock(spec=ModelLoader)
        mock_model = MagicMock()
        mock_loader.load.return_value = mock_model

        registry = ModelRegistry(loader=mock_loader, warmup=False)
        spec = _spec()
        registry.get(spec)

        mock_model.assert_not_called()

    def test_warmup_failure_does_not_prevent_caching(self):
        """A warm-up error should be logged but the detector is still cached."""
        mock_loader = MagicMock(spec=ModelLoader)
        mock_model = MagicMock()
        mock_model.side_effect = RuntimeError("warm-up OOM")
        mock_loader.load.return_value = mock_model

        registry = ModelRegistry(loader=mock_loader, warmup=True)
        spec = _spec()
        # Should not raise
        detector = registry.get(spec)
        assert detector is not None

        # Model load should NOT be called again on second get
        detector2 = registry.get(spec)
        assert detector is detector2
        mock_loader.load.assert_called_once()


class TestRegistryConcurrency:
    def test_concurrent_first_access_loads_model_once(self):
        """Two threads racing to get() the same model must load it only once."""
        mock_loader = MagicMock(spec=ModelLoader)
        load_count = [0]
        load_lock = threading.Lock()

        def slow_load(spec):
            time.sleep(0.05)  # Simulate model loading time
            with load_lock:
                load_count[0] += 1
            return MagicMock()

        mock_loader.load.side_effect = slow_load

        registry = ModelRegistry(loader=mock_loader, warmup=False)
        spec = _spec()

        detectors = []
        errors = []

        def worker():
            try:
                detectors.append(registry.get(spec))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors
        assert load_count[0] == 1
        # All threads should have gotten the same detector
        assert all(d is detectors[0] for d in detectors)


class TestRegistryClose:
    def test_close_clears_cache(self):
        registry, mock_loader = _make_registry()
        spec = _spec()
        registry.get(spec)
        registry.close()
        # After close, getting the model again should reload
        registry.get(spec)
        assert mock_loader.load.call_count == 2
