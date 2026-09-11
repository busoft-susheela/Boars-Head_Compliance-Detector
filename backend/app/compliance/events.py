"""Compliance output events published to the MessageQueue.

Two separate events with separate topics:

ComplianceEvent (lightweight alert)
    Published on ``compliance.alert`` for every confirmed violation.
    Contains only the metadata needed for downstream alerting — NO thumbnails,
    NO full detection arrays.  Subscribers can fan out notifications without
    handling large payloads.

EvidenceCaptureEvent (evidence payload)
    Published on ``evidence.capture`` only when a violation is confirmed.
    Contains the frozen evidence thumbnails collected during the absence
    episode.  Consumers that need to store or display evidence subscribe here.

Topic constants
---------------
Use ``TOPIC_COMPLIANCE_ALERT`` and ``TOPIC_EVIDENCE_CAPTURE`` throughout
the codebase instead of raw string literals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.app.compliance.evidence.models import EvidencePayload

# ── Topic names ───────────────────────────────────────────────────────────────
TOPIC_COMPLIANCE_ALERT = "compliance.alert"
TOPIC_EVIDENCE_CAPTURE = "evidence.capture"


@dataclass(frozen=True)
class ComplianceEvent:
    """Lightweight compliance alert — no evidence payload.

    Attributes:
        camera_id:  Source camera.
        zone_id:    Zone within the camera.
        person_id:  Tracked person identifier.
        timestamp:  Time the violation was confirmed (frame capture time).
        outcome:    Always ``"violation"`` for this event type.
        rule_name:  Identifies which rule triggered the alert.
        group_id:   Unique identifier correlating this alert with its
                    corresponding EvidenceCaptureEvent.
    """

    camera_id: str
    zone_id: str
    person_id: int
    timestamp: datetime
    outcome: str
    rule_name: str
    group_id: str


@dataclass(frozen=True)
class EvidenceCaptureEvent:
    """Evidence payload event — published alongside ComplianceEvent.

    Attributes:
        group_id:  Correlates with the matching ComplianceEvent.
        camera_id: Source camera.
        zone_id:   Zone within the camera.
        payload:   Frozen evidence payload with thumbnails.
        timestamp: Time the violation was confirmed.
    """

    group_id: str
    camera_id: str
    zone_id: str
    payload: EvidencePayload
    timestamp: datetime
