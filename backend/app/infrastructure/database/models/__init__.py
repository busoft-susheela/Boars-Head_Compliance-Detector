"""ORM model imports — import all models so Alembic/SQLAlchemy can discover them.

Import order matters: leaf tables first, then tables that reference them.
"""
# Foundation (no outgoing FKs to other domain tables)
from backend.app.infrastructure.database.models.cameras import Camera, Stream, Zone
from backend.app.infrastructure.database.models.sessions import IngestionSession, ProcessingSession
from backend.app.infrastructure.database.models.frames import Frame

# Inference layer
from backend.app.infrastructure.database.models.inference import Detection, Track

# Compliance layer (references processing_sessions / frames)
from backend.app.infrastructure.database.models.compliance import (
    Observation,
    StateTransition,
    TemporalMetric,
    ComplianceRule,
    ComplianceEvaluation,
)

# Business events
from backend.app.infrastructure.database.models.violations import (
    Violation,
    EvidenceGroup,
    EvidenceItem,
)
from backend.app.infrastructure.database.models.notifications import Notification

# Audit (no outgoing FKs — append-only)
from backend.app.infrastructure.database.models.audit import AuditLog

# Ingestion metadata
from backend.app.infrastructure.database.models.video_ingestion import VideoIngestion

__all__ = [
    "Camera", "Stream", "Zone",
    "IngestionSession", "ProcessingSession",
    "Frame",
    "Detection", "Track",
    "Observation", "StateTransition", "TemporalMetric",
    "ComplianceRule", "ComplianceEvaluation",
    "Violation", "EvidenceGroup", "EvidenceItem",
    "Notification",
    "AuditLog",
    "VideoIngestion",
]
