"""action_log — dedicated human-readable compliance action logger.

Writes pipe-separated lines to ``logs/action_log.log`` (and stdout) using
video-timeline timestamps rather than wall-clock time.

Output format::

    Person ID: 2 | Action: ENTERED SINK AREA | Video Time: 00:12
    Person ID: 2 | Action: LEFT SINK AREA | Video Time: 00:13 | Duration: 1.81s

The logger is backed by a dedicated stdlib logger named ``"action_log"``
configured by ``configure_action_log()`` in ``logging_config.py``.  It does
NOT propagate to the root logger so no JSON bleed into ``bh_cv.log``.

Usage::

    from backend.app.compliance.action_log import write_action_log

    write_action_log(
        person_id=person_id,
        action="ENTERED SINK AREA",
        frame_number=frame_id,
        fps=source_fps,
    )

    write_action_log(
        person_id=person_id,
        action="NOT WASHED",
        frame_number=frame_id,
        fps=source_fps,
        extra=f"Duration: {washing_seconds:.2f}s (< {min_duration}s required)",
    )
"""

from __future__ import annotations

import logging

import structlog

from backend.app.compliance.video_time import format_video_time


# ---------------------------------------------------------------------------
# Private processor
# ---------------------------------------------------------------------------

def _render_action_line(
    logger: object,
    method: str,
    event_dict: dict,
) -> dict:
    """Structlog processor: collapse event_dict into the pipe-separated action line."""
    del logger, method

    person_id = event_dict.get("person_id", "?")
    action = event_dict.get("event", "?")
    frame_id = event_dict.get("frame_id", 0)
    fps = event_dict.get("fps", 0.0)
    state = event_dict.get("state", "")
    result = event_dict.get("result", "")
    extra = event_dict.get("extra", "")

    video_time = format_video_time(frame_id, fps)

    line = (
        f"Person ID: {person_id} | "
        f"Action: {action} | "
        f"State: {state} | "
        f"Video Time: {video_time}"
    )
    if result:
        line += f" | Result: {result}"
    if extra:
        line += f" | {extra}"

    event_dict["event"] = line
    return event_dict


# ---------------------------------------------------------------------------
# Logger instance
# ---------------------------------------------------------------------------

# Wraps the dedicated stdlib logger configured by configure_action_log().
# Uses its own processor chain — independent of the global structlog config.
_action_logger = structlog.wrap_logger(
    logging.getLogger("action_log"),
    processors=[
        _render_action_line,
        structlog.stdlib.render_to_log_kwargs,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_action_log(
    person_id: int,
    action: str,
    frame_number: int,
    fps: float,
    state: str = "",
    result: str = "",
    extra: str = "",
) -> None:
    """Write a compliance action event using the video timeline.

    Args:
        person_id:    Tracked person identifier.
        action:       Human-readable action label (e.g. ``"ENTERED SINK AREA"``).
        frame_number: Current frame counter (used to compute the video timestamp).
        fps:          Source video FPS; passed to :func:`format_video_time`.
        state:        Current HandwashState name (e.g. ``"NOT_WASHED"``).
        result:       Final compliance verdict (``"VIOLATION"`` or ``"COMPLIANT"``).
                      Only set on PROCESS COMPLETE lines.
        extra:        Optional trailing detail appended after a pipe separator
                      (e.g. ``"Duration: 1.81s"``).
    """
    _action_logger.info(
        action,
        person_id=person_id,
        frame_id=frame_number,
        fps=fps,
        state=state,
        result=result,
        extra=extra,
    )
