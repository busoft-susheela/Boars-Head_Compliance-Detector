"""TemporalMetricsRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.compliance import TemporalMetric
from backend.app.infrastructure.database.repositories.base import BaseRepository


class TemporalMetricsRepository(BaseRepository[TemporalMetric]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TemporalMetric)
