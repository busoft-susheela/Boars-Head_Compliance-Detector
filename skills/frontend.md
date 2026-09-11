Frontend: Streamlit

You are designing a production-oriented web dashboard for a Computer Vision compliance monitoring system.

The backend pipeline is:

VIDEO / RTSP
    ↓
Stream Ingestion
    ↓
YOLO Detection
    ↓
ByteTrack
    ↓
Observation Builder
    ↓
State Transition
    ↓
Spatio-Temporal Analyzer
    ↓
Compliance Rule Engine
    ↓
Compliance Event
    ↓
Alert + Evidence
    ↓
Dashboard

The current use case is handwash compliance detection.

The dashboard must allow an operator to understand:

Whether video ingestion is running.
Whether frames are being processed.
Whether inference is healthy.
Current processing/progress status.
Current compliance state.
Whether a compliance violation occurred.
When a violation occurred.
Which camera/zone was affected.
A notification/alert when a violation occurs.
The violation thumbnail/evidence when the operator opens the violation.
Historical compliance violations.

The goal is not a decorative UI mockup. Design a clean, production-oriented monitoring dashboard that can later connect to the actual backend APIs/events.

1. FIRST: INSPECT THE EXISTING REPOSITORY

Before writing UI code:

Inspect the entire repository structure.
Identify:
frontend framework
existing frontend components
routing
state management
styling system
API client
WebSocket/SSE implementation if present
existing backend APIs
existing event schemas
existing DetectionEvent
existing ComplianceEvent
existing evidence payload
FrameStore
MessageQueue
camera/zone configuration
Reuse existing conventions and dependencies.
Do not introduce a new frontend framework if one already exists.
Do not duplicate backend logic in the frontend.
Do not invent API contracts when an existing backend contract can be reused.

If backend APIs/events required by the dashboard do not exist yet, define clean frontend-facing interfaces/adapters rather than implementing fake backend logic.

2. UI DESIGN OBJECTIVE

Create a dashboard for an operator monitoring one or more cameras.

The UI should answer the following questions immediately:

Are my cameras running?
        ↓
Are frames being ingested?
        ↓
Is inference processing?
        ↓
What is the current compliance state?
        ↓
Has anything violated?
        ↓
What happened?
        ↓
Can I see the evidence?

The dashboard should prioritize:

operational visibility
compliance visibility
violation visibility
evidence inspection
clear status indicators
low cognitive load
real-time updates
clean information hierarchy

Avoid excessive charts and decorative elements.

3. MAIN DASHBOARD LAYOUT

Design the main page approximately as:

┌─────────────────────────────────────────────────────────────────────┐
│ CV Compliance Monitoring                         ● System Healthy  │
│ Handwash Compliance                              Last updated: ... │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Cameras       Processing       Compliance       Violations         │
│  4 / 4         4 / 4            96.2%            3                 │
│  Online        Active            Compliant       Today              │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ CAMERA / ZONE STATUS                                                │
│                                                                     │
│ ┌───────────────────────────────────────────────────────────────┐   │
│ │ Camera 01   Main Sink Area              ● Processing          │   │
│ │                                                               │   │
│ │ Ingestion    ● Connected                                      │   │
│ │ FPS          5.0                                              │   │
│ │ Frames       12,482                                            │   │
│ │ Inference   ● Running                                         │   │
│ │                                                               │   │
│ │ Current State: WASHING                                        │   │
│ │ Duration: 14.2 sec                                            │   │
│ └───────────────────────────────────────────────────────────────┘   │
│                                                                     │
│ ┌───────────────────────────────────────────────────────────────┐   │
│ │ Camera 02   Secondary Sink             ● Processing            │   │
│ │ ...                                                           │   │
│ └───────────────────────────────────────────────────────────────┘   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ RECENT COMPLIANCE EVENTS                                            │
│                                                                     │
│ Time       Camera       Zone          Result       Duration         │
│ 21:24:32   Camera 01    Main Sink     ✓ PASS       23.4 sec         │
│ 21:21:14   Camera 02    Sink 2        ⚠ VIOLATION  8.2 sec          │
│ 21:18:09   Camera 01    Main Sink     ✓ PASS       25.1 sec         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

Use responsive cards/tables rather than forcing everything into a dense grid.

4. TOP-LEVEL KPI CARDS

Create four to six KPI cards.

Recommended:

System Status
● HEALTHY

4 / 4 cameras online
Cameras
4 / 4
ONLINE
Processing
4 / 4
PROCESSING
Compliance
96.2%
COMPLIANT
Violations
3
TODAY
Processing FPS
19.8 FPS
SYSTEM

The cards must update dynamically when real backend data becomes available.

Do not hard-code these values in the final architecture.

Mock data may be used during UI development, but isolate it behind a repository/service layer.

5. CAMERA MONITORING SECTION

Create a camera status section.

Each camera card should show:

Camera 01
Main Sink Area

● ONLINE

Ingestion
● Connected

FPS
5.0

Frames Processed
12,482

Inference
● Running

Current State
WASHING

State Duration
14.2 sec

Potential statuses:

ONLINE
CONNECTING
DEGRADED
DISCONNECTED
ERROR
STOPPED

Processing statuses:

STARTING
WARMING_UP
PROCESSING
BACKPRESSURED
ERROR
STOPPED

Use clear visual status indicators.

Do not rely only on color. Include text/icons.

6. VIDEO INGESTION STATUS

The dashboard must expose ingestion health.

For each camera show:

Video Ingestion

Connection       Connected
Source           RTSP
FPS              5.0
Frames Received  12,482
Frames Processed 12,401
Dropped Frames   81
Last Frame       21:29:41

If the source is a prerecorded video:

Source
video.mp4

Progress
████████████████░░░░ 78%

00:07:48 / 00:10:00

For RTSP:

Source
RTSP

Live
● LIVE

Received FPS
5.0

Important:

Do not show a fake progress percentage for an infinite/live RTSP stream.

For RTSP, use:

LIVE
Elapsed
Frames Received
Current FPS

For prerecorded video, show:

Current Position
Duration
Progress %
Frames Processed
7. PROCESSING PIPELINE STATUS

Provide an expandable pipeline status view.

Example:

Camera 01

● Ingestion
      ↓
● YOLO Detection
      ↓
● ByteTrack
      ↓
● Observation Builder
      ↓
● State Transition
      ↓
● Temporal Analyzer
      ↓
● Compliance Rule Engine
      ↓
● Alert / Evidence

Each stage should have:

status
last processed timestamp
throughput where applicable
error state where applicable

Example:

YOLO Detection
● Running
5.0 FPS
Avg inference: 82 ms

This is an operational view, not a developer-only debug page.

8. CURRENT COMPLIANCE STATE

The dashboard must show the current handwash state.

Possible states:

UNKNOWN
AT_SINK
WATER_ON
SOAP_APPLIED
WASHING
RINSING
COMPLETED

Display:

Current Compliance State

WASHING

Duration
14.2 sec

Required
20 sec

Progress
██████████████░░░░░░ 71%

The progress visualization must clearly communicate that:

14.2 sec < 20 sec

does not yet mean violation.

The rule engine decides the final compliance result.

The UI must not independently decide compliance.

9. STATE TRANSITION VISUALIZATION

Provide an optional expandable state timeline.

Example:

UNKNOWN
   │
   ▼
AT_SINK
   │ 2.4s
   ▼
WATER_ON
   │ 3.1s
   ▼
SOAP_APPLIED
   │ 1.7s
   ▼
WASHING
   │ 20.8s
   ▼
RINSING
   │ 4.2s
   ▼
COMPLETED

This allows the operator to understand why the compliance engine reached its result.

For each state show:

entered timestamp
duration
current/previous state
transition status

Do not expose internal implementation details unnecessarily.

10. COMPLIANCE RESULT

Create a dedicated compliance result area.

Example:

COMPLIANCE RESULT

✓ COMPLIANT

Handwashing completed successfully.

Washing Duration
23.4 sec

Required Duration
20 sec

Sequence
Valid

Completed
Yes

Evaluated
21:24:32

Violation:

COMPLIANCE RESULT

⚠ VIOLATION

Handwashing requirement was not completed.

Reason
Required washing duration was not reached.

Washing Duration
8.2 sec

Required Duration
20 sec

Sequence
Incomplete

Group ID
grp_8f32...

The exact reason should come from the backend ComplianceEvent.

Do not reconstruct the reason on the frontend.

11. REAL-TIME VIOLATION ALERT

When a violation occurs, display an immediate notification.

Example:

┌─────────────────────────────────────┐
│ ⚠ Compliance Violation              │
│                                     │
│ Camera 02                           │
│ Secondary Sink                      │
│                                     │
│ Required handwashing not completed. │
│                                     │
│ 21:21:14                            │
│                                     │
│ [View Violation]                    │
└─────────────────────────────────────┘

The notification should:

appear without refreshing the page
clearly indicate severity
identify camera
identify zone
show timestamp
show short violation reason
contain a View Violation action

Use WebSocket or SSE if already available.

If neither exists, create a clean real-time event adapter interface.

Do not tightly couple UI components directly to WebSocket implementation.

12. VIOLATION HISTORY

Create a dedicated violations table.

Columns:

Time
Camera
Zone
Violation
Duration
Status
Evidence

Example:

21:21:14
Camera 02
Secondary Sink
Incomplete handwash
8.2 sec
VIOLATION
[View]

21:03:42
Camera 01
Main Sink
Soap not detected
12.1 sec
VIOLATION
[View]

Support:

filtering by camera
filtering by zone
filtering by date/time
filtering by violation type
sorting newest first
pagination if backend supports it
13. VIOLATION DETAIL VIEW

When the user clicks:

View Violation

open a modal, drawer, or dedicated detail page.

Preferred information hierarchy:

┌──────────────────────────────────────────────────────────┐
│ Compliance Violation                              [X]   │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  VIOLATION                                               │
│                                                          │
│  Camera 02                                               │
│  Secondary Sink                                          │
│  21:21:14                                                 │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │                                                    │  │
│  │             VIOLATION THUMBNAIL                   │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Reason                                                  │
│  Required washing duration was not reached.             │
│                                                          │
│  Washing Duration       8.2 sec                          │
│  Required Duration      20 sec                           │
│  Sequence               Incomplete                       │
│                                                          │
│  Evidence Group         grp_8f32...                      │
│                                                          │
│  [Close]                                                 │
└──────────────────────────────────────────────────────────┘
14. EVIDENCE THUMBNAIL

The backend rule engine buffers thumbnails while a potential violation is developing.

The evidence lifecycle is:

Potential violation starts
        ↓
Create group_id
        ↓
Buffer thumbnails
        ↓
Compliance resumes?
     /       \
   YES        NO
    ↓          ↓
Discard       Continue buffering
buffer           ↓
             Violation confirmed
                    ↓
             Freeze evidence
                    ↓
             Publish evidence

The UI should reflect the final frozen evidence.

The frontend must not create or modify evidence.

The backend provides the evidence payload.

The UI should display:

Evidence
[thumbnail]

Optionally show multiple thumbnails if the evidence payload contains multiple frames:

Evidence Timeline

[Thumbnail 1] [Thumbnail 2] [Thumbnail 3] [Thumbnail 4]
   ↓              ↓              ↓              ↓
21:20:58       21:21:02       21:21:07       21:21:14

Keep the UI bounded.

Do not render thousands of thumbnails.

15. IMPORTANT EVENT SEPARATION

Respect the backend architecture.

The dashboard receives two conceptual event types:

ComplianceEvent

Lightweight alert-facing event:

{
  "event_type": "compliance_violation",
  "camera_id": "camera_02",
  "zone_id": "secondary_sink",
  "group_id": "grp_8f32",
  "timestamp": "2026-09-02T21:21:14Z",
  "rule_id": "handwash_compliance",
  "reason": "required_duration_not_reached"
}

This should be used for:

notifications
violation counters
recent-event list
dashboard alert state

It should NOT contain large image payloads.

Evidence Event

Separate evidence payload:

{
  "group_id": "grp_8f32",
  "camera_id": "camera_02",
  "zone_id": "secondary_sink",
  "timestamp": "...",
  "evidence": [
    {
      "frame_id": "...",
      "timestamp": "...",
      "thumbnail": "..."
    }
  ]
}

Use the group_id as the correlation key.

The UI should associate:

ComplianceEvent.group_id
          ↓
Evidence.group_id

Do not assume the two events arrive simultaneously.

Design the frontend state so the violation can initially appear as:

Violation detected
Evidence loading...

and then update when evidence arrives.

16. DASHBOARD STATE MODEL

Create a frontend domain model approximately like:

DashboardState
│
├── systemStatus
│
├── cameras[]
│   ├── cameraId
│   ├── name
│   ├── ingestionStatus
│   ├── processingStatus
│   ├── fps
│   ├── framesReceived
│   ├── framesProcessed
│   ├── droppedFrames
│   ├── currentState
│   └── stateDuration
│
├── compliance
│   ├── compliantCount
│   ├── violationCount
│   └── complianceRate
│
├── violations[]
│   ├── groupId
│   ├── cameraId
│   ├── zoneId
│   ├── timestamp
│   ├── ruleId
│   ├── reason
│   └── evidenceStatus
│
└── evidenceByGroupId
    └── evidence[]

Use a normalized state structure if appropriate for the existing frontend architecture.

17. FRONTEND COMPONENT ARCHITECTURE

Do not build the entire dashboard as one component.

Create clear components such as:

DashboardPage
│
├── DashboardHeader
│
├── SystemStatusCards
│   ├── SystemStatusCard
│   ├── CameraCountCard
│   ├── ProcessingCard
│   ├── ComplianceRateCard
│   └── ViolationCountCard
│
├── CameraStatusGrid
│   └── CameraStatusCard
│
├── PipelineStatus
│   └── PipelineStage
│
├── ComplianceOverview
│
├── ComplianceStateTimeline
│
├── RecentComplianceEvents
│
├── ViolationTable
│
├── ViolationNotification
│
└── ViolationDetail
    ├── ViolationSummary
    ├── EvidenceViewer
    └── ComplianceMetrics

Keep components focused.

18. DATA ACCESS ARCHITECTURE

Do not let UI components directly call HTTP/WebSocket APIs.

Use an abstraction such as:

DashboardRepository
        │
        ├── getSystemStatus()
        ├── getCameras()
        ├── getComplianceEvents()
        ├── getViolations()
        ├── getEvidence(groupId)
        └── subscribeToEvents()

Then provide:

ApiDashboardRepository

for the real backend.

For development:

MockDashboardRepository

can provide deterministic test data.

This allows the UI to be developed before every backend API is available.

19. REAL-TIME EVENT HANDLING

Create a clean event subscription layer:

Backend Event Stream
        ↓
Event Adapter
        ↓
Dashboard Store
        ↓
React/UI Components

Possible event types:

camera_status_changed
ingestion_started
ingestion_stopped
processing_started
processing_degraded
compliance_state_changed
compliance_passed
compliance_violation
evidence_available

Do not let each component create its own WebSocket connection.

Prefer:

ONE event connection
        ↓
central event dispatcher/store
        ↓
components subscribe to state

Handle:

reconnect
connection loss
duplicate events
stale events
event ordering
cleanup on unmount
20. ERROR AND DEGRADED STATES

Design UI states for failures.

Examples:

Camera disconnected
Camera 02

● DISCONNECTED

Last frame
21:27:42

No frames received for 18 sec.
Inference failure
YOLO Detection

⚠ DEGRADED

Inference latency: 1.8 sec
Evidence unavailable
Violation detected

Evidence
⚠ Evidence unavailable

The violation event was received but evidence
has not been retrieved.
Backend unavailable
● Reconnecting...

Last successful update
21:28:41

Do not silently show stale values as current.

Clearly indicate stale/degraded data.

21. VISUAL DESIGN

Use a professional monitoring/dashboard aesthetic.

Requirements:

clean
modern
minimal
enterprise-oriented
high information density without clutter
strong typography hierarchy
consistent spacing
accessible contrast
responsive layout
desktop-first but responsive

Use semantic status styles:

Healthy / Compliant
Warning / Processing degradation
Violation / Error
Neutral / Unknown

Do not rely exclusively on red/green.

Use:

✓
⚠
●
!

alongside text labels where appropriate.

22. RESPONSIVE DESIGN

Desktop:

Sidebar + Main Dashboard

Tablet:

Collapsible Sidebar
2-column cards

Mobile:

Single-column cards
Scrollable violation table
Full-screen violation detail

The evidence viewer must remain usable on small screens.

23. NAVIGATION

If appropriate, provide:

Dashboard
Cameras
Violations
System Health
Settings

Dashboard:

Current operational status

Cameras:

Camera-specific monitoring

Violations:

Historical compliance violations

System Health:

Ingestion
Inference
Queue
Processing latency
Errors

Settings:

Configuration

Do not duplicate backend configuration management unless the repository already supports it.

24. CAMERA DETAIL PAGE

Create a detailed camera view.

Example:

Camera 01
Main Sink Area

● ONLINE

┌──────────────────────┐
│ Current State        │
│ WASHING              │
│                      │
│ Duration: 14.2 sec   │
│ Required: 20 sec     │
└──────────────────────┘

Pipeline
✓ Ingestion
✓ Detection
✓ Tracking
✓ Observation
✓ State
✓ Temporal
✓ Compliance

Recent Events
...

If a live video preview is already supported by the backend, provide a dedicated area for it.

Do not invent a video streaming backend if one does not exist.

If no live preview exists, use:

Live preview unavailable

rather than pretending a stream exists.

25. ACCESSIBILITY

Implement:

keyboard navigation
focus states
semantic buttons
accessible modal/dialog behavior
ARIA labels where required
text labels in addition to color indicators
readable contrast
alt text for thumbnails
accessible status announcements for critical violations if appropriate

For violation notifications, ensure the alert is accessible to screen readers.

26. PERFORMANCE

The dashboard may receive frequent events.

Avoid:

re-render entire dashboard on every frame

The UI should NOT receive every raw frame unless explicitly required.

Prefer event-level updates:

camera status
FPS
state changes
compliance result
violation
evidence

Throttle/debounce high-frequency operational metrics where appropriate.

Do not render a new React tree for every inference frame.

Use memoization/selectors where appropriate for the existing frontend architecture.

27. SECURITY

Do not expose:

RTSP credentials
internal infrastructure details
raw backend secrets
authentication tokens in UI state
unnecessary internal exception traces

If evidence URLs are signed URLs or protected endpoints, use the existing backend authentication mechanism.

Do not place credentials in frontend configuration.

28. TESTING

Create tests for:

Dashboard rendering
system status
camera cards
processing state
compliance state
violation table
Real-time events

Test:

compliance_violation
        ↓
notification appears
        ↓
violation count increases
Evidence

Test:

violation event
        ↓
evidence loading
        ↓
evidence_available
        ↓
thumbnail displayed
Error states

Test:

camera disconnected
backend disconnected
evidence unavailable
stale data
Interaction

Test:

click View Violation
        ↓
ViolationDetail opens
        ↓
thumbnail displayed
Filtering

Test:

camera filter
zone filter
date filter
violation type

Use the repository's existing testing framework.

29. MOCK DATA

Create realistic development fixtures.

Example:

{
  "camera_id": "camera_01",
  "zone_id": "main_sink",
  "status": "online",
  "fps": 5.0,
  "frames_received": 12482,
  "frames_processed": 12401,
  "current_state": "WASHING",
  "state_duration": 14.2
}

Violation:

{
  "group_id": "grp_8f32",
  "camera_id": "camera_02",
  "zone_id": "secondary_sink",
  "rule_id": "handwash_compliance",
  "timestamp": "2026-09-02T21:21:14Z",
  "reason": "required_duration_not_reached"
}

Evidence:

{
  "group_id": "grp_8f32",
  "evidence": [
    {
      "frame_id": "frame_1201",
      "timestamp": "2026-09-02T21:21:02Z",
      "thumbnail": "..."
    },
    {
      "frame_id": "frame_1202",
      "timestamp": "2026-09-02T21:21:07Z",
      "thumbnail": "..."
    }
  ]
}

Keep mock data separate from production API code.

30. IMPORTANT DOMAIN BOUNDARY

The frontend must NOT implement:

YOLO detection logic
ByteTrack logic
state transition logic
temporal analysis
compliance rules
violation confirmation
evidence buffering

Those belong to the backend.

The frontend is responsible for:

displaying backend state
displaying backend decisions
receiving events
requesting evidence
displaying evidence
notifying operators

The source of truth for compliance is:

ComplianceRuleEngine

The source of truth for evidence is:

Evidence/Event backend
31. IMPLEMENTATION PHASES

Follow this workflow exactly.

Phase 1: Repository Discovery

Inspect:

frontend
backend API
event models
queue
existing components
styling
routing
tests

Report findings before making major architectural changes.

Phase 2: UI Architecture

Define:

pages
components
domain models
repository interfaces
state management
event adapter
Phase 3: Domain Contracts

Define frontend-safe models for:

CameraStatus
PipelineStatus
ComplianceState
ComplianceEvent
Violation
Evidence
SystemStatus
Phase 4: Dashboard Shell

Implement:

navigation
header
KPI cards
camera grid
recent events
Phase 5: Camera Monitoring

Implement:

camera status
ingestion status
processing status
current compliance state
Phase 6: Compliance Visualization

Implement:

state
duration
required duration
sequence
temporal metrics
PASS / VIOLATION
Phase 7: Violation Notification

Implement:

real-time event
notification
violation counter
recent violation
Phase 8: Evidence

Implement:

View Violation
ViolationDetail
EvidenceViewer
thumbnail display
evidence loading
Phase 9: Historical Violations

Implement:

table
filters
sorting
pagination
detail view
Phase 10: Error States

Implement:

disconnected
degraded
stale
loading
empty
error
Phase 11: Testing

Implement unit/component/integration tests.

Phase 12: Production Review

Check:

responsiveness
accessibility
performance
state consistency
real-time reconnection
duplicate event handling
stale data handling
security
error handling
component boundaries
32. ACCEPTANCE CRITERIA

The implementation is complete only when all of the following are true.

Dashboard

Dashboard loads without backend crashes.

System health is visible.

Camera count is visible.

Processing status is visible.

Compliance rate is visible.

Violation count is visible.

Ingestion

Camera connection status is visible.

FPS is visible.

Frames received/processed are visible.

Dropped frames can be displayed.

Prerecorded video shows progress.

RTSP shows LIVE status instead of fake progress.

Processing

Pipeline stages are visible.

Current processing state is visible.

Degraded/error state is visible.

Compliance

Current handwash state is visible.

State duration is visible.

Required duration is visible.

Compliance result comes from backend.

Violation reason comes from backend.

Notifications

Violation event creates a visible notification.

Notification identifies camera.

Notification identifies zone.

Notification includes timestamp.

Notification includes reason.

Notification provides View Violation.

Evidence

Violation detail can be opened.

Evidence is correlated using group_id.

Thumbnail is displayed.

Multiple evidence thumbnails can be displayed if provided.

Evidence loading state exists.

Evidence unavailable state exists.

Architecture

UI components do not contain business rules.

UI does not directly implement compliance logic.

API access is abstracted.

Real-time event handling is centralized.

Components are independently testable.

Mock data is isolated.

No secrets are exposed.

33. FINAL DELIVERABLE

After implementation, provide a concise report containing:

1. Repository findings

2. UI architecture

3. Pages created

4. Components created

5. Domain models created

6. API/event interfaces created

7. Real-time event handling

8. Evidence flow

9. Mock data strategy

10. Tests added

11. Commands to run the dashboard

12. Any backend APIs/events that are still required

13. Known limitations

14. Production-readiness assessment

Do not claim production readiness if important backend contracts are missing.

If an API/event contract is missing, explicitly document:

REQUIRED BACKEND CONTRACT

Endpoint/Event:
Purpose:
Request:
Response:

Most importantly, maintain this architectural separation:

                 BACKEND
                    │
       ┌────────────┴────────────┐
       │                         │
ComplianceEvent             EvidenceEvent
       │                         │
       ▼                         ▼
 Notification              Evidence Store
       │                         │
       └──────────┬──────────────┘
                  ▼
             DASHBOARD
                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
     Status    Compliance   Evidence
        │         │          │
        ▼         ▼          ▼
     Operator   Decision    Thumbnail

The dashboard is an observability and operator interface, not another compliance-processing engine.