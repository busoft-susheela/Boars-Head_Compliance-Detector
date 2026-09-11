"""ORM model: audit_logs.

APPEND-ONLY table.  No rows are ever updated or deleted (within retention
policy).  Each row records one meaningful business or lifecycle event.

Do NOT audit every frame — only transitions and business events.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Immutable audit trail record.

    actor_type: SYSTEM / USER
    outcome:    SUCCESS / FAILURE

    Example actions:
        STREAM_STARTED, STREAM_STOPPED, STREAM_RECONNECTED, STREAM_FAILED
        MODEL_LOADED, MODEL_LOAD_FAILED
        STATE_CHANGED
        COMPLIANCE_EVALUATED, VIOLATION_CREATED
        EVIDENCE_GROUP_CREATED, EVIDENCE_DISCARDED, EVIDENCE_FROZEN
        NOTIFICATION_CREATED, NOTIFICATION_FAILED
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # SYSTEM / USER
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="SYSTEM")
    actor_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Business action name (e.g. VIOLATION_CREATED)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # group_id when this event is part of a violation episode.
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Component that generated the event (e.g. ComplianceRuleEngine)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # SUCCESS / FAILURE
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCESS")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-form event metadata; NEVER include credentials or thumbnail bytes.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
