"""Unit tests for ModelSpec — immutability and validation."""

import pytest

from backend.app.inference.model_spec import ModelSpec


def _valid(**overrides) -> ModelSpec:
    defaults = dict(
        use_case="handwashing",
        model_path="artifacts/yolo11n.pt",
        confidence_threshold=0.5,
        device="cpu",
        image_size=640,
    )
    defaults.update(overrides)
    return ModelSpec(**defaults)


class TestModelSpecValid:
    def test_creates_successfully(self):
        spec = _valid()
        assert spec.use_case == "handwashing"
        assert spec.model_path == "artifacts/yolo11n.pt"
        assert spec.confidence_threshold == 0.5
        assert spec.device == "cpu"
        assert spec.image_size == 640

    def test_confidence_boundary_zero(self):
        spec = _valid(confidence_threshold=0.0)
        assert spec.confidence_threshold == 0.0

    def test_confidence_boundary_one(self):
        spec = _valid(confidence_threshold=1.0)
        assert spec.confidence_threshold == 1.0

    def test_cuda_device_accepted(self):
        spec = _valid(device="cuda")
        assert spec.device == "cuda"

    def test_mps_device_accepted(self):
        spec = _valid(device="mps")
        assert spec.device == "mps"

    def test_normalised_path_is_absolute(self):
        spec = _valid(model_path="artifacts/yolo11n.pt")
        assert spec.normalised_path == spec.normalised_path  # idempotent
        import os
        assert os.path.isabs(spec.normalised_path)


class TestModelSpecImmutable:
    def test_cannot_mutate_use_case(self):
        spec = _valid()
        with pytest.raises((AttributeError, TypeError)):
            spec.use_case = "other"  # type: ignore[misc]

    def test_cannot_mutate_confidence(self):
        spec = _valid()
        with pytest.raises((AttributeError, TypeError)):
            spec.confidence_threshold = 0.9  # type: ignore[misc]

    def test_cannot_add_attribute(self):
        spec = _valid()
        with pytest.raises((AttributeError, TypeError)):
            spec.extra = "value"  # type: ignore[attr-defined]


class TestModelSpecValidation:
    def test_empty_use_case_raises(self):
        with pytest.raises(ValueError, match="use_case"):
            _valid(use_case="")

    def test_whitespace_use_case_raises(self):
        with pytest.raises(ValueError, match="use_case"):
            _valid(use_case="   ")

    def test_empty_model_path_raises(self):
        with pytest.raises(ValueError, match="model_path"):
            _valid(model_path="")

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValueError, match="confidence_threshold"):
            _valid(confidence_threshold=-0.01)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValueError, match="confidence_threshold"):
            _valid(confidence_threshold=1.01)

    def test_invalid_device_raises(self):
        with pytest.raises(ValueError, match="device"):
            _valid(device="gpu")

    def test_zero_image_size_raises(self):
        with pytest.raises(ValueError, match="image_size"):
            _valid(image_size=0)

    def test_negative_image_size_raises(self):
        with pytest.raises(ValueError, match="image_size"):
            _valid(image_size=-640)


class TestModelSpecNormalisedPath:
    def test_same_relative_path_normalises_identically(self):
        spec_a = _valid(model_path="artifacts/yolo11n.pt")
        spec_b = _valid(model_path="./artifacts/yolo11n.pt")
        # Both should resolve to the same normalised path
        assert spec_a.normalised_path == spec_b.normalised_path
