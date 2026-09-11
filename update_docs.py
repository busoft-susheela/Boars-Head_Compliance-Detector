"""Update BH_CV_Compliance_Detector_Documentation.docx with current implementation."""
from __future__ import annotations

from copy import deepcopy
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re

DOC_PATH = "BH_CV_Compliance_Detector_Documentation.docx"

doc = Document(DOC_PATH)


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_para(text_fragment: str) -> int | None:
    for i, p in enumerate(doc.paragraphs):
        if text_fragment in p.text:
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


def replace_para_text(idx: int, old: str, new: str) -> None:
    para = doc.paragraphs[idx]
    for run in para.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)


def add_heading(doc, text: str, level: int = 1):
    p = doc.add_heading(text, level=level)
    return p


def add_code_block(doc, code: str):
    p = doc.add_paragraph(code, style="Normal")
    for run in p.runs:
        run.font.name = "Courier New"
        run.font.size = Pt(8)
    p.paragraph_format.left_indent = Inches(0.3)
    return p


def add_bullet(doc, text: str):
    return doc.add_paragraph(text, style="List Bullet")


# ── 1. Update version line ────────────────────────────────────────────────────
idx = find_para("Version 1.0")
if idx is not None:
    replace_para_text(idx, "Version 1.0", "Version 2.0")
    replace_para_text(idx, "MVP Release", "Production Release")

# ── 2. Update scope bullets (section 1.1) ────────────────────────────────────
idx = find_para("In-memory state (no external database or message broker)")
if idx is not None:
    set_para_text(idx, "Redis-backed frame store, message queue (Redis Streams), and state store")

# Add missing bullets after single-process deployment
idx = find_para("Single process deployment")
if idx is not None:
    # These will be inserted after — but docx doesn't easily insert mid-doc,
    # so we just update the existing text and note it's expanded below.
    pass

# ── 3. Update Tech Stack table (first table in doc) ──────────────────────────
# Table 0 is the tech stack table based on document structure
tech_table = doc.tables[0]
# Find the row with "Backend" and add new rows
rows_text = [[c.text for c in row.cells] for row in tech_table.rows]

# Update existing cells where needed
for row in tech_table.rows:
    cells = row.cells
    if len(cells) >= 2:
        if "In-Memory" in cells[1].text or "in-memory" in cells[1].text:
            cells[1].text = "Redis Streams (MessageQueue), Redis (FrameStore, StateStore)"
        if "FastAPI" in cells[0].text or "Backend" in cells[0].text:
            # Append to backend cell
            pass

# Add new rows to tech stack table
def add_table_row(table, col1: str, col2: str):
    row = table.add_row()
    row.cells[0].text = col1
    row.cells[1].text = col2
    return row

# Check if PostgreSQL row exists, add if not
has_postgres = any("PostgreSQL" in c.text or "psycopg" in c.text
                   for row in tech_table.rows for c in row.cells)
if not has_postgres:
    add_table_row(tech_table, "Database", "PostgreSQL + SQLAlchemy 2.0 + Alembic migrations (psycopg2-binary)")
    add_table_row(tech_table, "Message Broker", "Redis 7+ — Redis Streams for frame/detection/compliance/evidence topics")
    add_table_row(tech_table, "State Store", "Redis (RedisStateStore) — JSON-serialised zone state, TTL=3600s")
    add_table_row(tech_table, "Frontend", "Streamlit — live dashboard with Mock and Live (API) modes")
    add_table_row(tech_table, "ORM / Migrations", "SQLAlchemy 2.0 (scoped_session) + Alembic, 20-table schema")

# ── 4. Update Section 6.1 StateStore ─────────────────────────────────────────
idx = find_para("InMemoryStateStore")
if idx is not None:
    para = doc.paragraphs[idx]
    for run in para.runs:
        run.text = run.text.replace("InMemoryStateStore", "InMemoryStateStore / RedisStateStore")

idx = find_para("Unaware of handwashing, compliance, or YOLO. Stores only plain")
if idx is not None:
    set_para_text(idx,
        "Generic key/value persistence interface. Two implementations: InMemoryStateStore (testing) "
        "and RedisStateStore (production). RedisStateStore serialises zone state as JSON under key "
        "cv:state:{camera_id}:{zone_id} with TTL=3600s (reset on every write). Selected via "
        "state_store.backend in config.yaml ('in_memory' | 'redis').")

# ── 5. Update Section 8.1 config.yaml ────────────────────────────────────────
idx = find_para("# BH_CV Compliance Detector — runtime configuration")
if idx is not None:
    new_config = """# BH_CV Compliance Detector — runtime configuration

stream:
  type: video                        # "video" | "rtsp"
  camera_id: "handwash-camera-01"
  video:
    path: "data/videos"
    playback_mode: realtime
    loop: false
  rtsp:
    url: "${RTSP_URL}"
  reconnect:
    initial_delay_seconds: 1.0
    max_delay_seconds: 15.0
  sampling:
    target_fps: 5.0
  buffer:
    max_size: 1
    strategy: latest

models:
  handwashing:
    use_case: handwashing
    path: "artifacts/models/handwash_detection.pt"
    confidence: 0.5
    device: cpu
    image_size: 640

zones:
  handwash_zone:
    models: [handwashing]

cameras:
  handwash-camera-01:
    zones: [handwash_zone]

inference:
  queue_size: 10
  workers: 1
  warmup: true
  thumbnail:
    enabled: true
    max_width: 320
    jpeg_quality: 70

compliance:
  trigger_class: "handwash"
  handwash:
    minimum_washing_duration_seconds: 5.0
    absence_threshold_seconds: 5.0
    require_soap: false
    require_water: false
    require_sequence: false
    require_completion: false
    evidence_buffer_max: 10

state_store:
  backend: redis                     # "in_memory" | "redis"
  key_prefix: "cv:state"
  ttl_seconds: 3600

topics:
  detection_events: inference.detections
  compliance_alert: compliance.alert
  evidence_capture: evidence.capture

runtime:
  message_queue_backend: redis       # "memory" | "redis"
  frame_store_backend: redis         # "memory" | "redis"

redis:
  enabled: true
  url: "${REDIS_URL}"
  socket_timeout_seconds: 10.0
  socket_connect_timeout_seconds: 5.0
  health_check_interval_seconds: 30
  streams:
    frame_ingested: "cv:frame:ingested"
    detection_created: "cv:detection:created"
    compliance_alert: "cv:compliance:alert"
    evidence_capture: "cv:evidence:capture"
    max_length: 10000
    approximate_trim: true
  frame_store:
    ttl_seconds: 30
    key_prefix: "cv:frame"
  consumer:
    pending_idle_timeout_ms: 60000
    recovery_interval_seconds: 10

debug:
  frame_saving:
    max_frames: 200                  # 0 = disabled; cap per subfolder

evidence:
  output_dir: "evidence"

database:
  enabled: true
  url: "${DATABASE_URL}"
  pool:
    min_size: 2
    max_size: 10
  timeout_seconds: 10

persistence:
  enabled: true
  detections:
    enabled: true
    batch_size: 100
    flush_interval_seconds: 1.0
  observations:
    enabled: true
    batch_size: 100
    flush_interval_seconds: 1.0
  frame_metadata:
    enabled: false
  state_transitions:
    enabled: true
  temporal_metrics:
    enabled: true
  compliance_evaluations:
    enabled: true
  violations:
    enabled: true
  evidence:
    enabled: true
  audit:
    enabled: true

retention:
  frame_metadata_days: 7
  detections_days: 30
  observations_days: 30
  temporal_metrics_days: 90
  compliance_evaluations_days: 90
  violations_days: 365
  evidence_metadata_days: 365
  audit_logs_days: 730"""
    set_para_text(idx, new_config)

# ── 6. Update Section 8.3 Environment Variables ───────────────────────────────
idx = find_para("LOG_LEVEL=INFO")
if idx is not None:
    set_para_text(idx,
        "LOG_LEVEL=INFO\n"
        "FRAME_TTL_SEC=5.0\n"
        "REDIS_URL=redis://localhost:6379/0\n"
        "DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/bh_cv\n"
        "# Alternative: set individual POSTGRES_* vars instead of DATABASE_URL\n"
        "# POSTGRES_HOST=localhost\n"
        "# POSTGRES_PORT=5432\n"
        "# POSTGRES_USERNAME=user\n"
        "# POSTGRES_PASSWORD=password\n"
        "# POSTGRES_DB=bh_cv"
    )

# ── 7. Update Section 9 Startup Order ────────────────────────────────────────
idx = find_para("InMemoryFrameStore")
if idx is not None:
    set_para_text(idx,
        "\nStartup order:\n"
        "  1. RedisConnectionManager  (Redis Streams + frame store)\n"
        "  2. RedisFrameStore         (frame bytes keyed by frame_id, TTL=30s)\n"
        "  3. RedisStreamMessageQueue (4 Redis Streams: frames/detections/alerts/evidence)\n"
        "  4. RedisStateStore         (JSON zone state, TTL=3600s)\n"
        "  5. PostgreSQL Database     (connection pool, Alembic-managed schema)\n"
        "  6. StreamIngestionService  (VideoConnector / RTSPConnector + FpsSampler)\n"
        "  7. ModelRegistry           (eager YOLO model load + warmup)\n"
        "  8. YoloInferenceEngine     (thumbnail generator wired)\n"
        "  9. ComplianceRuleEngine    (IoUTracker, ObservationBuilder, StateMachine, Analyzer, Evaluator)\n"
        " 10. PersistenceWorker       (writes violations/evidence/detections to PostgreSQL)\n"
        " 11. ComplianceWorker        (thread, subscribes to inference.detections)\n"
        " 12. CPUInferenceWorker      (thread, subscribes to ingestion.frames)\n"
        " 13. StreamIngestionService.run()  (asyncio Task)\n"
    )

# ── 8. Update Section 9.1 Health Endpoint ────────────────────────────────────
idx = find_para("\"frames_read\": 1250")
if idx is not None:
    set_para_text(idx,
        '{\n'
        '    "status": "ok",\n'
        '    "ingestion": {\n'
        '        "frames_read": 1250, "frames_dropped": 3, "frames_published_total": 1247,\n'
        '        "current_fps": 4.97, "is_running": true\n'
        '    },\n'
        '    "message_queue": {\n'
        '        "frames_queued": 0, "detections_queued": 0,\n'
        '        "alerts_queued": 0, "evidence_queued": 0\n'
        '    },\n'
        '    "frame_store": { "frames_held": 1, "frames_evicted_total": 0 },\n'
        '    "inference": {\n'
        '        "frames_processed": 1247, "avg_inference_ms": 84.2, "is_running": true\n'
        '    },\n'
        '    "compliance": {\n'
        '        "evaluations_total": 1247, "violations_total": 4, "is_running": true\n'
        '    },\n'
        '    "database": {\n'
        '        "status": "ok", "violations_persisted": 4, "evidence_items_persisted": 32\n'
        '    }\n'
        '}'
    )

# ── 9. Update Section 10 File Structure ──────────────────────────────────────
idx = find_para("config/config.yaml")
if idx is not None:
    set_para_text(idx,
        "\nBH_CV_Compliance_Detector/\n"
        "│\n"
        "├── config/\n"
        "│   └── config.yaml                   Runtime configuration (stream/model/zones/redis/db/persistence)\n"
        "│\n"
        "├── artifacts/\n"
        "│   └── models/handwash_detection.pt  Trained YOLO11n weights (pre-built)\n"
        "│\n"
        "├── backend/app/\n"
        "│   ├── main.py                       FastAPI lifespan, REST API endpoints\n"
        "│   ├── logging_config.py             structlog JSON logging (stdout + rotating file)\n"
        "│   ├── ingestion/                    StreamIngestionService, connectors, sampler, publisher\n"
        "│   ├── inference/                    YoloInferenceEngine, ModelRegistry, ThumbnailGenerator\n"
        "│   ├── compliance/                   Rule engine, state machine, tracker, evidence\n"
        "│   └── infrastructure/\n"
        "│       ├── frame_store/              FrameStore ABC + InMemory + Redis implementations\n"
        "│       ├── message_queue/            MessageQueue ABC + InMemory + RedisStream implementations\n"
        "│       ├── state_store/              StateStore ABC + InMemory + Redis implementations\n"
        "│       ├── redis/                    RedisConnectionManager, serialization (JSON/base64)\n"
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
        "│   ├── components/                   Reusable UI components (KPI cards, violation table, sidebar)\n"
        "│   ├── domain/models.py              Frontend display models (Violation, CameraStatus, etc.)\n"
        "│   └── repository/                   DashboardRepository ABC + Mock + ApiDashboardRepository\n"
        "│\n"
        "├── alembic/                          Database migration scripts\n"
        "├── alembic.ini                       Alembic configuration\n"
        "├── data/videos/                      Input video files\n"
        "├── data/result/{session_id}/         Debug frame output (frames/, sample_frames/, detected_frames/)\n"
        "├── evidence/{group_id}/              Frozen JPEG evidence thumbnails per violation\n"
        "├── logs/bh_cv.log                    Rotating structured JSON log (100 MB × 3)\n"
        "└── tests/                            Unit tests (compliance, ingestion, infrastructure)\n"
    )

# ── 10. Update Section 12.1 Prerequisites ────────────────────────────────────
idx = find_para("uv sync")
if idx is not None:
    set_para_text(idx,
        "# 1. Install dependencies\n"
        "uv sync\n\n"
        "# 2. Start Redis (must be running before the app)\n"
        "docker run -d -p 6379:6379 redis:7-alpine\n\n"
        "# 3. Start PostgreSQL\n"
        "docker run -d -p 5432:5432 -e POSTGRES_DB=bh_cv -e POSTGRES_USER=user -e POSTGRES_PASSWORD=pass postgres:15\n\n"
        "# 4. Create .env file\n"
        "echo 'LOG_LEVEL=INFO' > .env\n"
        "echo 'FRAME_TTL_SEC=5.0' >> .env\n"
        "echo 'REDIS_URL=redis://localhost:6379/0' >> .env\n"
        "echo 'DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/bh_cv' >> .env\n\n"
        "# 5. Run database migrations\n"
        "uv run alembic upgrade head"
    )

# ── 11. Update Section 12.2 Start the Server ─────────────────────────────────
idx = find_para("uvicorn backend.app.main:app --host 0.0.0.0 --port 8000")
if idx is not None:
    set_para_text(idx,
        "# Start backend API (processes video, runs YOLO, writes to DB)\n"
        "uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000\n\n"
        "# Start Streamlit dashboard (separate terminal)\n"
        "uv run streamlit run frontend/app.py --server.port 8501 --server.headless true"
    )

# ── 12. Update Section 13.2 Replacing the State Store ────────────────────────
idx = find_para("Change state_store.backend to 'redis' in config.yaml and create a RedisStateStore")
if idx is not None:
    set_para_text(idx,
        "COMPLETED — RedisStateStore is fully implemented in "
        "backend/app/infrastructure/state_store/redis_store.py. "
        "Switch via state_store.backend: 'redis' in config.yaml (currently active). "
        "State is JSON-serialised under key cv:state:{camera_id}:{zone_id} with TTL=3600s."
    )

# ── 13. Update Section 13.5 Redis-Backed Message Queue ───────────────────────
idx = find_para("The MessageQueue ABC allows drop-in replacement. Implement a RedisMessageQueue")
if idx is not None:
    set_para_text(idx,
        "COMPLETED — RedisStreamMessageQueue is fully implemented in "
        "backend/app/infrastructure/message_queue/redis_stream.py using Redis Streams (XADD/XREADGROUP). "
        "All four topics are Redis Streams: cv:frame:ingested, cv:detection:created, "
        "cv:compliance:alert, cv:evidence:capture. "
        "All messages are serialised as newline-delimited JSON with schema_version and event_type fields. "
        "Switch via runtime.message_queue_backend: 'redis' in config.yaml (currently active)."
    )

# ── 14. Add new sections at the end ──────────────────────────────────────────

doc.add_page_break()

# Section 14: PostgreSQL Schema
h = doc.add_heading("14. PostgreSQL Database Schema", level=1)

doc.add_paragraph(
    "The PersistenceWorker subscribes to compliance.alert and evidence.capture topics and "
    "durably writes all compliance events to PostgreSQL. The database is optional — if disabled, "
    "the CV pipeline continues without interruption. Managed by Alembic migrations."
)

doc.add_heading("14.1 Table Overview (20 tables)", level=2)

# Create schema table
schema_table = doc.add_table(rows=1, cols=3)
schema_table.style = "Table Grid"
hdr = schema_table.rows[0].cells
hdr[0].text = "Table"
hdr[1].text = "Purpose"
hdr[2].text = "Key Fields"

schema_rows = [
    ("cameras", "Camera registration", "camera_id, name, location"),
    ("zones", "Zone definitions per camera", "zone_id, camera_id, name"),
    ("streams", "RTSP/video stream config", "stream_id, camera_id, url, type"),
    ("ingestion_sessions", "One record per video file / RTSP session", "session_id, camera_id, started_at, status"),
    ("processing_sessions", "One record per app startup", "session_id, started_at, config_snapshot"),
    ("video_ingestion", "Metadata per video file played", "video_uuid, filename, native_fps, resolution"),
    ("frames", "Frame metadata (optional, high-freq)", "frame_id, camera_id, captured_at, session_id"),
    ("detections", "YOLO detections per frame", "frame_id, class_name, confidence, bbox"),
    ("tracks", "IoU tracker track records", "track_id, camera_id, zone_id, first_seen_at"),
    ("observations", "Per-frame person observations (REAL + SYNTHETIC)", "track_id, inside_sink_zone, hands_interacting"),
    ("state_transitions", "Compliance state changes", "track_id, previous_state, new_state, duration_seconds"),
    ("temporal_metrics", "Accumulated duration metrics at evaluation time", "washing_duration, at_sink_duration, sequence_valid"),
    ("compliance_rules", "Versioned rule definitions", "rule_key, use_case, configuration (JSONB)"),
    ("compliance_evaluations", "One per rule check (IN_PROGRESS/COMPLIANT/VIOLATION)", "result, reason_code, evaluated_at"),
    ("violations", "Confirmed handwash violations", "group_id, camera_id, zone_id, track_id, confirmed_at"),
    ("evidence_groups", "Frozen evidence bundle per violation", "group_id, violation_id, item_count, frozen_at"),
    ("evidence_items", "One thumbnail per frame in evidence group", "frame_id, sequence_number, storage_key (file path)"),
    ("notifications", "Alert delivery records", "violation_id, channel, status, sent_at"),
    ("audit_logs", "System audit trail", "event_type, entity_type, entity_id, payload (JSONB)"),
    ("alembic_version", "Migration tracking", "version_num"),
]

for name, purpose, fields in schema_rows:
    row = schema_table.add_row()
    row.cells[0].text = name
    row.cells[1].text = purpose
    row.cells[2].text = fields

doc.add_heading("14.2 Evidence File Storage", level=2)
doc.add_paragraph(
    "Thumbnail bytes are written to disk (NOT stored in the database). "
    "PostgreSQL stores only the relative file path in evidence_items.storage_key."
)
add_code_block(doc,
    "evidence/\n"
    "  {group_id}/\n"
    "    000_{frame_id}.jpg   # sequence 0\n"
    "    001_{frame_id}.jpg   # sequence 1\n"
    "    ...                  # up to evidence_buffer_max items\n"
)

doc.add_heading("14.3 Failure Strategy", level=2)
doc.add_paragraph(
    "CRITICAL (retried up to 3×): violations, evidence_groups, evidence_items, audit trail.  "
    "BEST_EFFORT: notifications.  "
    "BATCHABLE: detections, observations (batch_size=100, flush every 1s).  "
    "If the database is unavailable, the CV pipeline continues without interruption — "
    "persistence failures are logged and metered."
)

# Section 15: REST API
doc.add_page_break()
doc.add_heading("15. REST API Reference", level=1)
doc.add_paragraph(
    "The FastAPI backend exposes the following endpoints. All responses are JSON."
)

api_table = doc.add_table(rows=1, cols=3)
api_table.style = "Table Grid"
hdr = api_table.rows[0].cells
hdr[0].text = "Method + Path"
hdr[1].text = "Parameters"
hdr[2].text = "Description"

api_rows = [
    ("GET /health",
     "—",
     "Full pipeline health snapshot: ingestion FPS, inference metrics, queue depths, compliance totals, DB status."),
    ("GET /api/violations",
     "limit (int, default 50), camera_id (str, optional)",
     "List confirmed violations from PostgreSQL, newest first. Includes washing_duration_seconds and required_duration_seconds."),
    ("GET /api/events/recent",
     "limit (int, default 10)",
     "Most recent violations — same schema as /api/violations."),
    ("GET /api/violations/{group_id}/evidence",
     "group_id (path)",
     "Evidence payload for one violation: list of frames with sequence_number, captured_at, thumbnail_b64 (base64 JPEG)."),
]

for method, params, desc in api_rows:
    row = api_table.add_row()
    row.cells[0].text = method
    row.cells[1].text = params
    row.cells[2].text = desc

doc.add_heading("15.1 Violation Response Schema", level=2)
add_code_block(doc,
    '{\n'
    '  "group_id": "96dc6a11-...",\n'
    '  "camera_id": "handwash-camera-01",\n'
    '  "zone_id": "handwash_zone",\n'
    '  "track_id": 86,\n'
    '  "violation_type": "HANDWASH_ABSENCE",\n'
    '  "reason_code": "ABSENCE_THRESHOLD_EXCEEDED",\n'
    '  "reason": "Person at sink without handwashing exceeded absence threshold",\n'
    '  "confirmed_at": "2026-09-08T01:13:24+05:30",\n'
    '  "started_at": null,\n'
    '  "status": "CONFIRMED",\n'
    '  "washing_duration_seconds": null,\n'
    '  "required_duration_seconds": 5.0\n'
    '}'
)

# Section 16: Streamlit Frontend
doc.add_page_break()
doc.add_heading("16. Streamlit Frontend Dashboard", level=1)
doc.add_paragraph(
    "A multi-page Streamlit dashboard provides real-time compliance monitoring. "
    "It supports two data source modes switchable from the sidebar on every page: "
    "Mock (time-based simulation, no backend required) and Live API (reads from the FastAPI backend)."
)

doc.add_heading("16.1 Pages", level=2)
pages_table = doc.add_table(rows=1, cols=3)
pages_table.style = "Table Grid"
hdr = pages_table.rows[0].cells
hdr[0].text = "Page"
hdr[1].text = "File"
hdr[2].text = "Content"

pages_rows = [
    ("Dashboard (Home)", "frontend/app.py",
     "KPI cards (compliance rate, violations today, system FPS), camera/zone status, recent violations table, live notifications for new violations"),
    ("Cameras", "pages/1_Cameras.py",
     "Per-camera detail: ingestion stats, pipeline stage status, live compliance state indicator, state timeline"),
    ("Violations", "pages/2_Violations.py",
     "Full violation history table with filters (camera, zone, reason), violation detail panel, evidence thumbnail strip"),
    ("System Health", "pages/3_System_Health.py",
     "Queue depths, inference FPS, DB write metrics, worker status"),
    ("Settings", "pages/4_Settings.py",
     "Data source selection, API base URL configuration"),
]

for page, file, content in pages_rows:
    row = pages_table.add_row()
    row.cells[0].text = page
    row.cells[1].text = file
    row.cells[2].text = content

doc.add_heading("16.2 Repository Pattern", level=2)
doc.add_paragraph(
    "All data access goes through DashboardRepository (frontend/repository/base.py). "
    "Two implementations:"
)
add_bullet(doc, "MockDashboardRepository — time-based simulation with a 60-second handwash cycle. No backend required. Safe to use during development.")
add_bullet(doc, "ApiDashboardRepository — calls /health, /api/violations, /api/events/recent, /api/violations/{group_id}/evidence. Parses responses into domain models.")

doc.add_heading("16.3 Starting the Dashboard", level=2)
add_code_block(doc,
    "# Ensure backend is running on port 8000 first\n"
    "uv run streamlit run frontend/app.py --server.port 8501 --server.headless true\n\n"
    "# Then open: http://localhost:8501\n"
    "# Switch sidebar → Live (API) to see real compliance results"
)

# Section 17: Debug Frame Saving
doc.add_page_break()
doc.add_heading("17. Debug Frame Saving", level=1)
doc.add_paragraph(
    "Controlled by debug.frame_saving.max_frames in config.yaml (0 = disabled). "
    "When enabled, up to max_frames frames are saved per subfolder per session. "
    "A new session_id (UUID) is generated each time a video file is opened."
)

doc.add_heading("17.1 Output Layout", level=2)
add_code_block(doc,
    "data/result/{session_id}/\n"
    "  frames/           Raw frames as read from the video source (every frame)\n"
    "  sample_frames/    Frames that passed the FpsSampler (at target_fps)\n"
    "  detected_frames/  Sample frames with YOLO bounding boxes drawn (only when detections > 0)\n"
)

doc.add_paragraph(
    "session_id is propagated through the full pipeline: VideoConnector → FrameEvent → "
    "FrameEnvelope (Redis serialisation) → YoloInferenceEngine. "
    "The Redis serialiser explicitly encodes and decodes session_id to prevent silent data loss."
)

doc.add_heading("17.2 Detected Frame Annotations", level=2)
doc.add_paragraph(
    "Detected frames show green bounding boxes with label text "
    "(class_name + confidence score). Only frames where YOLO found at least one detection are saved, "
    "preventing clutter from empty frames."
)

# Section 18: Structured Logging
doc.add_heading("18. Structured Logging", level=1)
doc.add_paragraph(
    "All logging uses structlog with JSON output. Every log event includes: "
    "correlation_id (per-frame UUID, set via structlog.contextvars), level, timestamp (ISO-8601 UTC), "
    "and event-specific key-value pairs. No positional log messages."
)

doc.add_heading("18.1 Log Sinks", level=2)
add_bullet(doc, "stdout — newline-delimited JSON (consumed by container log aggregators)")
add_bullet(doc, "logs/bh_cv.log — rotating file, 100 MB × 3 backups (delay=True to avoid Windows file-lock conflicts)")

doc.add_heading("18.2 Key Log Events", level=2)
log_table = doc.add_table(rows=1, cols=2)
log_table.style = "Table Grid"
hdr = log_table.rows[0].cells
hdr[0].text = "Event Name"
hdr[1].text = "Emitted By / Meaning"

log_events = [
    ("frame_published", "MessageQueuePublisher — frame stored in Redis, envelope queued"),
    ("inference_cycle_start / detection_event_published", "YoloInferenceEngine — per-frame inference lifecycle"),
    ("tracker_new_track / tracker_track_lost / tracker_update_done", "IoUTracker — track creation, loss, and frame summary"),
    ("observations_built", "ObservationBuilder — observation count per frame"),
    ("state_machine_transition", "HandwashStateMachine — person state change with reason"),
    ("temporal_continuity_gap_detected", "SpatioTemporalAnalyzer — gap > max_gap_seconds detected"),
    ("compliance_event_published / violation_confirmed", "HandwashRuleEvaluator / ComplianceRuleEngine"),
    ("evidence_buffer_initialized / evidence_buffer_frozen", "EvidenceBuffer — buffer lifecycle"),
    ("redis_state_store_initialized", "RedisStateStore — backend confirmed active"),
    ("database_connected / database_closed", "Database engine lifecycle"),
    ("persistence_worker_started", "PersistenceWorker — ready to consume compliance events"),
]

for row_data in log_events:
    if isinstance(row_data, tuple) and len(row_data) == 2:
        row = log_table.add_row()
        row.cells[0].text = row_data[0]
        row.cells[1].text = row_data[1]

# ── Save ──────────────────────────────────────────────────────────────────────
doc.save(DOC_PATH)
print("Document updated successfully.")
