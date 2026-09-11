"""Tests for StreamIngestionService — complete flow using fakes."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend.app.ingestion.connectors.base import ReadResult, ReadStatus, StreamConnector
from backend.app.ingestion.models.frame_event import FrameEvent
from backend.app.ingestion.publishing.base import Publisher
from backend.app.ingestion.sampling.base import Sampler
from backend.app.ingestion.service import StreamIngestionService
from backend.app.ingestion.validation.frame_validator import FrameValidator


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeConnector(StreamConnector):
    """Replays a sequence of ReadResults then signals EOF."""

    def __init__(self, results: list[ReadResult], reconnect_returns: bool = True) -> None:
        self._results = iter(results)
        self._reconnect_returns = reconnect_returns
        self.connect_calls = 0
        self.close_calls = 0
        self.reconnect_calls = 0

    @property
    def source_id(self) -> str:
        return "fake-source"

    async def connect(self) -> None:
        self.connect_calls += 1

    async def read(self) -> ReadResult:
        try:
            return next(self._results)
        except StopIteration:
            return ReadResult(status=ReadStatus.END_OF_STREAM)

    def close(self) -> None:
        self.close_calls += 1

    async def reconnect(self, stop_event) -> bool:
        self.reconnect_calls += 1
        return self._reconnect_returns


class FakeSampler(Sampler):
    def __init__(self, accept_all: bool = True) -> None:
        self._accept_all = accept_all

    def should_process(self) -> bool:
        return self._accept_all


class FakePublisher(Publisher):
    def __init__(self) -> None:
        self.events: list[FrameEvent] = []

    def publish(self, event: FrameEvent) -> None:
        self.events.append(event)


def _frame() -> np.ndarray:
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _service(connector, sampler=None, publisher=None) -> tuple[StreamIngestionService, FakePublisher]:
    pub = publisher or FakePublisher()
    svc = StreamIngestionService(
        connector=connector,
        sampler=sampler or FakeSampler(),
        publisher=pub,
        validator=FrameValidator(),
        camera_id="cam-01",
    )
    return svc, pub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestServiceFullFlow:
    async def test_frames_published_in_order(self):
        results = [
            ReadResult(ReadStatus.FRAME, _frame()),
            ReadResult(ReadStatus.FRAME, _frame()),
            ReadResult(ReadStatus.FRAME, _frame()),
        ]
        connector = FakeConnector(results)
        svc, pub = _service(connector)
        await svc.run()

        assert len(pub.events) == 3
        assert [e.frame_id for e in pub.events] == [1, 2, 3]

    async def test_camera_id_propagated_to_events(self):
        connector = FakeConnector([ReadResult(ReadStatus.FRAME, _frame())])
        svc, pub = _service(connector)
        await svc.run()

        assert pub.events[0].camera_id == "cam-01"

    async def test_frame_id_monotonically_increases(self):
        results = [ReadResult(ReadStatus.FRAME, _frame()) for _ in range(5)]
        connector = FakeConnector(results)
        svc, pub = _service(connector)
        await svc.run()

        ids = [e.frame_id for e in pub.events]
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)

    async def test_timestamps_are_set(self):
        connector = FakeConnector([ReadResult(ReadStatus.FRAME, _frame())])
        svc, pub = _service(connector)
        await svc.run()

        event = pub.events[0]
        assert isinstance(event.captured_at, datetime)
        assert isinstance(event.received_at, datetime)


class TestServiceVideoEOF:
    async def test_eof_stops_loop_gracefully(self):
        connector = FakeConnector([ReadResult(ReadStatus.END_OF_STREAM)])
        svc, pub = _service(connector)
        await svc.run()

        assert connector.close_calls == 1
        assert len(pub.events) == 0

    async def test_connector_always_closed_on_eof(self):
        connector = FakeConnector([
            ReadResult(ReadStatus.FRAME, _frame()),
            ReadResult(ReadStatus.END_OF_STREAM),
        ])
        svc, _ = _service(connector)
        await svc.run()
        assert connector.close_calls == 1


class TestServiceRTSPFailure:
    async def test_temporary_failure_triggers_reconnect(self):
        connector = FakeConnector(
            [
                ReadResult(ReadStatus.TEMPORARY_FAILURE),
                ReadResult(ReadStatus.FRAME, _frame()),
            ],
            reconnect_returns=True,
        )
        svc, pub = _service(connector)
        await svc.run()

        assert connector.reconnect_calls == 1
        assert len(pub.events) == 1

    async def test_failed_reconnect_stops_loop(self):
        connector = FakeConnector(
            [ReadResult(ReadStatus.TEMPORARY_FAILURE)],
            reconnect_returns=False,
        )
        svc, pub = _service(connector)
        await svc.run()

        assert connector.close_calls == 1
        assert len(pub.events) == 0

    async def test_reconnect_count_tracked_in_metrics(self):
        connector = FakeConnector(
            [
                ReadResult(ReadStatus.TEMPORARY_FAILURE),
                ReadResult(ReadStatus.TEMPORARY_FAILURE),
                ReadResult(ReadStatus.FRAME, _frame()),
            ],
            reconnect_returns=True,
        )
        svc, _ = _service(connector)
        await svc.run()

        assert svc.metrics.reconnect_count == 2


class TestServiceInvalidFrames:
    async def test_invalid_frame_skipped_not_published(self):
        bad_frame = ReadResult(ReadStatus.FRAME, None)  # None frame fails validation
        good_frame = ReadResult(ReadStatus.FRAME, _frame())
        connector = FakeConnector([bad_frame, good_frame])
        svc, pub = _service(connector)
        await svc.run()

        assert len(pub.events) == 1
        assert svc.metrics.invalid_frames_total == 1

    async def test_invalid_frame_does_not_crash_loop(self):
        results = [ReadResult(ReadStatus.FRAME, None)] * 5
        connector = FakeConnector(results)
        svc, pub = _service(connector)
        await svc.run()  # must not raise

        assert len(pub.events) == 0


class TestServiceSampling:
    async def test_sampler_rejection_skips_publish(self):
        results = [ReadResult(ReadStatus.FRAME, _frame()) for _ in range(10)]
        connector = FakeConnector(results)
        svc, pub = _service(connector, sampler=FakeSampler(accept_all=False))
        await svc.run()

        assert len(pub.events) == 0


class TestServiceShutdown:
    async def test_stop_halts_running_service(self):
        """stop() called from within the event loop terminates run() cleanly."""

        class InfiniteConnector(StreamConnector):
            @property
            def source_id(self):
                return "infinite"

            async def connect(self):
                pass

            async def read(self):
                await asyncio.sleep(0.005)
                return ReadResult(ReadStatus.FRAME, _frame())

            def close(self):
                pass

        svc, _ = _service(InfiniteConnector())
        task = asyncio.create_task(svc.run())
        await asyncio.sleep(0.05)
        svc.stop()
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done(), "Service did not stop within timeout"

    async def test_connector_closed_after_stop(self):
        connector = FakeConnector([ReadResult(ReadStatus.FRAME, _frame())])
        svc, _ = _service(connector)
        await svc.run()
        assert connector.close_calls == 1


class TestServiceMetrics:
    async def test_frames_received_counted(self):
        results = [ReadResult(ReadStatus.FRAME, _frame()) for _ in range(3)]
        connector = FakeConnector(results)
        svc, _ = _service(connector)
        await svc.run()
        assert svc.metrics.frames_received_total == 3

    async def test_frames_sampled_counted(self):
        results = [ReadResult(ReadStatus.FRAME, _frame()) for _ in range(3)]
        connector = FakeConnector(results)
        svc, _ = _service(connector)
        await svc.run()
        assert svc.metrics.frames_sampled_total == 3

    async def test_stream_not_connected_after_run(self):
        connector = FakeConnector([])
        svc, _ = _service(connector)
        await svc.run()
        assert svc.metrics.stream_connected is False
