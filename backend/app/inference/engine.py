"""YoloInferenceEngine — orchestrates one inference cycle for a camera/zone pair.

Responsibilities (and ONLY these):
1. Receive a FrameEnvelope from the MessageQueue consumer.
2. Resolve the applicable ModelSpecs via ModelResolver.
3. Fetch raw pixels from FrameStore.
4. For each spec, retrieve the cached Detector from ModelRegistry and run inference.
5. Generate a JPEG thumbnail while the frame is available.
6. Merge and sort detections deterministically.
7. Build and publish a DetectionEvent to the output topic.
8. Record timing/metrics.

What the engine does NOT do:
- Load or cache models (→ ModelRegistry / ModelLoader)
- Resolve which models apply (→ ModelResolver)
- Generate thumbnails (→ ThumbnailGenerator)
- Implement compliance rules, tracking, or notifications

Failure semantics
-----------------
- FrameStore miss    → skip inference, log + metric, continue.
- Per-model failure  → log + metric, continue with other models; publish partial result.
- Thumbnail failure  → DetectionEvent.thumbnail = None, detections are still published.

Detection ordering
------------------
All detections from all models are merged into one sorted tuple:
    (use_case ASC, class_id ASC, confidence DESC)
This guarantees deterministic ordering regardless of model execution order.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import structlog

from backend.app.inference.exceptions import InferenceError
from backend.app.inference.model_spec import ModelSpec
from backend.app.inference.models.detection import Detection, DetectionEvent
from backend.app.inference.registry import ModelRegistry
from backend.app.inference.resolver.base import ModelResolver
from backend.app.inference.thumbnail import ThumbnailGenerator
from backend.app.infrastructure.frame_store.base import FrameStore
from backend.app.infrastructure.message_queue.base import MessageQueue
from backend.app.ingestion.models.frame_envelope import FrameEnvelope

logger = structlog.get_logger(__name__)

DETECTIONS_TOPIC = "inference.detections"


class YoloInferenceEngine:
    """Orchestrates one inference cycle for a fixed camera/zone pair.

    Args:
        zone_id:            The zone this engine is responsible for.
        resolver:           Resolves applicable models for camera+zone.
        registry:           Caches and returns loaded detectors.
        frame_store:        Source of raw pixel data.
        message_queue:      Where DetectionEvents are published.
        thumbnail_generator: Creates JPEG evidence while the frame is live.
        output_topic:       MessageQueue topic for DetectionEvents.
    """

    def __init__(
        self,
        zone_id: str,
        resolver: ModelResolver,
        registry: ModelRegistry,
        frame_store: FrameStore,
        message_queue: MessageQueue,
        thumbnail_generator: ThumbnailGenerator,
        output_topic: str = DETECTIONS_TOPIC,
        frame_save_max: int = 0,
        draw_bboxes: bool = True,
        video_save_enabled: bool = False,
        video_fps: float = 5.0,
        video_filename: str = "detected.mp4",
        movement_history_size: int = 12,
    ) -> None:
        self._zone_id = zone_id
        self._resolver = resolver
        self._registry = registry
        self._frame_store = frame_store
        self._message_queue = message_queue
        self._thumbnail_generator = thumbnail_generator
        self._output_topic = output_topic
        self._frame_save_max = frame_save_max  # 0 = disabled
        self._draw_bboxes = draw_bboxes
        self._video_save_enabled = video_save_enabled
        self._video_fps = video_fps            # fallback FPS if source_fps is unknown
        self._video_filename = video_filename
        self._video_writer: cv2.VideoWriter | None = None
        self._video_path: Path | None = None
        self._movement_history_size = movement_history_size

        # Per-person tracking state keyed by ByteTrack ID.
        # Each entry is created on first encounter and persists for the session.
        self._person_states: dict = defaultdict(lambda: {
            "sink_index": None,

            # Current hand centers belonging to this person.
            "hand_centers": [],

            # Rolling window of hand centers for movement calculation.
            "movement_history": deque(maxlen=self._movement_history_size),

            "movement_score": 0.0,

            "hand_near_sink": False,
            "step_detected": False,

            "washing": False,

            # Event state and video-frame timing.
            "action_state": "NOT_NEAR_SINK",
            "last_action_frame": 0,
            "entered_sink_frame": None,
            "washing_start_frame": None,
            "washing_duration_logged": 0,

            "positive_frames": 0,
            "no_detection_frames": 0,

            "event_count": 0,

            "last_seen_frame": 0,
        })
        logger.info(
            "inference_engine_initialized",
            zone_id=zone_id,
            output_topic=output_topic,
            frame_store=type(frame_store).__name__,
            message_queue=type(message_queue).__name__,
            thumbnail_generator=type(thumbnail_generator).__name__,
            frame_save_max=frame_save_max,
            video_save_enabled=video_save_enabled,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def process(self, envelope: FrameEnvelope) -> None:
        """Run a full inference cycle for ``envelope``.

        This method is synchronous and intended to run in a worker thread.
        It handles all per-frame errors internally (FrameStore miss, model
        failure, thumbnail failure) so that the calling worker never crashes
        on a single bad frame.
        """
        camera_id = envelope.camera_id
        frame_id = envelope.frame_id
        t_start = time.monotonic()

        logger.info(
            "inference_cycle_start",
            camera_id=camera_id,
            zone_id=self._zone_id,
            frame_id=frame_id,
        )

        # 1. Resolve applicable models
        try:
            specs: list[ModelSpec] = self._resolver.resolve(camera_id, self._zone_id)
        except InferenceError as exc:
            logger.error(
                "inference_resolve_error",
                camera_id=camera_id,
                zone_id=self._zone_id,
                frame_id=frame_id,
                error=str(exc),
            )
            return

        if not specs:
            logger.debug(
                "inference_no_models",
                camera_id=camera_id,
                zone_id=self._zone_id,
                frame_id=frame_id,
            )
            return

        logger.info(
            "inference_models_resolved",
            camera_id=camera_id,
            zone_id=self._zone_id,
            frame_id=frame_id,
            model_count=len(specs),
            models=[s.use_case for s in specs],
        )

        # 2. Fetch raw pixels — must happen before inference AND thumbnail.
        frame = self._frame_store.get(frame_id)
        if frame is None:
            logger.warning(
                "inference_frame_store_miss",
                camera_id=camera_id,
                zone_id=self._zone_id,
                frame_id=frame_id,
            )
            return

        logger.info(
            "inference_frame_fetched",
            camera_id=camera_id,
            zone_id=self._zone_id,
            frame_id=frame_id,
            shape=list(frame.shape),
        )

        # 3. Run inference for each model, collecting detections.
        all_detections: list[Detection] = []
        for spec in specs:
            model_detections = self._run_model(spec, frame, camera_id, zone_id=self._zone_id, frame_id=frame_id)
            all_detections.extend(model_detections)

        # 4. Sort detections deterministically: use_case, class_id, confidence desc.
        sorted_detections = tuple(
            sorted(all_detections, key=lambda d: (d.use_case, d.class_id, -d.confidence))
        )

        # 5. Generate thumbnail after inference so bounding boxes can be drawn.
        # Only annotate with detections that meet the MAIN confidence threshold (washing level).
        # Low-confidence "presence" detections (presence_conf ≤ conf < confidence_threshold)
        # are used for tracking but must NOT appear as active-washing bboxes in evidence.
        display_thresholds = {spec.use_case: spec.confidence_threshold for spec in specs}
        display_detections = [
            d for d in sorted_detections
            if d.confidence >= display_thresholds.get(d.use_case, 0.5)
        ]
        thumbnail: bytes | None = None
        t_thumb = time.monotonic()
        if self._draw_bboxes and display_detections:
            thumbnail = self._thumbnail_generator.generate_annotated(
                frame, display_detections
            )
        else:
            thumbnail = self._thumbnail_generator.generate(frame)
        thumb_ms = (time.monotonic() - t_thumb) * 1000
        logger.debug(
            "thumbnail_generated",
            frame_id=frame_id,
            size_bytes=len(thumbnail) if thumbnail else 0,
            duration_ms=round(thumb_ms, 1),
            annotated=self._draw_bboxes and bool(sorted_detections),
        )

        # 6. Save detected frame to disk for debug (only when detections exist).
        session_id = getattr(envelope, "session_id", "")
        if session_id and self._frame_save_max > 0 and frame_id <= self._frame_save_max and display_detections:
            self._save_detected_frame(frame, display_detections, session_id, frame_id)

        # 7. Write annotated frame to video (every frame, with or without detections).
        if self._video_save_enabled and session_id:
            self._write_video_frame(frame, tuple(display_detections), session_id, envelope.source_fps)

        # 8. Build and publish DetectionEvent.
        total_ms = (time.monotonic() - t_start) * 1000
        event = DetectionEvent(
            camera_id=camera_id,
            zone_id=self._zone_id,
            frame_id=frame_id,
            captured_at=envelope.captured_at,
            processed_at=datetime.now(tz=timezone.utc),
            detections=sorted_detections,
            thumbnail=thumbnail,
            correlation_id=envelope.correlation_id,
            source_fps=envelope.source_fps,
            frame_shape=(int(frame.shape[0]), int(frame.shape[1])),
        )
        self._message_queue.publish(self._output_topic, event)

        logger.info(
            "detection_event_published",
            action=f"Detections for frame {frame_id} sent to compliance pipeline",
            camera_id=camera_id,
            zone_id=self._zone_id,
            frame_id=frame_id,
            detection_count=len(sorted_detections),
            detections=[
                {"class": d.class_name, "confidence": round(d.confidence, 2)}
                for d in sorted_detections
            ],
            total_duration_ms=round(total_ms, 1),
        )

    def close(self) -> None:
        """Release the video writer and finalise the output file (if any)."""
        if self._video_writer is not None:
            self._video_writer.release()
            logger.info("video_writer_closed", path=str(self._video_path))
            self._video_writer = None
            self._video_path = None
        self._person_states.clear()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _write_video_frame(
        self,
        frame: np.ndarray,
        detections: tuple,
        session_id: str,
        source_fps: float = 0.0,
    ) -> None:
        """Annotate *frame* with bboxes (if any detections) and append to video.

        Uses the original source FPS so that the output plays back at the same
        speed as the source footage.  Falls back to the configured ``video_fps``
        when ``source_fps`` is unknown (0).
        """
        try:
            if self._video_writer is None:
                out_dir = Path(f"data/result/{session_id}")
                out_dir.mkdir(parents=True, exist_ok=True)
                self._video_path = out_dir / self._video_filename
                h, w = frame.shape[:2]
                fps = source_fps if source_fps > 0 else self._video_fps
                self._video_writer = cv2.VideoWriter(
                    str(self._video_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    fps,
                    (w, h),
                )
                if not self._video_writer.isOpened():
                    logger.error(
                        "video_writer_open_failed",
                        path=str(self._video_path),
                        codec="mp4v",
                    )
                    self._video_writer = None
                    return
                logger.info(
                    "video_writer_opened",
                    path=str(self._video_path),
                    fps=fps,
                    source_fps=source_fps,
                    resolution=f"{w}x{h}",
                )

            annotated = frame.copy()
            for det in detections:
                b = det.bbox
                x1, y1, x2, y2 = int(b.x1), int(b.y1), int(b.x2), int(b.y2)
                pid = f" ID:{det.track_id}" if det.track_id is not None else ""
                label = f"{det.class_name}{pid} {det.confidence:.2f}"
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    annotated, label, (x1, max(y1 - 6, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                )
            self._video_writer.write(annotated)
        except Exception as exc:
            logger.warning("video_frame_write_failed", error=str(exc))

    @staticmethod
    def _save_detected_frame(
        frame: np.ndarray,
        detections: tuple,
        session_id: str,
        frame_id: int,
    ) -> None:
        """Draw bounding boxes on a copy of *frame* and save to detected_frames folder."""
        try:
            out_dir = Path(f"data/result/{session_id}/detected_frames")
            out_dir.mkdir(parents=True, exist_ok=True)
            annotated = frame.copy()
            for det in detections:
                b = det.bbox
                x1, y1, x2, y2 = int(b.x1), int(b.y1), int(b.x2), int(b.y2)
                pid = f" ID:{det.track_id}" if det.track_id is not None else ""
                label = f"{det.class_name}{pid} {det.confidence:.2f}"
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    annotated, label, (x1, max(y1 - 6, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                )
            path = out_dir / f"{frame_id:06d}.jpg"
            cv2.imwrite(str(path), annotated)
        except Exception as exc:
            logger.warning("detected_frame_save_failed", frame_id=frame_id, error=str(exc))

    def _run_model(
        self,
        spec: ModelSpec,
        frame,
        camera_id: str,
        zone_id: str,
        frame_id: int,
    ) -> list[Detection]:
        """Run one model against the frame; returns empty list on failure."""
        try:
            detector = self._registry.get(spec)
        except InferenceError as exc:
            logger.error(
                "inference_model_load_error",
                use_case=spec.use_case,
                model_path=spec.model_path,
                camera_id=camera_id,
                zone_id=zone_id,
                frame_id=frame_id,
                error=str(exc),
            )
            return []

        t_infer = time.monotonic()
        try:
            detections = detector.infer(frame)
        except InferenceError as exc:
            infer_ms = (time.monotonic() - t_infer) * 1000
            logger.error(
                "inference_error",
                use_case=spec.use_case,
                camera_id=camera_id,
                zone_id=zone_id,
                frame_id=frame_id,
                duration_ms=round(infer_ms, 1),
                error=str(exc),
            )
            return []

        infer_ms = (time.monotonic() - t_infer) * 1000
        logger.info(
            "model_inference_done",
            action=f"YOLO ran on frame {frame_id} — found {len(detections)} detection(s)",
            use_case=spec.use_case,
            camera_id=camera_id,
            zone_id=zone_id,
            frame_id=frame_id,
            detection_count=len(detections),
            inference_duration_ms=round(infer_ms, 1),
        )
        return detections
