"""Unit tests for StaticModelResolver — configuration-driven model resolution."""

import pytest

from backend.app.inference.resolver.static import StaticModelResolver


# ---------------------------------------------------------------------------
# Test configuration helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> dict:
    """Minimal valid config that exercises the resolver."""
    base = {
        "models": {
            "handwashing": {
                "use_case": "handwashing",
                "path": "artifacts/yolo11n.pt",
                "confidence": 0.5,
                "device": "cpu",
                "image_size": 640,
            },
            "ppe": {
                "use_case": "ppe",
                "path": "artifacts/ppe.pt",
                "confidence": 0.6,
                "device": "cpu",
                "image_size": 640,
            },
        },
        "zones": {
            "handwash_zone": {"models": ["handwashing"]},
            "entry_zone": {"models": ["ppe"]},
            "multi_zone": {"models": ["handwashing", "ppe"]},
            "empty_zone": {"models": []},
        },
        "cameras": {
            "cam-01": {"zones": ["handwash_zone"]},
            "cam-02": {"zones": ["entry_zone", "multi_zone"]},
        },
    }
    base.update(overrides)
    return base


class TestResolveSuccess:
    def test_single_model_zone(self):
        resolver = StaticModelResolver(_make_config())
        specs = resolver.resolve("cam-01", "handwash_zone")
        assert len(specs) == 1
        assert specs[0].use_case == "handwashing"

    def test_ppe_zone(self):
        resolver = StaticModelResolver(_make_config())
        specs = resolver.resolve("cam-02", "entry_zone")
        assert len(specs) == 1
        assert specs[0].use_case == "ppe"

    def test_multi_model_zone(self):
        resolver = StaticModelResolver(_make_config())
        specs = resolver.resolve("cam-02", "multi_zone")
        assert len(specs) == 2
        use_cases = {s.use_case for s in specs}
        assert "handwashing" in use_cases
        assert "ppe" in use_cases

    def test_model_ordering_preserved(self):
        resolver = StaticModelResolver(_make_config())
        specs = resolver.resolve("cam-02", "multi_zone")
        assert specs[0].use_case == "handwashing"
        assert specs[1].use_case == "ppe"

    def test_empty_zone_returns_empty_list(self):
        resolver = StaticModelResolver(_make_config())
        specs = resolver.resolve("cam-01", "empty_zone")
        assert specs == []

    def test_confidence_threshold_set_correctly(self):
        resolver = StaticModelResolver(_make_config())
        specs = resolver.resolve("cam-01", "handwash_zone")
        assert specs[0].confidence_threshold == 0.5

    def test_returns_defensive_copy(self):
        resolver = StaticModelResolver(_make_config())
        specs_a = resolver.resolve("cam-01", "handwash_zone")
        specs_b = resolver.resolve("cam-01", "handwash_zone")
        assert specs_a is not specs_b
        assert specs_a == specs_b


class TestResolveErrors:
    def test_unknown_camera_raises(self):
        resolver = StaticModelResolver(_make_config())
        with pytest.raises(KeyError, match="cam-99"):
            resolver.resolve("cam-99", "handwash_zone")

    def test_unknown_zone_raises(self):
        resolver = StaticModelResolver(_make_config())
        with pytest.raises(KeyError, match="unknown_zone"):
            resolver.resolve("cam-01", "unknown_zone")


class TestZonesForCamera:
    def test_single_zone_camera(self):
        resolver = StaticModelResolver(_make_config())
        zones = resolver.zones_for_camera("cam-01")
        assert zones == ["handwash_zone"]

    def test_multi_zone_camera(self):
        resolver = StaticModelResolver(_make_config())
        zones = resolver.zones_for_camera("cam-02")
        assert "entry_zone" in zones
        assert "multi_zone" in zones

    def test_unknown_camera_raises(self):
        resolver = StaticModelResolver(_make_config())
        with pytest.raises(KeyError):
            resolver.zones_for_camera("cam-99")


class TestConfigValidation:
    def test_no_models_raises(self):
        cfg = _make_config()
        del cfg["models"]
        with pytest.raises(ValueError, match="models"):
            StaticModelResolver(cfg)

    def test_no_zones_raises(self):
        cfg = _make_config()
        del cfg["zones"]
        with pytest.raises(ValueError, match="zones"):
            StaticModelResolver(cfg)

    def test_no_cameras_raises(self):
        cfg = _make_config()
        del cfg["cameras"]
        with pytest.raises(ValueError, match="cameras"):
            StaticModelResolver(cfg)

    def test_zone_references_undefined_model_raises(self):
        cfg = _make_config()
        cfg["zones"]["bad_zone"] = {"models": ["nonexistent"]}
        with pytest.raises(KeyError, match="nonexistent"):
            StaticModelResolver(cfg)


class TestDeduplication:
    def test_duplicate_model_in_zone_is_deduplicated(self):
        cfg = _make_config()
        cfg["zones"]["dup_zone"] = {"models": ["handwashing", "handwashing"]}
        cfg["cameras"]["cam-01"]["zones"].append("dup_zone")
        resolver = StaticModelResolver(cfg)
        specs = resolver.resolve("cam-01", "dup_zone")
        # Same model path should appear only once
        paths = [s.model_path for s in specs]
        assert len(paths) == len(set(paths))
