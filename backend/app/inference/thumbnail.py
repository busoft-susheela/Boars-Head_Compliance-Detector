"""ThumbnailGenerator — creates small JPEG evidence from raw frames.

The thumbnail is generated while the raw frame is still available (immediately
after FrameStore.get()).  This is mandatory because the FrameStore is ephemeral:
by the time a downstream consumer needs evidence, the original frame may have
been evicted.

The thumbnail does NOT change detection coordinate semantics.  Bounding box
coordinates in Detection objects always refer to the original frame.

Configuration::

    inference:
      thumbnail:
        enabled: true
        max_width: 320
        jpeg_quality: 70
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
import cv2
import numpy as np

if TYPE_CHECKING:
    from backend.app.inference.models.detection import Detection

logger = structlog.get_logger(__name__)


class ThumbnailGenerator:
    """Resizes a frame to at most ``max_width`` pixels wide and JPEG-encodes it.

    Aspect ratio is always preserved.  Frames already narrower than ``max_width``
    are not upscaled.

    Args:
        max_width:    Maximum output width in pixels.
        jpeg_quality: JPEG compression quality in [1, 100].  Lower = smaller file.
    """

    def __init__(self, max_width: int = 320, jpeg_quality: int = 70) -> None:
        if max_width <= 0:
            logger.error("thumbnail_invalid_max_width", max_width=max_width)
            raise ValueError(f"max_width must be > 0, got {max_width!r}")
        if not (1 <= jpeg_quality <= 100):
            logger.error("thumbnail_invalid_jpeg_quality", jpeg_quality=jpeg_quality)
            raise ValueError(f"jpeg_quality must be in [1, 100], got {jpeg_quality!r}")
        self._max_width = max_width
        self._jpeg_quality = jpeg_quality
        logger.info("thumbnail_generator_initialized", max_width=max_width, jpeg_quality=jpeg_quality)

    def generate_annotated(
        self,
        frame: np.ndarray,
        detections: list["Detection"],
    ) -> bytes | None:
        """Draw bounding boxes on a copy of ``frame``, then encode as JPEG.

        Args:
            frame:      BGR numpy array (original frame coordinates).
            detections: Detections whose bboxes will be drawn.  If empty,
                        falls back to a plain thumbnail with no annotations.

        Returns:
            Raw JPEG bytes with boxes drawn, or ``None`` if encoding fails.
        """
        if not detections:
            return self.generate(frame)

        try:
            # Resize first so bbox coordinates map correctly to thumbnail space.
            # Drawing on the original frame and then resizing would scale the
            # already-scaled coordinates a second time, placing boxes at the
            # wrong position (proportional to scale²).
            h_o, w_o = frame.shape[:2]
            resized = self._resize(frame)
            h_t, w_t = resized.shape[:2]
            sx = w_t / w_o if w_o > 0 else 1.0
            sy = h_t / h_o if h_o > 0 else 1.0
            for det in detections:
                b = det.bbox
                x1, y1 = int(b.x1 * sx), int(b.y1 * sy)
                x2, y2 = int(b.x2 * sx), int(b.y2 * sy)
                label = (
                    f"{det.class_name}:{det.track_id} {det.confidence:.2f}"
                    if det.track_id is not None
                    else f"{det.class_name} {det.confidence:.2f}"
                )
                cv2.rectangle(resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    resized, label, (x1, max(y1 - 6, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA,
                )
            ok, buf = cv2.imencode(
                ".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
            )
            return buf.tobytes() if ok else self.generate(frame)
        except Exception as exc:
            logger.warning("thumbnail_annotate_error", error=str(exc))
            return self.generate(frame)

    def generate(self, frame: np.ndarray) -> bytes | None:
        """Encode ``frame`` as a small JPEG thumbnail.

        Args:
            frame: BGR numpy array (as returned by FrameStore or OpenCV).

        Returns:
            Raw JPEG bytes, or ``None`` if encoding fails.
        """
        if frame is None or frame.size == 0:
            logger.warning("thumbnail_skip_empty_frame")
            return None

        try:
            resized = self._resize(frame)
            ok, buf = cv2.imencode(
                ".jpg",
                resized,
                [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
            )
            if not ok:
                logger.warning("thumbnail_encode_failed")
                return None
            jpeg_bytes = buf.tobytes()
            logger.info(
                "thumbnail_generated",
                original_shape=list(frame.shape),
                resized_shape=list(resized.shape),
                size_bytes=len(jpeg_bytes),
                jpeg_quality=self._jpeg_quality,
            )
            return jpeg_bytes
        except Exception as exc:
            logger.warning("thumbnail_error", error=str(exc))
            return None

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _resize(self, frame: np.ndarray) -> np.ndarray:
        """Return a resized frame; does nothing if already within max_width."""
        h, w = frame.shape[:2]
        if w <= self._max_width:
            return frame  # no upscaling
        scale = self._max_width / w
        new_w = self._max_width
        new_h = max(1, round(h * scale))
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
