"""StateTransitionRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.compliance import StateTransition
from backend.app.infrastructure.database.repositories.base import BaseRepository


class StateTransitionRepository(BaseRepository[StateTransition]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StateTransition)

    def list_for_track(self, camera_id: str, zone_id: str, track_id: int) -> list[StateTransition]:
        return (
            self._session.query(StateTransition)
            .filter(
                StateTransition.camera_id == camera_id,
                StateTransition.zone_id == zone_id,
                StateTransition.track_id == track_id,
            )
            .order_by(StateTransition.transition_at)
            .all()
        )
