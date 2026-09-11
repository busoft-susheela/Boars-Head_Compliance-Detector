"""Message serialization for Redis Streams.

Design rules (from redisstream.md §20-21)
------------------------------------------
- No pickle.  JSON only.
- Every message carries ``schema_version`` (int) and ``event_type`` (str).
- ``datetime`` objects are serialized as ISO-8601 UTC strings.
- ``bytes`` (thumbnails) are base64-encoded.
- Invalid messages are logged and NOT re-raised; callers receive ``None``
  so the worker can ACK-and-skip rather than crash.
- Serialization is deterministic and fully testable without Redis.

Supported message types
------------------------
| Topic                 | Python type          |
|-----------------------|----------------------|
| ingestion.frames      | FrameEnvelope        |
| inference.detections  | DetectionEvent       |
| compliance.alert      | ComplianceEvent      |
| evidence.capture      | EvidenceCaptureEvent |

All messages are stored as a single JSON string in the Redis stream field
``data``.  Using one field keeps deserialization simple and avoids partial-
update race conditions when writing multiple fields atomically.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from backend.app.compliance.events import ComplianceEvent, EvidenceCaptureEvent
from backend.app.compliance.evidence.models import EvidenceItem, EvidencePayload
from backend.app.inference.models.detection import BoundingBox, Detection, DetectionEvent
from backend.app.ingestion.models.frame_envelope import FrameEnvelope

logger = structlog.get_logger(__name__)

SCHEMA_VERSION = 1

# Mapping from application topic → event_type string
_TOPIC_TO_EVENT_TYPE: dict[str, str] = {
    "ingestion.frames": "frame.ingested",
    "inference.detections": "detection.created",
    "compliance.alert": "compliance.alert",
    "evidence.capture": "evidence.capture",
}


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _dt_to_str(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _bytes_to_b64(b: bytes | None) -> str | None:
    if b is None:
        return None
    return base64.b64encode(b).decode("ascii")


def _b64_to_bytes(s: str | None) -> bytes | None:
    if s is None:
        return None
    return base64.b64decode(s)


# ── Encoders (Python → dict) ──────────────────────────────────────────────────

def _encode_frame_envelope(obj: FrameEnvelope) -> dict:
    return {
        "camera_id": obj.camera_id,
        "frame_id": obj.frame_id,
        "captured_at": _dt_to_str(obj.captured_at),
        "received_at": _dt_to_str(obj.received_at),
        "topic": obj.topic,
        "correlation_id": obj.correlation_id,
        "session_id": obj.session_id,
        "source_fps": obj.source_fps,
    }


def _encode_detection(d: Detection) -> dict:
    return {
        "class_id": d.class_id,
        "class_name": d.class_name,
        "confidence": d.confidence,
        "use_case": d.use_case,
        "bbox": {"x1": d.bbox.x1, "y1": d.bbox.y1, "x2": d.bbox.x2, "y2": d.bbox.y2},
    }


def _encode_detection_event(obj: DetectionEvent) -> dict:
    return {
        "camera_id": obj.camera_id,
        "zone_id": obj.zone_id,
        "frame_id": obj.frame_id,
        "captured_at": _dt_to_str(obj.captured_at),
        "processed_at": _dt_to_str(obj.processed_at),
        "detections": [_encode_detection(d) for d in obj.detections],
        "thumbnail": _bytes_to_b64(obj.thumbnail),
        "correlation_id": obj.correlation_id,
        "source_fps": obj.source_fps,
    }


def _encode_compliance_event(obj: ComplianceEvent) -> dict:
    return {
        "camera_id": obj.camera_id,
        "zone_id": obj.zone_id,
        "person_id": obj.person_id,
        "timestamp": _dt_to_str(obj.timestamp),
        "outcome": obj.outcome,
        "rule_name": obj.rule_name,
        "group_id": obj.group_id,
    }


def _encode_evidence_item(item: EvidenceItem) -> dict:
    return {
        "frame_id": item.frame_id,
        "timestamp": _dt_to_str(item.timestamp),
        "thumbnail": _bytes_to_b64(item.thumbnail),
        "camera_id": item.camera_id,
        "zone_id": item.zone_id,
        "person_id": item.person_id,
    }


def _encode_evidence_capture_event(obj: EvidenceCaptureEvent) -> dict:
    return {
        "group_id": obj.group_id,
        "camera_id": obj.camera_id,
        "zone_id": obj.zone_id,
        "timestamp": _dt_to_str(obj.timestamp),
        "payload": {
            "group_id": obj.payload.group_id,
            "camera_id": obj.payload.camera_id,
            "zone_id": obj.payload.zone_id,
            "items": [_encode_evidence_item(i) for i in obj.payload.items],
        },
    }


# ── Decoders (dict → Python) ──────────────────────────────────────────────────

def _decode_frame_envelope(data: dict) -> FrameEnvelope:
    return FrameEnvelope(
        camera_id=data["camera_id"],
        frame_id=int(data["frame_id"]),
        captured_at=_str_to_dt(data["captured_at"]),
        received_at=_str_to_dt(data["received_at"]),
        topic=data["topic"],
        correlation_id=data.get("correlation_id", ""),
        session_id=data.get("session_id", ""),
        source_fps=float(data.get("source_fps", 0.0)),
    )


def _decode_detection(d: dict) -> Detection:
    bbox = BoundingBox(**d["bbox"])
    return Detection(
        class_id=int(d["class_id"]),
        class_name=d["class_name"],
        confidence=float(d["confidence"]),
        use_case=d["use_case"],
        bbox=bbox,
    )


def _decode_detection_event(data: dict) -> DetectionEvent:
    return DetectionEvent(
        camera_id=data["camera_id"],
        zone_id=data["zone_id"],
        frame_id=int(data["frame_id"]),
        captured_at=_str_to_dt(data["captured_at"]),
        processed_at=_str_to_dt(data["processed_at"]),
        detections=tuple(_decode_detection(d) for d in data["detections"]),
        thumbnail=_b64_to_bytes(data.get("thumbnail")),
        correlation_id=data.get("correlation_id", ""),
        source_fps=float(data.get("source_fps", 0.0)),
    )


def _decode_compliance_event(data: dict) -> ComplianceEvent:
    return ComplianceEvent(
        camera_id=data["camera_id"],
        zone_id=data["zone_id"],
        person_id=int(data["person_id"]),
        timestamp=_str_to_dt(data["timestamp"]),
        outcome=data["outcome"],
        rule_name=data["rule_name"],
        group_id=data["group_id"],
    )


def _decode_evidence_item(d: dict) -> EvidenceItem:
    return EvidenceItem(
        frame_id=int(d["frame_id"]),
        timestamp=_str_to_dt(d["timestamp"]),
        thumbnail=_b64_to_bytes(d.get("thumbnail")),
        camera_id=d["camera_id"],
        zone_id=d["zone_id"],
        person_id=int(d["person_id"]),
    )


def _decode_evidence_capture_event(data: dict) -> EvidenceCaptureEvent:
    payload_raw = data["payload"]
    payload = EvidencePayload(
        group_id=payload_raw["group_id"],
        camera_id=payload_raw["camera_id"],
        zone_id=payload_raw["zone_id"],
        items=tuple(_decode_evidence_item(i) for i in payload_raw["items"]),
    )
    return EvidenceCaptureEvent(
        group_id=data["group_id"],
        camera_id=data["camera_id"],
        zone_id=data["zone_id"],
        payload=payload,
        timestamp=_str_to_dt(data["timestamp"]),
    )


# ── Public API ────────────────────────────────────────────────────────────────

_ENCODERS = {
    "frame.ingested": _encode_frame_envelope,
    "detection.created": _encode_detection_event,
    "compliance.alert": _encode_compliance_event,
    "evidence.capture": _encode_evidence_capture_event,
}

_DECODERS = {
    "frame.ingested": _decode_frame_envelope,
    "detection.created": _decode_detection_event,
    "compliance.alert": _decode_compliance_event,
    "evidence.capture": _decode_evidence_capture_event,
}


def serialize(topic: str, message: Any) -> bytes:
    """Serialize a domain message to JSON bytes for a Redis stream field.

    Args:
        topic:   Application topic name (e.g. ``"ingestion.frames"``).
        message: Domain dataclass instance.

    Returns:
        UTF-8 JSON bytes including ``schema_version`` and ``event_type``.

    Raises:
        KeyError: if the topic has no registered encoder.
        ValueError: if JSON serialization fails.
    """
    event_type = _TOPIC_TO_EVENT_TYPE[topic]
    encoder = _ENCODERS[event_type]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        **encoder(message),
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def deserialize(topic: str, data_bytes: bytes) -> Any | None:
    """Deserialize JSON bytes from a Redis stream field into a domain object.

    Returns ``None`` if the message is malformed (logged; not re-raised so
    the worker can ACK-and-skip rather than crash).

    Args:
        topic:      Application topic name.
        data_bytes: Raw bytes from the Redis stream ``data`` field.
    """
    try:
        payload = json.loads(data_bytes)
        event_type = payload.get("event_type")
        decoder = _DECODERS.get(event_type)
        if decoder is None:
            logger.warning(
                "redis_unknown_event_type",
                event_type=event_type,
                topic=topic,
            )
            return None
        return decoder(payload)
    except Exception:
        logger.exception("redis_deserialization_failed", topic=topic)
        return None
