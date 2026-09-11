"""RTSPConnector — reads frames from a live RTSP stream with reconnect + backoff."""

import asyncio
import re
import time

import cv2
import structlog

from .base import ReadResult, ReadStatus, StreamConnector

logger = structlog.get_logger(__name__)

_CREDENTIAL_PATTERN = re.compile(r"(rtsp://)[^@]*@")


def _mask_url(url: str) -> str:
    """Strip user:pass from an RTSP URL so credentials never appear in logs."""
    return _CREDENTIAL_PATTERN.sub(r"\1***@", url)


class RTSPConnector(StreamConnector):
    """Connects to an RTSP stream and reads frames continuously.

    A failed read() returns TEMPORARY_FAILURE — never END_OF_STREAM — because
    a live stream does not normally terminate because one frame failed to decode.

    Reconnection uses exponential backoff:
        delay = min(initial_delay * 2^n, max_delay)
    The backoff resets after a successful re-connection.

    All blocking cv2 calls run in the default thread-pool executor so they
    never stall the asyncio event loop.
    """

    def __init__(
        self,
        url: str,
        camera_id: str,
        initial_delay_seconds: float = 1.0,
        max_delay_seconds: float = 15.0,
    ) -> None:
        self._url = url
        self._masked_url = _mask_url(url)
        self._camera_id = camera_id
        self._initial_delay = initial_delay_seconds
        self._max_delay = max_delay_seconds
        self._cap: cv2.VideoCapture | None = None

    @property
    def source_id(self) -> str:
        return self._masked_url

    async def connect(self) -> None:
        """Open the RTSP stream, retrying with backoff until successful."""
        delay = self._initial_delay
        loop = asyncio.get_running_loop()
        while True:
            cap = await loop.run_in_executor(None, lambda: cv2.VideoCapture(self._url))
            if cap.isOpened():
                self._cap = cap
                logger.info("stream_connected", camera_id=self._camera_id, source=self._masked_url)
                return
            cap.release()
            logger.warning(
                "stream_connect_failed",
                camera_id=self._camera_id,
                source=self._masked_url,
                retry_in=round(delay, 1),
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_delay)

    async def read(self) -> ReadResult:
        if self._cap is None:
            return ReadResult(status=ReadStatus.TEMPORARY_FAILURE)
        loop = asyncio.get_running_loop()
        ret, frame = await loop.run_in_executor(None, self._cap.read)
        if ret:
            return ReadResult(status=ReadStatus.FRAME, frame=frame)
        logger.debug("stream_read_failure", camera_id=self._camera_id, source=self._masked_url)
        return ReadResult(status=ReadStatus.TEMPORARY_FAILURE)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("stream_closed", camera_id=self._camera_id, source=self._masked_url)

    async def reconnect(self, stop_event: asyncio.Event) -> bool:
        """Close, then re-open the stream using exponential backoff.

        Sleeps between attempts; checks stop_event after each sleep so shutdown
        is responsive within one backoff interval.

        Returns:
            True  — successfully reconnected.
            False — stop_event was set; caller should terminate the loop.
        """
        self.close()
        delay = self._initial_delay
        attempt_start = time.monotonic()
        loop = asyncio.get_running_loop()
        while not stop_event.is_set():
            logger.warning(
                "reconnect_attempt",
                camera_id=self._camera_id,
                source=self._masked_url,
                retry_in=round(delay, 1),
            )
            await asyncio.sleep(delay)
            if stop_event.is_set():
                return False
            cap = await loop.run_in_executor(None, lambda: cv2.VideoCapture(self._url))
            if cap.isOpened():
                self._cap = cap
                downtime = round(time.monotonic() - attempt_start, 1)
                logger.info(
                    "stream_reconnected",
                    camera_id=self._camera_id,
                    source=self._masked_url,
                    downtime_seconds=downtime,
                )
                return True
            cap.release()
            delay = min(delay * 2, self._max_delay)
        return False
