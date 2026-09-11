"""FrameRepository."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.frames import Frame
from backend.app.infrastructure.database.repositories.base import BaseRepository


class FrameRepository(BaseRepository[Frame]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Frame)

    def get_by_session_and_frame_id(self, ingestion_session_id: UUID, frame_id: int) -> Frame | None:
        return (
            self._session.query(Frame)
            .filter(
                Frame.ingestion_session_id == ingestion_session_id,
                Frame.frame_id == frame_id,
            )
            .first()
        )
