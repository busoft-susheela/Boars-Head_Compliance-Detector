"""AuditLogRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.audit import AuditLog
from backend.app.infrastructure.database.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AuditLog)

    def list_for_correlation(self, correlation_id: str) -> list[AuditLog]:
        return (
            self._session.query(AuditLog)
            .filter(AuditLog.correlation_id == correlation_id)
            .order_by(AuditLog.occurred_at)
            .all()
        )

    def list_recent(self, action: str | None = None, limit: int = 100) -> list[AuditLog]:
        q = self._session.query(AuditLog)
        if action:
            q = q.filter(AuditLog.action == action)
        return q.order_by(AuditLog.occurred_at.desc()).limit(limit).all()
