"""Unit tests for Redis key helpers (no Redis required)."""

import pytest

from backend.app.infrastructure.redis.keys import frame_key, stream_consumer_group


class TestFrameKey:
    def test_basic(self):
        assert frame_key("cv:frame", "cam-01", 42) == "cv:frame:cam-01:42"

    def test_zero_frame_id(self):
        assert frame_key("cv:frame", "cam-01", 0) == "cv:frame:cam-01:0"

    def test_custom_prefix(self):
        assert frame_key("test:prefix", "camera-X", 100) == "test:prefix:camera-X:100"

    def test_camera_id_with_colons(self):
        # camera IDs with special chars are allowed; key reflects them verbatim
        key = frame_key("cv:frame", "site:cam:01", 1)
        assert key == "cv:frame:site:cam:01:1"


class TestStreamConsumerGroup:
    def test_appends_workers_suffix(self):
        assert stream_consumer_group("cv:frame:ingested") == "cv:frame:ingested:workers"

    def test_arbitrary_stream_name(self):
        assert stream_consumer_group("my:stream") == "my:stream:workers"
