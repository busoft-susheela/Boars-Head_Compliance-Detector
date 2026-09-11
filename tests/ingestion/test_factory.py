"""Tests for ConnectorFactory (create_connector)."""

import pytest

from backend.app.ingestion.connectors.rtsp import RTSPConnector
from backend.app.ingestion.connectors.video import VideoConnector
from backend.app.ingestion.factory import create_connector


def _video_cfg(path: str = "/tmp/v.mp4", **overrides) -> dict:
    cfg = {
        "type": "video",
        "camera_id": "cam-01",
        "video": {"path": path},
    }
    cfg.update(overrides)
    return cfg


def _rtsp_cfg(url: str = "rtsp://host/stream", **overrides) -> dict:
    cfg = {
        "type": "rtsp",
        "camera_id": "cam-01",
        "rtsp": {"url": url},
    }
    cfg.update(overrides)
    return cfg


class TestConnectorFactory:
    def test_video_type_returns_video_connector(self, tmp_path):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"")
        connector = create_connector(_video_cfg(path=str(video_file)))
        assert isinstance(connector, VideoConnector)

    def test_rtsp_type_returns_rtsp_connector(self):
        connector = create_connector(_rtsp_cfg())
        assert isinstance(connector, RTSPConnector)

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="stream.type must be one of"):
            create_connector({"type": "kafka", "camera_id": "cam"})

    def test_none_type_raises(self):
        with pytest.raises(ValueError, match="stream.type must be one of"):
            create_connector({"camera_id": "cam"})

    def test_video_missing_path_raises(self):
        with pytest.raises(ValueError, match="stream.video.path is required"):
            create_connector({"type": "video", "camera_id": "cam", "video": {}})

    def test_video_missing_video_section_raises(self):
        with pytest.raises(ValueError, match="stream.video.path is required"):
            create_connector({"type": "video", "camera_id": "cam"})

    def test_rtsp_missing_url_raises(self):
        with pytest.raises(ValueError, match="stream.rtsp.url is required"):
            create_connector({"type": "rtsp", "camera_id": "cam", "rtsp": {}})

    def test_rtsp_missing_rtsp_section_raises(self):
        with pytest.raises(ValueError, match="stream.rtsp.url is required"):
            create_connector({"type": "rtsp", "camera_id": "cam"})

    def test_reconnect_config_forwarded_to_rtsp(self):
        connector = create_connector(
            _rtsp_cfg(reconnect={"initial_delay_seconds": 2.0, "max_delay_seconds": 30.0})
        )
        assert isinstance(connector, RTSPConnector)
        assert connector._initial_delay == 2.0
        assert connector._max_delay == 30.0

    def test_video_playback_mode_forwarded(self, tmp_path):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"")
        connector = create_connector(
            {
                "type": "video",
                "camera_id": "cam",
                "video": {"path": str(video_file), "playback_mode": "realtime"},
            }
        )
        assert isinstance(connector, VideoConnector)
        assert connector._playback_mode == "realtime"
