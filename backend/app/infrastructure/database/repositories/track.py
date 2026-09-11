"""TrackRepository."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.inference import Track
from backend.app.infrastructure.database.repositories.base import BaseRepository


class TrackRepository(BaseRepository[Track]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Track)

    def get_active(self, camera_id: str, zone_id: str, track_id: int) -> Track | None:
        return (
            self._session.query(Track)
            .filter(
                Track.camera_id == camera_id,
                Track.zone_id == zone_id,
                Track.track_id == track_id,
                Track.status == "ACTIVE",
            )
            .first()
        )
