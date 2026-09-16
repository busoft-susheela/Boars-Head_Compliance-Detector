"""PersistenceWorker — background thread that durably persists compliance events.

Design
------
The worker subscribes to two MessageQueue topics:
    compliance.alert   → ComplianceEvent  (lightweight violation alert)
    evidence.capture   → EvidenceCaptureEvent (frozen evidence payload)

This keeps PostgreSQL writes completely off the hot CV pipeline path.
If the database is temporarily unavailable:
    - The CV pipeline continues without interruption.
    - Persistence failures are logged and metered.
    - Critical events (violations) are retried up to _MAX_RETRIES times.
    - After exhausting retries the failure is recorded in metrics and the
      worker moves on — it never blocks or crashes the process.

Failure strategy classification (database.md §38)
--------------------------------------------------
CRITICAL     — violation + evidence metadata + audit trail
BEST_EFFORT  — notification creation
BATCHABLE    — detections, observations (handled separately if enabled)

Evidence file storage
---------------------
Thumbnail bytes from EvidenceCaptureEvent are written to:
    evidence/<group_id>/<seq>_<frame_id>.jpg

PostgreSQL stores the relative path in evidence_items.storage_key.
Raw bytes are never inserted into the database.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import structlog

from backend.app.compliance.events import (
    TOPIC_COMPLIANCE_ALERT,
    TOPIC_EVIDENCE_CAPTURE,
    ComplianceEvent,
    EvidenceCaptureEvent,
)
from backend.app.infrastructure.database.engine import Database
from backend.app.infrastructure.database.metrics import DatabaseMetrics
from backend.app.infrastructure.database.models.violations import (
    EvidenceGroup,
    EvidenceItem,
    Violation,
)
from backend.app.infrastructure.database.models.notifications import Notification
from backend.app.infrastructure.database.repositories.evidence import (
    EvidenceGroupRepository,
    EvidenceItemRepository,
)
from backend.app.infrastructure.database.repositories.notification import NotificationRepository
from backend.app.infrastructure.database.repositories.violation import ViolationRepository
from backend.app.infrastructure.database.services.audit_service import AuditService
from backend.app.infrastructure.message_queue.base import MessageQueue

logger = structlog.get_logger(__name__)

_QUEUE_TIMEOUT = 1.0   # seconds — controls shutdown responsiveness
_MAX_RETRIES = 3
_RETRY_DELAY = 0.5     # seconds between retries


class PersistenceWorker:
    """Background thread that writes confirmed violations and evidence to PostgreSQL.

    Args:
        db:            Database engine + session factory.
        message_queue: Source of ComplianceEvent and EvidenceCaptureEvent messages.
        evidence_dir:  Root directory for evidence thumbnail files (e.g. "evidence/").
        metrics:       Optional shared metrics recorder.
    """

    def __init__(
        self,
        db: Database,
        message_queue: MessageQueue,
        evidence_dir: str = "evidence",
        metrics: DatabaseMetrics | None = None,
    ) -> None:
        self._db = db
        self._mq = message_queue
        # Resolve to absolute so that Path.relative_to() works correctly
        # regardless of whether evidence_dir was given as a relative path.
        self._evidence_dir = Path(evidence_dir).resolve()
        self._metrics = metrics or DatabaseMetrics()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Buffer incoming evidence events until we receive the matching alert.
        self._pending_evidence: dict[str, EvidenceCaptureEvent] = {}
        self._pending_lock = threading.Lock()

    @property
    def metrics(self) -> DatabaseMetrics:
        return self._metrics

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="persistence_worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("persistence_worker_started")

    def stop(self) -> None:
        self._stop_event.set()
        logger.info("persistence_worker_stop_requested")

    def join(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ── Thread body ───────────────────────────────────────────────────────────

    def _run(self) -> None:
        logger.debug("persistence_worker_running")
        while not self._stop_event.is_set():
            # Drain both topics on each iteration — prefer compliance alerts
            # because they trigger the evidence lookup.
            self._drain_evidence_topic()
            self._drain_alert_topic()
            # Small sleep to avoid spinning when both queues are empty.
            time.sleep(0.05)
        logger.debug("persistence_worker_stopped")

    def _drain_evidence_topic(self) -> None:
        try:
            event: EvidenceCaptureEvent = self._mq.get(TOPIC_EVIDENCE_CAPTURE, timeout=0)
            with self._pending_lock:
                self._pending_evidence[event.group_id] = event
        except queue.Empty:
            pass
        except Exception:
            logger.exception("persistence_worker_evidence_queue_error")

    def _drain_alert_topic(self) -> None:
        try:
            event: ComplianceEvent = self._mq.get(TOPIC_COMPLIANCE_ALERT, timeout=0)
        except queue.Empty:
            return
        except Exception:
            logger.exception("persistence_worker_alert_queue_error")
            return

        # Retrieve matching evidence (may arrive slightly after the alert).
        # During each sleep tick we also drain the evidence queue so that events
        # published after the last drain cycle are picked up immediately.
        evidence_event: EvidenceCaptureEvent | None = None
        for _ in range(20):          # wait up to ~200 ms
            self._drain_evidence_topic()   # pull any newly-arrived evidence into pending
            with self._pending_lock:
                evidence_event = self._pending_evidence.pop(event.group_id, None)
            if evidence_event is not None:
                break
            time.sleep(0.01)

        self._persist_violation_with_retry(event, evidence_event)

    # ── Persistence (with retry) ──────────────────────────────────────────────

    def _persist_violation_with_retry(
        self,
        alert: ComplianceEvent,
        evidence: EvidenceCaptureEvent | None,
    ) -> None:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._persist_violation(alert, evidence)
                return
            except Exception:
                self._metrics.record_write_failure()
                logger.exception(
                    "persistence_worker_write_failed",
                    group_id=alert.group_id,
                    attempt=attempt,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY * attempt)
                else:
                    logger.error(
                        "persistence_worker_max_retries_exceeded",
                        group_id=alert.group_id,
                    )

    def _persist_violation(
        self,
        alert: ComplianceEvent,
        evidence: EvidenceCaptureEvent | None,
    ) -> None:
        """Write violation + evidence group + evidence items + notification + audit in one transaction."""
        with self._db.session() as sess:
            audit = AuditService(sess)
            violation_repo = ViolationRepository(sess)
            evidence_group_repo = EvidenceGroupRepository(sess)
            evidence_item_repo = EvidenceItemRepository(sess)
            notification_repo = NotificationRepository(sess)

            # ── Idempotency guard: skip if already persisted ─────────────────
            if violation_repo.get_by_group_id(alert.group_id) is not None:
                logger.debug("persistence_worker_duplicate_skipped", group_id=alert.group_id)
                return

            # ── Determine start time from earliest evidence item ─────────────
            started_at: datetime | None = None
            if evidence is not None and evidence.payload.items:
                started_at = min(item.timestamp for item in evidence.payload.items)

            # ── Persist Violation ────────────────────────────────────────────
            violation = Violation(
                group_id=alert.group_id,
                camera_id=alert.camera_id,
                zone_id=alert.zone_id,
                track_id=alert.person_id,
                violation_type="HANDWASH_ABSENCE",
                reason="Person at sink without handwashing exceeded absence threshold",
                reason_code="ABSENCE_THRESHOLD_EXCEEDED",
                started_at=started_at,
                confirmed_at=alert.timestamp,
            )
            violation_repo.save(violation)
            self._metrics.record_violation()

            # ── Persist EvidenceGroup ────────────────────────────────────────
            evidence_group: EvidenceGroup | None = None
            if evidence is not None:
                evidence_group = EvidenceGroup(
                    group_id=alert.group_id,
                    violation_id=violation.id,
                    camera_id=alert.camera_id,
                    zone_id=alert.zone_id,
                    track_id=alert.person_id,
                    started_at=started_at,
                    frozen_at=alert.timestamp,
                    item_count=len(evidence.payload.items),
                )
                evidence_group_repo.save(evidence_group)

                # ── Write thumbnail files + EvidenceItem records ─────────────
                group_dir = self._evidence_dir / alert.group_id
                group_dir.mkdir(parents=True, exist_ok=True)

                items_to_save: list[EvidenceItem] = []
                for seq, ev_item in enumerate(evidence.payload.items):
                    storage_key: str | None = None
                    if ev_item.thumbnail is not None:
                        fname = f"{seq:03d}_{ev_item.frame_id}.jpg"
                        fpath = group_dir / fname
                        try:
                            fpath.write_bytes(ev_item.thumbnail)
                            storage_key = str(fpath.relative_to(self._evidence_dir.parent))
                        except (OSError, ValueError):
                            logger.exception(
                                "persistence_worker_thumbnail_write_failed",
                                group_id=alert.group_id,
                                frame_id=ev_item.frame_id,
                            )

                    item = EvidenceItem(
                        evidence_group_id=evidence_group.id,
                        frame_id=ev_item.frame_id,
                        sequence_number=seq,
                        captured_at=ev_item.timestamp,
                        thumbnail_reference=f"{alert.group_id}/{seq:03d}_{ev_item.frame_id}.jpg",
                        storage_key=storage_key,
                    )
                    items_to_save.append(item)
                    self._metrics.record_evidence_item()

                evidence_item_repo.save_batch(items_to_save)

                # ── Compile evidence video clip ──────────────────────────────
                self._create_evidence_clip(
                    list(evidence.payload.items), group_dir, alert=alert
                )

            # ── Persist Notification (DASHBOARD channel) ─────────────────────
            notification = Notification(
                violation_id=violation.id,
                channel="DASHBOARD",
                status="PENDING",
            )
            notification_repo.save(notification)

            # ── Audit trail ──────────────────────────────────────────────────
            audit.record(
                action="VIOLATION_CREATED",
                entity_type="violation",
                entity_id=str(violation.id),
                correlation_id=alert.group_id,
                source="PersistenceWorker",
                metadata={
                    "camera_id": alert.camera_id,
                    "zone_id": alert.zone_id,
                    "track_id": alert.person_id,
                    "rule_name": alert.rule_name,
                },
            )
            self._metrics.record_audit_event()

            if evidence_group is not None:
                audit.record(
                    action="EVIDENCE_FROZEN",
                    entity_type="evidence_group",
                    entity_id=str(evidence_group.id),
                    correlation_id=alert.group_id,
                    source="PersistenceWorker",
                    metadata={"item_count": evidence_group.item_count},
                )
                self._metrics.record_audit_event()

            audit.record(
                action="NOTIFICATION_CREATED",
                entity_type="notification",
                entity_id=str(notification.id),
                correlation_id=alert.group_id,
                source="PersistenceWorker",
                metadata={"channel": "DASHBOARD"},
            )
            self._metrics.record_audit_event()

        logger.info(
            "violation_persisted",
            group_id=alert.group_id,
            camera_id=alert.camera_id,
            zone_id=alert.zone_id,
            track_id=alert.person_id,
            evidence_items=len(evidence.payload.items) if evidence else 0,
        )

    def _create_evidence_clip(
        self,
        items: list,
        group_dir: Path,
        fps: float = 2.0,
        alert: ComplianceEvent | None = None,
    ) -> None:
        """Decode evidence thumbnails, overlay violation details in red, and write clip.avi."""
        try:
            frames: list[np.ndarray] = []
            timestamps: list[datetime] = []
            for ev_item in items:
                if ev_item.thumbnail is None:
                    continue
                arr = np.frombuffer(ev_item.thumbnail, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                frames.append(frame)
                timestamps.append(ev_item.timestamp)

            if not frames:
                logger.warning("evidence_clip_no_frames", group_dir=str(group_dir))
                return

            h, w = frames[0].shape[:2]
            clip_path = group_dir / "clip.avi"
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(str(clip_path), fourcc, fps, (w, h))
            if not writer.isOpened():
                logger.error("evidence_clip_writer_failed", path=str(clip_path))
                return

            # Pre-build violation overlay lines (static across all frames).
            RED   = (0, 0, 255)
            BLACK = (0, 0, 0)
            WHITE = (255, 255, 255)
            if alert is not None:
                confirmed_str = alert.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                overlay_lines = [
                    ("⚠ VIOLATION: NOT WASHED",          0.65, RED,   2),
                    (f"Person ID : {alert.person_id}",   0.55, RED,   1),
                    (f"Camera    : {alert.camera_id}",   0.50, RED,   1),
                    (f"Zone      : {alert.zone_id}",     0.50, RED,   1),
                    (f"Confirmed : {confirmed_str}",     0.45, RED,   1),
                    (f"Group     : {alert.group_id}",    0.38, RED,   1),
                ]
            else:
                overlay_lines = []

            for frame, ts in zip(frames, timestamps):
                if frame.shape[:2] != (h, w):
                    frame = cv2.resize(frame, (w, h))

                # ── Violation details — top-left, red ─────────────────────────
                y = 22
                for text, scale, colour, thickness in overlay_lines:
                    line_h = int(scale * 28)
                    # Black shadow for readability on any background
                    cv2.putText(frame, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX,
                                scale, BLACK, thickness + 1)
                    cv2.putText(frame, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX,
                                scale, colour, thickness)
                    y += line_h + 4

                # ── Frame timestamp — bottom-left, white ──────────────────────
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
                cv2.putText(frame, ts_str, (8, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, BLACK, 2)
                cv2.putText(frame, ts_str, (8, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)

                writer.write(frame)

            writer.release()
            logger.info(
                "evidence_clip_created",
                path=str(clip_path),
                frame_count=len(frames),
                fps=fps,
            )
        except Exception:
            logger.exception("evidence_clip_creation_failed", group_dir=str(group_dir))
