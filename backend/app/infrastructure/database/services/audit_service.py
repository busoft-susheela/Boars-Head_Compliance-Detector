"""AuditService — centralised audit log writer.

All audit events go through here so audit SQL is never scattered across
the codebase.  The service does NOT commit; callers provide the session
as part of their own transaction.

Usage
-----
    with db.session() as sess:
        audit = AuditService(sess)
        audit.record(
            action="VIOLATION_CREATED",
            entity_type="violation",
            entity_id=str(violation.id),
            correlation_id=group_id,
            source="PersistenceWorker",
            metadata={"camera_id": camera_id, "zone_id": zone_id},
        )
        # session commits when the `with` block exits cleanly
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

from backend.app.infrastructure.database.models.audit import AuditLog
from backend.app.infrastructure.database.repositories.audit_log import AuditLogRepository

logger = structlog.get_logger(__name__)


class AuditService:
    """Writes structured audit log entries within the caller's session."""

    def __init__(self, session) -> None:
        self._repo = AuditLogRepository(session)

    def record(
        self,
        action: str,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        source: str | None = None,
        actor_type: str = "SYSTEM",
        actor_id: str | None = None,
        outcome: str = "SUCCESS",
        reason: str | None = None,
        metadata: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditLog:
        """Append one audit record.  Does NOT commit.

        Args:
            action:         Business action name (e.g. VIOLATION_CREATED).
            entity_type:    Domain object type (e.g. "violation").
            entity_id:      String ID of the affected entity.
            correlation_id: group_id or other correlation key.
            source:         Component that generated the event.
            actor_type:     SYSTEM or USER.
            actor_id:       Identity of the actor (optional for SYSTEM).
            outcome:        SUCCESS or FAILURE.
            reason:         Human-readable reason (especially for FAILURE).
            metadata:       Free-form dict; NEVER include credentials or binary data.
            occurred_at:    Event time; defaults to now(UTC).
        """
        now = occurred_at or datetime.now(timezone.utc)
        entry = AuditLog(
            occurred_at=now,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            source=source,
            outcome=outcome,
            reason=reason,
            metadata_=metadata,
        )
        self._repo.save(entry)
        logger.debug(
            "audit_event_recorded",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            outcome=outcome,
        )
        return entry
