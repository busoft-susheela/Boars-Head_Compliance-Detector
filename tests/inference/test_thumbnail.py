"""Unit tests for ThumbnailGenerator — resize, encoding, and error handling."""

import numpy as np
import pytest

from backend.app.inference.thumbnail import ThumbnailGenerator


_JPEG_MAGIC = b"\xff\xd8\xff"  # First 3 bytes of any JPEG


class TestThumbnailGenerate:
    def test_returns_jpeg_bytes(self):
        gen = ThumbnailGenerator(max_width=320, jpeg_quality=70)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = gen.generate(frame)
        assert result is not None
        assert result[:3] == _JPEG_MAGIC

    def test_respects_max_width(self):
        """Output image should be at most max_width pixels wide."""
        import cv2
        gen = ThumbnailGenerator(max_width=160, jpeg_quality=70)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = gen.generate(frame)
        assert result is not None
        buf = np.frombuffer(result, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        assert img.shape[1] <= 160

    def test_aspect_ratio_preserved(self):
        """Width:height ratio of thumbnail should match the original."""
        import cv2
        gen = ThumbnailGenerator(max_width=320, jpeg_quality=70)
        # Original is 16:9
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        result = gen.generate(frame)
        assert result is not None
        buf = np.frombuffer(result, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        orig_ratio = 640 / 360
        thumb_ratio = img.shape[1] / img.shape[0]
        assert abs(thumb_ratio - orig_ratio) < 0.1  # allow minor rounding

    def test_small_frame_not_upscaled(self):
        """A frame already narrower than max_width should not be enlarged."""
        import cv2
        gen = ThumbnailGenerator(max_width=320, jpeg_quality=70)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = gen.generate(frame)
        assert result is not None
        buf = np.frombuffer(result, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        assert img.shape[1] <= 100

    def test_returns_none_for_empty_frame(self):
        gen = ThumbnailGenerator()
        result = gen.generate(np.zeros((0, 0, 3), dtype=np.uint8))
        assert result is None

    def test_returns_none_for_none_frame(self):
        gen = ThumbnailGenerator()
        result = gen.generate(None)  # type: ignore[arg-type]
        assert result is None


class TestThumbnailValidation:
    def test_invalid_max_width_raises(self):
        with pytest.raises(ValueError, match="max_width"):
            ThumbnailGenerator(max_width=0)

    def test_invalid_jpeg_quality_below_range_raises(self):
        with pytest.raises(ValueError, match="jpeg_quality"):
            ThumbnailGenerator(jpeg_quality=0)

    def test_invalid_jpeg_quality_above_range_raises(self):
        with pytest.raises(ValueError, match="jpeg_quality"):
            ThumbnailGenerator(jpeg_quality=101)
