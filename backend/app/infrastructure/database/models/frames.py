"""ORM model: frames."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.database.models.sessions import IngestionSession
    from backend.app.infrastructure.database.models.inference import Detection
    from backend.app.infrastructure.database.models.violations import EvidenceItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Frame(Base):
    __tablename__ = "frames"
    __table_args__ = (
        UniqueConstraint("ingestion_session_id", "frame_id", name="uq_frame_session_frame_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_sessions.id"), nullable=True
    )
    camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(128), nullable=False)
    frame_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_store_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    ingestion_session: Mapped[IngestionSession | None] = relationship(
        "IngestionSession", back_populates="frames"
    )
    detections: Mapped[list[Detection]] = relationship("Detection", back_populates="frame")
    evidence_items: Mapped[list[EvidenceItem]] = relationship("EvidenceItem", back_populates="frame")
