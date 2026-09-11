"""ApiDashboardRepository — reads from the real FastAPI backend.

Currently maps the /health endpoint to domain models.
Endpoints not yet implemented in the backend are documented below.

REQUIRED BACKEND CONTRACTS (not yet available)
===============================================
GET /api/cameras
    Purpose:  Per-camera status (ingestion, pipeline, compliance state)
    Response: list[CameraStatusResponse]

GET /api/violations
    Purpose:  Historical compliance violations with filter params
    Params:   camera_id, zone_id, date_from, date_to, reason, limit, offset
    Response: list[ViolationResponse]

GET /api/violations/{group_id}/evidence
    Purpose:  Evidence payload (thumbnails) for a confirmed violation
    Response: EvidenceResponse

GET /api/events/recent
    Purpose:  Most recent compliance events
    Response: list[ViolationResponse]

Until these endpoints exist, ApiDashboardRepository returns empty lists
for violations/evidence and maps /health for system+camera status.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests

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

logger = logging.getLogger(__name__)


class ApiDashboardRepository(DashboardRepository):
    """Reads from the FastAPI backend at base_url."""

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.timeout = 3.0

    # ------------------------------------------------------------------

    def get_system_status(self) -> SystemStatus:
        health = self._get_health()
        if health is None:
            return SystemStatus(
                healthy=False, backend_connected=False,
                last_updated=None,
                cameras_online=0, cameras_total=0,
                processing_active=0, processing_total=0,
                compliance_rate=0.0, violations_today=0,
                system_fps=0.0,
            )

        ingestion    = health.get("ingestion", {})
        inference    = health.get("inference", {})
        compliance   = health.get("compliance", {})
        mq           = health.get("message_queue", {})

        frames_total = ingestion.get("frames_published_total", 0)
        fps          = ingestion.get("current_fps", 0.0)
        violations   = compliance.get("violations_total", 0)

        # Compliance rate: (evaluations - violations) / evaluations
        evaluations = compliance.get("evaluations_total", 0)
        rate = ((evaluations - violations) / evaluations) if evaluations else 1.0

        online  = 1 if ingestion.get("is_running", False) else 0
        proc    = 1 if inference.get("is_running", False) else 0

        return SystemStatus(
            healthy=health.get("status") == "ok",
            backend_connected=True,
            last_updated=datetime.now(timezone.utc),
            cameras_online=online,
            cameras_total=1,
            processing_active=proc,
            processing_total=1,
            compliance_rate=round(rate, 3),
            violations_today=violations,
            system_fps=round(fps, 2),
        )

    def get_cameras(self) -> list[CameraStatus]:
        """Map /health ingestion/inference metrics to a CameraStatus.

        Full per-camera API (GET /api/cameras) is not yet implemented in
        the backend.  Returns a best-effort single camera status.
        """
        health = self._get_health()
        if health is None:
            return []

        ingestion  = health.get("ingestion", {})
        inference  = health.get("inference", {})
        compliance = health.get("compliance", {})

        conn = (
            CameraConnectionStatus.ONLINE
            if ingestion.get("is_running", False)
            else CameraConnectionStatus.STOPPED
        )
        proc = (
            ProcessingStatus.PROCESSING
            if inference.get("is_running", False)
            else ProcessingStatus.STOPPED
        )

        fps             = ingestion.get("current_fps", 0.0)
        frames_recv     = ingestion.get("frames_published_total", 0)
        frames_dropped  = ingestion.get("frames_dropped_total", 0)
        frames_proc     = max(0, frames_recv - frames_dropped)

        ing = IngestionInfo(
            connection=conn,
            source_type=StreamSourceType.VIDEO,
            fps=round(fps, 2),
            frames_received=frames_recv,
            frames_processed=frames_proc,
            dropped_frames=frames_dropped,
            last_frame_at=datetime.now(timezone.utc),
        )

        stages = self._build_pipeline_stages(ingestion, inference, compliance, fps)

        return [
            CameraStatus(
                camera_id="cam01",
                name="Camera 01",
                zone_id="handwash_zone",
                zone_name="Main Sink Area",
                connection=conn,
                processing=proc,
                ingestion=ing,
                pipeline_stages=stages,
                compliance_state=None,   # requires GET /api/cameras
                last_updated=datetime.now(timezone.utc),
            )
        ]

    def get_violations(self, **kwargs) -> list[Violation]:
        limit = kwargs.get("limit", 50)
        camera_id = kwargs.get("camera_id")
        params = {"limit": limit}
        if camera_id:
            params["camera_id"] = camera_id
        try:
            resp = self._session.get(f"{self._base}/api/violations", params=params)
            resp.raise_for_status()
            return [self._parse_violation(v) for v in resp.json()]
        except Exception as exc:
            logger.warning("api_violations_unavailable: %s", exc)
            return []

    def get_evidence(self, group_id: str) -> Optional[EvidencePayload]:
        try:
            resp = self._session.get(f"{self._base}/api/violations/{group_id}/evidence")
            resp.raise_for_status()
            data = resp.json()
            frames = []
            for f in data.get("frames", []):
                thumb = base64.b64decode(f["thumbnail_b64"]) if f.get("thumbnail_b64") else None
                captured_at = datetime.fromisoformat(f["captured_at"]) if f.get("captured_at") else datetime.now(timezone.utc)
                frames.append(EvidenceFrame(
                    frame_id=str(f["frame_id"]),
                    timestamp=captured_at,
                    thumbnail_bytes=thumb,
                ))
            clip_bytes = base64.b64decode(data["clip_b64"]) if data.get("clip_b64") else None
            return EvidencePayload(group_id=group_id, frames=frames, loaded_at=datetime.now(timezone.utc), clip_bytes=clip_bytes)
        except Exception as exc:
            logger.warning("api_evidence_unavailable: %s", exc)
            return None

    def get_recent_events(self, limit: int = 10) -> list[Violation]:
        try:
            resp = self._session.get(f"{self._base}/api/events/recent", params={"limit": limit})
            resp.raise_for_status()
            return [self._parse_violation(v) for v in resp.json()]
        except Exception as exc:
            logger.warning("api_recent_events_unavailable: %s", exc)
            return []

    @staticmethod
    def _parse_violation(v: dict) -> Violation:
        confirmed_at = datetime.fromisoformat(v["confirmed_at"]) if v.get("confirmed_at") else datetime.now(timezone.utc)
        reason_code = v.get("reason_code") or ""
        reason_text = v.get("reason") or ""
        reason_display = REASON_DISPLAY.get(reason_code) or reason_text or reason_code
        camera_id = v["camera_id"]
        zone_id = v["zone_id"]
        # Convert IDs to readable display names
        camera_name = camera_id.replace("-", " ").title()
        zone_name = zone_id.replace("_", " ").title()
        return Violation(
            group_id=v["group_id"],
            camera_id=camera_id,
            camera_name=camera_name,
            zone_id=zone_id,
            zone_name=zone_name,
            timestamp=confirmed_at,
            rule_id="handwash_compliance",
            reason=reason_code,
            reason_display=reason_display,
            washing_duration_seconds=v.get("washing_duration_seconds"),
            required_duration_seconds=v.get("required_duration_seconds", 5.0),
            evidence_status=EvidenceStatus.AVAILABLE,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_health(self) -> Optional[dict[str, Any]]:
        try:
            resp = self._session.get(f"{self._base}/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("backend_health_unavailable: %s", exc)
            return None

    @staticmethod
    def _build_pipeline_stages(
        ingestion: dict, inference: dict, compliance: dict, fps: float
    ) -> list[PipelineStage]:
        ok = PipelineStageStatus.OK
        stopped = PipelineStageStatus.STOPPED
        now = datetime.now(timezone.utc)

        ing_ok = ingestion.get("is_running", False)
        inf_ok = inference.get("is_running", False)
        avg_inf_ms = inference.get("avg_inference_ms", None)

        return [
            PipelineStage("Ingestion",              ok if ing_ok else stopped, fps if ing_ok else None, None, now),
            PipelineStage("YOLO Detection",         ok if inf_ok else stopped, fps if inf_ok else None, avg_inf_ms, now),
            PipelineStage("IoU Tracker",            ok if inf_ok else stopped, fps if inf_ok else None, None, now),
            PipelineStage("Observation Builder",    ok if inf_ok else stopped, fps if inf_ok else None, None, now),
            PipelineStage("State Machine",          ok if inf_ok else stopped, fps if inf_ok else None, None, now),
            PipelineStage("Temporal Analyzer",      ok if inf_ok else stopped, fps if inf_ok else None, None, now),
            PipelineStage("Compliance Rule Engine", ok if inf_ok else stopped, fps if inf_ok else None, None, now),
            PipelineStage("Alert / Evidence",       ok if inf_ok else stopped, fps if inf_ok else None, None, now),
        ]
