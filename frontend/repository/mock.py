"""MockDashboardRepository — time-based simulation of a live compliance system.

Simulates a single camera (cam01 / Main Sink Area) cycling through all
handwash states over a 60-second period.  Produces realistic FPS variance,
frame counts, and a static violation history.

This module contains NO compliance logic.  It only simulates the data that
the backend would publish for display purposes.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from domain.models import (
    CameraConnectionStatus,
    CameraStatus,
    ComplianceStateInfo,
    EvidenceFrame,
    EvidencePayload,
    EvidenceStatus,
    HandwashState,
    IngestionInfo,
    PipelineStage,
    PipelineStageStatus,
    ProcessingStatus,
    StreamSourceType,
    SystemStatus,
    Violation,
    REASON_DISPLAY,
)
from repository.base import DashboardRepository

# ── Constants ─────────────────────────────────────────────────────────────────

_EPOCH = datetime(2026, 9, 2, 8, 0, 0, tzinfo=timezone.utc)  # session start
_BASE_FPS   = 5.0
_REQUIRED_S = 20.0
_CAMERA_ID  = "cam01"
_CAMERA_NAME= "Camera 01"
_ZONE_ID    = "handwash_zone"
_ZONE_NAME  = "Main Sink Area"

# 60-second handwash cycle — (state, duration_seconds)
_STATE_CYCLE: list[tuple[HandwashState, float]] = [
    (HandwashState.UNKNOWN,      6.0),
    (HandwashState.AT_SINK,      8.0),
    (HandwashState.WATER_ON,     5.0),
    (HandwashState.SOAP_APPLIED, 4.0),
    (HandwashState.WASHING,     25.0),
    (HandwashState.RINSING,      7.0),
    (HandwashState.COMPLETED,    5.0),
]
_CYCLE_TOTAL = sum(d for _, d in _STATE_CYCLE)  # 60 s


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fps() -> float:
    """Vary FPS slightly to simulate real-world jitter."""
    return round(_BASE_FPS + 0.3 * math.sin(time.time() * 0.4), 2)


def _frames_since_start() -> int:
    elapsed = (_now() - _EPOCH).total_seconds()
    return max(0, int(elapsed * _BASE_FPS))


def _current_state_info() -> ComplianceStateInfo:
    """Determine the current handwash state based on wall-clock time."""
    t = time.time() % _CYCLE_TOTAL
    elapsed = 0.0
    for state, duration in _STATE_CYCLE:
        if t < elapsed + duration:
            duration_in_state = t - elapsed
            washing_s = (
                duration_in_state
                if state == HandwashState.WASHING
                else (_REQUIRED_S + 3.0 if state in (HandwashState.RINSING, HandwashState.COMPLETED) else 0.0)
            )
            return ComplianceStateInfo(
                current_state=state,
                state_duration_seconds=round(duration_in_state, 1),
                required_duration_seconds=_REQUIRED_S,
                sequence_valid=True,
                washing_duration_seconds=round(washing_s, 1),
                observation_count=int((_now() - _EPOCH).total_seconds() * _BASE_FPS),
            )
        elapsed += duration
    return ComplianceStateInfo(
        current_state=HandwashState.COMPLETED,
        state_duration_seconds=0.0,
        required_duration_seconds=_REQUIRED_S,
        sequence_valid=True,
        washing_duration_seconds=_REQUIRED_S + 3.0,
        observation_count=0,
    )


def _pipeline_stages(fps: float) -> list[PipelineStage]:
    now = _now()
    return [
        PipelineStage("Ingestion",             PipelineStageStatus.OK, fps,      None,  now),
        PipelineStage("YOLO Detection",        PipelineStageStatus.OK, fps, 82.0, now),
        PipelineStage("IoU Tracker",           PipelineStageStatus.OK, fps,  3.0, now),
        PipelineStage("Observation Builder",   PipelineStageStatus.OK, fps,  1.5, now),
        PipelineStage("State Machine",         PipelineStageStatus.OK, fps,  0.5, now),
        PipelineStage("Temporal Analyzer",     PipelineStageStatus.OK, fps,  0.8, now),
        PipelineStage("Compliance Rule Engine",PipelineStageStatus.OK, fps,  1.2, now),
        PipelineStage("Alert / Evidence",      PipelineStageStatus.OK, fps,  0.3, now),
    ]


def _static_violations() -> list[Violation]:
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        Violation(
            group_id="grp_a1b2c3",
            camera_id=_CAMERA_ID,
            camera_name=_CAMERA_NAME,
            zone_id=_ZONE_ID,
            zone_name=_ZONE_NAME,
            timestamp=today + timedelta(hours=9, minutes=14, seconds=22),
            rule_id="handwash_compliance",
            reason="required_duration_not_reached",
            reason_display=REASON_DISPLAY["required_duration_not_reached"],
            washing_duration_seconds=8.2,
            required_duration_seconds=20.0,
            evidence_status=EvidenceStatus.AVAILABLE,
        ),
        Violation(
            group_id="grp_d4e5f6",
            camera_id=_CAMERA_ID,
            camera_name=_CAMERA_NAME,
            zone_id=_ZONE_ID,
            zone_name=_ZONE_NAME,
            timestamp=today + timedelta(hours=11, minutes=3, seconds=47),
            rule_id="handwash_compliance",
            reason="required_duration_not_reached",
            reason_display=REASON_DISPLAY["required_duration_not_reached"],
            washing_duration_seconds=12.1,
            required_duration_seconds=20.0,
            evidence_status=EvidenceStatus.AVAILABLE,
        ),
        Violation(
            group_id="grp_g7h8i9",
            camera_id=_CAMERA_ID,
            camera_name=_CAMERA_NAME,
            zone_id=_ZONE_ID,
            zone_name=_ZONE_NAME,
            timestamp=today + timedelta(hours=13, minutes=58, seconds=5),
            rule_id="handwash_compliance",
            reason="required_duration_not_reached",
            reason_display=REASON_DISPLAY["required_duration_not_reached"],
            washing_duration_seconds=5.7,
            required_duration_seconds=20.0,
            evidence_status=EvidenceStatus.AVAILABLE,
        ),
    ]


def _make_evidence(group_id: str) -> EvidencePayload:
    """Produce a mock evidence payload — no real thumbnails available in mock."""
    base_time = _now() - timedelta(minutes=5)
    frames = [
        EvidenceFrame(f"frame_{1200 + i}", base_time + timedelta(seconds=i * 5), None)
        for i in range(4)
    ]
    return EvidencePayload(group_id=group_id, frames=frames, loaded_at=_now())


# ── Repository ────────────────────────────────────────────────────────────────

class MockDashboardRepository(DashboardRepository):
    """Time-based mock — safe to call multiple times per second."""

    def get_system_status(self) -> SystemStatus:
        violations = self.get_violations()
        today_count = len(violations)
        total_events = 18  # approximate events today
        compliant_events = total_events - today_count
        rate = compliant_events / total_events if total_events else 1.0
        elapsed = (_now() - _EPOCH).total_seconds()
        return SystemStatus(
            healthy=True,
            backend_connected=True,
            last_updated=_now(),
            cameras_online=1,
            cameras_total=1,
            processing_active=1,
            processing_total=1,
            compliance_rate=round(rate, 3),
            violations_today=today_count,
            system_fps=_fps(),
            uptime_seconds=elapsed,
        )

    def get_cameras(self) -> list[CameraStatus]:
        fps = _fps()
        frames = _frames_since_start()
        dropped = max(0, int(frames * 0.006))  # ~0.6% drop rate
        ingestion = IngestionInfo(
            connection=CameraConnectionStatus.ONLINE,
            source_type=StreamSourceType.VIDEO,
            fps=fps,
            frames_received=frames,
            frames_processed=frames - dropped,
            dropped_frames=dropped,
            last_frame_at=_now(),
            video_filename="data/handwash.mp4",
            video_position_seconds=(_now() - _EPOCH).total_seconds() % 600,
            video_duration_seconds=600.0,
        )
        return [
            CameraStatus(
                camera_id=_CAMERA_ID,
                name=_CAMERA_NAME,
                zone_id=_ZONE_ID,
                zone_name=_ZONE_NAME,
                connection=CameraConnectionStatus.ONLINE,
                processing=ProcessingStatus.PROCESSING,
                ingestion=ingestion,
                pipeline_stages=_pipeline_stages(fps),
                compliance_state=_current_state_info(),
                last_updated=_now(),
            )
        ]

    def get_violations(
        self,
        camera_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> list[Violation]:
        violations = _static_violations()
        if camera_id:
            violations = [v for v in violations if v.camera_id == camera_id]
        if zone_id:
            violations = [v for v in violations if v.zone_id == zone_id]
        if date_from:
            violations = [v for v in violations if v.timestamp >= date_from]
        if date_to:
            violations = [v for v in violations if v.timestamp <= date_to]
        if reason:
            violations = [v for v in violations if reason in v.reason]
        return sorted(violations, key=lambda v: v.timestamp, reverse=True)

    def get_evidence(self, group_id: str) -> Optional[EvidencePayload]:
        known = {v.group_id for v in _static_violations()}
        if group_id in known:
            return _make_evidence(group_id)
        return None

    def get_recent_events(self, limit: int = 10) -> list[Violation]:
        return self.get_violations()[:limit]
