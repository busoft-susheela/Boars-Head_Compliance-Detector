"""Unit tests for Redis serialization (no Redis required).

All round-trip tests: serialize → deserialize must reproduce the original object.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from backend.app.compliance.events import ComplianceEvent, EvidenceCaptureEvent
from backend.app.compliance.evidence.models import EvidenceItem, EvidencePayload
from backend.app.inference.models.detection import BoundingBox, Detection, DetectionEvent
from backend.app.ingestion.models.frame_envelope import FrameEnvelope
from backend.app.infrastructure.redis.serialization import (
    SCHEMA_VERSION,
    deserialize,
    serialize,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _frame_envelope() -> FrameEnvelope:
    return FrameEnvelope(
        camera_id="cam-01",
        frame_id=7,
        captured_at=_NOW,
        received_at=_NOW,
        topic="ingestion.frames",
    )


def _detection_event(with_thumbnail: bool = False) -> DetectionEvent:
    thumbnail = b"\xff\xd8\xff\xe0" if with_thumbnail else None
    return DetectionEvent(
        camera_id="cam-01",
        zone_id="zone-A",
        frame_id=7,
        captured_at=_NOW,
        processed_at=_NOW,
        detections=(
            Detection(
                class_id=0,
                class_name="handwash",
                confidence=0.95,
                use_case="handwash",
                bbox=BoundingBox(x1=0.1, y1=0.2, x2=0.8, y2=0.9),
            ),
        ),
        thumbnail=thumbnail,
    )


def _compliance_event() -> ComplianceEvent:
    return ComplianceEvent(
        camera_id="cam-01",
        zone_id="zone-A",
        person_id=3,
        timestamp=_NOW,
        outcome="VIOLATION",
        rule_name="handwash_duration",
        group_id="grp-abc",
    )


def _evidence_capture_event() -> EvidenceCaptureEvent:
    item = EvidenceItem(
        frame_id=10,
        timestamp=_NOW,
        thumbnail=b"\xff\xd8",
        camera_id="cam-01",
        zone_id="zone-A",
        person_id=3,
    )
    payload = EvidencePayload(
        group_id="grp-abc",
        camera_id="cam-01",
        zone_id="zone-A",
        items=(item,),
    )
    return EvidenceCaptureEvent(
        group_id="grp-abc",
        camera_id="cam-01",
        zone_id="zone-A",
        payload=payload,
        timestamp=_NOW,
    )


# ---------------------------------------------------------------------------
# serialize() — structural tests
# ---------------------------------------------------------------------------


class TestSerializeStructure:
    def test_schema_version_present(self):
        data = serialize("ingestion.frames", _frame_envelope())
        payload = json.loads(data)
        assert payload["schema_version"] == SCHEMA_VERSION

    def test_event_type_frame(self):
        data = serialize("ingestion.frames", _frame_envelope())
        assert json.loads(data)["event_type"] == "frame.ingested"

    def test_event_type_detection(self):
        data = serialize("inference.detections", _detection_event())
        assert json.loads(data)["event_type"] == "detection.created"

    def test_event_type_compliance(self):
        data = serialize("compliance.alert", _compliance_event())
        assert json.loads(data)["event_type"] == "compliance.alert"

    def test_event_type_evidence(self):
        data = serialize("evidence.capture", _evidence_capture_event())
        assert json.loads(data)["event_type"] == "evidence.capture"

    def test_unknown_topic_raises(self):
        with pytest.raises(KeyError):
            serialize("unknown.topic", object())

    def test_output_is_bytes(self):
        data = serialize("ingestion.frames", _frame_envelope())
        assert isinstance(data, bytes)


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_frame_envelope(self):
        original = _frame_envelope()
        data = serialize("ingestion.frames", original)
        result = deserialize("ingestion.frames", data)
        assert result is not None
        assert result.camera_id == original.camera_id
        assert result.frame_id == original.frame_id
        assert result.captured_at == original.captured_at
        assert result.received_at == original.received_at
        assert result.topic == original.topic

    def test_detection_event_no_thumbnail(self):
        original = _detection_event(with_thumbnail=False)
        result = deserialize("inference.detections", serialize("inference.detections", original))
        assert result is not None
        assert result.camera_id == original.camera_id
        assert result.frame_id == original.frame_id
        assert result.thumbnail is None
        assert len(result.detections) == 1
        d = result.detections[0]
        assert d.class_name == "handwash"
        assert abs(d.confidence - 0.95) < 1e-6
        assert abs(d.bbox.x1 - 0.1) < 1e-9

    def test_detection_event_with_thumbnail(self):
        original = _detection_event(with_thumbnail=True)
        result = deserialize("inference.detections", serialize("inference.detections", original))
        assert result is not None
        assert result.thumbnail == original.thumbnail

    def test_compliance_event(self):
        original = _compliance_event()
        result = deserialize("compliance.alert", serialize("compliance.alert", original))
        assert result is not None
        assert result.person_id == 3
        assert result.outcome == "VIOLATION"
        assert result.group_id == "grp-abc"
        assert result.timestamp == original.timestamp

    def test_evidence_capture_event(self):
        original = _evidence_capture_event()
        result = deserialize("evidence.capture", serialize("evidence.capture", original))
        assert result is not None
        assert result.group_id == original.group_id
        assert len(result.payload.items) == 1
        item = result.payload.items[0]
        assert item.frame_id == 10
        assert item.thumbnail == b"\xff\xd8"
        assert item.person_id == 3

    def test_datetime_round_trips_with_tzinfo(self):
        original = _frame_envelope()
        result = deserialize("ingestion.frames", serialize("ingestion.frames", original))
        assert result.captured_at.tzinfo is not None

    def test_no_thumbnail_round_trips_as_none(self):
        original = _detection_event(with_thumbnail=False)
        result = deserialize("inference.detections", serialize("inference.detections", original))
        assert result.thumbnail is None


# ---------------------------------------------------------------------------
# deserialize() — error handling
# ---------------------------------------------------------------------------


class TestDeserializeErrors:
    def test_invalid_json_returns_none(self):
        result = deserialize("ingestion.frames", b"not-json")
        assert result is None

    def test_unknown_event_type_returns_none(self):
        payload = json.dumps({"schema_version": 1, "event_type": "unknown.type"})
        result = deserialize("ingestion.frames", payload.encode())
        assert result is None

    def test_malformed_payload_returns_none(self):
        # Valid JSON but missing required fields for the decoder.
        payload = json.dumps({"schema_version": 1, "event_type": "frame.ingested"})
        result = deserialize("ingestion.frames", payload.encode())
        assert result is None
