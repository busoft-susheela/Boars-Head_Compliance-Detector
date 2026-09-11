"""Abstract repository interface — all dashboard data access goes through here.

Concrete implementations
------------------------
MockDashboardRepository  — deterministic simulated data for development/demo
ApiDashboardRepository   — real FastAPI backend via HTTP
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from domain.models import CameraStatus, EvidencePayload, SystemStatus, Violation


class DashboardRepository(ABC):

    @abstractmethod
    def get_system_status(self) -> SystemStatus:
        """Overall system health KPIs."""

    @abstractmethod
    def get_cameras(self) -> list[CameraStatus]:
        """Per-camera status: ingestion, pipeline, compliance."""

    @abstractmethod
    def get_violations(
        self,
        camera_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> list[Violation]:
        """Historical violations with optional filters, newest first."""

    @abstractmethod
    def get_evidence(self, group_id: str) -> Optional[EvidencePayload]:
        """Evidence payload for a confirmed violation, or None if unavailable."""

    @abstractmethod
    def get_recent_events(self, limit: int = 10) -> list[Violation]:
        """Most recent compliance events (violations only at this stage)."""
