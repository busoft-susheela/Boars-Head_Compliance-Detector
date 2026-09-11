"""Tests for FrameValidator."""

import numpy as np
import pytest

from backend.app.ingestion.validation.frame_validator import FrameValidator


@pytest.fixture()
def validator():
    return FrameValidator()


class TestFrameValidator:
    def test_valid_bgr_frame(self, validator):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        assert validator.validate(frame) is True

    def test_valid_grayscale_frame(self, validator):
        frame = np.zeros((480, 640), dtype=np.uint8)
        assert validator.validate(frame) is True

    def test_valid_single_channel(self, validator):
        frame = np.zeros((480, 640, 1), dtype=np.uint8)
        assert validator.validate(frame) is True

    def test_valid_bgra_frame(self, validator):
        frame = np.zeros((480, 640, 4), dtype=np.uint8)
        assert validator.validate(frame) is True

    def test_none_is_invalid(self, validator):
        assert validator.validate(None) is False

    def test_empty_array_is_invalid(self, validator):
        assert validator.validate(np.array([])) is False

    def test_1d_array_is_invalid(self, validator):
        assert validator.validate(np.zeros(640)) is False

    def test_unexpected_channels_invalid(self, validator):
        frame = np.zeros((480, 640, 5), dtype=np.uint8)
        assert validator.validate(frame) is False

    def test_non_ndarray_is_invalid(self, validator):
        assert validator.validate("not a frame") is False
        assert validator.validate(42) is False
        assert validator.validate([]) is False
