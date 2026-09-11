"""ProcessingSessionRepository."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.sessions import ProcessingSession
from backend.app.infrastructure.database.repositories.base import BaseRepository


class ProcessingSessionRepository(BaseRepository[ProcessingSession]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ProcessingSession)

    def update_status(self, session_id: UUID, status: str, ended_at: datetime | None = None) -> None:
        row = self.get(session_id)
        if row is None:
            return
        row.status = status
        if ended_at is not None:
            row.ended_at = ended_at
        self._session.flush()
