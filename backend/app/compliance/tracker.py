"""Tracker — assigns persistent IDs to detections across frames.

Responsibility: "Who is this?" — identity only.

The tracker maps incoming Detection bounding boxes to stable track_ids so
that downstream components can reason about the same person across frames
without knowing anything about bounding-box overlap arithmetic.

Interface
---------
``Tracker.update(detections, timestamp) -> list[Track]``

``Track`` carries the stable ``track_id`` plus the matched detection.
All downstream components use ``track_id`` as ``person_id``.

IoUTracker (MVP)
----------------
Lightweight single-process tracker using Intersection-over-Union overlap.
Sufficient for a single fixed handwash camera with at most one or two
people in the frame at once.

Extension path
--------------
Replace ``IoUTracker`` with a ByteTrack-backed implementation by creating
a new class that implements ``Tracker`` and injecting it at startup.
The downstream pipeline never imports ``IoUTracker`` directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from backend.app.inference.models.detection import BoundingBox, Detection

logger = structlog.get_logger(__name__)

# A track is considered lost after this many frames without a match.
_DEFAULT_MAX_LOST_FRAMES = 5


@dataclass(frozen=True)
class Track:
    """One tracked object with a stable identity.

    Attributes:
        track_id:  Monotonically increasing integer; stable for the life of
                   one tracked episode (e.g. one person's handwash session).
        detection: The matched Detection from the current frame.
        age:       Number of frames this track has been active.
    """

    track_id: int
    detection: Detection
    age: int


class Tracker(ABC):
    """Backend-independent interface for multi-frame object tracking."""

    @abstractmethod
    def update(
        self,
        detections: list[Detection],
        timestamp: datetime,
    ) -> list[Track]:
        """Match ``detections`` to existing tracks; return active ``Track`` list.

        Args:
            detections: Typed detections from the current frame.
            timestamp:  Frame capture time (for future velocity/motion models).

        Returns:
            One ``Track`` per matched detection.  New detections get a new
            ``track_id``; lost tracks are silently dropped after
            ``max_lost_frames`` frames.
        """

    @abstractmethod
    def reset(self) -> None:
        """Clear all active tracks.  Call when the video source restarts."""


# ---------------------------------------------------------------------------
# IoUTracker
# ---------------------------------------------------------------------------

def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """Return Intersection-over-Union of two bounding boxes."""
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    if inter == 0.0:
        return 0.0
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


@dataclass
class _ActiveTrack:
    track_id: int
    last_bbox: BoundingBox
    age: int
    lost_frames: int


class IoUTracker(Tracker):
    """Lightweight IoU-based tracker for single-camera, low-density scenes.

    Args:
        iou_threshold:    Minimum IoU to consider two boxes the same object.
        max_lost_frames:  Frames a track can go unmatched before removal.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_lost_frames: int = _DEFAULT_MAX_LOST_FRAMES,
    ) -> None:
        self._iou_threshold = iou_threshold
        self._max_lost_frames = max_lost_frames
        self._tracks: list[_ActiveTrack] = []
        self._next_id = 1
        logger.info(
            "iou_tracker_initialized",
            iou_threshold=iou_threshold,
            max_lost_frames=max_lost_frames,
        )

    def update(
        self,
        detections: list[Detection],
        timestamp: datetime,
    ) -> list[Track]:
        # ── ByteTrack passthrough ────────────────────────────────────────────
        # When the inference model ran with a built-in tracker (e.g. ByteTrack),
        # detections already carry stable track_ids.  Skip IoU matching entirely
        # and wrap each detection directly into a Track.
        if detections and all(d.track_id is not None for d in detections):
            result: list[Track] = []
            for det in detections:
                tid = det.track_id  # type: ignore[assignment]
                existing = next((t for t in self._tracks if t.track_id == tid), None)
                if existing is not None:
                    existing.last_bbox = det.bbox
                    existing.age += 1
                    existing.lost_frames = 0
                    result.append(Track(track_id=tid, detection=det, age=existing.age))
                else:
                    new_track = _ActiveTrack(
                        track_id=tid,
                        last_bbox=det.bbox,
                        age=1,
                        lost_frames=0,
                    )
                    self._tracks.append(new_track)
                    result.append(Track(track_id=tid, detection=det, age=1))
            # Expire tracks not seen this frame.
            seen_ids = {d.track_id for d in detections}
            survivors = []
            for t in self._tracks:
                if t.track_id in seen_ids:
                    survivors.append(t)
                else:
                    t.lost_frames += 1
                    if t.lost_frames <= self._max_lost_frames:
                        survivors.append(t)
            self._tracks = survivors
            logger.debug(
                "tracker_bytetrack_passthrough",
                detection_count=len(detections),
                active_tracks=len(self._tracks),
            )
            return result

        # ── IoU matching (fallback when no tracker is used) ──────────────────
        matched_track_ids: set[int] = set()
        matched_det_indices: set[int] = set()
        matches: list[tuple[_ActiveTrack, Detection]] = []

        # Greedy IoU matching (sufficient for low-density MVP).
        for track in self._tracks:
            best_iou = self._iou_threshold
            best_det_idx = -1
            for i, det in enumerate(detections):
                if i in matched_det_indices:
                    continue
                score = _iou(track.last_bbox, det.bbox)
                if score > best_iou:
                    best_iou = score
                    best_det_idx = i
            if best_det_idx >= 0:
                matches.append((track, detections[best_det_idx]))
                matched_track_ids.add(track.track_id)
                matched_det_indices.add(best_det_idx)

        # Update matched tracks.
        updated: dict[int, _ActiveTrack] = {}
        for track, det in matches:
            track.last_bbox = det.bbox
            track.age += 1
            track.lost_frames = 0
            updated[track.track_id] = track

        # Increment lost counter for unmatched existing tracks.
        for track in self._tracks:
            if track.track_id not in updated:
                track.lost_frames += 1
                if track.lost_frames <= self._max_lost_frames:
                    updated[track.track_id] = track

        # Create new tracks for unmatched detections.
        for i, det in enumerate(detections):
            if i not in matched_det_indices:
                new_track = _ActiveTrack(
                    track_id=self._next_id,
                    last_bbox=det.bbox,
                    age=1,
                    lost_frames=0,
                )
                self._next_id += 1
                updated[new_track.track_id] = new_track
                logger.info(
                    "tracker_new_track",
                    track_id=new_track.track_id,
                    class_name=det.class_name,
                    confidence=round(det.confidence, 2),
                )

        # Log tracks dropped after exceeding max_lost_frames.
        for track in self._tracks:
            if track.track_id not in updated and track.lost_frames > self._max_lost_frames:
                logger.info("tracker_track_lost", track_id=track.track_id, lost_frames=track.lost_frames)

        self._tracks = list(updated.values())

        # Return Track objects only for detections matched this frame.
        result: list[Track] = []
        for track, det in matches:
            result.append(Track(track_id=track.track_id, detection=det, age=track.age))
        for i, det in enumerate(detections):
            if i not in matched_det_indices:
                # Newly created track — find its entry.
                for t in self._tracks:
                    if t.last_bbox == det.bbox and t.age == 1:
                        result.append(Track(track_id=t.track_id, detection=det, age=1))
                        break

        logger.info(
            "tracker_update_done",
            detection_count=len(detections),
            matched=len(matches),
            new_tracks=len(detections) - len(matched_det_indices),
            active_tracks=len(self._tracks),
            returned_tracks=len(result),
        )
        return result

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1
        logger.debug("tracker_reset")
