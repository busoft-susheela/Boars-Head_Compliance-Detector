"""ViolationRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.violations import Violation
from backend.app.infrastructure.database.repositories.base import BaseRepository


class ViolationRepository(BaseRepository[Violation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Violation)

    def get_by_group_id(self, group_id: str) -> Violation | None:
        return (
            self._session.query(Violation)
            .filter(Violation.group_id == group_id)
            .first()
        )

    def list_recent(self, camera_id: str | None = None, limit: int = 50) -> list[Violation]:
        q = self._session.query(Violation)
        if camera_id:
            q = q.filter(Violation.camera_id == camera_id)
        return q.order_by(Violation.confirmed_at.desc()).limit(limit).all()
