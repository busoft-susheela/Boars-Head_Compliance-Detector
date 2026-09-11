"""Generate BH_CV Compliance Detector — Technical Documentation (Word format)."""

from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import docx.opc.constants


# ── Helpers ──────────────────────────────────────────────────────────────────

def set_heading(doc, text, level=1, color=None):
    h = doc.add_heading(text, level=level)
    if color:
        for run in h.runs:
            run.font.color.rgb = RGBColor(*color)
    return h


def add_para(doc, text, bold=False, italic=False, size=None, indent=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    if size:
        run.font.size = Pt(size)
    if indent is not None:
        p.paragraph_format.left_indent = Inches(indent)
    return p


def add_code(doc, text, indent=0.3):
    """Add a monospaced code block."""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(indent)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.font.name = "Courier New"
    run.font.size = Pt(9)
    # Light grey background via paragraph shading
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F2F2F2")
    pPr.append(shd)
    return p


def add_bullet(doc, text, level=0, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Inches(0.3 + level * 0.3)
    if bold_prefix:
        run = p.add_run(bold_prefix)
        run.bold = True
        p.add_run(text)
    else:
        p.add_run(text)
    return p


def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT

    # Header row
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        cell = hdr_cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(9)
        # Dark header background
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "1F3864")
        tcPr.append(shd)
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)

    # Data rows
    for r_idx, row in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        for c_idx, cell_text in enumerate(row):
            cell = row_cells[c_idx]
            cell.text = str(cell_text)
            cell.paragraphs[0].runs[0].font.size = Pt(9)
            if r_idx % 2 == 0:
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "EEF2F7")
                tcPr.append(shd)

    if col_widths:
        for i, width in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Inches(width)

    return table


def add_divider(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run("─" * 90)
    run.font.size = Pt(7)
    run.font.color.rgb = RGBColor(180, 180, 180)


# ── Document ──────────────────────────────────────────────────────────────────

doc = Document()

# Page margins
section = doc.sections[0]
section.top_margin    = Cm(2.0)
section.bottom_margin = Cm(2.0)
section.left_margin   = Cm(2.5)
section.right_margin  = Cm(2.0)

# Default body font
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(10)

# ─────────────────────────────────────────────────────────────────────────────
# TITLE PAGE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_paragraph()
doc.add_paragraph()
title = doc.add_heading("BH_CV Compliance Detector", 0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
subtitle = doc.add_paragraph("Technical Architecture & Implementation Documentation")
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
subtitle.runs[0].font.size = Pt(14)
subtitle.runs[0].font.color.rgb = RGBColor(70, 100, 140)
doc.add_paragraph()
version_p = doc.add_paragraph("Version 1.0  |  Handwash Detection Use Case  |  MVP Release")
version_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
version_p.runs[0].font.size = Pt(10)
version_p.runs[0].font.color.rgb = RGBColor(120, 120, 120)

doc.add_page_break()

# ─────────────────────────────────────────────────────────────────────────────
# 1. PROJECT OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
set_heading(doc, "1. Project Overview", 1)

add_para(doc,
    "BH_CV Compliance Detector is a computer-vision compliance monitoring system "
    "designed for a meat-processing warehouse. The system watches surveillance camera "
    "footage and automatically detects and flags staff hygiene violations — "
    "specifically, incomplete or absent handwashing at the designated handwash station.")

doc.add_paragraph()
set_heading(doc, "1.1 Current Scope (MVP)", 2)

add_bullet(doc, "Single fixed surveillance camera with a top-down angle over the handwash station")
add_bullet(doc, "Single handwash zone per camera")
add_bullet(doc, "CPU-based inference (no GPU required)")
add_bullet(doc, "In-memory state (no external database or message broker)")
add_bullet(doc, "Single process deployment")

doc.add_paragraph()
set_heading(doc, "1.2 Technology Stack", 2)

add_table(doc,
    ["Layer", "Technology", "Notes"],
    [
        ["Language",       "Python 3.12",                  "Primary implementation language"],
        ["Package Manager","uv + hatchling",               "Fast dependency resolution"],
        ["Web Framework",  "FastAPI + lifespan",           "REST API and startup/shutdown orchestration"],
        ["Detection Model","YOLO11n (Ultralytics)",        "Nano variant — CPU inference. AGPL-3.0 licensed."],
        ["Compliance Logic","Custom rule engine",          "State machine + temporal analyzer (no ML)"],
        ["Logging",        "Structlog",                    "Structured JSON logs, kwargs style"],
        ["Video I/O",      "OpenCV (cv2)",                 "Frame capture and thumbnail generation"],
        ["Concurrency",    "Python threading",             "NOT asyncio — ingestion + inference + compliance threads"],
        ["State Store",    "InMemoryStateStore (MVP)",     "Redis-compatible interface for future migration"],
        ["Frontend",       "Streamlit (planned)",          "Live view, alerts, evidence review"],
    ],
    col_widths=[1.5, 1.8, 3.0]
)

doc.add_paragraph()
add_para(doc,
    "LICENSING NOTE: YOLO11 ships under AGPL-3.0 by default. Commercial closed-source "
    "use requires an Ultralytics Enterprise License. This must be resolved before "
    "production deployment.",
    italic=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2. HIGH-LEVEL ARCHITECTURE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "2. High-Level Architecture", 1)

add_para(doc,
    "The system is organised as a three-stage event-driven pipeline running in a single "
    "process with multiple background threads. Each stage communicates through an "
    "in-memory message queue, allowing each stage to be independently tested and later "
    "replaced with a distributed implementation.")

doc.add_paragraph()
set_heading(doc, "2.1 Pipeline Overview", 2)

add_code(doc, """
  VIDEO / RTSP Camera
        |
        v
  StreamIngestionService              [Thread: ingestion]
    - RTSPConnector / VideoConnector
    - FpsSampler  (throttle to target FPS)
    - FrameValidator
    - MessageQueuePublisher
        |
        |  Topic: ingestion.frames  (FrameEnvelope)
        v
  CPUInferenceWorker                  [Thread: inference_worker]
    - YoloInferenceEngine
        - StaticModelResolver
        - ModelRegistry
        - YoloDetector
        - ThumbnailGenerator
        |
        |  Topic: inference.detections  (DetectionEvent)
        v
  ComplianceWorker                    [Thread: compliance_worker]
    - ComplianceRuleEngine
        - IoUTracker           -> Track IDs
        - ObservationBuilder   -> Observations
        - HandwashStateMachine -> State transitions
        - SpatioTemporalAnalyzer -> TemporalMetrics
        - HandwashRuleEvaluator  -> Compliance decision
        - InMemoryStateStore     -> Persist zone state
        |
        +----> Topic: compliance.alert   (ComplianceEvent)
        +----> Topic: evidence.capture   (EvidenceCaptureEvent)
""")

doc.add_paragraph()
set_heading(doc, "2.2 Architectural Separation Principle", 2)

add_para(doc,
    "Each component has a strictly bounded responsibility. No component crosses its "
    "boundary into another's domain:")

add_table(doc,
    ["Component", "Question It Answers", "Must NOT Do"],
    [
        ["IoUTracker",              '"Who is this person?"',          "Measure durations, decide compliance"],
        ["ObservationBuilder",      '"What is happening in this frame?"', "Determine compliance"],
        ["HandwashStateMachine",    '"What state is the person in?"', "Access StateStore, calculate durations"],
        ["SpatioTemporalAnalyzer",  '"For how long?"',                "Make compliance decisions"],
        ["RuleEvaluator",           '"Is it compliant?"',            "Access StateStore, publish messages"],
        ["ComplianceRuleEngine",    "Orchestrate, persist, publish",  "Contain compliance logic"],
    ],
    col_widths=[2.0, 2.0, 2.5]
)

# ─────────────────────────────────────────────────────────────────────────────
# 3. STEP-BY-STEP PIPELINE FLOW
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "3. Step-by-Step Pipeline Flow", 1)

add_para(doc,
    "This section traces a single camera frame from capture through to compliance "
    "event publication, detailing every transformation and decision point.")

doc.add_paragraph()

# ── Step 1
set_heading(doc, "Step 1 — Frame Capture (StreamIngestionService)", 2)
add_para(doc, "Thread: ingestion")
add_bullet(doc, "RTSPConnector opens the RTSP stream (or VideoConnector reads a .mp4 file).")
add_bullet(doc, "Each raw frame is read from the source.")
add_bullet(doc, "FpsSampler checks whether enough time has elapsed since the last processed frame "
           "to match the configured target_fps (default: 5 FPS). Frames that arrive too fast are dropped.")
add_bullet(doc, "FrameValidator confirms the frame is non-null and has valid dimensions.")
add_bullet(doc, "MessageQueuePublisher stores the raw frame in InMemoryFrameStore (keyed by frame_id) "
           "and publishes a lightweight FrameEnvelope (camera_id, zone_id, frame_id, captured_at) "
           "to the ingestion.frames topic.")
add_bullet(doc, "The raw frame is NOT sent through the queue — only the envelope. "
           "This keeps queue memory bounded.")

doc.add_paragraph()

# ── Step 2
set_heading(doc, "Step 2 — Inference (CPUInferenceWorker)", 2)
add_para(doc, "Thread: inference_worker")
add_bullet(doc, "CPUInferenceWorker blocks on ingestion.frames queue (1-second timeout for clean shutdown).")
add_bullet(doc, "On receiving a FrameEnvelope, YoloInferenceEngine is called.")
add_bullet(doc, "YoloInferenceEngine retrieves the raw frame from InMemoryFrameStore using frame_id. "
           "If the frame has already expired (TTL exceeded), the event is skipped and a metric is incremented.")
add_bullet(doc, "StaticModelResolver looks up which models are configured for the camera's zone "
           "and returns a list of ModelSpec objects.")
add_bullet(doc, "ModelRegistry loads (or returns cached) the YOLO model. "
           "On first load, a synthetic warmup pass is run.")
add_bullet(doc, "YoloDetector runs YOLO inference and converts raw model outputs to typed "
           "Detection objects: (class_id, class_name, bbox, confidence, use_case). "
           "Detections are sorted deterministically by (use_case, class_id, confidence DESC).")
add_bullet(doc, "ThumbnailGenerator resizes the frame to max_width=320px and encodes as JPEG "
           "(quality=70). The thumbnail bytes are embedded directly in the DetectionEvent.")
add_bullet(doc, "YoloInferenceEngine publishes a DetectionEvent to the inference.detections topic. "
           "The event is always published, even when detections is an empty tuple "
           "(the compliance layer uses absence of detections for state tracking).")

doc.add_paragraph()

# ── Step 3
set_heading(doc, "Step 3 — Tracking (IoUTracker)", 2)
add_para(doc, "Thread: compliance_worker  |  Component: ComplianceRuleEngine._process()")
add_bullet(doc, "ComplianceWorker dequeues the DetectionEvent from inference.detections.")
add_bullet(doc, "ComplianceRuleEngine.process() is called.")
add_bullet(doc, "IoUTracker.update() receives the list of Detection objects and the frame timestamp.")
add_bullet(doc, "For each existing active track, the tracker finds the detection with the "
           "highest IoU score (minimum threshold: 0.3). Greedy matching is used — sufficient "
           "for the single-camera, low-density MVP.")
add_bullet(doc, "Matched detections update the corresponding track (increment age, reset lost_frames).")
add_bullet(doc, "Unmatched existing tracks have their lost_frames counter incremented. "
           "Tracks alive up to max_lost_frames=5 frames are kept internally.")
add_bullet(doc, "Unmatched incoming detections create new tracks with a new monotonically "
           "increasing track_id.")
add_bullet(doc, "The method returns only the Track objects for detections matched or created this "
           "frame (track_id, detection, age). Lost tracks are retained internally but not returned.")

doc.add_paragraph()

# ── Step 4
set_heading(doc, "Step 4 — Observation Building (ObservationBuilder)", 2)
add_bullet(doc, "ObservationBuilder.build() converts each Track into a domain Observation.")
add_bullet(doc, "For each track, it checks whether the detection's class_name matches the "
           "trigger_class (\"handwash\"). If yes: hands_interacting=True.")
add_bullet(doc, "Water and soap detection are inferred from the full set of class names in the "
           "DetectionEvent. With the current single-class model, if \"handwash\" is detected, "
           "both water_detected and soap_detected are implicitly True.")
add_bullet(doc, "inside_sink_zone is set to True for all tracked persons (MVP assumption: "
           "all tracked objects are in the configured handwash zone).")
add_bullet(doc, "An Observation is produced for each active track: "
           "(camera_id, zone_id, person_id, timestamp, frame_id, inside_sink_zone, "
           "water_detected, soap_detected, hands_interacting, track_bbox).")

doc.add_paragraph()

# ── Step 4b — Absence synthesis
set_heading(doc, "Step 4b — Absence Observation Synthesis", 2)
add_para(doc,
    "Because the current model outputs only the \"handwash\" class (no separate person "
    "detection class), when a person is at the sink but not washing, the model produces "
    "zero detections. The engine handles this with absence synthesis:")
add_bullet(doc, "After building observations from active tracks, the engine checks the "
           "StateStore for persons who were previously tracked (state != UNKNOWN) but "
           "not seen in the current frame.")
add_bullet(doc, "For each such person, the engine computes frames_lost = "
           "current_frame_id - last_frame_id.")
add_bullet(doc, "If frames_lost <= MAX_LOST_FRAMES (5): a synthetic Observation is appended "
           "with inside_sink_zone=True and hands_interacting=False, water_detected=False.")
add_bullet(doc, "If frames_lost > MAX_LOST_FRAMES: a synthetic Observation is appended "
           "with inside_sink_zone=False (zone exit), causing the state machine to "
           "transition the person to UNKNOWN.")
add_bullet(doc, "This synthesis is only applied to persons who were previously known in "
           "the StateStore — it cannot manufacture observations for unknown persons.")

doc.add_paragraph()

# ── Step 5
set_heading(doc, "Step 5 — State Machine Transition (HandwashStateMachine)", 2)
add_bullet(doc, "The engine loads the zone state from InMemoryStateStore: "
           "key = \"camera_id:zone_id\", value = {\"persons\": {\"<pid>\": person_state}}.")
add_bullet(doc, "For each Observation, the current HandwashState is read from the person's "
           "stored state (or initialised to UNKNOWN if this person is new).")
add_bullet(doc, "HandwashStateMachine.transition() computes the next state deterministically "
           "from (current_state, observation). See Section 5 for the full transition table.")
add_bullet(doc, "The result is a StateTransitionResult: (previous_state, new_state, timestamp, "
           "person_id, transitioned, sequence_valid, reason).")
add_bullet(doc, "sequence_valid is False if soap was applied before water was ever detected.")

doc.add_paragraph()

# ── Step 6
set_heading(doc, "Step 6 — Temporal Analysis (SpatioTemporalAnalyzer)", 2)
add_bullet(doc, "SpatioTemporalAnalyzer.update_and_analyze() receives the person state dict "
           "and the StateTransitionResult.")
add_bullet(doc, "If the state has changed (transitioned=True), the elapsed duration in the "
           "previous state is computed as: duration = (transition.timestamp - state_started_at).")
add_bullet(doc, "The duration is accumulated into the corresponding field: "
           "at_sink_seconds, water_on_seconds, soap_applied_seconds, washing_seconds, rinsing_seconds.")
add_bullet(doc, "state_started_at is updated to transition.timestamp.")
add_bullet(doc, "sequence_valid in the person state degrades to False and never recovers "
           "(monotonically degrading validity flag).")
add_bullet(doc, "The gap from the previous observation (last_seen_at) is computed. If it "
           "exceeds max_gap_seconds=10.0, continuity_valid is set to False in the metrics.")
add_bullet(doc, "TemporalMetrics is returned: all durations include ongoing time in the "
           "current state (accumulated + time since state_started_at).")

doc.add_paragraph()

# ── Step 7
set_heading(doc, "Step 7 — Rule Evaluation (HandwashRuleEvaluator)", 2)
add_bullet(doc, "RuleEvaluator.evaluate() receives person_state, TemporalMetrics, "
           "camera_id, zone_id, timestamp, thumbnail, frame_id.")
add_bullet(doc, "The evaluator reads current_state from person_state.")
add_bullet(doc, "Branch 1 — Person left zone (UNKNOWN): any unconfirmed evidence group "
           "is discarded. No violation published. Group_id and absence_started_at are cleared.")
add_bullet(doc, "Branch 2 — Person is washing/completed (WASHING, RINSING, COMPLETED): "
           "if there is an active but unconfirmed evidence group, it is discarded "
           "(compliance resumed — no violation).")
add_bullet(doc, "Branch 3 — Person at sink but not washing (AT_SINK, WATER_ON, SOAP_APPLIED):")
add_bullet(doc, "If no active group: mint a new UUID group_id, record absence_started_at, "
           "create an EvidenceBuffer (ring buffer, capacity=evidence_buffer_max).", level=1)
add_bullet(doc, "Add an EvidenceItem (frame_id, timestamp, thumbnail, camera_id, zone_id, "
           "person_id) to the buffer. If buffer is full, oldest item is evicted.", level=1)
add_bullet(doc, "Compute absence_duration = (timestamp - absence_started_at).total_seconds().", level=1)
add_bullet(doc, "If absence_duration >= absence_threshold_seconds AND "
           "violation not already confirmed: mark violation_confirmed=True, "
           "freeze the EvidenceBuffer into an immutable EvidencePayload.", level=1)
add_bullet(doc, "Return RuleEvaluationResult(person_state, outcome='violation', evidence=payload).", level=1)
add_bullet(doc, "If violation_confirmed is already True (idempotency guard): return outcome=None. "
           "One violation per group_id, not one per frame.", level=0)

doc.add_paragraph()

# ── Step 8
set_heading(doc, "Step 8 — State Persistence", 2)
add_bullet(doc, "The engine writes the updated zone state back to InMemoryStateStore: "
           "StateStore.set(zone_key, {\"persons\": {\"<pid>\": updated_person_state}}).")
add_bullet(doc, "State is always persisted AFTER rule evaluation, so the persisted state "
           "reflects the new outcome (including violation_confirmed=True before publishing).")
add_bullet(doc, "This ordering prevents duplicate alerts after hypothetical retries.")

doc.add_paragraph()

# ── Step 9
set_heading(doc, "Step 9 — Event Publication", 2)
add_bullet(doc, "If outcome == \"violation\", the engine calls _publish_violation().")
add_bullet(doc, "ComplianceEvent is published to compliance.alert topic first:")
add_code(doc, """{
    camera_id:  "handwash-camera-01",
    zone_id:    "handwash_zone",
    person_id:  7,
    timestamp:  "2024-01-01T10:00:20+00:00",
    outcome:    "violation",
    rule_name:  "handwash_compliance",
    group_id:   "b7c3a9d1-..."
}""")
add_bullet(doc, "ComplianceEvent does NOT contain thumbnails, full frames, or evidence. "
           "It is intentionally lightweight for fast notification routing.")
add_bullet(doc, "EvidenceCaptureEvent is then published to evidence.capture topic:")
add_code(doc, """{
    group_id:   "b7c3a9d1-...",
    camera_id:  "handwash-camera-01",
    zone_id:    "handwash_zone",
    timestamp:  "2024-01-01T10:00:20+00:00",
    payload: {
        group_id: "b7c3a9d1-...",
        items: [
            { frame_id: 40, timestamp: "...", thumbnail: <JPEG bytes>,
              camera_id: "handwash-camera-01", zone_id: "handwash_zone", person_id: 7 },
            ...
        ]
    }
}""")
add_bullet(doc, "The evidence payload is independent of FrameStore — thumbnails were "
           "captured at inference time and embedded in the DetectionEvent.")
add_bullet(doc, "If ComplianceEvent publication fails, the engine still attempts "
           "EvidenceCaptureEvent publication (best-effort, failure logged and metered).")

# ─────────────────────────────────────────────────────────────────────────────
# 4. HANDWASH STATE MACHINE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "4. Handwash State Machine", 1)

add_para(doc,
    "The HandwashStateMachine is a deterministic per-person state machine. Given a "
    "current state and one Observation, it always returns the same next state. It is "
    "stateless — the caller supplies the current state and receives the result. "
    "Persistent state lives in the StateStore.")

doc.add_paragraph()
set_heading(doc, "4.1 States", 2)

add_table(doc,
    ["State", "Meaning"],
    [
        ["UNKNOWN",       "Person not yet detected at the sink, or has left the zone"],
        ["AT_SINK",       "Person present at the sink — no washing activity detected"],
        ["WATER_ON",      "Water-related class detected near the person"],
        ["SOAP_APPLIED",  "Soap-related class detected (ideally after WATER_ON)"],
        ["WASHING",       "Active handwash detected (trigger class observed)"],
        ["RINSING",       "Washing stopped — possible rinse/dry phase"],
        ["COMPLETED",     "Full session finished — stays until person leaves zone"],
    ],
    col_widths=[1.5, 4.5]
)

doc.add_paragraph()
set_heading(doc, "4.2 State Diagram", 2)

add_code(doc, """
    UNKNOWN
       |  person enters sink zone
       v
    AT_SINK ──────────────────────── SOAP_APPLIED (soap before water: sequence_valid=False)
       |                                  |
       | water detected                   | hands interacting
       v                                  v
    WATER_ON ──── soap detected ──► SOAP_APPLIED ──── hands interacting ──► WASHING
       |                                                                        |
       | hands interacting                                                      | no hands + (water or no water)
       v                                                                        v
    WASHING ◄────── resumed ──────────────────────────────────── RINSING
       |                                                              |
       | no hands + no water   OR   no hands + water still on         | no water, no hands
       v                                                              v
    RINSING                                                      COMPLETED
                                                                      |
    Any state ──────── person leaves zone (inside_sink_zone=False) ──► UNKNOWN
""")

doc.add_paragraph()
set_heading(doc, "4.3 Transition Table", 2)

add_table(doc,
    ["Current State", "Observation Condition", "Next State", "Reason"],
    [
        ["ANY",          "inside_sink_zone=False",                     "UNKNOWN",       "left_zone"],
        ["UNKNOWN",      "inside_sink_zone=True",                      "AT_SINK",       "person_detected_at_sink"],
        ["AT_SINK",      "hands_interacting=True",                     "WASHING",       "handwash_detected"],
        ["AT_SINK",      "water_detected=True",                        "WATER_ON",      "water_detected"],
        ["AT_SINK",      "soap_detected=True",                         "SOAP_APPLIED",  "soap_detected_before_water"],
        ["AT_SINK",      "(none of the above)",                        "AT_SINK",       "still_at_sink"],
        ["WATER_ON",     "hands_interacting=True",                     "WASHING",       "handwash_detected"],
        ["WATER_ON",     "soap_detected=True",                         "SOAP_APPLIED",  "soap_detected"],
        ["WATER_ON",     "(water still on only)",                      "WATER_ON",      "water_still_on"],
        ["SOAP_APPLIED", "hands_interacting=True",                     "WASHING",       "handwash_with_soap"],
        ["SOAP_APPLIED", "(hands not interacting)",                    "SOAP_APPLIED",  "soap_still_applied"],
        ["WASHING",      "no hands + no water",                       "RINSING",       "washing_stopped"],
        ["WASHING",      "no hands + water still on",                 "RINSING",       "rinsing_water_on"],
        ["WASHING",      "hands_interacting=True",                    "WASHING",        "still_washing"],
        ["RINSING",      "hands_interacting=True",                     "WASHING",       "resumed_washing"],
        ["RINSING",      "no water + no hands",                       "COMPLETED",     "session_complete"],
        ["RINSING",      "water still on",                            "RINSING",        "still_rinsing"],
        ["COMPLETED",    "any (inside zone)",                         "COMPLETED",     "session_already_complete"],
    ],
    col_widths=[1.3, 2.3, 1.3, 1.6]
)

doc.add_paragraph()
set_heading(doc, "4.4 Sequence Validity", 2)
add_para(doc,
    "The state machine flags sequence_valid=False when soap is applied before water "
    "was ever detected (i.e., transitioning from AT_SINK directly to SOAP_APPLIED "
    "without passing through WATER_ON). This flag is informational — the state "
    "machine allows the transition but marks it as non-standard. The RuleEvaluator "
    "may use this flag when require_sequence=True is configured.")

# ─────────────────────────────────────────────────────────────────────────────
# 5. EVIDENCE GROUP LIFECYCLE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "5. Evidence Group Lifecycle", 1)

add_para(doc,
    "Each potential handwash violation is tracked as an evidence group. The group "
    "collects thumbnail frames while absence is building. If compliance resumes before "
    "the threshold, the group is silently discarded. If the threshold is exceeded, the "
    "group is frozen and its evidence is published.")

doc.add_paragraph()
add_code(doc, """
    NO_GROUP (initial state — person washing or not at sink)
         |
         | Absence begins: person enters AT_SINK / WATER_ON / SOAP_APPLIED
         | AND has NOT been washing
         v
    GROUP_ACTIVE
         |   group_id = UUID (minted once, stable for entire episode)
         |   absence_started_at = current timestamp
         |   EvidenceBuffer created (ring buffer, capacity = evidence_buffer_max)
         |
         | Each frame: EvidenceItem (frame_id, timestamp, thumbnail) appended
         |             If buffer full: oldest item evicted (ring buffer policy)
         |
         +──────────────────────────────────────────────────────────────┐
         |                                                              |
         | Person enters WASHING / RINSING / COMPLETED state           | absence_duration >= absence_threshold_seconds
         v                                                              v
    DISCARD                                                        VIOLATION CONFIRMED
    - EvidenceBuffer.discard()                                     - violation_confirmed = True
    - group_id = None                                              - EvidenceBuffer.freeze()
    - absence_started_at = None                                    - Immutable EvidencePayload created
    - violation_confirmed = False                                  - ONE ComplianceEvent published
    - NO events published                                          - ONE EvidenceCaptureEvent published
                                                                   - Subsequent frames: outcome=None
                                                                     (idempotency guard)
""")

doc.add_paragraph()
set_heading(doc, "5.1 group_id Minting", 2)
add_bullet(doc, "A new UUID group_id is minted exactly ONCE when absence begins.")
add_bullet(doc, "The same group_id is reused for all frames in that absence episode.")
add_bullet(doc, "A new group_id is only minted when a new absence episode begins after "
           "a previous group was discarded or a violation was confirmed.")

doc.add_paragraph()
set_heading(doc, "5.2 Idempotency", 2)
add_bullet(doc, "Once violation_confirmed=True, the evaluator returns outcome=None for "
           "all subsequent frames in the same episode.")
add_bullet(doc, "This means exactly one ComplianceEvent and one EvidenceCaptureEvent "
           "are published per group_id — not one per frame.")

doc.add_paragraph()
set_heading(doc, "5.3 Evidence Buffer Ring Policy", 2)
add_bullet(doc, "When the buffer reaches evidence_buffer_max capacity, the oldest "
           "EvidenceItem is evicted to make room for the newest.")
add_bullet(doc, "This ensures the most recent frames leading up to the violation "
           "confirmation are retained in the evidence payload.")
add_bullet(doc, "After freeze(), the buffer rejects all further add() calls "
           "(RuntimeError). The EvidencePayload.items is an immutable tuple.")

# ─────────────────────────────────────────────────────────────────────────────
# 6. COMPONENT REFERENCE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "6. Component Reference", 1)

set_heading(doc, "6.1 StateStore (infrastructure/state_store/)", 2)
add_para(doc, "Generic key/value persistence interface. Unaware of handwashing, compliance, "
         "or YOLO. Stores only plain JSON-serializable dicts.")
add_table(doc,
    ["Method", "Signature", "Description"],
    [
        ["get(key)", "key: str → dict | None",       "Returns stored state or None if absent"],
        ["set(key, value)", "key: str, value: dict → None", "Persists value, overwriting any prior"],
        ["close()", "→ None",                        "Release resources — call at shutdown"],
    ],
    col_widths=[1.5, 2.5, 2.5]
)
add_para(doc, "Key convention: make_state_key(camera_id, zone_id) → \"camera_id:zone_id\"", italic=True)

doc.add_paragraph()
set_heading(doc, "6.2 IoUTracker (compliance/tracker.py)", 2)
add_para(doc,
    "Lightweight single-camera tracker using Intersection-over-Union overlap. "
    "Sufficient for a single fixed camera with at most one or two people in frame.")
add_table(doc,
    ["Parameter", "Default", "Description"],
    [
        ["iou_threshold",    "0.3", "Minimum IoU for two boxes to be considered the same object"],
        ["max_lost_frames",  "5",   "Frames a track survives without a new matching detection"],
    ],
    col_widths=[2.0, 1.0, 3.5]
)

doc.add_paragraph()
set_heading(doc, "6.3 ObservationBuilder (compliance/observation.py)", 2)
add_para(doc,
    "Converts IoUTracker output (list[Track]) plus DetectionEvent metadata into "
    "domain Observations. Does NOT determine compliance.")
add_table(doc,
    ["Parameter", "Default", "Description"],
    [
        ["trigger_class",  "\"handwash\"", "YOLO class name that means active handwashing"],
        ["water_classes",  "frozenset()", "Class names that imply water is present"],
        ["soap_classes",   "frozenset()", "Class names that imply soap is applied"],
    ],
    col_widths=[1.5, 1.5, 3.5]
)

doc.add_paragraph()
set_heading(doc, "6.4 SpatioTemporalAnalyzer (compliance/temporal/analyzer.py)", 2)
add_para(doc,
    "Accumulates time-based duration metrics from observation timestamps. "
    "Returns an updated person state dict and a TemporalMetrics snapshot.")
add_table(doc,
    ["Parameter", "Default", "Description"],
    [
        ["max_gap_seconds", "10.0", "Observation gap threshold above which continuity_valid=False"],
    ],
    col_widths=[2.0, 1.0, 3.5]
)
add_para(doc, "Person state dict fields tracked by the analyzer:", italic=True)
add_code(doc, """
{
    "person_id":            int,
    "current_state":        str,    # HandwashState.name
    "state_started_at":     str,    # ISO-8601 UTC — when current state began
    "last_seen_at":         str,    # ISO-8601 UTC — timestamp of last observation
    "last_frame_id":        int,    # frame_id of last real (non-synthetic) observation
    "observation_count":    int,
    "sequence_valid":       bool,   # False if soap was applied before water
    "at_sink_seconds":      float,  # finalized duration in AT_SINK
    "water_on_seconds":     float,  # finalized duration in WATER_ON
    "soap_applied_seconds": float,  # finalized duration in SOAP_APPLIED
    "washing_seconds":      float,  # finalized duration in WASHING
    "rinsing_seconds":      float,  # finalized duration in RINSING
    # Added by HandwashRuleEvaluator:
    "absence_started_at":   str | None,
    "group_id":             str | None,
    "violation_confirmed":  bool
}
""")

doc.add_paragraph()
set_heading(doc, "6.5 HandwashRuleEvaluator (compliance/rules/handwash.py)", 2)
add_para(doc,
    "Applies the handwash compliance rule. Maintains in-memory EvidenceBuffers keyed "
    "by (camera_id, zone_id, person_id). Does NOT access StateStore or MessageQueue.")
add_table(doc,
    ["Config Field", "Type", "Description"],
    [
        ["minimum_washing_duration_seconds", "float", "Required cumulative WASHING time"],
        ["absence_threshold_seconds",        "float", "Max non-washing time before violation"],
        ["require_soap",                     "bool",  "SOAP_APPLIED required for compliance"],
        ["require_water",                    "bool",  "WATER_ON required for compliance"],
        ["require_sequence",                 "bool",  "Water must precede soap"],
        ["require_completion",               "bool",  "Must reach COMPLETED state"],
        ["evidence_buffer_max",              "int",   "Max thumbnails per violation episode"],
    ],
    col_widths=[2.5, 0.7, 3.3]
)

doc.add_paragraph()
set_heading(doc, "6.6 ComplianceRuleEngine (compliance/engine.py)", 2)
add_para(doc,
    "Thin orchestrator. Receives DetectionEvent, runs the full pipeline, persists state, "
    "and publishes output events. Contains no compliance logic itself.")
add_bullet(doc, "Accepts all dependencies via constructor (dependency injection).")
add_bullet(doc, "Tracks evaluation count, violation count, failure count via ComplianceMetrics.")
add_bullet(doc, "_MAX_LOST_FRAMES=5: persons not seen for more than 5 frames receive a "
           "synthetic inside_sink_zone=False observation (zone exit).")

doc.add_paragraph()
set_heading(doc, "6.7 ComplianceWorker (compliance/worker.py)", 2)
add_para(doc,
    "Background thread consumer. Mirrors the design of CPUInferenceWorker.")
add_bullet(doc, "start() / stop() / join() lifecycle interface.")
add_bullet(doc, "Blocks on inference.detections topic with 1-second timeout (clean shutdown).")
add_bullet(doc, "Calls ComplianceRuleEngine.process() for each DetectionEvent.")
add_bullet(doc, "Exceptions from the engine are caught and logged; the worker continues.")

# ─────────────────────────────────────────────────────────────────────────────
# 7. DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "7. Data Models", 1)

set_heading(doc, "7.1 DetectionEvent (inference/models/detection.py)", 2)
add_code(doc, """
@dataclass(frozen=True)
class DetectionEvent:
    camera_id:    str                    # Source camera
    zone_id:      str                    # Zone within camera
    frame_id:     int                    # Monotonic frame counter
    captured_at:  datetime               # Frame capture time (compliance authority)
    processed_at: datetime               # Inference completion time
    detections:   tuple[Detection, ...]  # Sorted (use_case, class_id, confidence DESC)
    thumbnail:    bytes | None           # JPEG evidence bytes (embedded, no FrameStore needed)
""")

set_heading(doc, "7.2 Observation (compliance/observation.py)", 2)
add_code(doc, """
@dataclass(frozen=True)
class Observation:
    camera_id:       str
    zone_id:         str
    person_id:       int          # Stable track_id from IoUTracker
    timestamp:       datetime
    frame_id:        int
    inside_sink_zone: bool        # Person bounding box overlaps configured sink zone
    water_detected:  bool         # Water class detected near person
    soap_detected:   bool         # Soap class detected near person
    hands_interacting: bool       # Trigger class detected (active handwash)
    track_bbox:      BoundingBox | None
""")

set_heading(doc, "7.3 TemporalMetrics (compliance/temporal/models.py)", 2)
add_code(doc, """
@dataclass(frozen=True)
class TemporalMetrics:
    at_sink_duration:       float   # Total seconds in AT_SINK state
    water_on_duration:      float   # Total seconds in WATER_ON state
    soap_applied_duration:  float   # Total seconds in SOAP_APPLIED state
    washing_duration:       float   # Total seconds in WASHING (incl. ongoing)
    rinsing_duration:       float   # Total seconds in RINSING state
    sequence_valid:         bool    # False if soap before water
    continuity_valid:       bool    # False if gap between observations > max_gap_seconds
    observation_count:      int
    current_state:          str     # HandwashState.name at this measurement
    last_gap_seconds:       float   # Gap from previous observation (0.0 for first)
""")

set_heading(doc, "7.4 RuleEvaluationResult (compliance/rules/base.py)", 2)
add_code(doc, """
@dataclass(frozen=True)
class RuleEvaluationResult:
    person_state: dict               # Updated serializable person state (for StateStore)
    outcome:      str | None         # "violation" or None
    evidence:     EvidencePayload | None   # Set only when outcome == "violation"
""")

set_heading(doc, "7.5 ComplianceEvent (compliance/events.py)", 2)
add_code(doc, """
@dataclass(frozen=True)
class ComplianceEvent:             # Topic: compliance.alert
    camera_id:  str
    zone_id:    str
    person_id:  int
    timestamp:  datetime
    outcome:    str                # Always "violation"
    rule_name:  str                # "handwash_compliance"
    group_id:   str                # Correlates with EvidenceCaptureEvent
""")

set_heading(doc, "7.6 EvidenceCaptureEvent (compliance/events.py)", 2)
add_code(doc, """
@dataclass(frozen=True)
class EvidenceCaptureEvent:        # Topic: evidence.capture
    group_id:   str
    camera_id:  str
    zone_id:    str
    payload:    EvidencePayload    # Frozen evidence with thumbnail items
    timestamp:  datetime

@dataclass(frozen=True)
class EvidencePayload:
    group_id:   str
    camera_id:  str
    zone_id:    str
    items:      tuple[EvidenceItem, ...]   # Immutable

@dataclass(frozen=True)
class EvidenceItem:
    frame_id:   int
    timestamp:  datetime
    thumbnail:  bytes | None       # JPEG bytes
    camera_id:  str
    zone_id:    str
    person_id:  int
""")

# ─────────────────────────────────────────────────────────────────────────────
# 8. CONFIGURATION REFERENCE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "8. Configuration Reference", 1)

add_para(doc,
    "All runtime configuration lives in config/config.yaml. "
    "No business thresholds are hardcoded in source files. "
    "Environment-specific values (.env file) override config where applicable.")

doc.add_paragraph()
set_heading(doc, "8.1 Full config.yaml", 2)

add_code(doc, """# BH_CV Compliance Detector — runtime configuration

stream:
  type: video                        # "video" or "rtsp"
  camera_id: "handwash-camera-01"    # Must match cameras section

  video:
    path: "data/handwash.mp4"
    playback_mode: realtime          # Sleep to match native FPS

  rtsp:
    url: "${RTSP_URL}"               # Set env var: RTSP_URL=rtsp://user:pass@host/stream

  reconnect:
    initial_delay_seconds: 1.0      # Backoff start for RTSP reconnect
    max_delay_seconds: 15.0         # Maximum backoff cap

  sampling:
    target_fps: 5.0                 # Throttle inference load

  buffer:
    max_size: 1                     # Latest-frame strategy
    strategy: latest

models:
  handwashing:
    use_case: handwashing
    path: "artifacts/models/handwash_detection.pt"
    confidence: 0.5                 # Detection confidence threshold
    device: cpu
    image_size: 640

zones:
  handwash_zone:
    models:
      - handwashing

cameras:
  handwash-camera-01:
    zones:
      - handwash_zone

inference:
  queue_size: 10                    # Max FrameEnvelopes before drop-oldest
  workers: 1                        # CPU inference threads
  warmup: true                      # Synthetic forward pass after model load

  thumbnail:
    enabled: true
    max_width: 320                  # Pixels — aspect ratio preserved
    jpeg_quality: 70                # JPEG quality [1, 100]

compliance:
  trigger_class: "handwash"         # YOLO class for active washing

  handwash:
    minimum_washing_duration_seconds: 20.0   # Cumulative WASHING time required
    absence_threshold_seconds: 20.0          # Max non-washing before violation
    require_soap: false                       # SOAP_APPLIED required?
    require_water: false                      # WATER_ON required?
    require_sequence: false                   # Water before soap required?
    require_completion: false                 # COMPLETED state required?
    evidence_buffer_max: 10                   # Max thumbnails per episode

state_store:
  backend: in_memory                # Future: redis

topics:
  detection_events: inference.detections
  compliance_alert: compliance.alert
  evidence_capture: evidence.capture

evidence:
  output_dir: "evidence"
""")

doc.add_paragraph()
set_heading(doc, "8.2 Configuration Parameters Reference", 2)

add_table(doc,
    ["Parameter", "Type", "Default", "Description"],
    [
        ["stream.type",                "string",  "video",  "Source type: 'video' or 'rtsp'"],
        ["stream.camera_id",           "string",  "–",      "Must match cameras section key"],
        ["stream.sampling.target_fps", "float",   "5.0",    "Target processing FPS"],
        ["stream.buffer.max_size",     "int",     "1",      "Max frames buffered before eviction"],
        ["stream.reconnect.initial_delay_seconds", "float", "1.0", "Initial RTSP reconnect delay"],
        ["stream.reconnect.max_delay_seconds",     "float", "15.0","Maximum RTSP reconnect delay"],
        ["models.<name>.confidence",   "float",   "0.5",   "YOLO confidence threshold [0,1]"],
        ["models.<name>.device",       "string",  "cpu",   "Inference device ('cpu' or 'cuda')"],
        ["models.<name>.image_size",   "int",     "640",   "YOLO input resolution"],
        ["inference.queue_size",       "int",     "10",    "Max frames queued for inference"],
        ["inference.warmup",           "bool",    "true",  "Run warmup forward pass at startup"],
        ["inference.thumbnail.max_width","int",   "320",   "Thumbnail resize width (pixels)"],
        ["inference.thumbnail.jpeg_quality","int","70",    "JPEG compression quality [1,100]"],
        ["compliance.trigger_class",   "string",  "handwash","YOLO class for active handwash"],
        ["compliance.handwash.minimum_washing_duration_seconds","float","20.0","Required wash time"],
        ["compliance.handwash.absence_threshold_seconds","float","20.0","Non-wash violation threshold"],
        ["compliance.handwash.require_soap",      "bool","false","Require soap detection"],
        ["compliance.handwash.require_water",     "bool","false","Require water detection"],
        ["compliance.handwash.require_sequence",  "bool","false","Enforce water-before-soap order"],
        ["compliance.handwash.require_completion","bool","false","Require COMPLETED state"],
        ["compliance.handwash.evidence_buffer_max","int","10","Max thumbnails per episode"],
        ["state_store.backend",        "string",  "in_memory","State backend (in_memory or redis)"],
    ],
    col_widths=[2.8, 0.8, 0.9, 2.0]
)

doc.add_paragraph()
set_heading(doc, "8.3 Environment Variables (.env)", 2)
add_table(doc,
    ["Variable", "Description"],
    [
        ["LOG_LEVEL",    "Logging verbosity: DEBUG, INFO, WARNING, ERROR (default: INFO)"],
        ["FRAME_TTL_SEC","Seconds to keep raw frames in InMemoryFrameStore (default: 5.0)"],
        ["RTSP_URL",     "Full RTSP URL when stream.type=rtsp (e.g. rtsp://user:pass@host/stream)"],
    ],
    col_widths=[1.5, 5.0]
)

# ─────────────────────────────────────────────────────────────────────────────
# 9. STARTUP AND WIRING (main.py)
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "9. Application Startup (main.py)", 1)

add_para(doc,
    "FastAPI's lifespan context manager wires and starts all components. "
    "Components are started in dependency order and shut down in reverse:")

add_code(doc, """
Startup order:
  1. InMemoryFrameStore       (ttl_seconds from FRAME_TTL_SEC env var)
  2. InMemoryMessageQueue     (max_size_per_topic from inference.queue_size)
  3. InMemoryStateStore       (compliance state backend)
  4. StreamIngestionService   (RTSP/video connector, FPS sampler, publisher)
  5. ModelRegistry            (loads + warms up all models for configured camera zones)
  6. YoloInferenceEngine      (resolver + registry + thumbnail generator)
  7. CPUInferenceWorker       (starts thread consuming ingestion.frames)
  8. HandwashRuleConfig       (validated from config.yaml compliance section)
  9. ComplianceRuleEngine     (IoUTracker + ObservationBuilder + StateMachine +
                               SpatioTemporalAnalyzer + HandwashRuleEvaluator)
  10. ComplianceWorker        (starts thread consuming inference.detections)
  11. Ingestion thread        (starts — frames begin flowing)

Shutdown order (on SIGINT / server stop):
  1. Ingestion thread stopped (StreamIngestionService.stop())
  2. CPUInferenceWorker stopped and joined (5s timeout)
  3. ComplianceWorker stopped and joined (5s timeout)
  4. InMemoryStateStore closed
  5. ModelRegistry closed
""")

doc.add_paragraph()
set_heading(doc, "9.1 Health Endpoint", 2)
add_para(doc, "GET /health — returns a JSON snapshot of all pipeline metrics:")
add_code(doc, """{
    "status": "ok",
    "ingestion": {
        "frames_read": 1250, "frames_dropped": 3, "frames_published": 1247
    },
    "message_queue": {
        "frames_queued": 0, "frames_dropped": 0,
        "detections_queued": 0,
        "alerts_queued": 0, "evidence_queued": 0
    },
    "frame_store": {
        "frames_held": 0, "frames_evicted_total": 1247
    },
    "inference": {
        "frames_processed": 1247, "detections_total": 380, ...
    },
    "compliance": {
        "evaluations_total": 1247,
        "violations_total": 2,
        "evaluation_failures_total": 0,
        "evidence_groups_created_total": 4,
        "evidence_groups_discarded_total": 2,
        "evidence_groups_confirmed_total": 2,
        "evidence_publish_failures_total": 0
    }
}""")

# ─────────────────────────────────────────────────────────────────────────────
# 10. FILE STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "10. File Structure", 1)

add_code(doc, """
BH_CV_Compliance_Detector/
│
├── config/
│   └── config.yaml                   Runtime configuration (all parameters)
│
├── artifacts/
│   └── models/
│       └── handwash_detection.pt     Pre-trained YOLO11n weights (AGPL-3.0)
│
├── data/
│   └── handwash.mp4                  Test video for development
│
├── evidence/                         LocalDisk evidence output directory
│
├── backend/
│   └── app/
│       ├── main.py                   FastAPI entry point + lifespan wiring
│       ├── logging_config.py         Structlog configuration
│       │
│       ├── infrastructure/
│       │   ├── frame_store/
│       │   │   ├── base.py           FrameStore ABC
│       │   │   └── in_memory.py      InMemoryFrameStore (TTL-based eviction)
│       │   ├── message_queue/
│       │   │   ├── base.py           MessageQueue ABC
│       │   │   └── in_memory.py      InMemoryMessageQueue (queue.Queue per topic)
│       │   └── state_store/
│       │       ├── base.py           StateStore ABC + make_state_key()
│       │       └── in_memory.py      InMemoryStateStore (threading.Lock protected)
│       │
│       ├── ingestion/
│       │   ├── connectors/
│       │   │   ├── rtsp.py           RTSPConnector (OpenCV, exponential backoff)
│       │   │   └── video.py          VideoConnector (pre-recorded .mp4)
│       │   ├── sampling/
│       │   │   └── fps_sampler.py    FpsSampler (token bucket)
│       │   ├── validation/
│       │   │   └── frame_validator.py FrameValidator
│       │   ├── publishing/
│       │   │   └── message_queue_publisher.py  MessageQueuePublisher
│       │   ├── factory.py            create_connector() from config
│       │   └── service.py            StreamIngestionService
│       │
│       ├── inference/
│       │   ├── models/
│       │   │   └── detection.py      BoundingBox, Detection, DetectionEvent
│       │   ├── model_spec.py         ModelSpec frozen dataclass
│       │   ├── resolver/
│       │   │   ├── base.py           ModelResolver ABC
│       │   │   └── static.py         StaticModelResolver (config-driven)
│       │   ├── loader.py             ModelLoader (only file importing ultralytics)
│       │   ├── yolo_detector.py      YoloDetector
│       │   ├── registry.py           ModelRegistry (thread-safe cache + warmup)
│       │   ├── thumbnail.py          ThumbnailGenerator (JPEG, aspect-ratio)
│       │   ├── engine.py             YoloInferenceEngine (orchestrator)
│       │   ├── worker.py             CPUInferenceWorker (background thread)
│       │   └── health/
│       │       └── metrics.py        InferenceMetrics
│       │
│       └── compliance/
│           ├── tracker.py            Tracker ABC + IoUTracker
│           ├── observation.py        Observation + ObservationBuilder
│           ├── state_machine.py      HandwashState + HandwashStateMachine
│           ├── events.py             ComplianceEvent + EvidenceCaptureEvent + topics
│           ├── metrics.py            ComplianceMetrics
│           ├── engine.py             ComplianceRuleEngine (orchestrator)
│           ├── worker.py             ComplianceWorker (background thread)
│           │
│           ├── temporal/
│           │   ├── models.py         TemporalMetrics frozen dataclass
│           │   └── analyzer.py       SpatioTemporalAnalyzer + initial_person_state()
│           │
│           ├── evidence/
│           │   ├── models.py         EvidenceItem + EvidencePayload
│           │   └── buffer.py         EvidenceBuffer (ring buffer lifecycle)
│           │
│           └── rules/
│               ├── config.py         HandwashRuleConfig (validated frozen dataclass)
│               ├── base.py           RuleEvaluator ABC + RuleEvaluationResult
│               └── handwash.py       HandwashRuleEvaluator (absence group lifecycle)
│
└── tests/
    ├── ingestion/                    Ingestion layer tests (existing)
    ├── inference/                    Inference layer tests (existing)
    └── compliance/
        ├── test_state_store.py       StateStore + make_state_key (11 tests)
        ├── test_state_machine.py     HandwashStateMachine transitions (26 tests)
        ├── test_temporal_analyzer.py SpatioTemporalAnalyzer durations (15 tests)
        ├── test_evidence_buffer.py   EvidenceBuffer lifecycle (14 tests)
        ├── test_rule_evaluator.py    HandwashRuleEvaluator (17 tests)
        ├── test_engine.py            ComplianceRuleEngine (mocked deps, 5 tests)
        └── test_integration.py       End-to-end in-memory pipeline (5 classes)
""")

# ─────────────────────────────────────────────────────────────────────────────
# 11. TEST SUITE
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "11. Test Suite", 1)

add_para(doc,
    "All compliance tests are fully unit-testable without YOLO, a camera, RTSP, "
    "GPU, or any external service. They use synthetic observations and in-memory "
    "infrastructure only.")

doc.add_paragraph()
add_table(doc,
    ["Test File", "What It Tests", "Tests"],
    [
        ["test_state_store.py",      "make_state_key, InMemoryStateStore get/set/overwrite,\ndefensive copies, multi-key isolation, close behavior", "11"],
        ["test_state_machine.py",    "All state transitions (full table), sequence validity,\nperson-leaves-zone, same-state observations, result metadata", "26"],
        ["test_temporal_analyzer.py","Duration accumulation from timestamps (NOT frame count),\nsequence validity degradation, continuity gap detection,\nongoing state time included in metrics", "15"],
        ["test_evidence_buffer.py",  "Empty/add/ring eviction, max capacity never exceeded,\ndiscard (compliance resumed), freeze (violation confirmed),\nimmutable after freeze, add after freeze raises", "14"],
        ["test_rule_evaluator.py",   "No outcome when washing, group_id minted once,\ngroup_id stable across frames, compliance resumes discards group,\nviolation after threshold, idempotency, zone isolation,\nzone exit clears group, HandwashRuleConfig validation", "17"],
        ["test_engine.py",           "No observations skips evaluation, state loaded+persisted,\nno alert when outcome=None, both events published on violation,\nfailure counter incremented on exception", "5"],
        ["test_integration.py",      "Full pipeline: compliance resumes (no violation),\nviolation confirmed after threshold, one event per episode,\nalert has no thumbnail, evidence from DetectionEvent,\nbuffer cap respected, compliant wash no violation", "12+"],
    ],
    col_widths=[2.0, 3.3, 0.5]
)

doc.add_paragraph()
set_heading(doc, "11.1 Running the Tests", 2)
add_code(doc, "# Run all tests\npython -m pytest\n\n# Run only compliance tests\npython -m pytest tests/compliance/ -v\n\n# Run with coverage\npython -m pytest tests/compliance/ --cov=backend/app/compliance --cov-report=term-missing")

doc.add_paragraph()
set_heading(doc, "11.2 Test Status", 2)
add_table(doc,
    ["Test Group", "Total", "Passing", "Failing", "Notes"],
    [
        ["Ingestion",  "47",  "43", "4", "4 pre-existing failures (RTSPConnector, FpsSampler)"],
        ["Inference",  "104", "104","0", "All pass"],
        ["Compliance", "93",  "93", "0", "All pass — added in this implementation"],
        ["TOTAL",      "244", "240","4", "4 failures pre-date compliance implementation"],
    ],
    col_widths=[1.5, 0.7, 0.8, 0.7, 3.0]
)

# ─────────────────────────────────────────────────────────────────────────────
# 12. RUNNING THE APPLICATION
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "12. Running the Application", 1)

set_heading(doc, "12.1 Prerequisites", 2)
add_code(doc, "# Install dependencies\nuv sync\n\n# Create .env file\necho 'LOG_LEVEL=INFO' > .env\necho 'FRAME_TTL_SEC=5.0' >> .env")

set_heading(doc, "12.2 Start the Server", 2)
add_code(doc, "uvicorn backend.app.main:app --host 0.0.0.0 --port 8000")

set_heading(doc, "12.3 Verify Health", 2)
add_code(doc, "curl http://localhost:8000/health | python -m json.tool")

set_heading(doc, "12.4 Expected Startup Log (INFO)", 2)
add_code(doc, """eager_model_load      use_case=handwashing zone_id=handwash_zone
compliance_worker_started
inference_worker_started
ingestion_thread_started
# Then per-frame:
state_transition      person_id=1 previous=UNKNOWN new=AT_SINK reason=person_detected_at_sink
evidence_group_created camera_id=handwash-camera-01 group_id=b7c3...
violation_confirmed   group_id=b7c3... evidence_count=10
compliance_event_published  outcome=violation  group_id=b7c3...
evidence_event_published    evidence_count=10  group_id=b7c3...""")

# ─────────────────────────────────────────────────────────────────────────────
# 13. EXTENSIBILITY PATH
# ─────────────────────────────────────────────────────────────────────────────
doc.add_page_break()
set_heading(doc, "13. Extensibility and Future Migration Path", 1)

set_heading(doc, "13.1 Replacing the Tracker", 2)
add_para(doc,
    "The Tracker ABC is designed for ByteTrack replacement. Create a new class "
    "implementing Tracker.update() and Tracker.reset(), inject it at startup in main.py. "
    "No other code changes required.")

set_heading(doc, "13.2 Replacing the State Store", 2)
add_para(doc,
    "Change state_store.backend to 'redis' in config.yaml and create a RedisStateStore "
    "implementing the StateStore ABC. The ComplianceRuleEngine never imports "
    "InMemoryStateStore directly.")
add_code(doc, "# config.yaml\nstate_store:\n  backend: redis\n  url: redis://localhost:6379/0")

set_heading(doc, "13.3 Adding a New Compliance Rule", 2)
add_para(doc, "Implement a new class extending RuleEvaluator and create a corresponding "
         "RuleConfig dataclass. Inject into ComplianceRuleEngine at startup. The engine "
         "is rule-agnostic — it only calls RuleEvaluator.evaluate().")

set_heading(doc, "13.4 Multiple Cameras / Zones", 2)
add_para(doc,
    "The StateStore key convention (camera_id:zone_id) and the per-person state dict "
    "already support multiple cameras and multiple zones. Add entries to cameras and "
    "zones in config.yaml and start one ComplianceWorker per zone (or fan out inside "
    "a single worker).")

set_heading(doc, "13.5 Redis-Backed Message Queue", 2)
add_para(doc,
    "The MessageQueue ABC allows drop-in replacement. Implement a RedisMessageQueue "
    "using Pub/Sub or Streams. Producer and consumer code is decoupled from the "
    "in-memory implementation.")

# ─────────────────────────────────────────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────────────────────────────────────────
output_path = "BH_CV_Compliance_Detector_Documentation.docx"
doc.save(output_path)
print(f"Document saved: {output_path}")
