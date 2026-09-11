"""Tests for RTSPConnector."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from backend.app.ingestion.connectors.base import ReadStatus
from backend.app.ingestion.connectors.rtsp import RTSPConnector, _mask_url


class TestMaskUrl:
    def test_strips_credentials(self):
        assert _mask_url("rtsp://user:pass@192.168.1.1/stream") == "rtsp://***@192.168.1.1/stream"

    def test_url_without_credentials_unchanged(self):
        assert _mask_url("rtsp://192.168.1.1/stream") == "rtsp://192.168.1.1/stream"


def _make_connector(**kwargs) -> RTSPConnector:
    return RTSPConnector(
        url="rtsp://user:pass@host/stream",
        camera_id="cam-01",
        initial_delay_seconds=0.01,
        max_delay_seconds=0.04,
        **kwargs,
    )


class TestRTSPConnectorSourceId:
    def test_source_id_masks_credentials(self):
        c = _make_connector()
        assert "pass" not in c.source_id
        assert "user" not in c.source_id


class TestRTSPConnectorConnect:
    async def test_successful_connect(self):
        connector = _make_connector()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        with patch("cv2.VideoCapture", return_value=mock_cap):
            await connector.connect()

        assert connector._cap is mock_cap

    async def test_connect_retries_until_success(self):
        connector = _make_connector()
        fail_cap = MagicMock()
        fail_cap.isOpened.return_value = False
        ok_cap = MagicMock()
        ok_cap.isOpened.return_value = True

        caps = [fail_cap, fail_cap, ok_cap]

        with patch("cv2.VideoCapture", side_effect=caps), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await connector.connect()

        assert connector._cap is ok_cap


class TestRTSPConnectorRead:
    async def test_successful_read_returns_frame(self):
        connector = _make_connector()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.read.return_value = (True, frame)
        connector._cap = mock_cap

        result = await connector.read()
        assert result.status == ReadStatus.FRAME
        assert result.frame is frame

    async def test_failed_read_returns_temporary_failure(self):
        connector = _make_connector()
        mock_cap = MagicMock()
        mock_cap.read.return_value = (False, None)
        connector._cap = mock_cap

        result = await connector.read()
        assert result.status == ReadStatus.TEMPORARY_FAILURE
        assert result.frame is None

    async def test_read_without_connect_returns_temporary_failure(self):
        connector = _make_connector()
        result = await connector.read()
        assert result.status == ReadStatus.TEMPORARY_FAILURE


class TestRTSPConnectorReconnect:
    async def test_reconnect_succeeds_after_one_retry(self):
        connector = _make_connector()
        stop = asyncio.Event()

        fail_cap = MagicMock()
        fail_cap.isOpened.return_value = False
        ok_cap = MagicMock()
        ok_cap.isOpened.return_value = True

        with patch("cv2.VideoCapture", side_effect=[fail_cap, ok_cap]), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await connector.reconnect(stop)

        assert result is True
        assert connector._cap is ok_cap

    async def test_reconnect_returns_false_when_stop_set(self):
        connector = _make_connector()
        stop = asyncio.Event()
        stop.set()

        result = await connector.reconnect(stop)
        assert result is False

    async def test_reconnect_stops_when_stop_set_during_sleep(self):
        connector = _make_connector()
        stop = asyncio.Event()

        fail_cap = MagicMock()
        fail_cap.isOpened.return_value = False

        call_count = 0

        async def fake_sleep(delay):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                stop.set()

        with patch("cv2.VideoCapture", return_value=fail_cap), \
             patch("asyncio.sleep", side_effect=fake_sleep):
            result = await connector.reconnect(stop)

        assert result is False

    async def test_reconnect_closes_existing_cap(self):
        connector = _make_connector()
        old_cap = MagicMock()
        connector._cap = old_cap
        stop = asyncio.Event()
        stop.set()  # stop immediately

        await connector.reconnect(stop)
        old_cap.release.assert_called_once()

    async def test_backoff_increases_exponentially(self):
        connector = _make_connector(initial_delay_seconds=1.0, max_delay_seconds=8.0)
        stop = asyncio.Event()
        delays_seen = []

        fail_cap = MagicMock()
        fail_cap.isOpened.return_value = False
        ok_cap = MagicMock()
        ok_cap.isOpened.return_value = True

        caps = [fail_cap, fail_cap, fail_cap, ok_cap]

        async def fake_sleep(delay):
            delays_seen.append(delay)

        with patch("cv2.VideoCapture", side_effect=caps), \
             patch("asyncio.sleep", side_effect=fake_sleep):
            await connector.reconnect(stop)

        assert delays_seen == [1.0, 2.0, 4.0]

    async def test_backoff_caps_at_max_delay(self):
        connector = _make_connector(initial_delay_seconds=1.0, max_delay_seconds=3.0)
        stop = asyncio.Event()
        delays_seen = []

        fail_cap = MagicMock()
        fail_cap.isOpened.return_value = False
        ok_cap = MagicMock()
        ok_cap.isOpened.return_value = True

        caps = [fail_cap, fail_cap, fail_cap, fail_cap, ok_cap]

        async def fake_sleep(delay):
            delays_seen.append(delay)

        with patch("cv2.VideoCapture", side_effect=caps), \
             patch("asyncio.sleep", side_effect=fake_sleep):
            await connector.reconnect(stop)

        assert delays_seen[-1] == 3.0


class TestRTSPConnectorClose:
    def test_close_releases_cap(self):
        connector = _make_connector()
        mock_cap = MagicMock()
        connector._cap = mock_cap
        connector.close()
        mock_cap.release.assert_called_once()
        assert connector._cap is None

    def test_close_is_idempotent(self):
        connector = _make_connector()
        connector.close()  # _cap is None — should not raise
