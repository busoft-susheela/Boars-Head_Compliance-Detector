"""ORM models: observations, state_transitions, temporal_metrics,
compliance_rules, compliance_evaluations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.database.models.violations import Violation


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Observation(Base):
    """One frame's observation for a tracked person.

    observation_type: REAL (from inference) or SYNTHETIC (absence-synthesised).
    """

    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    frame_db_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("frames.id"), nullable=True
    )
    processing_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_sessions.id"), nullable=True
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inside_sink_zone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    water_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    soap_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hands_interacting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    track_bbox: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    observation_type: Mapped[str] = mapped_column(String(16), nullable=False, default="REAL")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class StateTransition(Base):
    """Meaningful state transition record (only created when state actually changes)."""

    __tablename__ = "state_transitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processing_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_sessions.id"), nullable=True
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_state: Mapped[str] = mapped_column(String(64), nullable=False)
    new_state: Mapped[str] = mapped_column(String(64), nullable=False)
    transition_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    sequence_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class TemporalMetric(Base):
    """SpatioTemporalAnalyzer snapshot at the time of compliance evaluation."""

    __tablename__ = "temporal_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processing_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_sessions.id"), nullable=True
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_state: Mapped[str] = mapped_column(String(64), nullable=False)
    at_sink_duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    water_on_duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    soap_applied_duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    washing_duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rinsing_duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sequence_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    continuity_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_gap_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    compliance_evaluations: Mapped[list[ComplianceEvaluation]] = relationship(
        "ComplianceEvaluation", back_populates="temporal_metric"
    )


class ComplianceRule(Base):
    """Versioned compliance rule definition."""

    __tablename__ = "compliance_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    use_case: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0")
    configuration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    evaluations: Mapped[list[ComplianceEvaluation]] = relationship(
        "ComplianceEvaluation", back_populates="rule"
    )


class ComplianceEvaluation(Base):
    """Result of one compliance check for a person+zone episode.

    result: IN_PROGRESS / COMPLIANT / VIOLATION
    Relationship direction: ComplianceEvaluation → TemporalMetric (one direction, no circle).
    """

    __tablename__ = "compliance_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processing_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_sessions.id"), nullable=True
    )
    temporal_metrics_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("temporal_metrics.id"), nullable=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compliance_rules.id"), nullable=True
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    temporal_metric: Mapped[TemporalMetric | None] = relationship(
        "TemporalMetric", back_populates="compliance_evaluations"
    )
    rule: Mapped[ComplianceRule | None] = relationship("ComplianceRule", back_populates="evaluations")
    violations: Mapped[list[Violation]] = relationship("Violation", back_populates="compliance_evaluation")
