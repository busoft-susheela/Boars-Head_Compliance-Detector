"""Tests for InMemoryStateStore and make_state_key."""

import pytest

from backend.app.infrastructure.state_store.base import StateStore, make_state_key
from backend.app.infrastructure.state_store.in_memory import InMemoryStateStore


# ── make_state_key ───────────────────────────────────────────────────────────

def test_make_state_key_format():
    key = make_state_key("cam01", "zone_a")
    assert key == "cam01:zone_a"


def test_make_state_key_different_cameras_same_zone():
    assert make_state_key("cam01", "zone_a") != make_state_key("cam02", "zone_a")


def test_make_state_key_same_camera_different_zones():
    assert make_state_key("cam01", "zone_a") != make_state_key("cam01", "zone_b")


# ── InMemoryStateStore ───────────────────────────────────────────────────────

class TestInMemoryStateStore:
    def test_is_state_store(self):
        store = InMemoryStateStore()
        assert isinstance(store, StateStore)

    def test_get_missing_key_returns_none(self):
        store = InMemoryStateStore()
        assert store.get("nonexistent") is None

    def test_set_and_get_roundtrip(self):
        store = InMemoryStateStore()
        store.set("k1", {"foo": "bar"})
        result = store.get("k1")
        assert result == {"foo": "bar"}

    def test_overwrite(self):
        store = InMemoryStateStore()
        store.set("k1", {"v": 1})
        store.set("k1", {"v": 2})
        assert store.get("k1") == {"v": 2}

    def test_defensive_copy_on_get(self):
        """Mutating the returned dict must not affect stored state."""
        store = InMemoryStateStore()
        store.set("k1", {"v": 1})
        result = store.get("k1")
        result["v"] = 999
        assert store.get("k1") == {"v": 1}

    def test_defensive_copy_on_set(self):
        """Mutating the dict after set must not affect stored state."""
        store = InMemoryStateStore()
        d = {"v": 1}
        store.set("k1", d)
        d["v"] = 999
        assert store.get("k1") == {"v": 1}

    def test_multiple_keys_isolated(self):
        store = InMemoryStateStore()
        store.set(make_state_key("cam01", "zone_a"), {"persons": {}})
        store.set(make_state_key("cam01", "zone_b"), {"persons": {"7": {}}})
        store.set(make_state_key("cam02", "zone_a"), {"persons": {"1": {}}})

        assert store.get(make_state_key("cam01", "zone_a")) == {"persons": {}}
        assert store.get(make_state_key("cam01", "zone_b")) == {"persons": {"7": {}}}
        assert store.get(make_state_key("cam02", "zone_a")) == {"persons": {"1": {}}}

    def test_close_clears_state(self):
        store = InMemoryStateStore()
        store.set("k1", {"v": 1})
        store.close()
        with pytest.raises(RuntimeError, match="closed"):
            store.get("k1")

    def test_set_after_close_raises(self):
        store = InMemoryStateStore()
        store.close()
        with pytest.raises(RuntimeError, match="closed"):
            store.set("k1", {})
