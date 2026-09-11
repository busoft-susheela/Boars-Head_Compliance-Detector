"""FastAPI entry point — starts ingestion, inference, compliance, and persistence services."""

from __future__ import annotations

import asyncio
import base64
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI

from backend.app.infrastructure.frame_store.base import FrameStore
from backend.app.infrastructure.frame_store.in_memory import InMemoryFrameStore
from backend.app.infrastructure.message_queue.base import MessageQueue
from backend.app.infrastructure.message_queue.in_memory import InMemoryMessageQueue
from backend.app.infrastructure.factory import build_frame_store, build_message_queue, build_state_store
from backend.app.ingestion.factory import create_connector
from backend.app.ingestion.publishing.message_queue_publisher import MessageQueuePublisher
from backend.app.ingestion.sampling.fps_sampler import FpsSampler
from backend.app.ingestion.service import StreamIngestionService
from backend.app.ingestion.validation.frame_validator import FrameValidator
from backend.app.compliance.engine import ComplianceRuleEngine
from backend.app.compliance.observation import ObservationBuilder
from backend.app.compliance.rules.config import HandwashRuleConfig
from backend.app.compliance.rules.handwash import HandwashRuleEvaluator
from backend.app.compliance.state_machine import HandwashStateMachine
from backend.app.compliance.temporal.analyzer import SpatioTemporalAnalyzer
from backend.app.compliance.tracker import IoUTracker
from backend.app.compliance.worker import ComplianceWorker
from backend.app.inference.engine import YoloInferenceEngine
from backend.app.inference.loader import ModelLoader
from backend.app.inference.registry import ModelRegistry
from backend.app.inference.resolver.static import StaticModelResolver
from backend.app.inference.thumbnail import ThumbnailGenerator
from backend.app.inference.worker import CPUInferenceWorker
from backend.app.infrastructure.state_store.base import StateStore
from backend.app.infrastructure.database.engine import Database, build_database_url, get_database, close_database
from backend.app.infrastructure.database.repositories.violation import ViolationRepository
from backend.app.infrastructure.database.repositories.evidence import EvidenceGroupRepository, EvidenceItemRepository
from backend.app.infrastructure.database.models.compliance import TemporalMetric
from backend.app.infrastructure.database.metrics import DatabaseMetrics
from backend.app.infrastructure.database.persistence_worker import PersistenceWorker
from backend.app.middleware.correlation_id import CorrelationIdMiddleware
from backend.app.logging_config import configure_action_log, configure_logging
from config.loader import load_config

# Load .env before configure_logging() so LOG_LEVEL is available from the file.
# override=True ensures .env always wins over stale shell environment variables.
load_dotenv(".env", override=True)

# Configure logging before any logger is used.
configure_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))
configure_action_log()

# Bind a session-level correlation ID so all startup/shutdown log events
# have a real value instead of the "-" fallback.  Per-frame processing
# overrides this with a frame-specific UUID via clear_contextvars() +
# bind_contextvars() in StreamIngestionService._loop().
structlog.contextvars.bind_contextvars(correlation_id=str(uuid.uuid4()))

logger = structlog.get_logger(__name__)

_ingestion_service: StreamIngestionService | None = None
_ingestion_task: asyncio.Task | None = None
_inference_worker: CPUInferenceWorker | None = None
_inference_thread: threading.Thread | None = None
_model_registry: ModelRegistry | None = None
_compliance_worker: ComplianceWorker | None = None
_state_store: StateStore | None = None
_database: Database | None = None
_persistence_worker: PersistenceWorker | None = None
_db_metrics: DatabaseMetrics = DatabaseMetrics()
_required_washing_duration: float = 5.0   # set from config during lifespan
_evidence_dir: str = "evidence"            # set from config during lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ingestion_service, _ingestion_task
    global _inference_worker, _inference_thread, _model_registry
    global _compliance_worker, _state_store
    global _database, _persistence_worker, _db_metrics
    global _required_washing_duration, _evidence_dir

    cfg = load_config()
    stream_cfg = cfg["stream"]
    sampling_cfg = stream_cfg.get("sampling", {})
    inference_cfg = cfg.get("inference", {})
    thumbnail_cfg = inference_cfg.get("thumbnail", {})
    compliance_cfg = cfg.get("compliance", {})
    db_cfg = cfg.get("database", {})
    evidence_cfg = cfg.get("evidence", {})
    _evidence_dir = evidence_cfg.get("output_dir", "evidence")
    frame_save_max = int(cfg.get("debug", {}).get("frame_saving", {}).get("max_frames", 0))
    video_save_cfg = cfg.get("debug", {}).get("video_saving", {})
    video_save_enabled = bool(video_save_cfg.get("enabled", False))
    video_fps = float(video_save_cfg.get("fps", 5.0))
    video_filename = str(video_save_cfg.get("filename", "detected.mp4"))

    frame_ttl = float(os.environ.get("FRAME_TTL_SEC", "5.0"))

    # ── Infrastructure ──────────────────────────────────────────────────────
    camera_id = stream_cfg.get("camera_id", "handwash-camera-01")
    frame_store = build_frame_store(cfg, camera_id=camera_id, frame_ttl_seconds=frame_ttl)
    message_queue = build_message_queue(cfg, max_size_per_topic=inference_cfg.get("queue_size", 10))
    _state_store = build_state_store(cfg)

    # Expose on app.state for routes and health endpoint.
    app.state.frame_store = frame_store
    app.state.message_queue = message_queue

    # ── PostgreSQL database (optional — if disabled, CV pipeline still runs) ─
    db_enabled = db_cfg.get("enabled", False)
    if db_enabled:
        try:
            db_url = db_cfg.get("url") or build_database_url()
            pool_cfg = db_cfg.get("pool", {})
            _database = get_database(
                url=db_url,
                pool_max_size=pool_cfg.get("max_size", 10),
                timeout_seconds=db_cfg.get("timeout_seconds", 10.0),
            )
            app.state.database = _database
            logger.info("database_connected")
        except Exception:
            logger.exception("database_connection_failed_continuing_without_db")
            _database = None
            db_enabled = False

    # ── Ingestion ────────────────────────────────────────────────────────────
    _cfg_cameras = cfg.get("cameras", {})
    _first_zone_id = next(
        iter(next(iter(_cfg_cameras.values()), {}).get("zones", [])),
        None,
    ) if _cfg_cameras else None

    connector = create_connector(stream_cfg, zone_id=_first_zone_id, database=_database)
    sampler = FpsSampler(target_fps=sampling_cfg.get("target_fps", 5.0))
    logger.info("sampler_configured", target_fps=sampler.target_fps, interval_seconds=round(1.0 / sampler.target_fps, 4))
    publisher = MessageQueuePublisher(frame_store, message_queue)

    _ingestion_service = StreamIngestionService(
        connector=connector,
        sampler=sampler,
        publisher=publisher,
        validator=FrameValidator(),
        camera_id=stream_cfg.get("camera_id", "handwash-camera-01"),
        frame_save_max=frame_save_max,
    )

   # ── Inference — build and eagerly load models before starting workers ────
    resolver = StaticModelResolver(cfg)
    loader = ModelLoader()
    _model_registry = ModelRegistry(
        loader=loader,
        warmup=inference_cfg.get("warmup", True),
    )

    for zone_id in resolver.zones_for_camera(camera_id):
        for spec in resolver.resolve(camera_id, zone_id):
            logger.info("eager_model_load", use_case=spec.use_case, zone_id=zone_id)
            _model_registry.get(spec)

    zones = resolver.zones_for_camera(camera_id)
    zone_id = zones[0] if zones else "handwash_zone"

    thumbnail_enabled = thumbnail_cfg.get("enabled", True)
    thumbnail_generator = ThumbnailGenerator(
        max_width=thumbnail_cfg.get("max_width", 320),
        jpeg_quality=thumbnail_cfg.get("jpeg_quality", 70),
    ) if thumbnail_enabled else _NullThumbnailGenerator()

    engine = YoloInferenceEngine(
        zone_id=zone_id,
        resolver=resolver,
        registry=_model_registry,
        frame_store=frame_store,
        message_queue=message_queue,
        thumbnail_generator=thumbnail_generator,
        frame_save_max=frame_save_max,
        draw_bboxes=thumbnail_cfg.get("draw_bboxes", True),
        video_save_enabled=video_save_enabled,
        video_fps=video_fps,
        video_filename=video_filename,
    )

    _inference_worker = CPUInferenceWorker(
        engine=engine,
        message_queue=message_queue,
    )
    app.state.inference_worker = _inference_worker

    #── Compliance ───────────────────────────────────────────────────────────
    trigger_class = compliance_cfg.get("trigger_class", "handwash")
    washing_confidence = float(compliance_cfg.get("washing_confidence", 0.5))
    rule_config = HandwashRuleConfig.from_config(compliance_cfg)
    _required_washing_duration = rule_config.minimum_washing_duration_seconds
    assert _state_store is not None
    compliance_engine = ComplianceRuleEngine(
        state_store=_state_store,
        tracker=IoUTracker(),
        observation_builder=ObservationBuilder(
            person_class="person",
            sink_class="sink",
            hand_class=trigger_class,
            person_box_expand_x=rule_config.person_box_expand_x,
            person_box_expand_y=rule_config.person_box_expand_y,
            max_person_sink_distance=rule_config.max_person_sink_distance,
            sink_horizontal_margin=rule_config.sink_horizontal_margin,
            sink_top_margin=rule_config.sink_top_margin,
            sink_bottom_margin=rule_config.sink_bottom_margin,
            min_hands_for_washing=rule_config.min_hands_for_washing,
            min_hand_movement=rule_config.min_hand_movement,
            require_hand_movement=rule_config.require_hand_movement,
            confirmation_frames=rule_config.confirmation_frames,
            reset_after_no_detection_seconds=rule_config.reset_after_no_detection_seconds,
            movement_history_size=int(
                compliance_cfg.get("washing", {}).get("movement_history_size", 12)
            ),
        ),
        state_machine=HandwashStateMachine(),
        temporal_analyzer=SpatioTemporalAnalyzer(
            max_gap_seconds=compliance_cfg.get("handwash", {}).get(
                "max_gap_seconds", 10.0
            )
        ),
        rule_evaluator=HandwashRuleEvaluator(config=rule_config),
        message_queue=message_queue,
    )
    _compliance_worker = ComplianceWorker(
        engine=compliance_engine,
        message_queue=message_queue,
    )
    app.state.compliance_worker = _compliance_worker

    #── Persistence worker (only when DB is available) ───────────────────────
    if _database is not None:
        _persistence_worker = PersistenceWorker(
            db=_database,
            message_queue=message_queue,
            evidence_dir=evidence_cfg.get("output_dir", "evidence"),
            metrics=_db_metrics,
        )
        app.state.persistence_worker = _persistence_worker

    # ── Start threads ────────────────────────────────────────────────────────
    _compliance_worker.start()
    logger.info("compliance_worker_started")

    _inference_worker.start()
    logger.info("inference_worker_started")

    if _persistence_worker is not None:
        _persistence_worker.start()
        logger.info("persistence_worker_started")

    _ingestion_task = asyncio.create_task(_ingestion_service.run(), name="ingestion")
    logger.info("ingestion_task_started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    if _ingestion_service is not None:
        _ingestion_service.stop()
    if _ingestion_task is not None:
        try:
            await asyncio.wait_for(_ingestion_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("ingestion_task_stop_timeout")
            _ingestion_task.cancel()
        except asyncio.CancelledError:
            pass
    logger.info("ingestion_task_stopped")
    if sampler is not None:
        sampler.log_summary()

    if _inference_worker is not None:
        _inference_worker.stop()
        _inference_worker.join(timeout=5.0)
    logger.info("inference_worker_stopped")
    engine.close()

    if _compliance_worker is not None:
        _compliance_worker.stop()
        _compliance_worker.join(timeout=5.0)
    logger.info("compliance_worker_stopped")

    #Stop persistence after CV workers so no new events are produced.
    if _persistence_worker is not None:
        _persistence_worker.stop()
        _persistence_worker.join(timeout=5.0)
        logger.info("persistence_worker_stopped")

    if _state_store is not None:
        _state_store.close()
    logger.info("state_store_closed")

    if _model_registry is not None:
        _model_registry.close()
    logger.info("model_registry_closed")

    close_database()
    logger.info("database_closed")


class _NullThumbnailGenerator:
    """No-op thumbnail generator used when thumbnails are disabled."""

    def generate(self, frame) -> None:
        return None


app = FastAPI(title="BH_CV Compliance Detector", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)


@app.get("/health")
def health() -> dict:
    mq: MessageQueue | None = getattr(app.state, "message_queue", None)
    fs: FrameStore | None = getattr(app.state, "frame_store", None)
    iw: CPUInferenceWorker | None = getattr(app.state, "inference_worker", None)
    cw: ComplianceWorker | None = getattr(app.state, "compliance_worker", None)
    db: Database | None = getattr(app.state, "database", None)

    db_health: dict = {}
    if db is not None:
        db_health = {
            "status": "ok" if db.check_health() else "error",
            "pending_writes": _db_metrics.pending_events,
            "failed_writes": _db_metrics.write_failures,
            "violations_persisted": _db_metrics.violations_persisted,
            "evidence_items_persisted": _db_metrics.evidence_items_persisted,
            "audit_events_persisted": _db_metrics.audit_events_persisted,
        }
    else:
        db_health = {"status": "disabled"}

    # dropped_count is InMemoryMessageQueue-specific; Redis backend omits it.
    _dropped = getattr(mq, "dropped_count", None)
    frames_dropped = _dropped("ingestion.frames") if callable(_dropped) else 0

    # evicted_total is InMemoryFrameStore-specific; Redis TTL handles eviction.
    frames_evicted = getattr(fs, "evicted_total", 0)

    return {
        "status": "ok",
        "ingestion": _ingestion_service.metrics.snapshot() if _ingestion_service else {},
        "message_queue": {
            "frames_queued": mq.qsize("ingestion.frames") if mq else 0,
            "frames_dropped": frames_dropped,
            "detections_queued": mq.qsize("inference.detections") if mq else 0,
            "alerts_queued": mq.qsize("compliance.alert") if mq else 0,
            "evidence_queued": mq.qsize("evidence.capture") if mq else 0,
        },
        "frame_store": {
            "frames_held": fs.size() if fs else 0,
            "frames_evicted_total": frames_evicted,
        },
        "inference": iw.metrics.snapshot() if iw else {},
        "compliance": cw.metrics.snapshot() if cw else {},
        "database": db_health,
    }


def _violation_to_dict(v, session=None) -> dict:
    washing_duration = None
    if session is not None:
        try:
            tm = (
                session.query(TemporalMetric)
                .filter(
                    TemporalMetric.camera_id == v.camera_id,
                    TemporalMetric.zone_id == v.zone_id,
                    TemporalMetric.track_id == v.track_id,
                    TemporalMetric.evaluated_at <= v.confirmed_at,
                )
                .order_by(TemporalMetric.evaluated_at.desc())
                .first()
            )
            if tm is not None:
                washing_duration = round(tm.washing_duration, 2)
        except Exception:
            pass
    return {
        "group_id": v.group_id,
        "camera_id": v.camera_id,
        "zone_id": v.zone_id,
        "track_id": v.track_id,
        "violation_type": v.violation_type,
        "reason_code": v.reason_code or "",
        "reason": v.reason or "",
        "confirmed_at": v.confirmed_at.isoformat() if v.confirmed_at else None,
        "started_at": v.started_at.isoformat() if v.started_at else None,
        "status": v.status,
        "washing_duration_seconds": washing_duration,
        "required_duration_seconds": _required_washing_duration,
    }


@app.get("/api/violations")
def api_violations(limit: int = 50, camera_id: str | None = None) -> list:
    if _database is None:
        return []
    with _database.session() as session:
        repo = ViolationRepository(session)
        rows = repo.list_recent(camera_id=camera_id, limit=limit)
        return [_violation_to_dict(v, session) for v in rows]


@app.get("/api/events/recent")
def api_recent_events(limit: int = 10) -> list:
    if _database is None:
        return []
    with _database.session() as session:
        repo = ViolationRepository(session)
        rows = repo.list_recent(limit=limit)
        return [_violation_to_dict(v, session) for v in rows]


@app.get("/api/violations/{group_id}/evidence")
def api_evidence(group_id: str) -> dict:
    if _database is None:
        return {"group_id": group_id, "frames": []}
    with _database.session() as session:
        eg_repo = EvidenceGroupRepository(session)
        ei_repo = EvidenceItemRepository(session)
        group = eg_repo.get_by_group_id(group_id)
        if group is None:
            return {"group_id": group_id, "frames": []}
        items = ei_repo.list_for_group(group.id)
        frames = []
        for item in items:
            thumb_b64 = None
            if item.storage_key:
                path = Path(item.storage_key)
                if path.exists():
                    thumb_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            frames.append({
                "frame_id": item.frame_id,
                "sequence_number": item.sequence_number,
                "captured_at": item.captured_at.isoformat() if item.captured_at else None,
                "thumbnail_b64": thumb_b64,
            })
        clip_b64: str | None = None
        clip_path = Path(_evidence_dir) / group_id / "clip.avi"
        if clip_path.exists():
            clip_b64 = base64.b64encode(clip_path.read_bytes()).decode("ascii")

        return {
            "group_id": group_id,
            "camera_id": group.camera_id,
            "zone_id": group.zone_id,
            "frames": frames,
            "clip_b64": clip_b64,
        }
