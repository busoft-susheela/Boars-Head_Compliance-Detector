"""MessageQueuePublisher — splits a FrameEvent into pixels + routing message.

Responsibility
--------------
1. Store the raw frame in FrameStore (keyed by frame_id).
2. Build a lightweight FrameEnvelope (no pixels).
3. Publish the envelope to the MessageQueue.

This keeps the queue message small: downstream components receive only metadata
and fetch pixels from FrameStore by frame_id only if they need them.
"""

import structlog

from backend.app.infrastructure.frame_store.base import FrameStore
from backend.app.infrastructure.message_queue.base import MessageQueue
from ..models.frame_envelope import FrameEnvelope
from ..models.frame_event import FrameEvent
from .base import Publisher

logger = structlog.get_logger(__name__)

FRAMES_TOPIC = "ingestion.frames"


class MessageQueuePublisher(Publisher):
    """Publishes sampled frames via FrameStore + MessageQueue.

    Args:
        frame_store:   Where raw pixels are stored.
        message_queue: Where FrameEnvelopes are routed.
        topic:         MessageQueue topic to publish to.
                       Defaults to FRAMES_TOPIC ("ingestion.frames").
    """

    def __init__(
        self,
        frame_store: FrameStore,
        message_queue: MessageQueue,
        topic: str = FRAMES_TOPIC,
    ) -> None:
        self._frame_store = frame_store
        self._message_queue = message_queue
        self._topic = topic
        logger.info(
            "publisher_initialized",
            topic=self._topic,
            frame_store=type(frame_store).__name__,
            message_queue=type(message_queue).__name__,
        )

    def publish(self, event: FrameEvent) -> None:
        # 1. Store pixels — must happen before the envelope is enqueued so that
        #    a fast consumer never races to fetch a frame not yet stored.
        try:
            self._frame_store.put(event.frame_id, event.frame)
        except Exception:
            logger.error(
                "frame_store_put_failed",
                camera_id=event.camera_id,
                frame_id=event.frame_id,
                exc_info=True,
            )
            return

        # 2. Build lightweight envelope (no frame field).
        envelope = FrameEnvelope(
            camera_id=event.camera_id,
            frame_id=event.frame_id,
            captured_at=event.captured_at,
            received_at=event.received_at,
            topic=self._topic,
            correlation_id=event.correlation_id,
            session_id=event.session_id,
            source_fps=event.source_fps,
        )

        # 3. Enqueue — never blocks indefinitely (InMemoryMessageQueue drops
        #    oldest on overflow and logs the drop).
        try:
            self._message_queue.publish(self._topic, envelope)
        except Exception:
            logger.error(
                "frame_queue_publish_failed",
                camera_id=event.camera_id,
                frame_id=event.frame_id,
                topic=self._topic,
                exc_info=True,
            )
            return

        logger.info(
            "frame_published",
            camera_id=event.camera_id,
            frame_id=event.frame_id,
            topic=self._topic,
            store_size=self._frame_store.size(),
            queue_depth=self._message_queue.qsize(self._topic),
        )
