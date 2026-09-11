"""DetectionRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.inference import Detection
from backend.app.infrastructure.database.repositories.base import BaseRepository


class DetectionRepository(BaseRepository[Detection]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Detection)

    def save_batch(self, detections: list[Detection]) -> None:
        """Bulk-insert a list of detections (more efficient than individual saves)."""
        self._session.add_all(detections)
        self._session.flush()
