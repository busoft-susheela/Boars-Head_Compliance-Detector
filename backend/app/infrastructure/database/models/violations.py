"""ORM models: violations, evidence_groups, evidence_items."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.database.models.compliance import ComplianceEvaluation
    from backend.app.infrastructure.database.models.notifications import Notification
    from backend.app.infrastructure.database.models.frames import Frame


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Violation(Base):
    """One confirmed handwash compliance violation. Uniquely identified by group_id."""

    __tablename__ = "violations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    compliance_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_evaluations.id"), nullable=True
    )
    processing_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_sessions.id"), nullable=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_rules.id"), nullable=True
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    violation_type: Mapped[str] = mapped_column(String(128), nullable=False, default="HANDWASH_ABSENCE")
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CONFIRMED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    compliance_evaluation: Mapped[ComplianceEvaluation | None] = relationship(
        "ComplianceEvaluation", back_populates="violations"
    )
    evidence_group: Mapped[EvidenceGroup | None] = relationship(
        "EvidenceGroup", back_populates="violation", uselist=False
    )
    notifications: Mapped[list[Notification]] = relationship("Notification", back_populates="violation")


class EvidenceGroup(Base):
    """Frozen evidence bundle for one confirmed violation."""

    __tablename__ = "evidence_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    violation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("violations.id"), nullable=True
    )
    processing_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_sessions.id"), nullable=True
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    violation: Mapped[Violation | None] = relationship("Violation", back_populates="evidence_group")
    items: Mapped[list[EvidenceItem]] = relationship("EvidenceItem", back_populates="evidence_group")


class EvidenceItem(Base):
    """One frame evidence thumbnail reference. Bytes are on disk; only path stored here."""

    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_groups.id"), nullable=False
    )
    frame_db_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("frames.id"), nullable=True
    )
    frame_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    thumbnail_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    evidence_group: Mapped[EvidenceGroup] = relationship("EvidenceGroup", back_populates="items")
    frame: Mapped[Frame | None] = relationship("Frame", back_populates="evidence_items")
