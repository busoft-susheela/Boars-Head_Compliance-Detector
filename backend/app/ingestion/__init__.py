"""Ingestion package — public API surface."""

from .connectors.base import ReadResult, ReadStatus, StreamConnector
from .connectors.rtsp import RTSPConnector
from .connectors.video import VideoConnector
from .factory import create_connector
from .models.frame_event import FrameEvent
from .service import StreamIngestionService

__all__ = [
    "StreamIngestionService",
    "FrameEvent",
    "StreamConnector",
    "ReadResult",
    "ReadStatus",
    "RTSPConnector",
    "VideoConnector",
    "create_connector",
]
