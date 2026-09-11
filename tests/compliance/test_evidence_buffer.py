"""Tests for EvidenceBuffer lifecycle: add, evict, discard, freeze."""

from datetime import datetime, timezone

import pytest

from backend.app.compliance.evidence.buffer import EvidenceBuffer
from backend.app.compliance.evidence.models import EvidenceItem, EvidencePayload

_T0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

_THUMB = b"\xff\xd8\xff\xe0" + b"\x00" * 10  # fake JPEG header


def _item(frame_id: int = 1) -> EvidenceItem:
    return EvidenceItem(
        frame_id=frame_id,
        timestamp=_T0,
        thumbnail=_THUMB,
        camera_id="cam01",
        zone_id="zone_a",
        person_id=7,
    )


def _buf(max_items: int = 5) -> EvidenceBuffer:
    return EvidenceBuffer(
        max_items=max_items,
        group_id="g-001",
        camera_id="cam01",
        zone_id="zone_a",
    )


# ── Construction ─────────────────────────────────────────────────────────────

def test_invalid_max_items_raises():
    with pytest.raises(ValueError):
        EvidenceBuffer(max_items=0, group_id="g", camera_id="c", zone_id="z")


# ── Add ───────────────────────────────────────────────────────────────────────

def test_empty_buffer_after_construction():
    buf = _buf()
    assert buf.size == 0
    assert not buf.frozen


def test_single_add():
    buf = _buf()
    buf.add(_item(1))
    assert buf.size == 1


def test_multiple_adds():
    buf = _buf(max_items=3)
    for i in range(3):
        buf.add(_item(i))
    assert buf.size == 3


def test_ring_buffer_evicts_oldest():
    buf = _buf(max_items=3)
    buf.add(_item(10))
    buf.add(_item(20))
    buf.add(_item(30))
    buf.add(_item(40))  # evicts frame_id=10
    assert buf.size == 3
    payload = buf.freeze()
    frame_ids = [e.frame_id for e in payload.items]
    assert 10 not in frame_ids
    assert 40 in frame_ids


def test_buffer_never_exceeds_max(max_items=5):
    buf = _buf(max_items=max_items)
    for i in range(20):
        buf.add(_item(i))
    assert buf.size <= max_items


# ── Discard ───────────────────────────────────────────────────────────────────

def test_discard_clears_items():
    buf = _buf()
    buf.add(_item(1))
    buf.add(_item(2))
    buf.discard()
    assert buf.size == 0


def test_discard_allows_continued_use():
    """After discard the buffer is NOT frozen — it can still be re-used by caller
    if desired (though the caller typically discards the buffer object itself)."""
    buf = _buf()
    buf.add(_item(1))
    buf.discard()
    assert not buf.frozen


# ── Freeze ────────────────────────────────────────────────────────────────────

def test_freeze_returns_evidence_payload():
    buf = _buf()
    buf.add(_item(1))
    payload = buf.freeze()
    assert isinstance(payload, EvidencePayload)
    assert payload.group_id == "g-001"
    assert payload.camera_id == "cam01"
    assert payload.zone_id == "zone_a"


def test_freeze_payload_is_immutable_tuple():
    buf = _buf()
    buf.add(_item(1))
    payload = buf.freeze()
    assert isinstance(payload.items, tuple)


def test_frozen_buffer_rejects_add():
    buf = _buf()
    buf.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        buf.add(_item(1))


def test_freeze_marks_frozen():
    buf = _buf()
    buf.freeze()
    assert buf.frozen


def test_freeze_captures_all_items():
    buf = _buf(max_items=5)
    for i in range(3):
        buf.add(_item(i + 1))
    payload = buf.freeze()
    assert len(payload.items) == 3
    frame_ids = {e.frame_id for e in payload.items}
    assert frame_ids == {1, 2, 3}
