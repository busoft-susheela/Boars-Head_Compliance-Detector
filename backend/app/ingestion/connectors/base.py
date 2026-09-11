"""StreamConnector abstraction — source-independent interface for frame acquisition."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import numpy as np


class ReadStatus(Enum):
    FRAME = "frame"
    END_OF_STREAM = "end_of_stream"
    TEMPORARY_FAILURE = "temporary_failure"


@dataclass
class ReadResult:
    status: ReadStatus
    frame: np.ndarray | None = None


class StreamConnector(ABC):
    """Common interface implemented by VideoConnector and RTSPConnector.

    The ingestion service works exclusively through this interface so that
    downstream code is unaware of whether frames originate from a file or a
    live RTSP stream.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Human-readable source identifier — must never contain credentials."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the source.  Raises on unrecoverable failure."""

    @abstractmethod
    async def read(self) -> ReadResult:
        """Read one frame.

        Returns:
            ReadResult with status FRAME, END_OF_STREAM, or TEMPORARY_FAILURE.
            TEMPORARY_FAILURE is only used for recoverable failures (e.g. RTSP
            network hiccup).  END_OF_STREAM is used when the source is
            permanently exhausted (e.g. video EOF).
        """

    @abstractmethod
    def close(self) -> None:
        """Release all resources associated with this connector."""

    async def reconnect(self, stop_event: asyncio.Event) -> bool:
        """Attempt to reconnect after a TEMPORARY_FAILURE.

        The default implementation returns False (reconnect not supported).
        RTSPConnector overrides this with exponential backoff.

        Returns:
            True if reconnected successfully, False if stop_event was set or
            reconnect is not supported.
        """
        return False
