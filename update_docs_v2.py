"""Update BH_CV_Compliance_Detector_Documentation.docx — v2 delta patch.

Applies all changes not covered by update_docs.py:
  - Corrected compliance.trigger_class ("hand_washing" not "handwash")
  - New config fields: presence_confidence, tracker, washing_confidence,
    max_gap_seconds, draw_bboxes, debug.video_saving
  - ByteTrack integration note
  - Video clip saving (debug.video_saving -> data/result/{session_id}/detected.avi)
  - Evidence API clip_b64 field
  - InfrastructureFactory (backend/app/infrastructure/factory.py)
  - CorrelationIdMiddleware (backend/app/middleware/)
  - Updated startup order (matches current main.py)
  - Updated file structure (factory, middleware, violation_detail component)
  - Updated frontend violation_detail component
"""
from __future__ import annotations

from docx import Document
from docx.shared import Pt, Inches
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

DOC_PATH = "BH_CV_Compliance_Detector_Documentation.docx"
doc = Document(DOC_PATH)


# ── Helpers ──────────────────────────────────────────────────────────────────

def find_para(fragment: str) -> int | None:
    for i, p in enumerate(doc.paragraphs):
        if fragment in p.text:
            return i
    return None


def set_para_text(idx: int, text: str) -> None:
    para = doc.paragraphs[idx]
    for run in para.runs:
        run.text = ""
    if para.runs:
        para.runs[0].text = text
    else:
        para.add_run(text)


def replace_text(idx: int, old: str, new: str) -> None:
    para = doc.paragraphs[idx]
    for run in para.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)


def add_code_block(doc, code: str):
    p = doc.add_paragraph(code, style="Normal")
    for run in p.runs:
        run.font.name = "Courier New"
        run.font.size = Pt(8)
    p.paragraph_format.left_indent = Inches(0.3)
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F2F2F2")
    pPr.append(shd)
    return p


def add_bullet(doc, text: str):
    return doc.add_paragraph(text, style="List Bullet")


def add_table_row(table, *cols):
    row = table.add_row()
    for i, text in enumerate(cols):
        row.cells[i].text = text
    return row


# ── 1. Fix compliance trigger_class ("hand_washing" not "handwash") ──────────
# Update in the config code block (Section 8.1 area)
idx = find_para('trigger_class: "handwash"')
if idx is not None:
    replace_text(idx, 'trigger_class: "handwash"', 'trigger_class: "hand_washing"')
    print("Fixed: compliance.trigger_class")

# Also fix in the full config block from update_docs.py
idx = find_para('trigger_class: "handwash"')
while idx is not None:
    replace_text(idx, 'trigger_class: "handwash"', 'trigger_class: "hand_washing"')
    idx = find_para('trigger_class: "handwash"')


# ── 2. Update full config.yaml section ───────────────────────────────────────
# Find and replace the config block with the latest config.yaml content
idx = find_para("# BH_CV Compliance Detector — runtime configuration")
if idx is not None:
    new_config = (
        "# BH_CV Compliance Detector — runtime configuration\n\n"
        "stream:\n"
        '  type: video                        # "video" | "rtsp"\n'
        '  camera_id: "handwash-camera-01"\n'
        "  video:\n"
        '    path: "data/videos"\n'
        "    playback_mode: realtime\n"
        "    loop: false\n"
        "  rtsp:\n"
        '    url: "${RTSP_URL}"\n'
        "  reconnect:\n"
        "    initial_delay_seconds: 1.0\n"
        "    max_delay_seconds: 15.0\n"
        "  sampling:\n"
        "    target_fps: 5.0\n"
        "  buffer:\n"
        "    max_size: 1\n"
        "    strategy: latest\n\n"
        "models:\n"
        "  handwashing:\n"
        "    use_case: handwashing\n"
        '    path: "artifacts/models/handwash_detection.pt"\n'
        "    confidence: 0.5             # washing threshold\n"
        "    presence_confidence: 0.25   # presence threshold (detect anyone near sink)\n"
        "    device: cpu\n"
        "    image_size: 640\n"
        '    tracker: "bytetrack.yaml"   # Ultralytics built-in tracker (set null = IoUTracker)\n\n'
        "zones:\n"
        "  handwash_zone:\n"
        "    models: [handwashing]\n\n"
        "cameras:\n"
        "  handwash-camera-01:\n"
        "    zones: [handwash_zone]\n\n"
        "inference:\n"
        "  queue_size: 10\n"
        "  workers: 1\n"
        "  warmup: true\n"
        "  thumbnail:\n"
        "    enabled: true\n"
        "    max_width: 320\n"
        "    jpeg_quality: 70\n"
        "    draw_bboxes: true           # draw YOLO boxes on evidence thumbnails\n\n"
        "compliance:\n"
        '  trigger_class: "hand_washing"   # YOLO class name for active washing\n'
        "  washing_confidence: 0.5         # min confidence to treat as active washing\n"
        "  handwash:\n"
        "    minimum_washing_duration_seconds: 5.0\n"
        "    absence_threshold_seconds: 5.0\n"
        "    require_soap: false\n"
        "    require_water: false\n"
        "    require_sequence: false\n"
        "    require_completion: false\n"
        "    evidence_buffer_max: 10\n"
        "    max_gap_seconds: 5.0        # max gap between observations before continuity breaks\n\n"
        "state_store:\n"
        '  backend: redis                   # "in_memory" | "redis"\n'
        '  key_prefix: "cv:state"\n'
        "  ttl_seconds: 3600\n\n"
        "topics:\n"
        "  detection_events: inference.detections\n"
        "  compliance_alert: compliance.alert\n"
        "  evidence_capture: evidence.capture\n\n"
        "runtime:\n"
        "  message_queue_backend: redis     # memory | redis\n"
        "  frame_store_backend: redis       # memory | redis\n\n"
        "redis:\n"
        "  enabled: true\n"
        '  url: "${REDIS_URL}"\n'
        "  socket_timeout_seconds: 10.0\n"
        "  socket_connect_timeout_seconds: 5.0\n"
        "  health_check_interval_seconds: 30\n"
        "  streams:\n"
        '    frame_ingested: "cv:frame:ingested"\n'
        '    detection_created: "cv:detection:created"\n'
        '    compliance_alert: "cv:compliance:alert"\n'
        '    evidence_capture: "cv:evidence:capture"\n'
        "    max_length: 10000\n"
        "    approximate_trim: true\n"
        "  frame_store:\n"
        "    ttl_seconds: 30\n"
        '    key_prefix: "cv:frame"\n'
        "  consumer:\n"
        "    pending_idle_timeout_ms: 60000\n"
        "    recovery_interval_seconds: 10\n\n"
        "debug:\n"
        "  frame_saving:\n"
        "    max_frames: 200              # 0 = disabled; cap per subfolder per session\n"
        "  video_saving:\n"
        "    enabled: true\n"
        "    fps: 5.0                     # should match sampling.target_fps\n"
        '    filename: "detected.avi"     # output in data/result/{session_id}/\n\n'
        "evidence:\n"
        '  output_dir: "evidence"\n\n'
        "database:\n"
        "  enabled: true\n"
        '  url: "${DATABASE_URL}"\n'
        "  pool:\n"
        "    min_size: 2\n"
        "    max_size: 10\n"
        "  timeout_seconds: 10\n\n"
        "persistence:\n"
        "  enabled: true\n"
        "  detections:\n"
        "    enabled: true\n"
        "    batch_size: 100\n"
        "    flush_interval_seconds: 1.0\n"
        "  observations:\n"
        "    enabled: true\n"
        "    batch_size: 100\n"
        "    flush_interval_seconds: 1.0\n"
        "  frame_metadata:\n"
        "    enabled: false\n"
        "  state_transitions:\n"
        "    enabled: true\n"
        "  temporal_metrics:\n"
        "    enabled: true\n"
        "  compliance_evaluations:\n"
        "    enabled: true\n"
        "  violations:\n"
        "    enabled: true\n"
        "  evidence:\n"
        "    enabled: true\n"
        "  audit:\n"
        "    enabled: true\n\n"
        "retention:\n"
        "  frame_metadata_days: 7\n"
        "  detections_days: 30\n"
        "  observations_days: 30\n"
        "  temporal_metrics_days: 90\n"
        "  compliance_evaluations_days: 90\n"
        "  violations_days: 365\n"
        "  evidence_metadata_days: 365\n"
        "  audit_logs_days: 730"
    )
    set_para_text(idx, new_config)
    print("Updated: config.yaml section")


# ── 3. Update startup order (Section 9) ──────────────────────────────────────
idx = find_para("InMemoryFrameStore")
if idx is not None:
    set_para_text(idx,
        "\nStartup order (from lifespan in backend/app/main.py):\n"
        "  1. build_frame_store()         (InMemoryFrameStore or RedisFrameStore via factory)\n"
        "  2. build_message_queue()       (InMemoryMessageQueue or RedisStreamMessageQueue via factory)\n"
        "  3. build_state_store()         (InMemoryStateStore or RedisStateStore via factory)\n"
        "  4. PostgreSQL Database         (optional — pipeline runs without DB if disabled)\n"
        "  5. StreamIngestionService      (VideoConnector / RTSPConnector + FpsSampler)\n"
        "  6. ModelRegistry               (eager YOLO model load + warmup via StaticModelResolver)\n"
        "  7. YoloInferenceEngine         (ThumbnailGenerator, draw_bboxes, video saving wired)\n"
        "  8. ComplianceRuleEngine        (IoUTracker/ByteTrack, ObservationBuilder, StateMachine,\n"
        "                                  SpatioTemporalAnalyzer, HandwashRuleEvaluator)\n"
        "  9. PersistenceWorker           (only instantiated if DB is available)\n"
        " 10. ComplianceWorker.start()    (background thread)\n"
        " 11. CPUInferenceWorker.start()  (background thread)\n"
        " 12. PersistenceWorker.start()   (background thread, if DB available)\n"
        " 13. asyncio.create_task(ingestion_service.run())  (async ingestion loop)\n"
    )
    print("Updated: startup order")


# ── 4. Update evidence API response schema (add clip_b64) ────────────────────
idx = find_para('"thumbnail_b64":')
if idx is not None:
    replace_text(idx, '"thumbnail_b64": thumb_b64', '"thumbnail_b64": <base64 JPEG string>')
    print("Updated: evidence thumbnail field")

idx = find_para('"group_id": group_id')
if idx is not None:
    set_para_text(idx,
        '{\n'
        '  "group_id": "96dc6a11-...",\n'
        '  "camera_id": "handwash-camera-01",\n'
        '  "zone_id": "handwash_zone",\n'
        '  "frames": [\n'
        '    {\n'
        '      "frame_id": "...",\n'
        '      "sequence_number": 0,\n'
        '      "captured_at": "2026-09-09T10:00:00+05:30",\n'
        '      "thumbnail_b64": "<base64 JPEG string>"\n'
        '    }\n'
        '  ],\n'
        '  "clip_b64": "<base64 AVI clip — null if not recorded>"\n'
        '}'
    )
    print("Updated: evidence response schema")


# ── 5. Update file structure (add factory, middleware, violation_detail) ──────
idx = find_para("config/config.yaml")
if idx is not None:
    set_para_text(idx,
        "\nBH_CV_Compliance_Detector/\n"
        "│\n"
        "├── config/\n"
        "│   └── config.yaml                   Runtime configuration\n"
        "│\n"
        "├── artifacts/\n"
        "│   └── models/handwash_detection.pt  Trained YOLO11n weights (pre-built)\n"
        "│\n"
        "├── backend/app/\n"
        "│   ├── main.py                       FastAPI lifespan, REST API endpoints\n"
        "│   ├── logging_config.py             structlog JSON logging (stdout + rotating file)\n"
        "│   ├── middleware/\n"
        "│   │   └── correlation_id.py         CorrelationIdMiddleware — per-request UUID via structlog contextvars\n"
        "│   ├── ingestion/                    StreamIngestionService, connectors, sampler, publisher, factory\n"
        "│   ├── inference/                    YoloInferenceEngine, ModelRegistry, ThumbnailGenerator\n"
        "│   ├── compliance/                   Rule engine, state machine, tracker, evidence, worker\n"
        "│   └── infrastructure/\n"
        "│       ├── factory.py                build_frame_store / build_message_queue / build_state_store\n"
        "│       ├── frame_store/              FrameStore ABC + InMemoryFrameStore + RedisFrameStore\n"
        "│       ├── message_queue/            MessageQueue ABC + InMemoryMessageQueue + RedisStreamMessageQueue\n"
        "│       ├── state_store/              StateStore ABC + InMemoryStateStore + RedisStateStore\n"
        "│       ├── redis/                    RedisConnectionManager, RedisConfig, keys, metrics\n"
        "│       └── database/                 SQLAlchemy engine, 20-table schema, repositories,\n"
        "│                                     PersistenceWorker, AuditService\n"
        "│\n"
        "├── frontend/\n"
        "│   ├── app.py                        Streamlit main dashboard (KPI cards, camera status, violations)\n"
        "│   ├── pages/\n"
        "│   │   ├── 1_Cameras.py              Per-camera detail + pipeline stages + compliance state\n"
        "│   │   ├── 2_Violations.py           Full violation history table with filters + evidence viewer\n"
        "│   │   ├── 3_System_Health.py        Queue depths, FPS, DB metrics\n"
        "│   │   └── 4_Settings.py             Data source toggle, API URL configuration\n"
        "│   ├── components/\n"
        "│   │   ├── styles.py                 CSS injection (dark theme)\n"
        "│   │   ├── kpi_cards.py              Compliance rate, violations today, system FPS cards\n"
        "│   │   ├── camera_card.py            Per-camera status card\n"
        "│   │   ├── pipeline_view.py          Pipeline stage status visualization\n"
        "│   │   ├── compliance_state.py       Handwash compliance state indicator\n"
        "│   │   ├── violation_table.py        Violation list/recent events table\n"
        "│   │   ├── violation_detail.py       Inline violation detail panel with evidence thumbnails + clip\n"
        "│   │   ├── notifications.py          Toast-style violation notifications\n"
        "│   │   └── sidebar.py                Shared sidebar (data source, auto-refresh)\n"
        "│   ├── domain/models.py              Frontend display models (Violation, CameraStatus, etc.)\n"
        "│   └── repository/\n"
        "│       ├── base.py                   DashboardRepository ABC\n"
        "│       ├── mock.py                   MockDashboardRepository (time-based simulation)\n"
        "│       └── api.py                    ApiDashboardRepository (calls FastAPI backend)\n"
        "│\n"
        "├── alembic/                          Database migration scripts\n"
        "├── alembic.ini                       Alembic configuration\n"
        "├── data/videos/                      Input video files\n"
        "├── data/result/{session_id}/         Debug frame output:\n"
        "│                                       frames/         raw frames\n"
        "│                                       sample_frames/  FpsSampler output\n"
        "│                                       detected_frames/ YOLO-annotated frames\n"
        "│                                       detected.avi    recorded clip (if video_saving enabled)\n"
        "├── evidence/{group_id}/              Frozen JPEG thumbnails + clip.avi per violation\n"
        "├── logs/bh_cv.log                    Rotating structured JSON log (100 MB × 3)\n"
        "└── tests/                            Unit tests (compliance, ingestion, infrastructure)\n"
    )
    print("Updated: file structure")


# ── 6. Add new appendix sections at end of document ──────────────────────────

doc.add_page_break()

# ── Section 19: ByteTrack Integration ────────────────────────────────────────
doc.add_heading("19. ByteTrack Integration", level=1)
doc.add_paragraph(
    "The YOLO model can optionally use Ultralytics' built-in ByteTrack tracker "
    "instead of the custom IoUTracker. ByteTrack is a multi-object tracker that "
    "maintains track IDs across frames using motion and appearance cues, providing "
    "more robust tracking under occlusion."
)

doc.add_heading("19.1 Configuration", level=2)
doc.add_paragraph(
    "Set tracker: \"bytetrack.yaml\" on any model entry in config.yaml to enable "
    "ByteTrack for that model. Setting tracker: null (or omitting the field) falls "
    "back to the project's built-in IoUTracker."
)
add_code_block(doc,
    "models:\n"
    "  handwashing:\n"
    "    use_case: handwashing\n"
    '    path: "artifacts/models/handwash_detection.pt"\n'
    "    confidence: 0.5\n"
    "    presence_confidence: 0.25   # presence threshold — anyone near the sink\n"
    '    tracker: "bytetrack.yaml"   # Ultralytics built-in tracker\n'
    "    # tracker: null             # fall back to IoUTracker\n"
)

doc.add_heading("19.2 presence_confidence Field", level=2)
doc.add_paragraph(
    "The presence_confidence field is a second threshold below the main confidence "
    "threshold. It allows the engine to detect that a person is near the sink "
    "(presence) even if their hands are not actively washing (confidence < main threshold). "
    "This distinction enables the state machine to enter PRESENCE_DETECTED state "
    "and start the absence timer before the person begins washing."
)
doc.add_paragraph(
    "Example: confidence=0.5 means hands_interacting=True (active washing). "
    "presence_confidence=0.25 means the person is detected near the sink but "
    "may not be washing yet."
)


# ── Section 20: Video Clip Saving ─────────────────────────────────────────────
doc.add_page_break()
doc.add_heading("20. Video Clip Saving", level=1)
doc.add_paragraph(
    "When debug.video_saving.enabled is true in config.yaml, the YoloInferenceEngine "
    "records an AVI video clip of all detected frames (frames with at least one YOLO "
    "detection). One clip is saved per video session (new session_id per video file open)."
)

doc.add_heading("20.1 Configuration", level=2)
add_code_block(doc,
    "debug:\n"
    "  video_saving:\n"
    "    enabled: true\n"
    "    fps: 5.0           # should match stream.sampling.target_fps\n"
    '    filename: "detected.avi"\n'
)

doc.add_heading("20.2 Output Location", level=2)
add_code_block(doc,
    "data/result/{session_id}/\n"
    "  frames/             Raw frames (all, up to max_frames)\n"
    "  sample_frames/      Frames that passed FpsSampler\n"
    "  detected_frames/    YOLO-annotated frames (bounding boxes drawn)\n"
    "  detected.avi        Recorded clip of detected frames\n"
)
doc.add_paragraph(
    "The clip writer is opened lazily on the first detected frame "
    "and closed gracefully on engine.close(). If video_saving is disabled, "
    "no clip is produced and the API's clip_b64 field returns null."
)

doc.add_heading("20.3 Evidence Clip", level=2)
doc.add_paragraph(
    "For confirmed violations, the compliance rule engine also saves a violation "
    "evidence clip at evidence/{group_id}/clip.avi alongside the individual JPEG "
    "thumbnails. This clip is served base64-encoded via the REST API:"
)
add_code_block(doc,
    "GET /api/violations/{group_id}/evidence\n\n"
    "Response:\n"
    "{\n"
    '  "group_id": "96dc6a11-...",\n'
    '  "camera_id": "handwash-camera-01",\n'
    '  "zone_id": "handwash_zone",\n'
    '  "frames": [\n'
    "    {\n"
    '      "frame_id": "...", "sequence_number": 0,\n'
    '      "captured_at": "2026-09-09T10:00:00+05:30",\n'
    '      "thumbnail_b64": "<base64 JPEG>"\n'
    "    }, ...\n"
    "  ],\n"
    '  "clip_b64": "<base64 AVI clip — null if no clip saved>"\n'
    "}"
)


# ── Section 21: Infrastructure Factory ───────────────────────────────────────
doc.add_page_break()
doc.add_heading("21. Infrastructure Factory", level=1)
doc.add_paragraph(
    "backend/app/infrastructure/factory.py provides three factory functions that "
    "read config.yaml and return the appropriate infrastructure implementation. "
    "This centralises backend selection logic and keeps main.py free of if/else chains."
)

infra_table = doc.add_table(rows=1, cols=3)
infra_table.style = "Table Grid"
hdr = infra_table.rows[0].cells
hdr[0].text = "Factory Function"
hdr[1].text = "Config Key"
hdr[2].text = "Returns"

infra_rows = [
    ("build_frame_store(cfg, camera_id, frame_ttl_seconds)",
     "runtime.frame_store_backend",
     '"memory" → InMemoryFrameStore; "redis" → RedisFrameStore'),
    ("build_message_queue(cfg, max_size_per_topic)",
     "runtime.message_queue_backend",
     '"memory" → InMemoryMessageQueue; "redis" → RedisStreamMessageQueue'),
    ("build_state_store(cfg)",
     "state_store.backend",
     '"in_memory" → InMemoryStateStore; "redis" → RedisStateStore'),
]
for func, key, returns in infra_rows:
    r = infra_table.add_row()
    r.cells[0].text = func
    r.cells[1].text = key
    r.cells[2].text = returns


# ── Section 22: CorrelationIdMiddleware ───────────────────────────────────────
doc.add_heading("22. Correlation ID Middleware", level=1)
doc.add_paragraph(
    "backend/app/middleware/correlation_id.py adds CorrelationIdMiddleware to the "
    "FastAPI application. For each incoming HTTP request, it reads or generates a "
    "correlation_id UUID and binds it to structlog's contextvars, so every log event "
    "emitted during that request automatically includes the request's correlation_id. "
    "The ID is also returned in the X-Correlation-ID response header."
)
add_code_block(doc,
    "# FastAPI wiring (backend/app/main.py)\n"
    "app.add_middleware(CorrelationIdMiddleware)\n\n"
    "# Incoming header (optional — generated if absent):\n"
    "X-Correlation-ID: <uuid4>\n\n"
    "# Log output per request:\n"
    '{"event": "inference_cycle_start", "correlation_id": "d3a1b2c4-...", ...}'
)


# ── Section 23: Updated Tech Stack table ─────────────────────────────────────
doc.add_page_break()
doc.add_heading("23. Complete Technology Stack (Current)", level=1)

ts_table = doc.add_table(rows=1, cols=3)
ts_table.style = "Table Grid"
hdr = ts_table.rows[0].cells
hdr[0].text = "Layer"
hdr[1].text = "Technology"
hdr[2].text = "Notes"

ts_rows = [
    ("Language", "Python 3.12", "Primary implementation language"),
    ("Package Manager", "uv + hatchling", "Fast dependency resolution"),
    ("Web Framework", "FastAPI + lifespan", "REST API and startup/shutdown orchestration"),
    ("Frontend", "Streamlit (multi-page)", "5-page dashboard with Mock + Live (API) modes"),
    ("Detection Model", "YOLO11n (Ultralytics)", "Nano variant — CPU inference. AGPL-3.0 licensed."),
    ("Tracker", "ByteTrack (Ultralytics built-in)", "Per-model; falls back to IoUTracker when tracker: null"),
    ("Compliance Logic", "Custom rule engine", "State machine + temporal analyzer (no ML)"),
    ("Logging", "Structlog", "Structured JSON logs, kwargs style; correlation_id per request/frame"),
    ("Middleware", "CorrelationIdMiddleware", "Binds correlation_id to structlog contextvars per request"),
    ("Video I/O", "OpenCV (cv2)", "Frame capture, thumbnail generation, AVI clip recording"),
    ("Concurrency", "Python threading + asyncio", "Ingestion is async coroutine; inference/compliance/persistence are threads"),
    ("Frame Store", "InMemoryFrameStore / RedisFrameStore", "Selected via runtime.frame_store_backend in config.yaml"),
    ("Message Queue", "InMemoryMessageQueue / RedisStreamMessageQueue", "Selected via runtime.message_queue_backend; 4 Redis Streams"),
    ("State Store", "InMemoryStateStore / RedisStateStore", "Selected via state_store.backend; Redis key TTL=3600s"),
    ("Database", "PostgreSQL + SQLAlchemy 2.0 + Alembic", "Optional; 20-table schema; psycopg2-binary driver"),
    ("ORM / Migrations", "SQLAlchemy 2.0 (scoped_session) + Alembic", "20 tables; repositories per entity"),
    ("Infrastructure Factory", "backend/app/infrastructure/factory.py", "Centralised backend selection for frame_store/mq/state_store"),
]
for layer, tech, notes in ts_rows:
    r = ts_table.add_row()
    r.cells[0].text = layer
    r.cells[1].text = tech
    r.cells[2].text = notes


# ── Save ──────────────────────────────────────────────────────────────────────
doc.save(DOC_PATH)
print("Document updated successfully — v2 patch applied.")
