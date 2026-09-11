"""Unit tests for RedisFrameStore — Redis client is mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from backend.app.infrastructure.redis.frame_store import RedisFrameStore
from backend.app.infrastructure.redis.metrics import RedisMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(client: MagicMock | None = None) -> tuple[RedisFrameStore, MagicMock, RedisMetrics]:
    conn = MagicMock()
    conn.client = client or MagicMock()
    metrics = RedisMetrics()
    store = RedisFrameStore(
        connection=conn,
        metrics=metrics,
        camera_id="cam-01",
        ttl_seconds=30,
        key_prefix="cv:frame",
    )
    return store, conn.client, metrics


def _small_frame(color=(0, 128, 255)) -> np.ndarray:
    """Return a 4x4 BGR frame."""
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    frame[:] = color
    return frame


def _encode_frame(frame: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return buf.tobytes()


# ---------------------------------------------------------------------------
# put()
# ---------------------------------------------------------------------------


class TestPut:
    def test_calls_set_with_correct_key(self):
        store, client, _ = _make_store()
        frame = _small_frame()
        store.put(1, frame)
        call_args = client.set.call_args
        assert call_args[0][0] == "cv:frame:cam-01:1"

    def test_calls_set_with_ttl(self):
        store, client, _ = _make_store()
        store.put(1, _small_frame())
        call_kwargs = client.set.call_args[1]
        assert call_kwargs.get("ex") == 30

    def test_records_frame_put_metric(self):
        store, _, metrics = _make_store()
        store.put(1, _small_frame())
        assert metrics.frame_store_put_total == 1

    def test_redis_error_records_connection_failure(self):
        client = MagicMock()
        client.set.side_effect = ConnectionError("refused")
        store, _, metrics = _make_store(client)
        store.put(1, _small_frame())  # must not raise
        assert metrics.connection_failures == 1
        assert metrics.frame_store_put_total == 0

    def test_unencodable_frame_does_not_call_set(self):
        store, client, _ = _make_store()
        with patch("cv2.imencode", return_value=(False, None)):
            store.put(1, _small_frame())
        client.set.assert_not_called()


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestGet:
    def test_returns_frame_on_hit(self):
        frame = _small_frame()
        client = MagicMock()
        client.getdel.return_value = _encode_frame(frame)
        store, _, metrics = _make_store(client)
        result = store.get(1)
        assert result is not None
        assert result.shape == frame.shape
        assert metrics.frame_store_get_total == 1
        assert metrics.frame_store_miss_total == 0

    def test_returns_none_on_miss(self):
        client = MagicMock()
        client.getdel.return_value = None
        store, _, metrics = _make_store(client)
        result = store.get(99)
        assert result is None
        assert metrics.frame_store_miss_total == 1

    def test_uses_correct_key(self):
        client = MagicMock()
        client.getdel.return_value = None
        store, _, _ = _make_store(client)
        store.get(42)
        client.getdel.assert_called_once_with("cv:frame:cam-01:42")

    def test_redis_error_returns_none(self):
        client = MagicMock()
        client.getdel.side_effect = ConnectionError("refused")
        store, _, metrics = _make_store(client)
        result = store.get(1)
        assert result is None
        assert metrics.connection_failures == 1

    def test_corrupt_jpeg_returns_none(self):
        client = MagicMock()
        client.getdel.return_value = b"\x00\x01\x02corrupt"
        store, _, metrics = _make_store(client)
        result = store.get(1)
        assert result is None
        assert metrics.frame_store_miss_total == 1


# ---------------------------------------------------------------------------
# evict_expired() and size()
# ---------------------------------------------------------------------------


class TestEvictAndSize:
    def test_evict_expired_is_noop(self):
        store, client, _ = _make_store()
        assert store.evict_expired() == 0
        client.assert_not_called()

    def test_size_scans_with_pattern(self):
        client = MagicMock()
        # Simulate single scan page returning 3 keys then cursor=0.
        client.scan.return_value = (0, [b"k1", b"k2", b"k3"])
        store, _, _ = _make_store(client)
        assert store.size() == 3
        call_args = client.scan.call_args
        match_pattern = call_args[1].get("match") or call_args[0][1]
        assert b"cam-01" in match_pattern

    def test_size_redis_error_returns_zero(self):
        client = MagicMock()
        client.scan.side_effect = ConnectionError("refused")
        store, _, _ = _make_store(client)
        assert store.size() == 0
