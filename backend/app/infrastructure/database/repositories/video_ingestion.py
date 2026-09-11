"""Repository for VideoIngestion records."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.video_ingestion import VideoIngestion
from backend.app.infrastructure.database.repositories.base import BaseRepository


class VideoIngestionRepository(BaseRepository[VideoIngestion]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, VideoIngestion)

    def create(
        self,
        *,
        video_name: str,
        source_path: str,
        stored_path: str,
        camera_id: str,
        zone_id: str | None = None,
        duration_sec: float | None = None,
        total_frame_count: int | None = None,
        frame_sec: float | None = None,
        height: int | None = None,
        width: int | None = None,
        status: str = "INGESTING",
        timestamp: datetime | None = None,
        error_description: str | None = None,
    ) -> VideoIngestion:
        record = VideoIngestion(
            video_name=video_name,
            source_path=source_path,
            stored_path=stored_path,
            camera_id=camera_id,
            zone_id=zone_id,
            duration_sec=duration_sec,
            total_frame_count=total_frame_count,
            frame_sec=frame_sec,
            height=height,
            width=width,
            status=status,
            timestamp=timestamp or datetime.now(timezone.utc),
            error_description=error_description,
        )
        return self.save(record)

    def update_status(self, video_uuid: uuid.UUID, status: str) -> VideoIngestion | None:
        record = (
            self._session.query(VideoIngestion)
            .filter(VideoIngestion.video_uuid == video_uuid)
            .first()
        )
        if record is not None:
            record.status = status
            record.modified_at = datetime.now(timezone.utc)
            self._session.flush()
        return record
