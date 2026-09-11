"""EvidenceGroupRepository, EvidenceItemRepository."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.violations import EvidenceGroup, EvidenceItem
from backend.app.infrastructure.database.repositories.base import BaseRepository


class EvidenceGroupRepository(BaseRepository[EvidenceGroup]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, EvidenceGroup)

    def get_by_group_id(self, group_id: str) -> EvidenceGroup | None:
        return (
            self._session.query(EvidenceGroup)
            .filter(EvidenceGroup.group_id == group_id)
            .first()
        )


class EvidenceItemRepository(BaseRepository[EvidenceItem]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, EvidenceItem)

    def list_for_group(self, evidence_group_id: UUID) -> list[EvidenceItem]:
        return (
            self._session.query(EvidenceItem)
            .filter(EvidenceItem.evidence_group_id == evidence_group_id)
            .order_by(EvidenceItem.sequence_number)
            .all()
        )

    def save_batch(self, items: list[EvidenceItem]) -> None:
        self._session.add_all(items)
        self._session.flush()
