# Add PostgreSQL Persistence to BH_CV Compliance Detector
# End-to-End Persistence + Audit + Dashboard Integration

You are implementing PostgreSQL persistence for the existing
BH_CV Compliance Detector system.

IMPORTANT:

Do NOT redesign the existing CV architecture.

Do NOT replace the existing in-memory MessageQueue, FrameStore, StateStore,
or threading architecture unless there is a specific requirement to do so.

The current architecture is a single-process Python application using:

- Python 3.12
- FastAPI
- Python threading
- OpenCV
- YOLO11n CPU inference
- InMemoryMessageQueue
- InMemoryFrameStore
- InMemoryStateStore
- IoUTracker
- ObservationBuilder
- HandwashStateMachine
- SpatioTemporalAnalyzer
- HandwashRuleEvaluator
- ComplianceRuleEngine
- ComplianceWorker

PostgreSQL is being added as the DURABLE PERSISTENCE layer.

The runtime pipeline must remain low-latency and must not become
database-bound.

============================================================
1. FIRST: REPOSITORY DISCOVERY
============================================================

Before changing code, inspect the entire repository.

Specifically inspect:

backend/app/
config/
tests/
main.py
infrastructure/
ingestion/
inference/
compliance/

Identify the actual implementation of:

- StreamIngestionService
- VideoConnector
- RTSPConnector
- FpsSampler
- FrameValidator
- FrameStore
- MessageQueue
- DetectionEvent
- IoUTracker
- ObservationBuilder
- HandwashStateMachine
- StateStore
- SpatioTemporalAnalyzer
- TemporalMetrics
- EvidenceBuffer
- EvidencePayload
- HandwashRuleConfig
- HandwashRuleEvaluator
- ComplianceRuleEngine
- ComplianceEvent
- EvidenceCaptureEvent
- ComplianceWorker
- existing /health endpoint
- FastAPI lifespan
- existing API routes

Also identify whether the repository already contains:

- SQLAlchemy
- SQLModel
- asyncpg
- psycopg
- Alembic
- repository abstractions
- database session management
- Pydantic models
- dependency injection
- existing configuration conventions

DO NOT introduce a second ORM or database library if one already exists.

Reuse the existing project conventions.

Before implementation, report:

DATABASE DISCOVERY

ORM:
DATABASE DRIVER:
MIGRATION TOOL:
EXISTING DATABASE CODE:
EXISTING REPOSITORY PATTERN:
API FRAMEWORK:
CONFIGURATION APPROACH:
TEST DATABASE APPROACH:

============================================================
2. PRESERVE THE EXISTING ARCHITECTURE
============================================================

The documented architecture is:

VIDEO / RTSP
    |
    v
StreamIngestionService
    |
    | ingestion.frames
    v
CPUInferenceWorker
    |
    | inference.detections
    v
ComplianceWorker
    |
    +--> IoUTracker
    |
    +--> ObservationBuilder
    |
    +--> HandwashStateMachine
    |
    +--> SpatioTemporalAnalyzer
    |
    +--> HandwashRuleEvaluator
    |
    +--> InMemoryStateStore
    |
    +--> compliance.alert
    |
    +--> evidence.capture

Maintain this architecture.

The document explicitly defines strict responsibility boundaries:

IoUTracker:
    Identity only.

ObservationBuilder:
    Convert tracking/detections into observations.

HandwashStateMachine:
    Determine state transitions.

SpatioTemporalAnalyzer:
    Calculate temporal metrics.

RuleEvaluator:
    Determine compliance.

ComplianceRuleEngine:
    Orchestrate, persist state, and publish events.

Do not move business logic into the database layer.

Do not move compliance logic into PostgreSQL repositories.

============================================================
3. NEW ARCHITECTURE WITH POSTGRESQL
============================================================

Add PostgreSQL as:

                 PostgreSQL
                     ^
                     |
               Repository Layer
                     ^
                     |
              Application Services
                     ^
                     |
        Existing CV Pipeline

The resulting architecture should be:

VIDEO / RTSP
    |
    v
StreamIngestionService
    |
    +----------------------+
    |                      |
    v                      v
MessageQueue          Persistence Service
    |                      |
    v                      v
CPUInferenceWorker     PostgreSQL
    |
    v
DetectionEvent
    |
    v
ComplianceWorker
    |
    +--> IoUTracker
    |
    +--> ObservationBuilder
    |
    +--> HandwashStateMachine
    |
    +--> SpatioTemporalAnalyzer
    |
    +--> HandwashRuleEvaluator
    |
    +--> StateStore
    |
    +--> PostgreSQL Persistence
    |
    +--> ComplianceEvent
    |
    +--> EvidenceCaptureEvent
    |
    v
Dashboard / Alert API

IMPORTANT:

MessageQueue remains responsible for runtime event transport.

PostgreSQL remains responsible for durable persistence.

FrameStore remains responsible for short-lived frame bytes.

StateStore remains responsible for low-latency active compliance state.

Do not make PostgreSQL the runtime message broker.

Do not make PostgreSQL the FrameStore.

============================================================
4. EXISTING EVENT CONTRACTS MUST BE PRESERVED
============================================================

Do not change the existing DetectionEvent contract unnecessarily.

The documented DetectionEvent is:

DetectionEvent:
    camera_id: str
    zone_id: str
    frame_id: int
    captured_at: datetime
    processed_at: datetime
    detections: tuple[Detection, ...]
    thumbnail: bytes | None

The thumbnail is already generated by ThumbnailGenerator and embedded
directly in DetectionEvent.

The current implementation uses:

- max thumbnail width: 320px
- JPEG quality: 70

Do not fetch the raw frame from FrameStore merely to generate evidence.

The thumbnail already exists in DetectionEvent.

Also preserve the important behavior:

DetectionEvent MUST still be published when detections is empty.

Empty detections are meaningful because the compliance layer uses absence
to synthesize observations for persons already known to StateStore.

============================================================
5. DO NOT CHANGE FRAME ID SEMANTICS
============================================================

The existing system uses:

frame_id: int

Do not replace this with UUID in the domain event.

If PostgreSQL requires an internal UUID primary key, that is acceptable.

Example:

frames.id             UUID PRIMARY KEY
frames.frame_id       BIGINT NOT NULL

The frame_id is scoped to the ingestion/session context.

Do NOT assume frame_id alone is globally unique.

Use a uniqueness strategy such as:

UNIQUE(ingestion_session_id, frame_id)

where appropriate.

============================================================
6. DATABASE RESPONSIBILITY
============================================================

PostgreSQL should provide durable storage for:

1. Cameras
2. Streams
3. Zones
4. Ingestion sessions
5. Processing sessions
6. Frame metadata
7. Detection metadata
8. Track lifecycle metadata
9. Observations
10. State transitions
11. Temporal metrics
12. Compliance rule definitions
13. Compliance evaluations
14. Violations
15. Evidence groups
16. Evidence items
17. Notifications
18. Audit logs

Do NOT automatically persist every high-frequency object.

Classify every persistence target as:

REAL_TIME_ONLY
OPTIONALLY_PERSISTED
DURABLE
AUDIT_EVENT

Before implementation, document this classification.

============================================================
7. CAMERA TABLE
============================================================

Create:

cameras

Fields:

id
camera_key
name
description
location
status
enabled
created_at
updated_at

camera_key must be unique.

For the current MVP there is one fixed camera, but the schema must
support future multiple cameras.

Do not hard-code camera_01 assumptions into the database layer.

============================================================
8. STREAM TABLE
============================================================

Create:

streams

Fields:

id
camera_id
stream_type
source_reference
enabled
configuration
created_at
updated_at

stream_type:

VIDEO
RTSP

IMPORTANT SECURITY REQUIREMENT:

Never expose RTSP credentials through dashboard APIs.

Do not log passwords.

Do not store credentials in audit metadata.

Prefer secret references or environment/secret-manager configuration.

For pre-recorded video, store a safe source reference/path identifier,
not unnecessary binary video data.

============================================================
9. ZONE TABLE
============================================================

The current MVP has:

ONE HANDWASH ZONE PER CAMERA.

Create:

zones

Fields:

id
camera_id
zone_key
name
zone_type
geometry
enabled
created_at
updated_at

Use:

zone_type = HANDWASH / SINK

depending on existing naming conventions.

Store zone geometry as JSON/JSONB if appropriate.

Do not hard-code zone geometry into Python.

============================================================
10. INGESTION SESSION
============================================================

Create:

ingestion_sessions

This represents one execution of VideoConnector or RTSPConnector.

Fields:

id
camera_id
stream_id
started_at
ended_at
status
frames_read
frames_dropped
frames_published
frames_failed
reconnect_count
last_frame_at
error_count
created_at

Statuses should align with the existing connector/service semantics.

Do not invent conflicting status enums if the repository already has them.

The session must allow us to answer:

- When did ingestion start?
- When did it stop?
- Which camera was involved?
- Which stream was used?
- How many frames were read?
- How many were dropped?
- Did RTSP reconnect?
- Did ingestion fail?

============================================================
11. INGESTION AUDIT EVENTS
============================================================

When an ingestion session starts:

AUDIT:
STREAM_STARTED

When it stops:

AUDIT:
STREAM_STOPPED

For RTSP reconnect:

AUDIT:
STREAM_RECONNECTED

For terminal failure:

AUDIT:
STREAM_FAILED

Do NOT create audit records for every successfully read frame.

Audit logs are for meaningful lifecycle/business events.

============================================================
12. FRAME METADATA
============================================================

Create:

frames

Do NOT store raw frame bytes in PostgreSQL by default.

Fields:

id
ingestion_session_id
camera_id
zone_id
frame_id
captured_at
received_at
width
height
frame_store_key
processing_status
created_at

Suggested status values:

RECEIVED
PROCESSING
PROCESSED
DROPPED
EXPIRED
FAILED

However, inspect the existing code before creating duplicate concepts.

IMPORTANT:

The existing FrameStore is TTL based.

The documented default FRAME_TTL_SEC is 5 seconds.

Therefore PostgreSQL frame metadata must NOT imply that the actual frame
is retained indefinitely.

PostgreSQL contains metadata/reference only.

============================================================
13. PROCESSING SESSION
============================================================

Create:

processing_sessions

A processing session identifies the model/configuration used for a run.

Fields:

id
camera_id
started_at
ended_at
status
model_name
model_version
model_path/reference
configuration
created_at

This allows a violation to be traced to the exact processing configuration.

============================================================
14. DETECTION PERSISTENCE
============================================================

Create:

detections

Preserve the existing Detection model.

Persist:

id
frame_db_id
camera_id
zone_id
processing_session_id
class_id
class_name
confidence
x1
y1
x2
y2
use_case
created_at

Do not persist raw Ultralytics objects.

Persist normalized domain values.

IMPORTANT:

Detection persistence must be configurable.

The application must not become slower simply because PostgreSQL is enabled.

For high-frequency detection persistence, evaluate:

- batching
- asynchronous persistence
- bounded queue
- configurable enable/disable
- retention

============================================================
15. TRACK PERSISTENCE
============================================================

The current tracker is:

IoUTracker

The documented MVP uses:

iou_threshold = 0.3
max_lost_frames = 5

The tracker is lightweight and designed for a fixed single camera with
low person density.

Persist track lifecycle metadata, not every internal tracker operation.

Create:

tracks

Fields:

id
camera_id
zone_id
processing_session_id
track_id
first_seen_at
last_seen_at
status
created_at
updated_at

IMPORTANT:

track_id is not globally unique.

Scope it by the relevant processing/camera/session context.

Do not alter IoUTracker just to satisfy database persistence.

============================================================
16. OBSERVATION TABLE
============================================================

The existing Observation contains:

camera_id
zone_id
person_id
timestamp
frame_id
inside_sink_zone
water_detected
soap_detected
hands_interacting
track_bbox

Create:

observations

Fields:

id
frame_db_id
camera_id
zone_id
processing_session_id
track_id
observed_at
inside_sink_zone
water_detected
soap_detected
hands_interacting
track_bbox
metadata
created_at

Use proper columns for frequently queried fields.

Use JSONB only for extensible metadata.

============================================================
17. ABSENCE OBSERVATION SYNTHESIS
============================================================

This is important.

The current model can produce zero detections because the current YOLO
model outputs the handwash class rather than an explicit person class.

The ComplianceRuleEngine therefore synthesizes observations for persons
already known to StateStore.

Current behavior:

frames_lost <= 5:
    inside_sink_zone=True
    hands_interacting=False
    water_detected=False

frames_lost > 5:
    inside_sink_zone=False

This causes the state machine to eventually transition to UNKNOWN.

PostgreSQL must distinguish:

REAL observation

from:

SYNTHETIC observation

Add a field such as:

observation_type

with:

REAL
SYNTHETIC

Do not change existing Observation semantics unless required.

This distinction is essential for audit/debugging.

============================================================
18. STATE TRANSITIONS
============================================================

Persist state transition history.

The existing state machine is:

UNKNOWN
    ↓
AT_SINK
    ↓
WATER_ON
    ↓
SOAP_APPLIED
    ↓
WASHING
    ↓
RINSING
    ↓
COMPLETED

The state machine determines state.

PostgreSQL must NOT determine state.

Create:

state_transitions

Fields:

id
camera_id
zone_id
processing_session_id
track_id
previous_state
new_state
transition_at
duration_seconds
sequence_valid
reason
correlation_id
created_at

Only persist meaningful state transitions.

Do not create a database row every frame when the state remains unchanged.

============================================================
19. CURRENT STATE VS HISTORY
============================================================

Maintain the existing:

InMemoryStateStore

for active state.

The documented StateStore key is:

camera_id:zone_id

The stored value contains:

{
    "persons": {
        "<pid>": person_state
    }
}

Do NOT replace this with a PostgreSQL lookup on every frame.

Instead:

InMemoryStateStore
    =
low-latency current state

PostgreSQL
    =
durable state transition/history

If durable state snapshots are needed for restart recovery, add them
explicitly as a separate persistence mechanism.

Do not accidentally turn StateStore into a database repository.

============================================================
20. PERSON-LEVEL STATE MUST BE PRESERVED
============================================================

Although StateStore is keyed by:

camera_id:zone_id

the actual state contains:

persons -> person_id -> person_state

Therefore database persistence must preserve person/track context.

Do NOT implement one global compliance state per zone.

Correct:

camera
  ↓
zone
  ↓
person/track
  ↓
handwash state

This is important for future multi-person support.

============================================================
21. TEMPORAL METRICS
============================================================

The documented SpatioTemporalAnalyzer calculates metrics from timestamps,
NOT frame count.

Persist:

TemporalMetrics

Fields:

id
camera_id
zone_id
processing_session_id
track_id
evaluated_at
current_state
at_sink_duration
water_on_duration
soap_applied_duration
washing_duration
rinsing_duration
sequence_valid
continuity_valid
observation_count
last_gap_seconds
created_at

Optional:

metrics JSONB

for future extensions.

IMPORTANT:

Do not persist a temporal metric snapshot on every frame unless required.

Prefer persistence when:

- state changes
- compliance evaluation occurs
- violation occurs
- a configurable periodic snapshot is required

============================================================
22. TEMPORAL RULES FROM THE EXISTING DOCUMENT
============================================================

Preserve the documented behavior:

Duration is calculated from timestamps.

For state transition:

duration =
transition.timestamp - state_started_at

The analyzer accumulates:

at_sink_seconds
water_on_seconds
soap_applied_seconds
washing_seconds
rinsing_seconds

Ongoing time in the current state is included.

sequence_valid degrades monotonically.

If observation gap exceeds:

max_gap_seconds = 10.0

then:

continuity_valid = False

Do not move this logic into PostgreSQL.

PostgreSQL only records the result.

============================================================
23. COMPLIANCE RULE TABLE
============================================================

Create:

compliance_rules

Fields:

id
rule_key
name
use_case
version
configuration
enabled
created_at

The current handwash configuration contains:

minimum_washing_duration_seconds = 20.0
absence_threshold_seconds = 20.0
require_soap = false
require_water = false
require_sequence = false
require_completion = false
evidence_buffer_max = 10

These values come from the existing project configuration.

DO NOT hard-code them in the database.

Persist the actual rule configuration/version used.

A compliance result must always be traceable to the rule version.

============================================================
24. COMPLIANCE EVALUATIONS
============================================================

Create:

compliance_evaluations

Fields:

id
camera_id
zone_id
processing_session_id
track_id
rule_id
evaluated_at
result
reason_code
reason
correlation_id
created_at

Possible result values:

IN_PROGRESS
COMPLIANT
VIOLATION

Use the existing application's terminology if different.

IMPORTANT:

Avoid a circular database relationship between:

compliance_evaluations
and
temporal_metrics

Use a single-direction relationship.

Recommended:

temporal_metrics.evaluation_id -> compliance_evaluations.id

OR:

compliance_evaluations.temporal_metrics_id -> temporal_metrics.id

but not both unless there is a very strong reason.

Prefer the simpler relationship based on the actual repository flow.

============================================================
25. VIOLATION MODEL
============================================================

A violation is a business event.

Create:

violations

Fields:

id
group_id
compliance_evaluation_id
camera_id
zone_id
processing_session_id
track_id
rule_id
violation_type
reason_code
reason
started_at
confirmed_at
status
created_at
updated_at

group_id MUST be unique.

The documented RuleEvaluator behavior is:

absence begins
    ↓
mint group_id once
    ↓
buffer evidence
    ↓
either:
    compliance resumes
        ↓
        discard buffer

OR:

    absence threshold reached
        ↓
        violation confirmed
        ↓
        freeze evidence

Do not create one violation per frame.

Exactly one violation is associated with a confirmed group_id.

============================================================
26. EVIDENCE GROUP
============================================================

Preserve the documented EvidenceBuffer lifecycle.

Current behavior:

NO_GROUP
    ↓
GROUP_ACTIVE
    ↓
VIOLATION_CONFIRMED

The group_id is minted once when absence begins.

The current evidence buffer is a ring buffer.

Current default:

evidence_buffer_max = 10

When full:

oldest evidence item is evicted.

When compliance resumes:

discard the entire buffer.

When violation is confirmed:

freeze the buffer.

After freeze:

the evidence is immutable.

This behavior is already explicitly documented and must not be changed.

============================================================
27. EVIDENCE GROUP TABLE
============================================================

Create:

evidence_groups

Fields:

id
group_id
violation_id
camera_id
zone_id
processing_session_id
track_id
started_at
frozen_at
item_count
created_at

group_id must be unique.

============================================================
28. EVIDENCE ITEMS
============================================================

Create:

evidence_items

Fields:

id
evidence_group_id
frame_db_id
frame_id
sequence_number
captured_at
thumbnail_reference
storage_key
metadata
created_at

Do NOT store thumbnail bytes in PostgreSQL by default.

The existing DetectionEvent contains thumbnail bytes.

For the MVP, determine whether evidence should be stored in:

- local evidence/ directory
- object storage
- another existing storage abstraction

If the current evidence implementation already writes to:

evidence/

reuse it.

PostgreSQL should store metadata/reference to that evidence.

Do not introduce object storage merely because PostgreSQL is being added.

============================================================
29. EVIDENCE PUBLICATION
============================================================

The existing architecture publishes:

compliance.alert

and:

evidence.capture

Maintain those topics.

On confirmed violation:

1. Persist violation
2. Persist evidence metadata/reference
3. Publish ComplianceEvent
4. Publish EvidenceCaptureEvent

Use group_id as the correlation identifier.

Do not publish evidence for discarded groups.

Do not publish duplicate evidence for the same group_id.

============================================================
30. NOTIFICATION TABLE
============================================================

Create:

notifications

Fields:

id
violation_id
channel
status
created_at
sent_at
delivered_at
failure_reason

For the current dashboard use case:

channel = DASHBOARD

The notification is associated with the violation.

Do not make notification creation responsible for compliance evaluation.

============================================================
31. DASHBOARD READ MODEL
============================================================

The dashboard needs to answer:

1. Is the camera running?
2. Is video ingestion active?
3. How many frames have been processed?
4. Is inference healthy?
5. Is compliance processing healthy?
6. How many violations occurred?
7. Which violations are new?
8. What is the current compliance state?
9. What evidence belongs to a violation?
10. What happened during a particular violation?

Do not make the dashboard reconstruct these by reading raw pipeline events.

Provide database-backed query services.

============================================================
32. DASHBOARD APIs
============================================================

Inspect existing FastAPI routes first.

Add APIs consistent with existing conventions.

Potential endpoints:

GET /health

GET /api/v1/dashboard/summary

GET /api/v1/cameras

GET /api/v1/cameras/{camera_id}

GET /api/v1/cameras/{camera_id}/status

GET /api/v1/ingestion/sessions

GET /api/v1/compliance/events

GET /api/v1/compliance/violations

GET /api/v1/compliance/violations/{violation_id}

GET /api/v1/compliance/violations/{violation_id}/evidence

GET /api/v1/audit-logs

Do not blindly create these exact URLs.

Follow the existing FastAPI route structure.

============================================================
33. DASHBOARD SUMMARY
============================================================

The dashboard summary should expose information such as:

{
    "system_status": "RUNNING",

    "camera": {
        "camera_id": "...",
        "status": "ONLINE"
    },

    "ingestion": {
        "status": "RUNNING",
        "frames_read": 1250,
        "frames_dropped": 3,
        "frames_published": 1247
    },

    "inference": {
        "status": "RUNNING",
        "frames_processed": 1247,
        "detections_total": 380
    },

    "compliance": {
        "status": "RUNNING",
        "evaluations_total": 1247,
        "violations_total": 2
    },

    "latest_violation": {
        "group_id": "...",
        "camera_id": "...",
        "zone_id": "...",
        "reason": "...",
        "confirmed_at": "..."
    }
}

The existing /health endpoint already exposes similar runtime metrics.

Do not duplicate metrics unnecessarily.

Determine whether dashboard APIs should reuse health metrics or create
a dedicated read model.

============================================================
34. AUDIT LOG
============================================================

Create:

audit_logs

This table is APPEND ONLY.

Fields:

id
occurred_at
actor_type
actor_id
action
entity_type
entity_id
correlation_id
source
outcome
reason
metadata
created_at

For system-generated events:

actor_type = SYSTEM

Examples:

STREAM_STARTED
STREAM_STOPPED
STREAM_RECONNECTED
STREAM_FAILED

MODEL_LOADED
MODEL_LOAD_FAILED

STATE_CHANGED

COMPLIANCE_EVALUATED
VIOLATION_CREATED

EVIDENCE_GROUP_CREATED
EVIDENCE_DISCARDED
EVIDENCE_FROZEN

NOTIFICATION_CREATED
NOTIFICATION_FAILED

============================================================
35. AUDIT LOG RULE
============================================================

Do NOT audit every frame.

Do audit important state/business transitions.

For a confirmed violation, the audit trail should allow:

VIOLATION_CREATED
    ↓
EVIDENCE_FROZEN
    ↓
NOTIFICATION_CREATED

For a state change:

STATE_CHANGED

with:

previous_state
new_state
track_id
camera_id
zone_id
timestamp

For compliance:

COMPLIANCE_EVALUATED

with:

rule_key
rule_version
result
reason
track_id
camera_id
zone_id

Do not put thumbnail bytes into audit logs.

============================================================
36. CORRELATION ID
============================================================

Use group_id as the business correlation ID for violation episodes.

Trace:

Detection
    ↓
Observation
    ↓
State
    ↓
Temporal Metrics
    ↓
Compliance Evaluation
    ↓
Violation
    ↓
Evidence
    ↓
Notification
    ↓
Audit

Where the event is part of a violation episode:

correlation_id = group_id

For events before group creation, use a suitable processing/frame/session
correlation identifier.

Do not invent group_id for every frame.

============================================================
37. TRANSACTION BOUNDARIES
============================================================

Define transaction boundaries carefully.

When a violation is confirmed, the durable operation should establish:

ComplianceEvaluation
+
Violation
+
EvidenceGroup
+
Evidence metadata
+
Notification
+
Audit

with clear consistency semantics.

However:

DO NOT hold a PostgreSQL transaction open while performing:

- large file writes
- object storage uploads
- network calls
- dashboard communication
- message queue blocking operations

If external event publication cannot be made transactionally consistent,
document the limitation.

Evaluate an Outbox pattern only if the repository's production
requirements justify it.

Do not add an elaborate distributed transaction system to the current
single-process MVP unnecessarily.

============================================================
38. DATABASE FAILURE MUST NOT KILL CV PROCESSING
============================================================

This is critical.

Do NOT implement:

process frame
    ↓
write PostgreSQL
    ↓
continue

for every frame if that makes PostgreSQL a synchronous bottleneck.

Instead determine which operations are:

CRITICAL
BEST_EFFORT
BATCHABLE

For example:

Critical:
    confirmed violation persistence

Durable but batchable:
    detections
    observations

Historical:
    state transitions

Operational:
    ingestion counters

Best effort:
    high-frequency diagnostics

If PostgreSQL becomes temporarily unavailable:

- do not crash the ingestion thread
- do not permanently stop inference
- do not lose process lifecycle control
- log the failure
- increment metrics
- retry critical persistence
- use bounded buffering where appropriate
- never allow unbounded memory growth

Document the selected failure strategy.

============================================================
39. BATCH PERSISTENCE
============================================================

For high-frequency entities:

detections
observations
frame metadata

evaluate batch persistence.

Configuration should support something similar to:

persistence:
    enabled: true

    detections:
        enabled: true
        batch_size: 100
        flush_interval_seconds: 1

    observations:
        enabled: true
        batch_size: 100
        flush_interval_seconds: 1

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

Use the existing configuration conventions.

Do not introduce these exact values without considering the actual workload.

============================================================
40. RETENTION
============================================================

Add configurable retention policies.

Do not assume the database should retain every frame/detection forever.

Potential categories:

frame metadata
detections
observations
temporal metrics
compliance evaluations
violations
evidence metadata
audit logs

The actual retention values must be configurable.

Do not automatically delete audit logs unless the project's retention
policy explicitly allows it.

============================================================
41. INDEXING
============================================================

Design indexes based on dashboard and operational queries.

At minimum evaluate:

camera + time
zone + time
ingestion session
processing session
frame lookup
track lookup
compliance result + time
violation + confirmed_at
group_id
evidence_group_id
correlation_id
audit entity
audit action
audit timestamp

Do not create excessive indexes on high-write tables.

Explain why each index exists.

============================================================
42. DATABASE SCHEMA RELATIONSHIP
============================================================

The logical relationship should be approximately:

CAMERA
  |
  +---- STREAM
  |
  +---- ZONE
          |
          +---- INGESTION SESSION
          |        |
          |        +---- FRAME
          |
          +---- PROCESSING SESSION
                   |
                   +---- DETECTION
                   |
                   +---- TRACK
                   |
                   +---- OBSERVATION
                   |
                   +---- STATE TRANSITION
                   |
                   +---- TEMPORAL METRICS
                   |
                   +---- COMPLIANCE EVALUATION
                              |
                              +---- VIOLATION
                                      |
                                      +---- EVIDENCE GROUP
                                      |        |
                                      |        +---- EVIDENCE ITEM
                                      |
                                      +---- NOTIFICATION

AUDIT LOG
    |
    +---- references any important entity
    +---- correlation_id connects related operations

============================================================
43. IMPORTANT: NO CIRCULAR FOREIGN KEY DESIGN
============================================================

Avoid creating this:

compliance_evaluations
    -> temporal_metrics

and:

temporal_metrics
    -> compliance_evaluations

unless there is a strong requirement.

Prefer:

compliance_evaluations
    |
    +---- temporal_metrics

OR:

temporal_metrics
    |
    +---- compliance_evaluation

Use the direction that matches the actual lifecycle.

============================================================
44. DATABASE REPOSITORY LAYER
============================================================

Create interfaces such as:

CameraRepository
StreamRepository
ZoneRepository
IngestionSessionRepository
ProcessingSessionRepository
FrameRepository
DetectionRepository
TrackRepository
ObservationRepository
StateTransitionRepository
TemporalMetricsRepository
ComplianceRuleRepository
ComplianceEvaluationRepository
ViolationRepository
EvidenceRepository
NotificationRepository
AuditLogRepository

Use Protocol/ABC based on existing project conventions.

The CV components must not execute SQL directly.

Example:

ComplianceRuleEngine
    ↓
ComplianceRepository
    ↓
PostgreSQL implementation

NOT:

ComplianceRuleEngine
    ↓
SQLAlchemy query

============================================================
45. AUDIT SERVICE
============================================================

Create an AuditService abstraction.

Example:

audit_service.record(
    action="VIOLATION_CREATED",
    entity_type="violation",
    entity_id=str(violation.id),
    correlation_id=group_id,
    source="ComplianceRuleEngine",
    actor_type="SYSTEM",
    outcome="SUCCESS",
    metadata={...},
)

Do not spread audit SQL across the codebase.

============================================================
46. DATABASE SESSION MANAGEMENT
============================================================

Use dependency injection.

Do not create a global database connection inside each component.

Provide:

Database
DatabaseSessionFactory
UnitOfWork if appropriate

Ensure:

- connection pooling
- transaction handling
- rollback
- connection cleanup
- shutdown cleanup
- configurable timeout
- database health check

Follow the project's threading model.

The current application uses Python threading, NOT asyncio.

Therefore inspect how database access should safely operate with threads.

Do not accidentally introduce unsafe shared SQLAlchemy sessions between
threads.

============================================================
47. APPLICATION STARTUP
============================================================

The documented startup order is:

1. InMemoryFrameStore
2. InMemoryMessageQueue
3. InMemoryStateStore
4. StreamIngestionService
5. ModelRegistry
6. YoloInferenceEngine
7. CPUInferenceWorker
8. HandwashRuleConfig
9. ComplianceRuleEngine
10. ComplianceWorker
11. ingestion thread

PostgreSQL should be initialized in a way that does not violate this
dependency model.

Recommended conceptual order:

Database infrastructure
    ↓
InMemoryFrameStore
    ↓
InMemoryMessageQueue
    ↓
InMemoryStateStore
    ↓
existing CV components
    ↓
persistence services
    ↓
workers
    ↓
ingestion

Do not start frame processing before required database migrations/
connectivity checks if the application's selected mode requires durable
persistence.

However, do not make an optional PostgreSQL feature prevent a local
in-memory development mode from starting unless explicitly configured
as mandatory.

============================================================
48. APPLICATION SHUTDOWN
============================================================

Preserve graceful shutdown.

Current documented order:

1. Stop ingestion
2. Stop CPUInferenceWorker
3. Stop ComplianceWorker
4. Close StateStore
5. Close ModelRegistry

Add:

flush pending persistence
close persistence workers
close database pool

The order must prevent new writes while shutdown is occurring.

Do not terminate the database writer before the pipeline has stopped
producing persistence events.

============================================================
49. DATABASE CONFIGURATION
============================================================

Add database configuration using environment variables.

Example:

DATABASE_URL

or the project's preferred convention.

Never commit:

- passwords
- database credentials
- RTSP credentials

Example:

database:
    enabled: true
    url: ${DATABASE_URL}
    pool:
        min_size: 2
        max_size: 10
    timeout_seconds: 10

Use actual project configuration conventions.

============================================================
50. MIGRATIONS
============================================================

Use the existing migration framework.

If Alembic exists, use Alembic.

Create migrations for:

cameras
streams
zones
ingestion_sessions
processing_sessions
frames
detections
tracks
observations
state_transitions
temporal_metrics
compliance_rules
compliance_evaluations
violations
evidence_groups
evidence_items
notifications
audit_logs

If an outbox is justified:

outbox_events

Migrations must work from an empty PostgreSQL database.

Do not manually create production tables outside the migration system.

============================================================
51. END-TO-END TRACEABILITY
============================================================

The most important acceptance requirement:

Given:

group_id

the system must be able to trace:

group_id
    ↓
violation
    ↓
compliance evaluation
    ↓
rule + version
    ↓
temporal metrics
    ↓
state transitions
    ↓
observation
    ↓
track
    ↓
detection
    ↓
frame
    ↓
processing session
    ↓
ingestion session
    ↓
camera
    ↓
stream

And:

group_id
    ↓
evidence group
    ↓
evidence items
    ↓
thumbnail reference

And:

group_id
    ↓
notification

And:

group_id
    ↓
audit logs

This must be demonstrable through repository/service/API queries.

============================================================
52. DASHBOARD VIOLATION VIEW
============================================================

The dashboard must be able to show:

VIOLATION

Camera:
Zone:
Detected at:
Confirmed at:
Violation reason:
Rule:
Rule version:
Group ID:
Current status:

Temporal metrics:

Washing duration:
At sink duration:
Water duration:
Soap duration:
Continuity:
Sequence valid:

Evidence:

Thumbnail 1
Thumbnail 2
...
Thumbnail N

The dashboard should retrieve thumbnails through a backend API.

Do not expose local filesystem paths directly to the browser.

Do not expose database credentials.

============================================================
53. REAL-TIME DASHBOARD ALERT
============================================================

The existing MessageQueue contains:

compliance.alert
evidence.capture

Reuse this architecture.

For a violation:

ComplianceRuleEngine
    ↓
ComplianceEvent
    ↓
compliance.alert
    ↓
dashboard notification

The dashboard should display:

NEW COMPLIANCE VIOLATION

Camera:
Zone:
Reason:
Timestamp:

with:

View Violation

When the user selects:

View Violation

the dashboard retrieves:

violation details
+
evidence metadata
+
thumbnail references

The lightweight alert must NOT contain the complete evidence payload.

============================================================
54. HEALTH AND MONITORING
============================================================

The existing /health endpoint already reports:

ingestion metrics
message queue metrics
frame store metrics
inference metrics
compliance metrics

Preserve it.

Extend it with database health:

database:
    status
    connection_pool
    pending_writes
    failed_writes
    write_latency

Do not make /health execute expensive queries.

A simple SELECT 1 or equivalent is sufficient for connectivity.

============================================================
55. DATABASE METRICS
============================================================

Add:

database_connections
database_write_latency
database_write_failures
database_transaction_rollbacks
database_batch_size
database_pending_events
database_pool_utilization

Persistence metrics:

frames_persisted
detections_persisted
observations_persisted
state_transitions_persisted
compliance_evaluations_persisted
violations_persisted
evidence_items_persisted
audit_events_persisted

============================================================
56. TESTING STRATEGY
============================================================

Do not require:

- YOLO
- GPU
- RTSP camera
- external message broker

for compliance unit tests.

The existing project already has extensive compliance tests for:

StateStore
StateMachine
TemporalAnalyzer
EvidenceBuffer
RuleEvaluator
ComplianceRuleEngine

Preserve those tests.

Add PostgreSQL tests independently.

============================================================
57. DATABASE UNIT TESTS
============================================================

Test:

CameraRepository
StreamRepository
ZoneRepository
IngestionSessionRepository
FrameRepository
DetectionRepository
ObservationRepository
StateTransitionRepository
TemporalMetricsRepository
ComplianceEvaluationRepository
ViolationRepository
EvidenceRepository
NotificationRepository
AuditLogRepository

Test:

create
read
update
list
filter
duplicate handling
transaction rollback
foreign keys
unique constraints

============================================================
58. POSTGRESQL INTEGRATION TESTS
============================================================

Use a real PostgreSQL test instance.

Prefer the existing Docker/Testcontainers approach if present.

Test:

- migration from empty database
- repository operations
- transactions
- rollback
- foreign keys
- uniqueness
- JSONB
- timestamp handling
- concurrent repository access where applicable

Do not mock PostgreSQL for all integration tests.

============================================================
59. END-TO-END SYNTHETIC TEST
============================================================

Create an end-to-end test using synthetic detections/observations.

Example:

Camera:
camera_01

Zone:
main_sink

Person:
track_id = 7

Sequence:

UNKNOWN
    ↓
AT_SINK
    ↓
WATER_ON
    ↓
SOAP_APPLIED
    ↓
WASHING
    ↓
8 seconds
    ↓
person stops washing

With:

absence_threshold_seconds = 20

Expected:

Compliance = VIOLATION
Violation = CREATED
group_id = CREATED
Evidence = FROZEN
Evidence Items = PERSISTED
Notification = CREATED
Audit = CREATED

Then test:

WASHING
    ↓
23 seconds
    ↓
RINSING
    ↓
COMPLETED

Expected:

Compliance = COMPLIANT
Violation = NONE
Evidence = NONE
Notification = NONE

============================================================
60. EVIDENCE LIFECYCLE TEST
============================================================

Test the exact documented lifecycle.

Scenario 1:

absence starts
    ↓
group_id generated
    ↓
thumbnail buffered
    ↓
compliance resumes before threshold
    ↓
buffer discarded
    ↓
NO violation
    ↓
NO evidence persisted

Scenario 2:

absence starts
    ↓
group_id generated
    ↓
thumbnail buffer fills
    ↓
oldest thumbnails evicted
    ↓
threshold reached
    ↓
violation confirmed
    ↓
buffer frozen
    ↓
evidence persisted
    ↓
ComplianceEvent published
    ↓
EvidenceCaptureEvent published

Scenario 3:

additional frames arrive after confirmation

Expected:

NO second violation
NO additional evidence mutation
NO second ComplianceEvent
NO second EvidenceCaptureEvent

This preserves the documented idempotency guarantee:
one violation/evidence publication per group_id, not per frame.

============================================================
61. MULTI-CAMERA / MULTI-ZONE ISOLATION TEST
============================================================

Even though the current MVP is:

single camera
single zone

test database isolation for:

camera_01 + zone_01
camera_01 + zone_02
camera_02 + zone_01

State and violations must never leak between cameras/zones.

Also test:

camera_01
zone_01
track_id=7

versus:

camera_01
zone_01
track_id=8

============================================================
62. AUDIT TEST
============================================================

For one confirmed violation, verify:

COMPLIANCE_EVALUATED
VIOLATION_CREATED
EVIDENCE_FROZEN
NOTIFICATION_CREATED

Each must have:

timestamp
entity
entity_id
correlation_id
source
outcome

Verify that audit logs cannot be modified through the normal application
service.

============================================================
63. IDEMPOTENCY
============================================================

The system must tolerate duplicate processing events.

At minimum evaluate:

duplicate DetectionEvent
duplicate frame
duplicate group_id
duplicate ComplianceEvent
duplicate evidence event

A repeated violation confirmation for the same group_id must not create:

two violations
two evidence groups
two notifications

Use database constraints where appropriate.

Do not rely only on Python in-memory flags for database idempotency.

============================================================
64. PERFORMANCE REQUIREMENT
============================================================

The application currently processes approximately:

target_fps = 5

The existing configuration also has:

inference.queue_size = 10
FrameStore TTL = 5 seconds
evidence_buffer_max = 10

Do not allow PostgreSQL persistence to cause:

frame expiration spikes
inference backlog
compliance queue starvation
unbounded memory growth

Measure:

ingestion latency
inference latency
compliance latency
database write latency
end-to-end latency

Compare:

PostgreSQL disabled
vs
PostgreSQL enabled

The CV pipeline should remain responsive.

============================================================
65. IMPORTANT DESIGN DECISION
============================================================

Do NOT turn this:

DetectionEvent
    ↓
ComplianceWorker
    ↓
ComplianceRuleEngine
    ↓
PostgreSQL

into:

DetectionEvent
    ↓
PostgreSQL
    ↓
read from PostgreSQL
    ↓
ComplianceWorker

That would unnecessarily introduce database latency into the hot path.

The intended design is:

DetectionEvent
    ↓
ComplianceWorker
    ↓
ComplianceRuleEngine
    |
    +--> StateStore
    |
    +--> SpatioTemporalAnalyzer
    |
    +--> RuleEvaluator
    |
    +--> persistence service
    |
    +--> MessageQueue

============================================================
66. AUDITABILITY VS HIGH-FREQUENCY DATA
============================================================

The database should make the system auditable without storing every
intermediate runtime operation.

Persist enough information to reconstruct:

WHY did the violation happen?

Not necessarily:

WHAT happened on every single frame?

The minimum useful chain is:

Violation
    ↓
ComplianceEvaluation
    ↓
Rule Version
    ↓
TemporalMetrics
    ↓
StateTransitions
    ↓
Observations
    ↓
Detection / Track
    ↓
Frame
    ↓
Ingestion Session
    ↓
Camera

Document any information intentionally not persisted.

============================================================
67. PRODUCTION SECURITY
============================================================

Implement:

- parameterized SQL / ORM
- no SQL string concatenation
- environment-based DB credentials
- secure DB connection
- least-privilege database user
- no secrets in logs
- no RTSP credentials in API responses
- no RTSP credentials in audit metadata
- evidence authorization
- audit endpoint authorization
- validation on all API parameters

============================================================
68. IMPLEMENTATION WORKFLOW
============================================================

Follow:

DISCOVER
    ↓
ASSESS EXISTING ARCHITECTURE
    ↓
DESIGN PERSISTENCE BOUNDARIES
    ↓
DESIGN ER MODEL
    ↓
DEFINE DOMAIN/PERSISTENCE MODELS
    ↓
DEFINE REPOSITORY INTERFACES
    ↓
IMPLEMENT DATABASE INFRASTRUCTURE
    ↓
IMPLEMENT MIGRATIONS
    ↓
IMPLEMENT REPOSITORIES
    ↓
IMPLEMENT AUDIT SERVICE
    ↓
INTEGRATE INGESTION
    ↓
INTEGRATE PROCESSING
    ↓
INTEGRATE STATE/OBSERVATION
    ↓
INTEGRATE TEMPORAL METRICS
    ↓
INTEGRATE COMPLIANCE
    ↓
INTEGRATE VIOLATION/EVIDENCE
    ↓
INTEGRATE NOTIFICATION
    ↓
INTEGRATE DASHBOARD APIs
    ↓
ADD DATABASE HEALTH
    ↓
TEST
    ↓
PERFORMANCE TEST
    ↓
FAILURE TEST
    ↓
SECURITY REVIEW
    ↓
PRODUCTION READINESS REVIEW

============================================================
69. DO NOT OVER-ENGINEER
============================================================

The source architecture is explicitly an MVP.

Current documented scope:

- single fixed camera
- single handwash zone
- CPU inference
- single process
- in-memory message queue
- in-memory state
- Streamlit planned frontend

Therefore:

DO NOT introduce unnecessarily:

- Kafka
- Redis Streams
- Kubernetes
- microservices
- distributed transactions
- complex event sourcing
- CQRS
- distributed locks

unless the repository already contains them or there is a clear requirement.

PostgreSQL should be introduced cleanly while preserving the MVP's
simplicity.

============================================================
70. FUTURE EXTENSIBILITY
============================================================

The persistence design should allow future replacement of:

InMemoryMessageQueue
    -> Redis/Kafka

InMemoryStateStore
    -> Redis/PostgreSQL-backed state

Local evidence/
    -> Object Storage

single camera
    -> multiple cameras

single process
    -> distributed workers

But do not implement these future systems now unless explicitly required.

Use interfaces so they can be introduced later.

============================================================
71. FINAL ACCEPTANCE CRITERIA
============================================================

The implementation is complete only when:

DATABASE

[ ] PostgreSQL starts successfully
[ ] migrations work from empty DB
[ ] migrations work on existing DB
[ ] connection pooling works
[ ] database sessions are thread-safe
[ ] rollback works
[ ] shutdown closes connections

INGESTION

[ ] camera persisted
[ ] stream persisted
[ ] ingestion session created
[ ] start/stop persisted
[ ] meaningful ingestion audit events created
[ ] high-frequency ingestion is not blocked by DB

PROCESSING

[ ] processing session persisted
[ ] model/version traceable
[ ] frame metadata optionally persisted
[ ] detections optionally persisted
[ ] track context traceable
[ ] observations traceable

STATE

[ ] existing InMemoryStateStore remains
[ ] state machine remains independent
[ ] state transitions persisted
[ ] person-level state preserved
[ ] camera/zone isolation works

TEMPORAL

[ ] timestamp-based durations preserved
[ ] temporal metrics persisted
[ ] sequence validity traceable
[ ] continuity traceable

COMPLIANCE

[ ] rule configuration persisted
[ ] rule version persisted
[ ] compliance evaluation persisted
[ ] result persisted
[ ] reason persisted

VIOLATION

[ ] group_id unique
[ ] exactly one violation per confirmed group
[ ] violation reason persisted
[ ] violation timestamps persisted
[ ] violation status persisted

EVIDENCE

[ ] evidence group created
[ ] evidence buffer lifecycle preserved
[ ] discarded groups are not treated as violations
[ ] frozen evidence is immutable
[ ] evidence items persisted
[ ] thumbnails referenced correctly
[ ] evidence is viewable through API

NOTIFICATION

[ ] dashboard notification created
[ ] notification linked to violation
[ ] notification status tracked
[ ] duplicate notifications prevented

AUDIT

[ ] audit log is append-only
[ ] violation lifecycle auditable
[ ] ingestion lifecycle auditable
[ ] state changes auditable
[ ] compliance evaluations auditable
[ ] evidence lifecycle auditable
[ ] correlation IDs work

DASHBOARD

[ ] dashboard summary works
[ ] camera status works
[ ] ingestion status works
[ ] compliance status works
[ ] violation list works
[ ] violation details work
[ ] evidence thumbnails can be viewed
[ ] audit information can be queried by authorized users

PERFORMANCE

[ ] PostgreSQL does not block the hot CV path
[ ] persistence is bounded
[ ] database failures do not crash workers
[ ] database metrics are exposed
[ ] shutdown flushes pending persistence safely

============================================================
72. FINAL REPORT REQUIRED
============================================================

After implementation, provide:

1. Existing architecture discovered
2. Existing components reused
3. PostgreSQL architecture
4. Why PostgreSQL does not sit in the hot path
5. Complete ER diagram in text
6. Tables created
7. Important columns
8. Primary keys
9. Foreign keys
10. Unique constraints
11. Indexes
12. Migrations
13. Repository interfaces
14. PostgreSQL implementations
15. Transaction boundaries
16. Ingestion integration
17. Detection integration
18. Tracking integration
19. Observation integration
20. State transition integration
21. Temporal metrics integration
22. Compliance integration
23. Violation integration
24. Evidence integration
25. Notification integration
26. Audit implementation
27. Dashboard API implementation
28. Real-time alert integration
29. Failure/retry behavior
30. Idempotency strategy
31. Retention strategy
32. Performance measurements
33. Security considerations
34. Tests added
35. End-to-end test result
36. Migration commands
37. PostgreSQL startup commands
38. Application startup commands
39. Known limitations
40. Remaining production work

Do not claim "production ready" merely because PostgreSQL works.

Explicitly identify remaining production concerns such as:

- PostgreSQL backup/restore
- high-volume detection/observation retention
- evidence object storage
- outbox/event delivery
- database failover
- monitoring
- authentication/authorization
- data retention jobs
- partitioning if volume requires it
- operational deployment
- database migration strategy
- YOLO/Ultralytics licensing

============================================================
73. FINAL ARCHITECTURAL PRINCIPLE
============================================================

The final implementation must preserve this architecture:

                         VIDEO / RTSP
                              |
                              v
                    StreamIngestionService
                              |
                     ingestion.frames
                              |
                              v
                    CPUInferenceWorker
                              |
                     inference.detections
                              |
                              v
                     ComplianceWorker
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
      IoUTracker       ObservationBuilder   StateMachine
          |                   |                   |
          +-------------------+-------------------+
                              |
                              v
                  SpatioTemporalAnalyzer
                              |
                              v
                     RuleEvaluator
                              |
                              v
                    ComplianceRuleEngine
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
        StateStore       PostgreSQL       MessageQueue
             |                |                |
             |                |          compliance.alert
             |                |          evidence.capture
             |                |
             |                v
             |          Durable History
             |
             v
       Current Runtime State

PostgreSQL:

DURABLE SYSTEM OF RECORD

MessageQueue:

REAL-TIME EVENT TRANSPORT

FrameStore:

SHORT-LIVED FRAME STORAGE

StateStore:

LOW-LATENCY ACTIVE COMPLIANCE STATE

Evidence Store:

ACTUAL THUMBNAIL / IMAGE BYTES

Dashboard:

READS DURABLE DATA THROUGH API
+
RECEIVES REAL-TIME ALERTS

The implementation must preserve these boundaries.