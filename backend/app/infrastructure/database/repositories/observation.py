"""ObservationRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.compliance import Observation
from backend.app.infrastructure.database.repositories.base import BaseRepository


class ObservationRepository(BaseRepository[Observation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Observation)

    def save_batch(self, observations: list[Observation]) -> None:
        self._session.add_all(observations)
        self._session.flush()
