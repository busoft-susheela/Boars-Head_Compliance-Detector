"""ComplianceEvaluationRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.compliance import ComplianceEvaluation
from backend.app.infrastructure.database.repositories.base import BaseRepository


class ComplianceEvaluationRepository(BaseRepository[ComplianceEvaluation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ComplianceEvaluation)

    def list_violations(self, camera_id: str | None = None, limit: int = 100) -> list[ComplianceEvaluation]:
        q = (
            self._session.query(ComplianceEvaluation)
            .filter(ComplianceEvaluation.result == "VIOLATION")
        )
        if camera_id:
            q = q.filter(ComplianceEvaluation.camera_id == camera_id)
        return q.order_by(ComplianceEvaluation.evaluated_at.desc()).limit(limit).all()
