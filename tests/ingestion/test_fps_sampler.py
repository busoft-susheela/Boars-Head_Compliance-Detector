"""Tests for FpsSampler."""

from unittest.mock import patch

import pytest

from backend.app.ingestion.sampling.fps_sampler import FpsSampler


class TestFpsSamplerInit:
    def test_zero_fps_raises(self):
        with pytest.raises(ValueError):
            FpsSampler(0)

    def test_negative_fps_raises(self):
        with pytest.raises(ValueError):
            FpsSampler(-1)

    def test_valid_fps_accepted(self):
        s = FpsSampler(5.0)
        assert s.target_fps == pytest.approx(5.0)


class TestFpsSamplerShouldProcess:
    def test_first_call_always_passes(self):
        s = FpsSampler(5.0)
        with patch("time.monotonic", return_value=0.0):
            assert s.should_process() is True

    def test_second_call_too_soon_blocked(self):
        s = FpsSampler(5.0)  # interval = 0.2 s
        times = iter([0.0, 0.05])
        with patch("time.monotonic", side_effect=times):
            s.should_process()  # first — passes
            assert s.should_process() is False

    def test_second_call_after_interval_passes(self):
        s = FpsSampler(5.0)  # interval = 0.2 s
        times = iter([0.0, 0.21])
        with patch("time.monotonic", side_effect=times):
            s.should_process()
            assert s.should_process() is True

    def test_target_fps_respected_over_multiple_frames(self):
        s = FpsSampler(2.0)  # interval = 0.5 s
        accepted = 0
        for i in range(10):
            t = i * 0.1  # 10 Hz source
            with patch("time.monotonic", return_value=t):
                if s.should_process():
                    accepted += 1
        # At 10 Hz source, 2 Hz target over 1 second → ~2 frames accepted
        assert accepted == 2
