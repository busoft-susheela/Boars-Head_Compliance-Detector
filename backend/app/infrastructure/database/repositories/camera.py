"""CameraRepository, StreamRepository, ZoneRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.cameras import Camera, Stream, Zone
from backend.app.infrastructure.database.repositories.base import BaseRepository


class CameraRepository(BaseRepository[Camera]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Camera)

    def get_by_key(self, camera_key: str) -> Camera | None:
        return (
            self._session.query(Camera)
            .filter(Camera.camera_key == camera_key)
            .first()
        )

    def get_or_create(self, camera_key: str, name: str, **kwargs) -> Camera:
        """Return existing camera or create a new one."""
        cam = self.get_by_key(camera_key)
        if cam is None:
            cam = Camera(camera_key=camera_key, name=name, **kwargs)
            self.save(cam)
        return cam


class StreamRepository(BaseRepository[Stream]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Stream)

    def list_for_camera(self, camera_id) -> list[Stream]:
        return self.list(camera_id=camera_id)


class ZoneRepository(BaseRepository[Zone]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Zone)

    def get_by_key(self, camera_id, zone_key: str) -> Zone | None:
        return (
            self._session.query(Zone)
            .filter(Zone.camera_id == camera_id, Zone.zone_key == zone_key)
            .first()
        )

    def get_or_create(self, camera_id, zone_key: str, name: str, **kwargs) -> Zone:
        zone = self.get_by_key(camera_id, zone_key)
        if zone is None:
            zone = Zone(camera_id=camera_id, zone_key=zone_key, name=name, **kwargs)
            self.save(zone)
        return zone
