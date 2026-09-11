"""Publisher ABC — decouples the ingestion service from its downstream consumer."""

from abc import ABC, abstractmethod

from ..models.frame_event import FrameEvent


class Publisher(ABC):
    @abstractmethod
    def publish(self, event: FrameEvent) -> None:
        """Deliver a FrameEvent to the downstream pipeline."""
