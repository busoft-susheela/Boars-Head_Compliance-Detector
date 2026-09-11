"""QueuePublisher — delivers FrameEvents via a BoundedBuffer."""

from ..buffering.bounded_buffer import BoundedBuffer
from ..models.frame_event import FrameEvent
from .base import Publisher


class QueuePublisher(Publisher):
    def __init__(self, buffer: BoundedBuffer) -> None:
        self._buffer = buffer

    def publish(self, event: FrameEvent) -> None:
        self._buffer.put(event)
