"""Tests for BoundedBuffer."""

import queue

import pytest

from backend.app.ingestion.buffering.bounded_buffer import BoundedBuffer


class TestBoundedBufferInit:
    def test_max_size_zero_raises(self):
        with pytest.raises(ValueError):
            BoundedBuffer(0)

    def test_negative_max_size_raises(self):
        with pytest.raises(ValueError):
            BoundedBuffer(-1)


class TestBoundedBufferPut:
    def test_put_and_get(self):
        buf = BoundedBuffer(max_size=2)
        buf.put("a")
        assert buf.get_nowait() == "a"

    def test_never_exceeds_max_size(self):
        buf = BoundedBuffer(max_size=1)
        buf.put("a")
        buf.put("b")
        buf.put("c")
        assert buf.depth == 1

    def test_latest_frame_retained_when_full(self):
        buf = BoundedBuffer(max_size=1)
        buf.put("old")
        buf.put("new")
        assert buf.get_nowait() == "new"

    def test_drop_counter_increments(self):
        buf = BoundedBuffer(max_size=1)
        buf.put("a")
        assert buf.dropped_count == 0
        buf.put("b")  # evicts "a"
        assert buf.dropped_count == 1
        buf.put("c")  # evicts "b"
        assert buf.dropped_count == 2

    def test_no_drop_when_buffer_has_space(self):
        buf = BoundedBuffer(max_size=3)
        buf.put("a")
        buf.put("b")
        assert buf.dropped_count == 0


class TestBoundedBufferGet:
    def test_get_nowait_raises_when_empty(self):
        buf = BoundedBuffer(max_size=1)
        with pytest.raises(queue.Empty):
            buf.get_nowait()

    def test_get_with_timeout_raises_when_empty(self):
        buf = BoundedBuffer(max_size=1)
        with pytest.raises(queue.Empty):
            buf.get(timeout=0.01)

    def test_depth_reflects_queue_size(self):
        buf = BoundedBuffer(max_size=5)
        assert buf.depth == 0
        buf.put("x")
        assert buf.depth == 1
        buf.get_nowait()
        assert buf.depth == 0
