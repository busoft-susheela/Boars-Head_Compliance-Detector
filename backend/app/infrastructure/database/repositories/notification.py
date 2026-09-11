"""NotificationRepository."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.notifications import Notification
from backend.app.infrastructure.database.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Notification)

    def list_for_violation(self, violation_id: UUID) -> list[Notification]:
        return self.list(violation_id=violation_id)
