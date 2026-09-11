"""VideoConnector — reads frames from a pre-recorded video file or a folder of videos."""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import structlog

from .base import ReadResult, ReadStatus, StreamConnector

if TYPE_CHECKING:
    from backend.app.infrastructure.database.engine import Database

logger = structlog.get_logger(__name__)

_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}

# Signatures found inside MP4/MOV files that indicate an incomplete recording.
_INCOMPLETE_SIGNATURES = [b"moov", b"mdat"]


def _describe_open_failure(path: Path) -> str:
    """Return a short human-readable reason why cv2 could not open *path*."""
    try:
        size = path.stat().st_size
        if size == 0:
            return "File is empty (0 bytes)"
        # Peek at the first 64 bytes to detect truncated MP4 containers.
        with path.open("rb") as f:
            header = f.read(64)
        if path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
            # ftyp in the header means the file started writing correctly but
            # the moov atom (index) — written at the end — is absent, which
            # happens when a recording is cut off before it was finalised.
            if b"ftyp" in header and b"moov" not in header:
                return "Incomplete recording — moov atom missing (file was not finalised)"
        return "File could not be opened by cv2 (unsupported codec or corrupt container)"
    except OSError:
        return "File could not be read (I/O error)"


def _collect_videos(path: Path) -> list[Path]:
    """Return video files under *path* sorted by name.

    If *path* is a file, return it as a single-item list.
    If *path* is a directory, return all recognised video files sorted
    alphabetically (case-insensitive).
    """
    if path.is_file():
        return [path]
    files = sorted(
        (p for p in path.iterdir() if p.suffix.lower() in _VIDEO_EXTENSIONS),
        key=lambda p: p.name.lower(),
    )
    if not files:
        raise FileNotFoundError(f"No video files found in directory: {path}")
    return files


class VideoConnector(StreamConnector):
    """Opens a local video file (or every video in a folder) and reads frames sequentially.

    When *path* points to a directory all recognised video files (``*.mp4``,
    ``*.avi``, ``*.mov``, ``*.mkv``, ``*.m4v``) are played in alphabetical
    order.  When the last file ends the connector returns END_OF_STREAM, or
    restarts from the first file when ``loop=True``.

    playback_mode="realtime"  — sleeps between frames to match the file's
    native FPS, simulating a live source.  This is the only supported mode.

    All blocking cv2 calls run in the default thread-pool executor so they
    never stall the asyncio event loop.
    """

    def __init__(
        self,
        path: str | Path,
        camera_id: str,
        playback_mode: str = "realtime",
        loop: bool = False,
        source_path: str | None = None,
        zone_id: str | None = None,
        database: "Database | None" = None,
    ) -> None:
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"Video path not found: {root}")
        self._playlist: list[Path] = _collect_videos(root)
        self._playlist_index: int = 0
        self._camera_id = camera_id
        self._playback_mode = playback_mode
        self._loop = loop
        self._source_path = source_path or str(root)
        self._zone_id = zone_id
        self._database = database
        self._cap: cv2.VideoCapture | None = None
        self._native_fps: float = 25.0
        self._last_read_at: float = 0.0
        self._current_video_uuid: uuid.UUID | None = None
        self._session_id: str = ""

    @property
    def _current_path(self) -> Path:
        return self._playlist[self._playlist_index]

    @property
    def source_id(self) -> str:
        return self._current_path.name

    @property
    def session_id(self) -> str:
        """UUID string for the current video file session, used for frame output paths."""
        return self._session_id

    @property
    def native_fps(self) -> float:
        return self._native_fps

    @property
    def resolution(self) -> tuple[int, int] | None:
        """(width, height) or None if not yet connected."""
        if self._cap is None:
            return None
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h)

    async def connect(self) -> None:
        await self._open_current()

    async def read(self) -> ReadResult:
        if self._cap is None:
            raise RuntimeError("Call connect() first")

        if self._playback_mode == "realtime":
            await self._throttle_to_native_fps()

        loop = asyncio.get_running_loop()
        ret, frame = await loop.run_in_executor(None, self._cap.read)

        if not ret:
            # Current file exhausted — try to advance to the next one.
            logger.info("video_eof", camera_id=self._camera_id, source=self.source_id)
            advanced = await self._advance()
            if not advanced:
                return ReadResult(status=ReadStatus.END_OF_STREAM)
            # Read the first frame of the next file.
            ret, frame = await loop.run_in_executor(None, self._cap.read)
            if not ret:
                return ReadResult(status=ReadStatus.END_OF_STREAM)

        self._last_read_at = time.monotonic()
        return ReadResult(status=ReadStatus.FRAME, frame=frame)

    def close(self) -> None:
        if self._database is not None and self._current_video_uuid is not None:
            self._update_status(self._database, self._current_video_uuid, "COMPLETED")
            self._current_video_uuid = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("video_closed", camera_id=self._camera_id, source=self.source_id)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _open_current(self) -> None:
        """Open (or re-open) the file at the current playlist index."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        path = self._current_path
        loop = asyncio.get_running_loop()
        cap = await loop.run_in_executor(None, lambda: cv2.VideoCapture(str(path)))

        if not cap.isOpened():
            cap.release()
            error_description = _describe_open_failure(path)
            logger.warning(
                "video_unreadable",
                camera_id=self._camera_id,
                source=path.name,
                playlist_index=self._playlist_index,
                playlist_total=len(self._playlist),
                reason=error_description,
            )
            if self._database is not None:
                db = self._database
                meta = dict(
                    video_name=path.name,
                    source_path=self._source_path,
                    stored_path=str(path.resolve()),
                    camera_id=self._camera_id,
                    zone_id=self._zone_id,
                    status="FAILED",
                    timestamp=datetime.now(timezone.utc),
                    error_description=error_description,
                )
                await loop.run_in_executor(None, lambda: self._insert_record(db, meta))
            raise RuntimeError(
                f"camera_id={self._camera_id} Cannot open video file: {path}"
            )
        # Always assign a session UUID so frame output dirs are available even
        # when the database is disabled.
        self._session_id = str(uuid.uuid4())

        self._cap = cap
        reported_fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._native_fps = reported_fps if reported_fps > 0 else 25.0
        self._last_read_at = 0.0

        total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration_sec = total_frames / self._native_fps if self._native_fps > 0 else None

        logger.info(
            "video_opened",
            camera_id=self._camera_id,
            source=self.source_id,
            session_id=self._session_id,
            playlist_index=self._playlist_index,
            playlist_total=len(self._playlist),
            native_fps=round(self._native_fps, 2),
            resolution=self.resolution,
        )

        if self._database is not None:
            meta = dict(
                video_name=path.name,
                source_path=self._source_path,
                stored_path=str(path.resolve()),
                camera_id=self._camera_id,
                zone_id=self._zone_id,
                duration_sec=duration_sec,
                total_frame_count=total_frames if total_frames > 0 else None,
                frame_sec=self._native_fps,
                height=height if height > 0 else None,
                width=width if width > 0 else None,
                status="INGESTING",
                timestamp=datetime.now(timezone.utc),
            )
            db = self._database
            video_uuid = await loop.run_in_executor(None, lambda: self._insert_record(db, meta))
            self._current_video_uuid = video_uuid

    async def _advance(self) -> bool:
        """Move to the next file in the playlist, skipping unreadable files.

        Returns True if a next file was opened, False if the playlist is
        exhausted (and loop=False).
        """
        await self._mark_current_completed()

        # Walk forward through the playlist (with optional wrap) until we
        # successfully open a file or run out of candidates.
        candidates = list(range(self._playlist_index + 1, len(self._playlist)))
        if self._loop:
            candidates += list(range(0, self._playlist_index + 1))

        for idx in candidates:
            if idx == 0 and self._loop and idx <= self._playlist_index:
                logger.debug(
                    "playlist_loop",
                    camera_id=self._camera_id,
                    playlist_total=len(self._playlist),
                )
            self._playlist_index = idx
            try:
                await self._open_current()
                return True
            except RuntimeError:
                # File is unreadable — already logged and DB row inserted;
                # continue to the next candidate.
                continue

        return False

    async def _mark_current_completed(self) -> None:
        if self._database is not None and self._current_video_uuid is not None:
            video_uuid = self._current_video_uuid
            db = self._database
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._update_status(db, video_uuid, "COMPLETED"))
            self._current_video_uuid = None

    @staticmethod
    def _insert_record(db: "Database", meta: dict) -> uuid.UUID:
        from backend.app.infrastructure.database.repositories.video_ingestion import VideoIngestionRepository
        with db.session() as sess:
            repo = VideoIngestionRepository(sess)
            record = repo.create(**meta)
            return record.video_uuid

    @staticmethod
    def _update_status(db: "Database", video_uuid: uuid.UUID, status: str) -> None:
        from backend.app.infrastructure.database.repositories.video_ingestion import VideoIngestionRepository
        with db.session() as sess:
            repo = VideoIngestionRepository(sess)
            repo.update_status(video_uuid, status)

    async def _throttle_to_native_fps(self) -> None:
        if self._last_read_at == 0.0:
            return
        interval = 1.0 / self._native_fps
        elapsed = time.monotonic() - self._last_read_at
        remaining = interval - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
