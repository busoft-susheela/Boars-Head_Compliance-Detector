"""FrameValidator — sanity-checks a raw frame before further processing."""

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

_VALID_CHANNELS = {1, 3, 4}


class FrameValidator:
    """Validates basic structural properties of a numpy frame array.

    One bad frame never crashes the ingestion loop; the frame is simply skipped
    and the invalid_frames counter is incremented.
    """

    def validate(self, frame: object) -> bool:
        """Return True if the frame is safe to process, False otherwise."""
        if frame is None:
            logger.warning("invalid_frame", reason="none")
            return False

        if not isinstance(frame, np.ndarray):
            logger.warning("invalid_frame", reason="not_ndarray", frame_type=type(frame).__name__)
            return False

        if frame.size == 0:
            logger.warning("invalid_frame", reason="empty")
            return False

        if frame.ndim < 2:
            logger.warning("invalid_frame", reason="wrong_ndim", ndim=frame.ndim)
            return False

        if frame.ndim == 3 and frame.shape[2] not in _VALID_CHANNELS:
            logger.warning("invalid_frame", reason="unexpected_channels", channels=frame.shape[2])
            return False

        logger.debug(
            "frame_valid",
            shape=frame.shape,
            dtype=str(frame.dtype),
        )
        return True
