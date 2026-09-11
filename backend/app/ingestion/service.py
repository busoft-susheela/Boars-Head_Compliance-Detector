"""StreamIngestionService — orchestrates the ingestion pipeline for one camera.

Responsibility:
    connect → read → validate → sample → create FrameEvent → publish (repeat)

The service knows nothing about YOLO, ByteTrack, compliance rules, or
notifications.  Those are downstream concerns.

Shutdown is cooperative: call stop() from within the running event loop and
the run() coroutine exits cleanly after releasing connector resources.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from .connectors.base import ReadStatus, StreamConnector
from .health.metrics import IngestionMetrics
from .models.frame_event import FrameEvent
from .publishing.base import Publisher
from .sampling.base import Sampler
from .validation.frame_validator import FrameValidator

logger = structlog.get_logger(__name__)


class StreamIngestionService:
    """Drives frame acquisition for a single camera source.

    All concrete implementations (VideoConnector, RTSPConnector, FpsSampler,
    QueuePublisher, …) are injected via the constructor — no concrete class is
    instantiated inside this service.

    Example usage::

        service = StreamIngestionService(
            connector=connector,
            sampler=sampler,
            publisher=publisher,
            validator=FrameValidator(),
            camera_id="handwash-camera-01",
        )
        task = asyncio.create_task(service.run())
        ...
        service.stop()
        await task
    """

    def __init__(
        self,
        connector: StreamConnector,
        sampler: Sampler,
        publisher: Publisher,
        camera_id: str,
        validator: FrameValidator | None = None,
        metrics: IngestionMetrics | None = None,
        frame_save_max: int = 0,
    ) -> None:
        self._connector = connector
        self._sampler = sampler
        self._publisher = publisher
        self._validator = validator or FrameValidator()
        self._camera_id = camera_id
        self._metrics = metrics or IngestionMetrics()
        self._stop = asyncio.Event()
        self._frame_id = 0
        self._raw_frame_count = 0
        self._frame_save_max = frame_save_max  # 0 = disabled

    @property
    def metrics(self) -> IngestionMetrics:
        return self._metrics

    async def run(self) -> None:
        """Main ingestion coroutine.  Runs until stop() is called or the source
        reaches EOF.  Resources are always released in the finally block.
        """
        logger.info("ingestion_start",connector=self._connector, camera_id=self._camera_id)
        await self._connector.connect()
        self._metrics.set("stream_connected", True)
        try:
            await self._loop()
        finally:
            self._metrics.set("stream_connected", False)
            self._connector.close()
            logger.info("ingestion_stop", connector=self._connector, camera_id=self._camera_id)

    def stop(self) -> None:
        """Signal the run() coroutine to exit cleanly.

        Must be called from within the same event loop that is running run().
        """
        logger.info("ingestion_stop_requested", connector=self._connector, camera_id=self._camera_id)
        self._stop.set()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _save_frame(frame, folder: str, index: int) -> None:
        """Write *frame* as a JPEG to ``{folder}/{index:06d}.jpg``, creating dirs as needed."""
        try:
            out_dir = Path(folder)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{index:06d}.jpg"
            cv2.imwrite(str(path), frame)
        except Exception as exc:
            logger.warning("frame_save_failed", folder=folder, index=index, error=str(exc))

    async def _loop(self) -> None:
        while not self._stop.is_set():
            result = await self._connector.read()

            if result.status == ReadStatus.END_OF_STREAM:
                logger.info("source_eof", connector=self._connector, camera_id=self._camera_id)
                break

            if result.status == ReadStatus.TEMPORARY_FAILURE:
                self._metrics.set("stream_connected", False)
                reconnected = await self._connector.reconnect(self._stop)
                if not reconnected:
                    logger.info(
                        "reconnect_aborted",
                        connector=self._connector,
                        camera_id=self._camera_id,
                        reason="stop_requested",
                    )
                    break
                self._metrics.increment("reconnect_count")
                self._metrics.set("stream_connected", True)
                continue

            # ReadStatus.FRAME
            frame = result.frame
            self._metrics.increment("frames_received_total")
            self._metrics.set("last_frame_received_at", datetime.now(tz=timezone.utc))

            # Resolve the session_id from the connector (VideoConnector only).
            session_id = getattr(self._connector, "session_id", "")

            # Save every raw frame from the video source (capped at frame_save_max).
            self._raw_frame_count += 1
            if session_id and self._frame_save_max > 0 and self._raw_frame_count <= self._frame_save_max:
                self._save_frame(frame, f"data/result/{session_id}/frames", self._raw_frame_count)

            if not self._validator.validate(frame):
                self._metrics.increment("invalid_frames_total")
                continue

            if not self._sampler.should_process():
                continue

            self._frame_id += 1
            correlation_id = str(uuid.uuid4())
            clear_contextvars()
            bind_contextvars(
                correlation_id=correlation_id,
                camera_id=self._camera_id,
                frame_id=self._frame_id,
                connector=self._connector,
            )

            # Save sampled frames (those that passed the FPS filter, capped at frame_save_max).
            if session_id and self._frame_save_max > 0 and self._frame_id <= self._frame_save_max:
                self._save_frame(frame, f"data/result/{session_id}/sample_frames", self._frame_id)

            now = datetime.now(tz=timezone.utc)
            event = FrameEvent(
                camera_id=self._camera_id,
                frame_id=self._frame_id,
                captured_at=now,   # best approximation; RTSP timestamps not reliably available
                received_at=now,
                frame=frame,
                correlation_id=correlation_id,
                session_id=session_id,
                source_fps=getattr(self._connector, "native_fps", 0.0),
            )
            self._publisher.publish(event)
            self._metrics.increment("frames_sampled_total")
            logger.info(
                "frame_sampled",
                action="Frame captured from video source and queued for inference",
                connector=self._connector,
                camera_id=self._camera_id,
                frame_id=self._frame_id,
            )
