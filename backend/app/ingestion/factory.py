"""ConnectorFactory — selects the right StreamConnector from configuration.

Source selection happens exactly once here.  The ingestion service receives a
StreamConnector and is never aware of whether it is talking to a file or RTSP.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .connectors.base import StreamConnector
from .connectors.rtsp import RTSPConnector
from .connectors.video import VideoConnector

if TYPE_CHECKING:
    from backend.app.infrastructure.database.engine import Database

_SUPPORTED_TYPES = ("video", "rtsp")


def create_connector(
    stream_cfg: dict,
    zone_id: str | None = None,
    database: "Database | None" = None,
) -> StreamConnector:
    """Build and return a StreamConnector from the ``stream`` config section.

    Expected config shape::

        stream:
          type: video          # or "rtsp"
          camera_id: "handwash-camera-01"

          video:
            path: "/data/handwashing.mp4"
            playback_mode: realtime   # optional, default "realtime"
            loop: false               # optional, default false

          rtsp:
            url: "${RTSP_URL}"

          reconnect:
            initial_delay_seconds: 1.0
            max_delay_seconds: 15.0

    Raises:
        ValueError: if ``type`` is missing, unsupported, or required sub-keys
                    are absent.
    """
    stream_type = stream_cfg.get("type")
    if stream_type not in _SUPPORTED_TYPES:
        raise ValueError(
            f"stream.type must be one of {_SUPPORTED_TYPES!r}, got {stream_type!r}"
        )

    camera_id: str = stream_cfg.get("camera_id", "handwash-camera-01")
    reconnect_cfg: dict = stream_cfg.get("reconnect", {})

    if stream_type == "video":
        video_cfg = stream_cfg.get("video")
        if not video_cfg or not video_cfg.get("path"):
            raise ValueError(
                "stream.video.path is required when stream.type=video "
                "(may be a single file or a folder containing video files)"
            )
        return VideoConnector(
            path=video_cfg["path"],
            camera_id=camera_id,
            playback_mode=video_cfg.get("playback_mode", "realtime"),
            loop=video_cfg.get("loop", False),
            source_path=video_cfg["path"],
            zone_id=zone_id,
            database=database,
        )

    # stream_type == "rtsp"
    rtsp_cfg = stream_cfg.get("rtsp")
    url = (rtsp_cfg or {}).get("url", "")
    if not url:
        raise ValueError("stream.rtsp.url is required when stream.type=rtsp")
    if "${" in url:
        raise ValueError(
            f"stream.rtsp.url contains an unexpanded placeholder: {url!r}. "
            "Set RTSP_URL in your .env file or shell environment."
        )

    return RTSPConnector(
        url=url,
        camera_id=camera_id,
        initial_delay_seconds=reconnect_cfg.get("initial_delay_seconds", 1.0),
        max_delay_seconds=reconnect_cfg.get("max_delay_seconds", 15.0),
    )
