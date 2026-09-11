"""Unit tests for RedisStreamMessageQueue — Redis client is mocked."""
from __future__ import annotations

import json
import queue
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from backend.app.infrastructure.redis.config import RedisConfig
from backend.app.infrastructure.redis.message_queue import RedisStreamMessageQueue
from backend.app.infrastructure.redis.metrics import RedisMetrics
from backend.app.ingestion.models.frame_envelope import FrameEnvelope
from backend.app.infrastructure.redis.serialization import serialize

_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

_TOPIC = "ingestion.frames"
_STREAM = "cv:frame:ingested"
_GROUP = "cv:frame:ingested:workers"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_queue(client: MagicMock | None = None) -> tuple[RedisStreamMessageQueue, MagicMock, RedisMetrics]:
    conn = MagicMock()
    conn.client = client or MagicMock()
    config = RedisConfig()
    metrics = RedisMetrics()
    mq = RedisStreamMessageQueue(
        connection=conn,
        config=config,
        metrics=metrics,
        consumer_name="test-consumer",
    )
    return mq, conn.client, metrics


def _frame_envelope() -> FrameEnvelope:
    return FrameEnvelope(
        camera_id="cam-01",
        frame_id=1,
        captured_at=_NOW,
        received_at=_NOW,
        topic=_TOPIC,
    )


def _xreadgroup_result(payload_bytes: bytes, msg_id: bytes = b"1-0") -> list:
    """Produce a fake xreadgroup return value."""
    return [(b"cv:frame:ingested", [(msg_id, {b"data": payload_bytes})])]


# ---------------------------------------------------------------------------
# publish()
# ---------------------------------------------------------------------------


class TestPublish:
    def test_calls_xadd(self):
        mq, client, _ = _make_queue()
        mq.publish(_TOPIC, _frame_envelope())
        assert client.xadd.called

    def test_xadd_uses_correct_stream(self):
        mq, client, _ = _make_queue()
        mq.publish(_TOPIC, _frame_envelope())
        stream_arg = client.xadd.call_args[0][0]
        assert stream_arg == _STREAM

    def test_xadd_payload_contains_data_field(self):
        mq, client, _ = _make_queue()
        mq.publish(_TOPIC, _frame_envelope())
        fields_arg = client.xadd.call_args[0][1]
        assert b"data" in fields_arg

    def test_records_publish_metric(self):
        mq, _, metrics = _make_queue()
        mq.publish(_TOPIC, _frame_envelope())
        assert metrics.publish_total == 1

    def test_redis_error_records_failure_metric(self):
        client = MagicMock()
        client.xadd.side_effect = ConnectionError("refused")
        mq, _, metrics = _make_queue(client)
        mq.publish(_TOPIC, _frame_envelope())  # must not raise
        assert metrics.publish_failure_total == 1
        assert metrics.publish_total == 0

    def test_unknown_topic_records_failure(self):
        mq, _, metrics = _make_queue()
        mq.publish("unknown.topic", object())
        assert metrics.publish_failure_total == 1


# ---------------------------------------------------------------------------
# get() — successful read
# ---------------------------------------------------------------------------


class TestGet:
    def _setup_client(self, payload_bytes: bytes) -> MagicMock:
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        client.xreadgroup.return_value = _xreadgroup_result(payload_bytes)
        # Disable pending recovery by making last_recovery far in the past.
        return client

    def test_returns_deserialized_message(self):
        envelope = _frame_envelope()
        payload = serialize(_TOPIC, envelope)
        client = self._setup_client(payload)
        mq, _, _ = _make_queue(client)
        # Suppress recovery (set last_recovery to prevent it triggering)
        mq._last_recovery[_TOPIC] = 1e18
        result = mq.get(_TOPIC, timeout=1.0)
        assert isinstance(result, FrameEnvelope)
        assert result.camera_id == "cam-01"

    def test_calls_xack_after_read(self):
        envelope = _frame_envelope()
        payload = serialize(_TOPIC, envelope)
        client = self._setup_client(payload)
        mq, _, _ = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        mq.get(_TOPIC, timeout=1.0)
        assert client.xack.called

    def test_records_stream_read_and_ack_metrics(self):
        envelope = _frame_envelope()
        payload = serialize(_TOPIC, envelope)
        client = self._setup_client(payload)
        mq, _, metrics = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        mq.get(_TOPIC, timeout=1.0)
        assert metrics.stream_read_total == 1
        assert metrics.stream_ack_total == 1

    def test_timeout_raises_queue_empty(self):
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        client.xreadgroup.return_value = []  # no messages
        mq, _, _ = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        with pytest.raises(queue.Empty):
            mq.get(_TOPIC, timeout=0.1)

    def test_invalid_message_acks_and_raises_empty(self):
        invalid_json = b"not-json-at-all"
        client = self._setup_client(invalid_json)
        mq, _, metrics = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        with pytest.raises(queue.Empty):
            mq.get(_TOPIC, timeout=1.0)
        # Should have ACKed the bad message.
        assert client.xack.called
        assert metrics.stream_processing_failure_total == 1

    def test_redis_error_raises_queue_empty(self):
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        client.xreadgroup.side_effect = ConnectionError("refused")
        mq, _, metrics = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        with pytest.raises(queue.Empty):
            mq.get(_TOPIC, timeout=1.0)
        assert metrics.connection_failures == 1

    def test_block_ms_computed_from_timeout(self):
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        client.xreadgroup.return_value = []
        mq, _, _ = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        with pytest.raises(queue.Empty):
            mq.get(_TOPIC, timeout=2.5)
        _, kwargs = client.xreadgroup.call_args
        assert kwargs.get("block") == 2500

    def test_none_timeout_uses_block_zero(self):
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        client.xreadgroup.return_value = []
        mq, _, _ = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        with pytest.raises(queue.Empty):
            mq.get(_TOPIC, timeout=None)
        _, kwargs = client.xreadgroup.call_args
        assert kwargs.get("block") == 0  # block forever


# ---------------------------------------------------------------------------
# Pending recovery
# ---------------------------------------------------------------------------


class TestPendingRecovery:
    def test_xautoclaim_result_returned_and_acked(self):
        envelope = _frame_envelope()
        payload = serialize(_TOPIC, envelope)
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        # Return a valid pending message from xautoclaim.
        client.xautoclaim.return_value = (
            b"0-0",
            [(b"1-0", {b"data": payload})],
            [],
        )
        mq, _, metrics = _make_queue(client)
        # Force recovery to be due immediately.
        mq._last_recovery[_TOPIC] = 0.0

        result = mq.get(_TOPIC, timeout=1.0)
        assert isinstance(result, FrameEnvelope)
        assert client.xack.called
        assert metrics.stream_pending_recovered == 1

    def test_xautoclaim_empty_falls_through_to_xreadgroup(self):
        envelope = _frame_envelope()
        payload = serialize(_TOPIC, envelope)
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        client.xautoclaim.return_value = (b"0-0", [], [])  # nothing pending
        client.xreadgroup.return_value = _xreadgroup_result(payload)
        mq, _, _ = _make_queue(client)
        mq._last_recovery[_TOPIC] = 0.0

        result = mq.get(_TOPIC, timeout=1.0)
        assert isinstance(result, FrameEnvelope)
        assert client.xreadgroup.called


# ---------------------------------------------------------------------------
# qsize()
# ---------------------------------------------------------------------------


class TestQsize:
    def test_calls_xlen(self):
        client = MagicMock()
        client.xlen.return_value = 5
        mq, _, _ = _make_queue(client)
        assert mq.qsize(_TOPIC) == 5
        client.xlen.assert_called_once_with(_STREAM)

    def test_redis_error_returns_zero(self):
        client = MagicMock()
        client.xlen.side_effect = ConnectionError("refused")
        mq, _, _ = _make_queue(client)
        assert mq.qsize(_TOPIC) == 0


# ---------------------------------------------------------------------------
# Consumer group creation
# ---------------------------------------------------------------------------


class TestEnsureGroup:
    def test_busygroup_error_is_silently_ignored(self):
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("BUSYGROUP Consumer Group name already exists")
        client.xreadgroup.return_value = []
        mq, _, _ = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        with pytest.raises(queue.Empty):
            mq.get(_TOPIC, timeout=0.0)

    def test_non_busygroup_error_is_logged_but_not_raised(self):
        client = MagicMock()
        client.xgroup_create.side_effect = Exception("WRONGTYPE Operation against a key")
        client.xreadgroup.return_value = []
        mq, _, _ = _make_queue(client)
        mq._last_recovery[_TOPIC] = 1e18
        # Should not raise on ensure_group failure.
        with pytest.raises(queue.Empty):
            mq.get(_TOPIC, timeout=0.0)
