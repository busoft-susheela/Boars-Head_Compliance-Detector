"""Video-timeline utilities for action logging.

Converts frame numbers to human-readable video timestamps (MM:SS) so that
every compliance action log entry can be correlated against a specific
position in the recorded footage — matching the reference script's
``format_video_time`` / ``write_action_log`` pattern.

Usage
-----
::

    from backend.app.compliance.video_time import video_time_str

    logger.info(
        "entered_sink_area",
        person_id=pid,
        video_time=video_time_str(frame_id, source_fps),
    )
"""

from __future__ import annotations

_DEFAULT_FPS = 25.0


def format_video_time(frame_id: int, fps: float) -> str:
    """Convert a frame index to a ``MM:SS`` video timestamp string.

    Args:
        frame_id: 1-based monotonic frame counter (same as ``FrameEnvelope.frame_id``).
        fps:      Native FPS of the source video.  When 0 or negative the
                  function falls back to ``_DEFAULT_FPS`` (25 fps).

    Returns:
        Zero-padded ``"MM:SS"`` string, e.g. ``"01:23"``.
    """
    if fps <= 0:
        fps = _DEFAULT_FPS

    total_seconds = int(max(0, frame_id - 1) / fps)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def video_time_str(frame_id: int, fps: float) -> str:
    """Alias for :func:`format_video_time` — shorter name for inline use."""
    return format_video_time(frame_id, fps)
