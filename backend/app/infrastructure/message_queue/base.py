"""MessageQueue — pub/sub contract every component depends on.

The interface is backend-independent: swap InMemoryMessageQueue for a Redis,
RabbitMQ, or asyncio-native implementation without touching any component that
depends on this ABC.

Design notes
------------
- Topics are opaque strings.  Convention: "service.noun", e.g. "ingestion.frames".
- publish() is fire-and-forget; it never blocks indefinitely.
- get() blocks until a message is available or the timeout elapses.
- One consumer per topic is assumed at current (single-camera) scale.
  Fan-out / broadcast can be added to implementations later without changing
  the interface contract used by producers.
"""

from abc import ABC, abstractmethod
from typing import Any


class MessageQueue(ABC):
    @abstractmethod
    def publish(self, topic: str, message: Any) -> None:
        """Publish a message to a topic.

        Must not block indefinitely.  Implementations may drop the oldest
        message when a topic's capacity is exceeded (log drops).

        Args:
            topic:   Destination topic name.
            message: Any picklable object.
        """

    @abstractmethod
    def get(self, topic: str, timeout: float | None = None) -> Any:
        """Consume and return the next message from a topic.

        Args:
            topic:   Source topic name.
            timeout: Seconds to wait.  None = wait forever.

        Raises:
            queue.Empty: if timeout elapses with no message.
        """

    @abstractmethod
    def qsize(self, topic: str) -> int:
        """Return the approximate number of messages waiting in a topic."""
