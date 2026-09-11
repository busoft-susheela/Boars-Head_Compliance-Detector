"""Frontend domain models — display-layer representations of backend state.

These dataclasses are the frontend's own view of the system.  They are NOT
the backend's internal models.  The repository layer maps backend API
responses into these display models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Status enumerations ───────────────────────────────────────────────────────

class CameraConnectionStatus(str, Enum):
    ONLINE       = "ONLINE"
    CONNECTING   = "CONNECTING"
    DEGRADED     = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    ERROR        = "ERROR"
    STOPPED      = "STOPPED"


class ProcessingStatus(str, Enum):
    STARTING     = "STARTING"
    WARMING_UP   = "WARMING_UP"
    PROCESSING   = "PROCESSING"
    BACKPRESSURED= "BACKPRESSURED"
    ERROR        = "ERROR"
    STOPPED      = "STOPPED"


class HandwashState(str, Enum):
    UNKNOWN      = "UNKNOWN"
    AT_SINK      = "AT_SINK"
    WATER_ON     = "WATER_ON"
    SOAP_APPLIED = "SOAP_APPLIED"
    WASHING      = "WASHING"
    RINSING      = "RINSING"
    COMPLETED    = "COMPLETED"


class EvidenceStatus(str, Enum):
    LOADING     = "LOADING"
    AVAILABLE   = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class StreamSourceType(str, Enum):
    RTSP  = "RTSP"
    VIDEO = "VIDEO"


class PipelineStageStatus(str, Enum):
    OK       = "ok"
    DEGRADED = "degraded"
    ERROR    = "error"
    STOPPED  = "stopped"
    STARTING = "starting"


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class IngestionInfo:
    connection: CameraConnectionStatus
    source_type: StreamSourceType
    fps: float
    frames_received: int
    frames_processed: int
    dropped_frames: int
    last_frame_at: Optional[datetime]
    # Video-file only
    video_filename: Optional[str] = None
    video_position_seconds: Optional[float] = None
    video_duration_seconds: Optional[float] = None
    # RTSP only
    elapsed_seconds: Optional[float] = None


@dataclass
class PipelineStage:
    name: str
    status: PipelineStageStatus
    throughput_fps: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    last_processed_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class ComplianceStateInfo:
    current_state: HandwashState
    state_duration_seconds: float
    required_duration_seconds: float
    sequence_valid: bool
    washing_duration_seconds: float
    observation_count: int


@dataclass
class CameraStatus:
    camera_id: str
    name: str
    zone_id: str
    zone_name: str
    connection: CameraConnectionStatus
    processing: ProcessingStatus
    ingestion: IngestionInfo
    pipeline_stages: list[PipelineStage]
    compliance_state: Optional[ComplianceStateInfo]
    last_updated: datetime


@dataclass
class EvidenceFrame:
    frame_id: str
    timestamp: datetime
    thumbnail_bytes: Optional[bytes]  # raw JPEG bytes from backend


@dataclass
class EvidencePayload:
    group_id: str
    frames: list[EvidenceFrame]
    loaded_at: datetime
    clip_bytes: Optional[bytes] = None


@dataclass
class Violation:
    group_id: str
    camera_id: str
    camera_name: str
    zone_id: str
    zone_name: str
    timestamp: datetime
    rule_id: str
    reason: str               # machine key, e.g. "required_duration_not_reached"
    reason_display: str       # human-readable label
    washing_duration_seconds: Optional[float]
    required_duration_seconds: float
    evidence_status: EvidenceStatus
    evidence: Optional[EvidencePayload] = None


@dataclass
class SystemStatus:
    healthy: bool
    backend_connected: bool
    last_updated: Optional[datetime]
    cameras_online: int
    cameras_total: int
    processing_active: int
    processing_total: int
    compliance_rate: float      # 0.0–1.0
    violations_today: int
    system_fps: float
    uptime_seconds: float = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

HANDWASH_STATE_ORDER: list[HandwashState] = [
    HandwashState.UNKNOWN,
    HandwashState.AT_SINK,
    HandwashState.WATER_ON,
    HandwashState.SOAP_APPLIED,
    HandwashState.WASHING,
    HandwashState.RINSING,
    HandwashState.COMPLETED,
]

REASON_DISPLAY: dict[str, str] = {
    "required_duration_not_reached": "Required washing duration was not reached",
    "soap_not_detected":             "Soap was not detected",
    "water_not_detected":            "Water was not detected",
    "sequence_invalid":              "Handwash sequence was not followed correctly",
    "incomplete":                    "Handwashing was not completed",
}
