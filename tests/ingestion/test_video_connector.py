"""Tests for VideoConnector."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.app.ingestion.connectors.base import ReadStatus
from backend.app.ingestion.connectors.video import VideoConnector


def _make_connector(path, **kwargs) -> VideoConnector:
    return VideoConnector(path=path, camera_id="cam-01", **kwargs)


class TestVideoConnectorInit:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _make_connector(tmp_path / "nope.mp4")

    def test_existing_file_does_not_raise(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"")
        connector = _make_connector(f)
        assert connector.source_id == "v.mp4"


class TestVideoConnectorConnect:
    async def test_connect_opens_capture(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"")
        connector = _make_connector(f)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0

        with patch("cv2.VideoCapture", return_value=mock_cap):
            await connector.connect()

        assert connector._cap is mock_cap
        assert connector.native_fps == 30.0

    async def test_connect_raises_when_capture_fails(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"")
        connector = _make_connector(f)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False

        with patch("cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(RuntimeError, match="Cannot open video file"):
                await connector.connect()

        assert connector._cap is None


class TestVideoConnectorRead:
    def _connected_connector(self, tmp_path, read_returns) -> VideoConnector:
        f = tmp_path / "v.mp4"
        f.write_bytes(b"")
        connector = VideoConnector(
            path=f,
            camera_id="cam-01",
            playback_mode="realtime",
        )
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0
        mock_cap.read.side_effect = read_returns
        connector._cap = mock_cap
        connector._last_read_at = 0.0  # skip throttle on first read
        return connector

    async def test_successful_read_returns_frame(self, tmp_path):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        connector = self._connected_connector(tmp_path, [(True, frame)])
        result = await connector.read()
        assert result.status == ReadStatus.FRAME
        assert result.frame is frame

    async def test_eof_returns_end_of_stream(self, tmp_path):
        connector = self._connected_connector(tmp_path, [(False, None)])
        result = await connector.read()
        assert result.status == ReadStatus.END_OF_STREAM

    def test_close_releases_capture(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"")
        connector = _make_connector(f)
        mock_cap = MagicMock()
        connector._cap = mock_cap
        connector.close()
        mock_cap.release.assert_called_once()
        assert connector._cap is None

    def test_close_is_idempotent(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"")
        connector = _make_connector(f)
        connector.close()  # _cap is None — should not raise
