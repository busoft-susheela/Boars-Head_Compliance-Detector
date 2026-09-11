You are a senior Python backend/Computer Vision architect. Implement a production-ready StreamIngestionService for our computer vision compliance pipeline.

The current MVP needs to support two input sources:

Prerecorded video file
Live RTSP stream

The source must be selected entirely through configuration.

The downstream pipeline must not care whether a frame came from a video file or RTSP.

Primary objective

Implement a production-oriented StreamIngestionService that:

Selects the connector based on configuration.
Supports prerecorded video through VideoConnector.
Supports live streams through RTSPConnector.
Uses a common StreamConnector abstraction.
Samples frames according to configured target FPS.
Creates a strongly defined FrameEvent.
Prevents unbounded frame buffering.
Handles RTSP reconnects with exponential backoff.
Correctly distinguishes video EOF from RTSP temporary failure.
Supports graceful shutdown.
Provides useful logging and metrics/health information.
Is testable without requiring a real camera.
Does not contain inference, tracking, temporal analysis, compliance, or notification logic.

Do not implement this as a simple OpenCV while cap.read() loop.

1. First inspect the existing repository

Before modifying code:

Inspect the repository structure.
Identify the existing configuration mechanism.
Identify existing logging conventions.
Identify existing dependency injection patterns.
Identify existing event/message models.
Identify existing queue/stream abstractions.
Identify existing tests and test conventions.
Identify whether OpenCV is already used.
Identify existing lifecycle/startup/shutdown patterns.
Reuse existing project conventions wherever possible.

Do not introduce a new framework or architecture if an equivalent abstraction already exists.

Before implementation, provide a short summary of:

Relevant existing files
Existing abstractions that should be reused
Files you intend to add/change
Any architectural conflicts you found

Then implement the solution.

2. Target architecture

Use this conceptual structure:

stream_ingestion/
│
├── service.py
│
├── connectors/
│   ├── base.py
│   ├── video.py
│   └── rtsp.py
│
├── sampling/
│   ├── base.py
│   └── fps_sampler.py
│
├── models/
│   └── frame_event.py
│
├── buffering/
│   └── bounded_buffer.py
│
├── publishing/
│   ├── base.py
│   └── ...
│
├── health/
│   └── ...
│
└── factory.py

Do not blindly create this exact folder structure if the repository already has an established structure. Adapt to the existing codebase.

3. StreamConnector abstraction

Create or reuse a common interface similar to:

class StreamConnector(ABC):

    def connect(self) -> None:
        ...

    def read(self) -> ReadResult:
        ...

    def close(self) -> None:
        ...

The interface must be source-independent.

Do not expose OpenCV-specific objects or behavior to the rest of the application unnecessarily.

4. ReadResult

Do not use None to represent every possible read failure.

Create an explicit result model.

For example:

class ReadStatus(Enum):
    FRAME = "frame"
    END_OF_STREAM = "end_of_stream"
    TEMPORARY_FAILURE = "temporary_failure"


@dataclass
class ReadResult:
    status: ReadStatus
    frame: np.ndarray | None = None

Adapt this to the repository's existing conventions if an equivalent model already exists.

Required semantics:

VideoConnector
successful read
    → FRAME

video reaches EOF
    → END_OF_STREAM

unrecoverable file/read problem
    → appropriate error
RTSPConnector
successful read
    → FRAME

temporary network/decode/read failure
    → TEMPORARY_FAILURE

explicit shutdown
    → handled by lifecycle

Do not interpret an RTSP read() failure as permanent end-of-stream.

5. VideoConnector

Implement support for prerecorded video.

Configuration example:

stream:
  type: video

  video:
    path: "/data/videos/handwashing.mp4"

  sampling:
    target_fps: 5

Requirements:

Validate the configured path.
Fail clearly if the file does not exist.
Open the video safely.
Detect failure to open.
Read frames sequentially.
Detect EOF.
Release resources correctly.
Expose useful source metadata such as native FPS and resolution where practical.
Do not loop the video automatically unless explicitly configured.
Do not terminate the entire application because a single video reaches EOF. Return END_OF_STREAM and let the service decide lifecycle behavior.

Support a configurable playback mode if appropriate:

stream:
  video:
    playback_mode: realtime

At minimum support:

realtime

Do not add unnecessary complexity for offline/fast playback unless the existing architecture needs it.

6. RTSPConnector

Implement support for live RTSP streams.

Configuration example:

stream:
  type: rtsp

  rtsp:
    url: "${RTSP_URL}"

  reconnect:
    initial_delay_seconds: 1
    max_delay_seconds: 15

Requirements:

Connect to the configured RTSP URL.
Validate connection success.
Read frames continuously.
Distinguish temporary read failures from EOF.
Release the capture cleanly.
Support reconnecting.
Do not busy-loop when the camera is unavailable.
Use exponential backoff with a configurable maximum.
Reset the backoff after a successful connection.
Log connection/reconnection events with camera/source ID.
Do not allow credentials to appear in logs.

Example retry progression:

1 sec
2 sec
4 sec
8 sec
15 sec
15 sec
...

Do not implement infinite tight reconnect loops.

7. ConnectorFactory

Implement a factory that selects the connector based on configuration.

Example:

stream:
  type: video

must result in:

VideoConnector

and:

stream:
  type: rtsp

must result in:

RTSPConnector

The factory should reject unsupported values clearly.

The ingestion service should receive a StreamConnector, not directly instantiate VideoConnector or RTSPConnector.

Avoid code such as:

if config.type == "video":
    ...
elif config.type == "rtsp":
    ...

being repeated throughout the ingestion service.

The source selection should happen once through the factory.

8. FrameSampler

Implement configurable frame sampling.

Example:

sampling:
  target_fps: 5

If the source produces:

30 FPS

the ingestion service should publish approximately:

5 FPS

Prefer time-based sampling for live streams rather than relying only on:

frame_number % N

The sampler should be independently testable.

It should not contain inference logic.

9. FrameEvent

Create a strongly typed event representing a sampled frame.

At minimum include:

@dataclass(frozen=True)
class FrameEvent:
    camera_id: str
    frame_id: int
    captured_at: datetime
    received_at: datetime
    frame: np.ndarray

Add other metadata only if justified by the existing architecture.

Important:

camera_id must identify the source.
frame_id must monotonically increase per source.
captured_at represents source/frame timing as accurately as available.
received_at represents ingestion time.
Do not use only frame number for temporal analysis.

The event should be suitable for downstream:

Inference
Tracking
State Machine
Temporal Analyzer
Compliance Engine
10. Buffering and backpressure

The ingestion service must not create an unbounded frame queue.

For live CV processing, stale frames are generally less valuable than the latest frame.

Implement or reuse a bounded buffer/queue.

Default behavior should be similar to:

max_size = 1
strategy = latest

Conceptually:

Camera
   ↓
Sampler
   ↓
┌─────────────────┐
│ Latest Frame    │
│ bounded buffer  │
└────────┬────────┘
         ↓
     Inference

If inference falls behind:

old frame → dropped
new frame → retained

Do not allow:

camera → unbounded queue → inference

because this creates increasing latency and memory consumption.

Track dropped-frame counts.

If the repository already has a messaging abstraction, integrate with it rather than introducing a second queue mechanism.

11. Frame validation

Before publishing a frame, validate basic properties.

At minimum handle:

None
empty frames
invalid dimensions
unexpected channel structure where applicable

Do not crash the entire ingestion service because of one invalid frame.

Track invalid-frame metrics.

12. Service orchestration

The high-level service should follow this responsibility:

initialize
    ↓
create connector
    ↓
connect
    ↓
read frame
    ↓
validate
    ↓
sample
    ↓
create FrameEvent
    ↓
publish to bounded downstream mechanism
    ↓
repeat

The service must not know about:

YOLO
ByteTrack
TemporalAnalyzer
ComplianceRuleEngine
NotificationService

Those are downstream concerns.

13. RTSP failure behavior

Implement this behavior explicitly:

RTSP read
   │
   ├── frame
   │     ↓
   │   validate
   │     ↓
   │   sample
   │     ↓
   │   publish
   │
   └── temporary failure
          ↓
       reconnect
          ↓
       backoff
          ↓
       retry

Do NOT implement:

if frame is None:
    break

for RTSP.

A live stream does not normally end because one frame failed to decode.

14. Video EOF behavior

For prerecorded video:

read frame
   │
   ├── frame → process
   │
   └── EOF → END_OF_STREAM

Do not reconnect to the video file.

Do not silently loop unless explicitly configured.

15. Graceful shutdown

The service must support clean shutdown.

Handle:

SIGTERM
SIGINT
application shutdown

Shutdown sequence should approximately be:

stop ingestion
    ↓
stop reading
    ↓
stop publishing
    ↓
close connector
    ↓
release OpenCV resources
    ↓
exit cleanly

Avoid leaked VideoCapture objects or background threads/tasks.

If async code is used, ensure tasks are cancelled and awaited correctly.

16. Health monitoring

Expose enough state to determine whether the service is healthy.

Useful metrics/state include:

stream_connected
last_frame_received_at
frames_received_total
frames_sampled_total
frames_dropped_total
invalid_frames_total
reconnect_count
current_source_fps
current_processing_fps
queue_depth

Do not over-engineer the metrics layer if the repository already has Prometheus/OpenTelemetry/etc.

Integrate with the existing observability mechanism.

17. Logging

Use structured logging if the project supports it.

Logs should include source/camera ID.

Examples:

camera_id=handwash-camera-01
event=stream_connected
camera_id=handwash-camera-01
event=stream_read_failure
retry_in=4
camera_id=handwash-camera-01
event=stream_reconnected
downtime_seconds=7.3

Never log RTSP passwords or full credential-bearing URLs.

Avoid excessive per-frame logging.

Do not log every successful frame at INFO level.

18. Configuration validation

Validate configuration at startup.

Example:

stream:
  type: video

requires:

stream:
  video:
    path: ...

Whereas:

stream:
  type: rtsp

requires:

stream:
  rtsp:
    url: ...

Invalid configurations should fail fast with useful error messages.

Do not silently fall back from RTSP to video or vice versa.

19. Dependency injection

Prefer dependency injection.

For example:

StreamIngestionService(
    connector=connector,
    sampler=sampler,
    publisher=publisher,
    validator=validator,
)

Do not hardcode concrete implementations inside the service.

This should allow tests to inject:

FakeConnector
FakePublisher
FakeSampler

without requiring an actual RTSP camera or video file.

20. Testing requirements

Add unit tests and integration-level tests appropriate for the existing repository.

At minimum test:

Factory
type=video → VideoConnector
type=rtsp → RTSPConnector
unsupported type → configuration error
VideoConnector
valid file opens
invalid file fails
frames are read
EOF is detected
resources are released
RTSPConnector

Mock the underlying capture.

Test:

successful connection
successful frame read
temporary read failure
reconnect
backoff
successful reconnect
resource cleanup
FrameSampler

Test:

target FPS respected
frames skipped appropriately
timestamps handled correctly
FrameEvent

Test:

camera_id
frame_id
timestamps
frame metadata
Bounded buffer

Test:

queue never exceeds configured size
latest-frame policy drops stale frames
drop counter increments
StreamIngestionService

Test the complete flow:

connector
   ↓
frame
   ↓
validator
   ↓
sampler
   ↓
FrameEvent
   ↓
publisher

Also test:

video EOF → graceful stop
RTSP failure → reconnect
invalid frame → skipped
shutdown → connector closed

Tests must not require a real camera.

21. Production quality requirements

Follow SOLID principles.

Use clear interfaces and dependency inversion.

Avoid:

giant classes
giant run() methods
global state
hardcoded paths
hardcoded FPS
hardcoded RTSP URLs
print() statements
infinite tight retry loops
unbounded queues
business/compliance logic inside ingestion
notification logic inside ingestion

Keep the implementation simple enough for the current single-camera deployment but architected so that multiple cameras can later be supported.

22. Future multi-camera compatibility

The current scope is one handwashing camera.

However, design around:

camera_id

so the architecture can later support:

camera-01 → RTSP
camera-02 → RTSP
camera-03 → video

without changing the downstream FrameEvent contract.

Do not implement a full multi-camera orchestration system now unless the existing repository requires it.

Just ensure the abstractions do not prevent it.

23. Expected final flow

The implementation should result in:

                         config.yaml
                              │
                              ▼
                     ConnectorFactory
                              │
                   ┌──────────┴──────────┐
                   │                     │
                   ▼                     ▼
            VideoConnector        RTSPConnector
                   │                     │
                   │                     │
                   └──────────┬──────────┘
                              ▼
                         Raw Frame
                              │
                              ▼
                       FrameValidator
                              │
                              ▼
                        FrameSampler
                              │
                              ▼
                        FrameEvent
                              │
                              ▼
                       Bounded Buffer
                              │
                              ▼
                         Publisher
                              │
                              ▼
                      Inference Pipeline
24. Important architectural rule

The following must remain true:

VideoConnector ─┐
                ├── StreamConnector ──→ StreamIngestionService
RTSPConnector ──┘

and NOT:

StreamIngestionService
    ├── VideoConnector logic
    ├── RTSPConnector logic
    ├── YOLO logic
    ├── tracking logic
    ├── compliance logic
    └── notification logic

The ingestion component is responsible only for reliable frame acquisition and delivery.

25. Deliverables

After implementation, provide:

Files created/modified.
Architecture summary.
Configuration example for video.
Configuration example for RTSP.
Explanation of connector selection.
Explanation of RTSP reconnect behavior.
Explanation of frame sampling.
Explanation of backpressure/bounded buffering.
Test coverage/results.
Any assumptions or limitations.
Any production risks that remain.

Before finishing, review the implementation specifically for:

race conditions
resource leaks
unbounded queues
blocking operations
retry storms
incorrect RTSP EOF handling
timestamp correctness
shutdown behavior
sensitive information in logs
configuration validation
testability

Do not stop at creating the classes. Integrate the component into the existing application according to the repository's architecture and run the relevant tests.

As a next step, implement this | **MessageQueue** *(infra)* | interface | Pub/sub contract every component depends on, backend-independent | Abstraction kept even at single-camera scale, for a clean swap later |
| | InMemoryMessageQueue | MVP backend — one `asyncio.Queue` per topic | Default backend for this single-process deployment |
| **FrameStore** *(infra)* | interface | Ephemeral pixel storage, separate from queue messages | Keeps queue messages small — only IDs travel through it |
| | InMemoryFrameStore | dict keyed by `frame_id`, TTL eviction on read | Default backend |

The next implementation should make the model/inference layer sit cleanly on top of the MessageQueue + FrameStore architecture.

Implement the model resolution, model loading, model registry, detector, thumbnail generation, and inference orchestration layer for an event-driven computer vision compliance pipeline.

The implementation must integrate with the existing architecture rather than creating a parallel architecture.

The current system conceptually looks like:

Video File / RTSP Camera
        |
        v
StreamIngestionService
        |
        +--------------------+
        |                    |
        v                    v
   FrameStore          MessageQueue
        |                    |
        |               FrameEvent
        |                    |
        +---------+----------+
                  |
                  v
        YoloInferenceEngine
                  |
          +-------+-------+
          |               |
          v               v
    ModelResolver    FrameStore
          |
          v
      ModelSpec
          |
          v
     ModelRegistry
          |
          v
       Detector
          |
          v
   YOLO / ONNX / OpenVINO
          |
          v
      Detection[]
          |
          v
    DetectionEvent
          |
          v
     MessageQueue
          |
          v
 Tracking / State Transition
          |
          v
 Temporal Analyzer
          |
          v
 Compliance Rule Engine
          |
          v
 Notification

The implementation must be production-oriented, while keeping the MVP deployment simple enough for:

single process
single camera
CPU inference
in-memory MessageQueue
in-memory FrameStore

The architecture must also allow future expansion to:

multiple cameras
multiple zones
multiple models
GPU
ONNX
OpenVINO
Redis
Kafka
distributed inference workers

without requiring downstream business logic to change.

1. Implement the following components:

YoloInferenceEngine
ModelSpec
ModelResolver
StaticModelResolver
ModelRegistry
ModelLoader
Detector
ThumbnailGenerator
CPUInferenceWorker
Detection
DetectionEvent

Reuse existing models/events/interfaces when they already exist in the repository.

Do not blindly create duplicates.

The most important architectural principle is:

Model selection, model lifecycle, model execution, and inference orchestration are separate responsibilities.

Do not combine everything into one YoloInferenceEngine class.

2. Before implementing anything, inspect the existing repository.

Search for:

StreamIngestionService
FrameEvent
FrameEnvelope
Detection
DetectionEvent
MessageQueue
FrameStore
Model
YOLO
Ultralytics
inference
detector
registry
worker
config
metrics

Also inspect:

Python version
package manager
dependency management
existing configuration
dependency injection
application startup
async architecture
threading/process architecture
existing queue implementation
existing FrameStore
existing logging
existing metrics
existing lifecycle/shutdown
existing test structure
existing OpenCV/NumPy usage
existing ML dependencies
existing exception hierarchy

Before implementation, provide:

Repository findings:
- Existing inference code:
- Existing YOLO integration:
- Existing model configuration:
- Existing FrameEvent:
- Existing FrameStore:
- Existing MessageQueue:
- Existing worker pattern:
- Existing DI:
- Existing metrics:
- Existing lifecycle:
- Relevant files:
- Reuse opportunities:
- Potential conflicts:
- Proposed implementation files:

Then implement.

Do not make large speculative refactors.

3. The desired architecture is:

                    FrameEvent
                        |
                        v
              YoloInferenceEngine
                        |
          +-------------+-------------+
          |                           |
          v                           v
    ModelResolver                FrameStore
          |                           |
          v                           v
      ModelSpec                  Raw Frame
          |
          v
    ModelRegistry
          |
          v
        Detector
          |
          v
 YOLO / ONNX / OpenVINO
          |
          v
      Detection[]
          |
          +------------------+
                             |
                             v
                     ThumbnailGenerator
                             |
                             v
                     DetectionEvent
                             |
                             v
                       MessageQueue

The responsibilities must remain separated.

4. Implement the following responsibility boundaries.

Component	Responsibility
ModelSpec	Immutable declaration of one trained model
ModelResolver	Decides which model specs apply to a camera/zone
StaticModelResolver	MVP configuration-based resolver
ModelLoader	Loads model weights/runtime
ModelRegistry	Caches one loaded detector per unique model
Detector	Runs one model against one frame
ThumbnailGenerator	Creates small JPEG evidence from the current frame
YoloInferenceEngine	Orchestrates resolution, frame retrieval, inference, merging, thumbnail creation
CPUInferenceWorker	Controls asynchronous/bounded execution of inference work
Detection	Typed result of one detected object
DetectionEvent	Message sent downstream

Do not allow these responsibilities to bleed into each other.

5. ModelSpec

Implement an immutable ModelSpec.

Conceptually:

@dataclass(frozen=True)
class ModelSpec:
    use_case: str
    model_path: str
    confidence_threshold: float
    device: str
    image_size: int

Adapt the fields to the existing configuration architecture.

Potential fields:

use_case
model_path
confidence_threshold
device
image_size
model_format

Do not add fields unless they are actually needed.

The object represents:

one declaration of one trained model and how it should be used.

It is configuration/data.

It is NOT:

loaded YOLO object
runtime state
cache entry
worker

6. ModelSpec Must Be Immutable

ModelSpec must not be mutated after creation.

Do not implement:

spec.confidence_threshold = 0.7

after construction.

The same ModelSpec may be referenced by multiple inference requests.

Use the project's preferred immutable model mechanism:

frozen dataclass
Pydantic frozen model
other existing configuration model

Prefer the repository's existing conventions.

7. ModelSpec Validation

Validate:

use_case is non-empty
model_path is non-empty
confidence_threshold is between 0 and 1
device is valid
image_size is positive

Do not necessarily require the model file to exist during ModelSpec construction.

Configuration declaration and runtime model loading are separate responsibilities.

However, startup validation may verify the configured path where appropriate.

8. Model Identity

The system must know when two ModelSpec objects refer to the same model.

The primary registry identity should be:

normalized model path

unless the architecture requires runtime settings to distinguish models.

The registry must prevent:

same model loaded twice

For example:

model A -> models/handwashing.pt
model B -> ./models/handwashing.pt

should resolve to the same physical model if their normalized paths are identical.

Do not create two detector instances unnecessarily.

9. ModelResolver Interface

Define a backend-independent abstraction:

class ModelResolver(ABC):

    @abstractmethod
    def resolve(
        self,
        camera_id: str,
        zone_id: str,
    ) -> list[ModelSpec]:
        ...

The exact API should follow repository conventions.

The resolver answers only:

Which models apply to this camera and zone?

It must NOT:

load models
run inference
access FrameStore
publish events
generate thumbnails

10. StaticModelResolver

Implement the MVP:

StaticModelResolver

based on configuration.

Conceptually:

models:
  handwashing:
    use_case: handwashing
    path: models/handwashing.pt
    confidence: 0.5
    device: cpu
    image_size: 640

  ppe:
    use_case: ppe
    path: models/ppe.pt
    confidence: 0.5
    device: cpu
    image_size: 640

zones:
  handwash_zone:
    models:
      - handwashing

  entry_zone:
    models:
      - ppe

The exact schema must match the existing configuration system.

Resolver mapping:

camera_id + zone_id
        |
        v
StaticModelResolver
        |
        v
list[ModelSpec]

11. Camera and Zone Semantics

Do not assume camera_id alone determines models.

The contract should support:

camera_id
zone_id

because one camera may eventually contain multiple zones.

Example:

Camera 01
   |
   +--> handwash_zone
   |       -> handwashing model
   |
   +--> entry_zone
           -> PPE model

If the MVP only uses one zone, preserve the abstraction anyway.

12. Resolver Validation

The resolver should fail clearly when:

camera_id is unknown
zone_id is unknown
zone has no configured models
model name references a nonexistent model definition

Do not silently return an empty list if that indicates configuration error.

Distinguish between:

valid zone with intentionally zero models

and:

invalid configuration

based on the project's configuration semantics.

13. ModelLoader

Implement:

ModelLoader

whose responsibility is:

Load a configured model into its runtime representation.

Conceptually:

class ModelLoader:

    def load(self, model_spec: ModelSpec):
        ...

For the initial POC/CPU implementation, support the existing model format.

If using Ultralytics:

YOLO(model_spec.model_path)

But do not scatter:

YOLO(...)

through the application.

Only the model-loading boundary should know how the model is loaded.

14. Runtime Backend Abstraction

Design ModelLoader so that the application does not need to know whether the model is:

.pt
.onnx
OpenVINO

The runtime can evolve.

The desired conceptual architecture is:

ModelSpec
    |
    v
ModelLoader
    |
    +--> Ultralytics
    +--> ONNX Runtime
    +--> OpenVINO

Do NOT implement all of those backends now unless the repository already requires them.

Implement the current backend cleanly and leave a clear extension point.

15. CPU Configuration

For the current deployment:

model:
  device: cpu

or the repository-equivalent configuration.

Do not hardcode:

device = "cpu"

inside Detector.

The runtime device must be configuration-driven.

For MVP, validate that CPU execution works.
16. ModelRegistry

Implement:

ModelRegistry

whose responsibility is:

Load and cache exactly one Detector per unique model identity.

Conceptually:

class ModelRegistry:

    def get(self, model_spec: ModelSpec) -> Detector:
        ...

The registry should internally maintain something equivalent to:

dict[ModelKey, Detector]

Do not expose the internal cache.

17. ModelRegistry Behavior

First request:

get(model_spec)
    |
    v
not cached
    |
    v
ModelLoader.load()
    |
    v
Detector
    |
    v
cache
    |
    v
return Detector

Second request:

get(model_spec)
    |
    v
cached
    |
    v
return existing Detector

Never reload the model for every frame.

This is a critical production requirement.

18. Concurrent Model Loading

Consider this race:

Worker A -> get(model_spec)
Worker B -> get(model_spec)

Both arrive before loading completes.

The implementation must prevent:

YOLO(...)
YOLO(...)

for the same model.

Only one model instance should be created.

Use an appropriate async/thread-safe synchronization strategy based on the existing architecture.

Do not introduce unnecessary locks if inference is single-threaded.

But explicitly test concurrent registry access.
19. Model Warm-Up

Support model warm-up.

Configuration:

inference:
  warmup: true

Warm-up should happen once after the model is loaded.

Conceptually:

ModelRegistry
      |
      v
ModelLoader
      |
      v
Detector
      |
      v
warmup()
      |
      v
cache

Do not warm up once per frame.

Do not warm up once per request.

20. Warm-Up Input

Use a safe synthetic input compatible with the configured inference size.

For example:

dummy image
640 x 640

or the appropriate model input shape.

Do not require a real camera frame for warm-up.

Warm-up should not publish any DetectionEvent.

Warm-up failures must be reported clearly.

21. Detector

Implement:

Detector

whose responsibility is:

Run one loaded model against one frame and return typed detections.

Conceptually:

class Detector:

    def infer(
        self,
        frame: np.ndarray,
    ) -> list[Detection]:
        ...

The detector owns model-specific inference mechanics.

It does NOT own:

model selection
FrameStore
MessageQueue
camera routing
zone routing
compliance logic
notification

22. Detection Model

Create or reuse:

@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    bbox: BoundingBox
    confidence: float
    use_case: str

The exact structure should follow existing conventions.

A bounding box should have a clear coordinate convention.

For example:

x1
y1
x2
y2

Document:

pixel coordinates
origin
inclusive/exclusive semantics if relevant
original frame coordinate system
whether coordinates are integers or floats

Do not leave this ambiguous.

23. Detection Must Carry use_case

Every detection must identify which model/use case generated it.

Example:

Detection
    class_name = person
    confidence = 0.91
    use_case = handwashing

This is important when multiple models are applied to the same frame.

Do not rely on downstream code guessing:

which model generated this detection?

24. Detector Output Normalization

Normalize the underlying model output into the project's Detection representation.

Do not allow Ultralytics result objects to leak into downstream business components.

Bad:

return ultralytics_result

Preferred:

Ultralytics
    |
    v
Detector
    |
    v
list[Detection]

This keeps the downstream pipeline framework-independent.

25. Detector Thread Safety

Determine whether the chosen runtime/model object is safe for concurrent inference.

Do not assume it is.

If one cached Detector is shared between concurrent workers, explicitly control access if necessary.

The requirement:

one Detector per model path

does NOT automatically mean:

unlimited concurrent calls on one Detector

Design the execution model accordingly.

For the CPU MVP, a controlled worker model is preferred over uncontrolled concurrent inference calls.

26. CPUInferenceWorker

Implement a bounded worker mechanism around inference.

The goal is to avoid:

unbounded inference tasks

when ingestion is faster than inference.

Conceptually:

MessageQueue
     |
     v
CPUInferenceWorker
     |
 bounded work queue
     |
     v
YoloInferenceEngine
     |
     v
Detector

Configuration:

inference:
  target_fps: 5
  queue_size: 10
  workers: 1

Use existing queue infrastructure where appropriate.

27. Backpressure

Inference must have explicit backpressure.

Do NOT do:

asyncio.create_task(infer(frame))

for every incoming frame without a bound.

That can produce:

100 frames
100 inference tasks
1000 frames
1000 inference tasks

and eventually exhaust memory.

Instead use a bounded mechanism.

For live CV, stale frames are generally less useful than current frames.

Therefore, consider:

latest-frame-wins

or another explicit policy for FrameEvent processing.

Do not silently apply frame-dropping semantics to critical non-frame events.

28. Frame Expiration

The FrameStore has TTL semantics.

A frame event may arrive after its frame has expired:

FrameEvent
    |
    v
FrameStore.get(frame_id)
    |
    v
None

This must be treated as an expected runtime condition.

Do not crash the inference worker.

Log appropriately and increment a metric such as:

inference_frame_store_miss_total

Then continue processing subsequent events.

29. Frame Retrieval

The inference engine should retrieve the raw pixels from:

FrameStore

using:

frame_id

from the FrameEvent.

Do NOT modify the MessageQueue architecture to send the full NumPy array.

The desired flow remains:

FrameEvent
    |
    +--> camera_id
    +--> zone_id
    +--> frame_id
    +--> captured_at
    +--> received_at

Then:

frame = await frame_store.get(event.frame_id)

30. FrameEnvelope

If the repository already has a FrameEnvelope, reuse it.

Conceptually:

FrameEnvelope
    |
    +--> FrameEvent metadata
    +--> frame pixels

The inference layer may construct/use this internal envelope while processing.

Do not automatically put the full pixels back into the queue message.

31. YoloInferenceEngine

Implement the orchestrator:

YoloInferenceEngine

Its responsibility is:

receive a frame event
resolve applicable models
retrieve frame pixels
obtain detectors from registry
execute inference
merge detections
generate thumbnail
create DetectionEvent
publish event
record metrics/timing

It must NOT:

implement model loading
implement model caching
implement configuration parsing
implement compliance rules
implement tracking
implement notification

32. Inference Flow

The expected flow is:

FrameEvent
    |
    v
resolve(camera_id, zone_id)
    |
    v
list[ModelSpec]
    |
    v
FrameStore.get(frame_id)
    |
    v
Raw frame
    |
    +----------------------+
    |                      |
    v                      v
ModelRegistry         ThumbnailGenerator
    |                      |
    v                      v
Detector[]            JPEG bytes
    |
    v
Inference
    |
    v
Detection[]
    |
    v
Merge
    |
    v
DetectionEvent
    |
    v
MessageQueue.publish()

33. Multiple Models

A camera/zone may resolve to:

Model A
Model B
Model C

The inference engine must support this.

Example:

camera_01
  |
  +--> handwashing model
  +--> PPE model

Run applicable models according to the configured execution strategy.

The architecture should allow concurrent execution where safe and beneficial.

However, do not create uncontrolled parallelism.

For CPU MVP, bounded concurrency is preferred.

34. Concurrent Model Inference

The requirement says models should be able to run concurrently.

Implement controlled concurrency.

Do NOT simply do:

await asyncio.gather(
    detector_a.infer(frame),
    detector_b.infer(frame),
    detector_c.infer(frame),
)

if infer() is CPU-bound and synchronous.

That would block the event loop.

Instead, use the repository's appropriate worker/thread/process model.

For CPU-bound synchronous inference, consider:

async orchestration
       |
       v
bounded executor / worker
       |
       v
CPU inference

The exact implementation must follow the project's architecture.

Do not create one unlimited thread per model.

35. CPU Concurrency

For the initial MVP:

inference:
  workers: 1

is acceptable.

The architecture should allow:

workers: 2

or more later.

Do not assume increasing workers always improves CPU inference.

Multiple YOLO models can compete heavily for CPU resources.

Measure before increasing concurrency.
36. Inference Timing

Measure inference duration.

At minimum capture:

inference_duration_ms

per model.

Also consider:

total_inference_duration_ms
model_load_duration_ms
model_warmup_duration_ms
frame_store_get_duration_ms
thumbnail_generation_duration_ms

Do not put raw timing data into every event unless required.

Metrics/logs are preferred.
37. Model Metrics

Track useful metrics:

model_load_total
model_load_failures_total
model_warmup_total
inference_total
inference_failures_total
inference_duration_seconds

Where appropriate, include a low-cardinality:

use_case
model_name

Do NOT use:

frame_id

as a metric label.

That would create high cardinality.

38. ThumbnailGenerator

Implement:

ThumbnailGenerator

whose responsibility is:

Create a small JPEG representation of the raw frame while the frame is already available.

The purpose is evidence.

The evidence must not depend on later retrieving the frame from FrameStore.

This is important because the FrameStore is ephemeral.

39. Thumbnail Semantics

Input:

raw frame
max_width

Output:

JPEG bytes

Target size:

approximately 5-10 KB

Treat this as a target, not a hard guarantee.

Actual JPEG size depends on:

resolution
image content
compression quality

Do not endlessly compress in an attempt to guarantee exactly 5 KB.

40. Thumbnail Configuration

Use configuration:

inference:
  thumbnail:
    enabled: true
    max_width: 320
    jpeg_quality: 70

Adapt to the existing configuration architecture.

Do not hardcode:

max_width = 320

inside the generator.

41. Thumbnail Generation

Preserve aspect ratio.

For example:

Original:
1920 x 1080

max_width:
320

Thumbnail:
320 x 180

Do not distort the frame.

Do not upscale an already-small image.

42. Thumbnail Encoding

Use the project's existing image library.

If OpenCV is already used:

cv2.imencode(".jpg", ...)

is acceptable.

The generator should return:

bytes

not:

numpy.ndarray

and not:

base64

unless the downstream event contract explicitly requires base64.

Prefer raw JPEG bytes internally.

43. Thumbnail Failure

If thumbnail generation fails, define the behavior explicitly.

Preferred behavior:

inference succeeded
    |
thumbnail failed
    |
log/metric
    |
DetectionEvent with thumbnail=None

Do not discard successful detections solely because evidence generation failed unless the application explicitly requires evidence for every detection.
44. DetectionEvent

Create or reuse:

DetectionEvent

It should contain the detection results plus evidence metadata.

Conceptually:

@dataclass(frozen=True)
class DetectionEvent:
    camera_id: str
    zone_id: str
    frame_id: int
    captured_at: datetime
    processed_at: datetime
    detections: tuple[Detection, ...]
    thumbnail: bytes | None

Adapt to existing event conventions.

45. DetectionEvent Must Be Backend-Friendly

The event will eventually travel through:

MessageQueue

Therefore consider serialization.

Raw:

numpy.ndarray

must NOT be included.

Thumbnail bytes may be included because it is intentionally small evidence.

If the project's message serialization does not support raw bytes, use the project's established binary-safe representation.

Do not invent a serialization protocol unnecessarily.

46. Thumbnail vs FrameStore

The distinction must remain clear:

FrameStore
    |
    +--> full-resolution raw frame
    +--> ephemeral
    +--> internal pipeline use

versus:

DetectionEvent
    |
    +--> small JPEG thumbnail
    +--> evidence
    +--> survives FrameStore expiration

Therefore:

DetectionEvent must contain its own thumbnail if evidence is required downstream.

Do not make downstream consumers retrieve the original frame just to generate evidence.

47. Detection Ordering

When multiple models run:

Model A
Model B
Model C

their completion order may differ.

Do not let asynchronous completion order create nondeterministic detection ordering unless that is acceptable.

Define a deterministic merge strategy.

For example:

sort by:
    use_case
    class_id
    confidence

or preserve the configured model order.

Use the approach that best fits existing requirements.

Document it.

48. Model Failure Semantics

If one of several configured models fails:

Model A -> success
Model B -> failure
Model C -> success

define the behavior.

For a compliance pipeline, consider:

continue successful models
record failure
publish partial result with metadata

versus:

fail entire DetectionEvent

Do not silently hide model failures.

The behavior must be explicit and observable.

If the model failure represents a configuration/startup problem, fail fast rather than silently producing incomplete compliance results.

Distinguish startup/configuration failures from per-frame runtime failures.

49. Empty Detection Semantics

Define what happens when:

no objects detected

Possible semantics:

publish DetectionEvent with detections=[]

or:

do not publish

For an event-driven temporal/compliance pipeline, publishing an event with an empty detection list may be important because downstream state machines may need explicit absence information.

Use the repository's existing semantics if available.

Do not invent silent filtering.

50. Confidence Threshold

The confidence threshold belongs to:

ModelSpec

not to:

YoloInferenceEngine

Example:

handwashing model
confidence = 0.5

PPE model
confidence = 0.6

The Detector applies the configured model-specific threshold.

Do not use one global hardcoded threshold.

51. mage Size

image_size belongs to model/runtime configuration.

Example:

image_size: 640

Pass it through the detector/model runtime.

Do not hardcode:

imgsz=640

unless 640 is the configured default.

32. No Downstream Business Logic

YoloInferenceEngine must NOT contain:

handwashing compliance
hand washing state
PPE compliance
violation rules
temporal rules
notification
alerting
tracking

It only produces detections.

The correct boundary is:

Inference
   |
   v
DetectionEvent
   |
   v
Tracking / State / Temporal / Compliance

33. MessageQueue Integration

Use the existing:

MessageQueue

abstraction.

Do not import:

InMemoryMessageQueue

inside YoloInferenceEngine.

Dependency injection should provide:

MessageQueue

The inference engine should publish to a configured topic.

Example:

topics:
  frame_events: frame.detect
  detection_events: detection.completed

Adapt to the existing topic configuration.

34. FrameStore Integration

Use:

FrameStore

abstraction.

Do not import:

InMemoryFrameStore

inside the inference engine.

Dependency injection should provide:

FrameStore

35. CPUInferenceWorker Responsibilities

The worker should own:

consume FrameEvents
bound work
invoke inference
handle cancellation
handle frame misses
handle inference failures
publish DetectionEvents
record metrics

It should NOT own:

model loading implementation
model resolution rules
YOLO-specific parsing
compliance rules

Those remain separate.

36. Suggested Worker Flow

Conceptually:

async def run():
    while not stopping:
        event = await subscription.get()

        try:
            await engine.process(event)
        except FrameNotFound:
            ...
        except InferenceError:
            ...

Do not let one bad frame terminate the entire worker unless the error is classified as fatal.

37. Worker Cancellation

The worker must respond to:

application shutdown
queue shutdown
task cancellation

without hanging.

Avoid:

while True:
    await asyncio.sleep(...)

polling loops.

Use proper async cancellation.

38. Graceful Shutdown

Define lifecycle:

created
   |
   v
started
   |
   v
running
   |
   v
stopping
   |
   v
stopped

Shutdown should:

stop accepting new inference work
stop/cancel consumer
finish or cancel in-flight inference according to policy
close worker resources
preserve queue/store lifecycle ownership
release model resources if required

Do not allow CPUInferenceWorker to unexpectedly close shared infrastructure it does not own unless ownership is explicitly defined.

39. ModelRegistry Lifecycle

Define:

async def close()

or equivalent if the runtime requires cleanup.

The registry owns its detectors.

Therefore it should own cleanup of:

loaded model runtime
executor resources

where applicable.

Do not make Detector responsible for closing FrameStore or MessageQueue.

60.Model Registry Ownership

The ownership model should be:

Application
   |
   +--> ModelRegistry
   |       |
   |       +--> Detector A
   |       +--> Detector B
   |
   +--> FrameStore
   |
   +--> MessageQueue

The registry owns model lifecycle.

The inference engine uses the registry but does not own the models directly.

61. Configuration

Integrate with the existing configuration system.

Conceptually:

models:
  handwashing:
    use_case: handwashing
    path: models/best.pt
    confidence: 0.5
    device: cpu
    image_size: 640

zones:
  handwash_zone:
    models:
      - handwashing

inference:
  target_fps: 5
  queue_size: 10
  workers: 1
  warmup: true

  thumbnail:
    enabled: true
    max_width: 320
    jpeg_quality: 70

Do not assume this exact YAML schema must be used.

Reuse the repository's configuration conventions.

62. Model Path Validation

At application startup, validate configured model paths where appropriate.

For example:

models/best.pt

must exist before starting the inference pipeline if eager loading is enabled.

If lazy loading is intentionally used, the failure must still be explicit and observable.

Do not silently continue with a missing model.

63. Eager vs Lazy Loading

Support a clear model-loading strategy.

For production CPU inference, prefer:

startup
   |
   v
resolve configured models
   |
   v
load
   |
   v
warm up
   |
   v
ready

This prevents the first real frame from experiencing model-loading latency.

If the application architecture requires lazy loading, preserve it, but do not mix loading and inference unpredictably.

64. Readiness

If the application has health/readiness support, inference should expose meaningful state:

model_loaded
model_warmed_up
registry_ready
worker_running

A system should not report itself fully ready if required inference models are still loading.

Reuse existing health infrastructure.

65. Startup Race

Avoid this situation:

Frame ingestion starts
       |
       v
FrameEvent published
       |
       v
InferenceWorker starts
       |
       v
Model starts loading

causing unnecessary frame accumulation.

Prefer:

Load models
   |
Warm up
   |
Mark inference ready
   |
Start/enable frame processing

or use an explicit readiness barrier consistent with the application lifecycle.

66. Inference Timing and Startup

Model loading time must NOT be counted as normal per-frame inference latency.

Track separately:

model_load_duration
model_warmup_duration
inference_duration

This is important for production diagnostics.

67. Logging

Use structured logging.

Include useful context:

camera_id
zone_id
frame_id
use_case
model_name
inference_duration_ms
detection_count

Do not log:

raw frames
full NumPy arrays
thumbnail bytes
model weights
credentials

Avoid INFO logs for every frame unless the existing project explicitly uses them.

Prefer DEBUG for high-frequency inference details.

68. Error Classification

Distinguish between:

Configuration errors

Examples:

missing model
invalid confidence
invalid device
unknown model reference

These should generally fail fast.

Startup errors

Examples:

model cannot load
runtime unavailable
warmup fails

These should prevent readiness if the model is required.

Per-frame errors

Examples:

FrameStore miss
malformed frame
inference runtime error
thumbnail encoding error

These should generally be isolated to the affected frame where safe.

Do not terminate the whole pipeline for a recoverable frame-level error.

69. Unit Tests: ModelSpec

Test:

immutable
valid configuration
invalid confidence
invalid path declaration
invalid device
invalid image size

Verify mutation is rejected.

70. Unit Tests: StaticModelResolver

Test:

camera + zone -> expected ModelSpec list
multiple models
unknown camera
unknown zone
unknown model reference
model ordering

Ensure returned ModelSpec values are correct.

71. Unit Tests: ModelLoader

Mock the underlying YOLO/runtime loader.

Test:

valid model loads
invalid path fails
runtime failure propagates correctly
device configuration is passed
image/runtime configuration is passed

Do not require actual model weights for unit tests.

72. Unit Tests: ModelRegistry

Test:

first get -> loads model
second get -> same Detector instance
same normalized path -> one instance
different paths -> different detectors

Most importantly:

concurrent get()

must not load the same model twice.

Test warm-up occurs exactly once.

73. Unit Tests: Detector

Mock the model runtime.

Test:

raw result -> Detection
confidence threshold
bbox normalization
class name
class ID
use_case
multiple detections
empty detections
runtime error

Verify no Ultralytics-specific result object leaks from the detector.

74. Unit Tests: ThumbnailGenerator

Test:

valid frame -> JPEG bytes
aspect ratio preserved
max width respected
small frame is not unnecessarily upscaled
invalid frame handled
encoding failure handled

Verify output is actually JPEG data.

75. Unit Tests: YoloInferenceEngine

Test:

FrameEvent received
models resolved
frame retrieved
registry returns detectors
detectors invoked
detections merged
thumbnail generated
DetectionEvent created
DetectionEvent published

Verify:

FrameStore.get(frame_id)

happens before inference.

76. Critical Integration Test

Create an in-memory end-to-end test:

FrameStore
    |
    v
MessageQueue
    |
    v
CPUInferenceWorker
    |
    v
YoloInferenceEngine
    |
    +--> StaticModelResolver
    |
    +--> ModelRegistry
    |
    +--> FakeDetector
    |
    +--> ThumbnailGenerator
    |
    v
DetectionEvent

Use:

fake model
fake detector
fake frame
InMemoryFrameStore
InMemoryMessageQueue

No real GPU or external infrastructure.

Verify:

FrameEvent
    |
    v
frame retrieved
    |
    v
detector called
    |
    v
Detection[]
    |
    v
thumbnail created
    |
    v
DetectionEvent
    |
    v
published

77. Frame Expiration Integration Test

Test:

FrameEvent exists
       |
FrameStore frame expires
       |
InferenceWorker receives event
       |
FrameStore.get() -> None
       |
No inference performed
       |
No worker crash
       |
Metric/log generated
       |
Worker continues

This is a mandatory production test.

78. Model Failure Integration Test

Test multiple models:

Model A -> success
Model B -> failure
Model C -> success

Verify the configured failure semantics.

No silent failure.

No worker crash unless the failure is classified as fatal.

79. Queue Backpressure Test

Generate frames faster than inference can process.

Verify:

bounded queue

does not become:

unbounded memory

Verify the configured drop/block strategy.

Measure or expose dropped work where applicable.

80. Graceful Shutdown Test

Verify:

worker running
    |
shutdown
    |
consumer stops
    |
in-flight work handled according to policy
    |
worker exits
    |
registry closes

No leaked tasks.

No event loop blocking.

Performance Considerations

The system is currently CPU-based.

Avoid unnecessary copies of:

NumPy frames
JPEG buffers
detection lists

Do not optimize prematurely, but identify obvious expensive operations.

Important areas:

model loading
model warm-up
NumPy -> runtime conversion
inference
thumbnail resize
JPEG encoding
FrameStore access

Measure rather than guessing.

82. Frame Copy Semantics

Be careful with NumPy ownership.

The inference layer should not unexpectedly mutate the frame stored in FrameStore.

If the underlying model/runtime may modify input arrays, determine whether a copy is required.

Do not blindly call:

frame.copy()

for every operation because that can significantly increase CPU and memory pressure.

Document the chosen ownership behavior.

83. Thumbnail and Detection Coordinates

Detection coordinates must correspond to the original frame coordinate system.

Do not return coordinates relative to the thumbnail.

For example:

Original:
1920 x 1080

Detection:
x1=500
y1=200
x2=900
y2=800

The thumbnail is only evidence.

It must not change detection coordinate semantics.

84. Model-Specific Classes

Different models may contain different classes.

For example:

handwashing model:
    person
    hand
    soap

Another model:

PPE model:
    helmet
    gloves
    vest

Do not assume one global class list.

The Detector must use the class mapping associated with its loaded model.

85. Model Registry and Use Case

Do not use only:

use_case

as the registry key.

Two different trained models could theoretically implement the same use case.

Prefer model identity based on normalized model path or another explicit unique model identity.

Example:

use_case:
handwashing

model path:
models/handwashing_v2.pt

Registry key:

models/handwashing_v2.pt

not merely:

handwashing
86. Duplicate Model Specs

If resolver returns:

Model A
Model A

do not run the same model twice accidentally.

The inference engine should either:

deduplicate model specs

or the resolver should guarantee uniqueness.

Prefer enforcing uniqueness at the resolver/configuration boundary.

Still protect the engine against accidental duplicates where practical.

87. Event Metadata

The DetectionEvent should preserve important frame context:

camera_id
zone_id
frame_id
captured_at
processed_at

Potentially:

source
model_versions
inference_duration

only if the existing event contract requires them.

Do not overload the event with operational internals.

88. Model Version

If practical, capture model identity/version in detection metadata.

For example:

model_name = handwashing
model_version = v2

This is useful for auditability.

Do not fabricate versions from filenames if the project does not have a versioning convention.

If unavailable, use model path/identity where appropriate.

89. Evidence Requirements

The thumbnail is generated:

while raw frame is available

not later.

This is mandatory.

Correct:

FrameStore.get()
     |
     +--> inference
     |
     +--> thumbnail

Incorrect:

FrameEvent
     |
     v
inference
     |
     v
later attempt to retrieve frame
     |
     v
thumbnail

The second design is vulnerable to FrameStore TTL expiration.

90. Do Not Make DetectionEvent Depend on FrameStore

Once created:

DetectionEvent

should be self-contained enough for downstream evidence needs.

It should not require:

FrameStore.get(frame_id)

to display the detection evidence thumbnail.

The original full frame remains ephemeral.

The thumbnail is the durable event evidence.
Production CPU Deployment

The current deployment target is CPU.

POC may use:

best.pt
   |
   v
Ultralytics YOLO
   |
   v
CPU

Production evolution:

best.pt
   |
   v
ONNX / OpenVINO export
   |
   v
CPU runtime
   |
   v
Detector

Do not force an export migration as part of this implementation unless explicitly configured.

The important requirement is that:

Detector

hides the underlying inference runtime.

Downstream code should not care whether it is:

Ultralytics
ONNX Runtime
OpenVINO
92. Configuration Over Code

Keep these configurable:

models:
  handwashing:
    path: models/best.pt
    device: cpu
    confidence: 0.5
    image_size: 640

inference:
  target_fps: 5
  queue_size: 10
  workers: 1
  warmup: true

  thumbnail:
    enabled: true
    max_width: 320
    jpeg_quality: 70

Do not require code changes to:

change model
change threshold
change device
change image size
change zone/model mapping
change worker count
change queue capacity
change thumbnail size
93. Non-Goals

Do NOT implement:

tracking
ByteTrack
state transition
temporal analysis
compliance rules
notifications
alerts
Redis
Kafka
distributed model serving
GPU orchestration
model training
model export pipeline
model version registry service

Only implement the inference-layer foundation required now.

94. Avoid Over-Engineering

This is an MVP running:

single process
single camera
CPU
in-memory infrastructure

Do not create unnecessary layers such as:

AbstractModelFactoryProvider
InferenceStrategyResolverFactory
ModelLifecycleCoordinatorFactory
RuntimeBackendOrchestratorFactory

unless the repository already uses such patterns.

The desired architecture is:

ModelResolver
ModelRegistry
ModelLoader
Detector
YoloInferenceEngine
CPUInferenceWorker

with clear responsibilities.

95. Dependency Direction

Maintain:

Application
    |
    v
Inference Interfaces
    |
    +--> ModelResolver
    +--> ModelRegistry
    +--> FrameStore
    +--> MessageQueue
    |
    v
Concrete implementations

Do not let the application layer depend directly on:

Ultralytics YOLO
InMemoryFrameStore
InMemoryMessageQueue

The only component that should know about Ultralytics-specific behavior is the appropriate runtime/model-loading implementation.
### Phase 3
Implement the state, spatio-temporal analysis, and compliance rule engine layer for the existing event-driven computer vision compliance pipeline.

The current use case is:

HANDWASH DETECTION

The implementation must integrate with the existing architecture already developed for:

StreamIngestionService
MessageQueue
FrameStore
ModelResolver
ModelRegistry
Detector
YoloInferenceEngine
DetectionEvent

Do not create a parallel architecture.

1. Existing Overall Architecture

The pipeline is:

                         VIDEO / RTSP
                              |
                              v
                     StreamIngestion
                              |
                              v
                          FrameEvent
                              |
                              v
                         YOLO Detector
                              |
                              v
                         DetectionEvent
                              |
                              v
                         ByteTrack
                              |
                              v
                    Persistent Track IDs
                              |
                              v
                    Observation Builder
                              |
                              v
                         Observation
                              |
                              v
                    State Transition
                              |
                              v
                 Spatio-Temporal Analyzer
                              |
                              v
                    Temporal Metrics
                              |
                              v
                  Compliance Rule Engine
                              |
                   +----------+----------+
                   |                     |
                   v                     v
             ComplianceEvent       Evidence Event
                alert topic        evidence topic

The critical architectural separation is:

YOLO
  ↓
Detection

ByteTrack
  ↓
Identity

Observation Builder
  ↓
Observation

State Machine
  ↓
State + State Events

Spatio-Temporal Analyzer
  ↓
Temporal / spatial metrics

RuleEvaluator
  ↓
Compliance decision

ComplianceRuleEngine
  ↓
Persistence + publishing

Do NOT combine these responsibilities.

2. Primary Objective

Implement:

StateStore
InMemoryStateStore

Observation
ObservationBuilder if required

HandwashState
StateTransition / StateMachine

SpatioTemporalAnalyzer

TemporalMetrics

RuleEvaluator

ComplianceResult

EvidenceBuffer

ComplianceRuleEngine

ComplianceEvent
EvidenceCaptureEvent

Reuse existing implementations where present.

The implementation must be production-oriented while remaining suitable for the current MVP:

single process
single camera
single handwash zone
CPU inference
in-memory state
in-memory FrameStore
in-memory MessageQueue

The architecture must remain extensible to:

multiple cameras
multiple zones
multiple people
multiple handwash stations
multiple compliance rules
persistent state
Redis-backed state
distributed workers

3. IMPORTANT: Inspect Repository First

Before writing code, inspect the existing repository.

Search for:

DetectionEvent
Detection
ByteTrack
tracker
Track
Observation
ObservationBuilder
state
StateTransition
TemporalAnalyzer
Temporal
Compliance
RuleEngine
MessageQueue
FrameStore
topic
camera_id
zone_id
frame_id
thumbnail

Also inspect:

existing configuration
existing event models
existing detection models
existing tracker implementation
existing state abstractions
existing temporal analysis
existing logging
existing metrics
existing exception hierarchy
existing async architecture
existing dependency injection
existing lifecycle/shutdown
existing tests
existing topic naming conventions

Before implementation, provide a concise discovery summary:

Repository findings:
- Existing DetectionEvent:
- Existing tracker:
- Existing Observation:
- Existing state machine:
- Existing temporal analyzer:
- Existing compliance code:
- Existing MessageQueue:
- Existing FrameStore:
- Existing configuration:
- Existing metrics:
- Existing lifecycle:
- Relevant files:
- Reuse opportunities:
- Conflicts:
- Proposed implementation files:

Then implement.

Do not wait for approval unless an ambiguity materially affects correctness.

4. Critical Architectural Rule

The implementation MUST preserve:

ByteTrack
    = identity only

State Machine
    = state transitions only

Spatio-Temporal Analyzer
    = temporal/spatial measurements only

RuleEvaluator
    = compliance decision only

ComplianceRuleEngine
    = orchestration + state persistence + event publishing

Do NOT put:

duration >= 20 seconds
soap required
washing sequence
violation evidence buffering

inside ByteTrack.

Do NOT put tracker-specific logic inside the rule engine.

5. Current Handwash State Model

The current conceptual state machine is:

UNKNOWN
   |
   v
AT_SINK
   |
   v
WATER_ON
   |
   v
SOAP_APPLIED
   |
   v
WASHING
   |
   v
RINSING
   |
   v
COMPLETED

Treat this as a domain state machine.

Do not assume every frame must transition to the next state.

The same state may persist for many observations:

WASHING
WASHING
WASHING
WASHING

Transitions must be based on observations and configured transition conditions.

6. Observation

Use or create a typed Observation.

Conceptually:

@dataclass(frozen=True)
class Observation:
    camera_id: str
    zone_id: str
    person_id: int
    timestamp: datetime

    inside_sink_zone: bool
    water_detected: bool
    soap_detected: bool
    hands_interacting: bool

    track_bbox: BoundingBox | None

Adapt this to the actual detections produced by the existing tracker and observation builder.

Do not force fields that the detector cannot currently provide.

If the existing repository has a richer Observation model, reuse it.

7. Observation Builder

If not already implemented, create a clear boundary:

DetectionEvent
    |
    v
ByteTrack
    |
    v
Track
    |
    v
ObservationBuilder
    |
    v
Observation

The ObservationBuilder converts computer-vision outputs into domain observations.

It may determine:

inside_sink_zone
water_detected
soap_detected
hands_interacting

based on configured zones, tracked objects, and spatial relationships.

It must NOT determine compliance.

For example, it should not say:

if washing_duration >= 20:
    violation = True

That belongs to the rule layer.

8. Spatial Analysis

The system needs spatial reasoning before temporal reasoning.

Examples:

person inside sink zone
hands near water
hands near soap
hands interacting
person inside configured handwash region

Create or reuse a spatial analyzer where appropriate.

Conceptually:

class SpatialAnalyzer:
    def analyze(
        self,
        tracks,
        zone_config,
    ) -> SpatialMetrics:
        ...

Possible metrics:

inside_sink_zone
water_near_hands
soap_near_hands
hands_interacting

Do not embed temporal duration logic here.

9. Spatio-Temporal Analyzer

Implement:

SpatioTemporalAnalyzer

as a component responsible for deriving temporal metrics from observations/state history.

It should answer questions such as:

How long was the person at the sink?
How long was water active?
How long was soap applied?
How long was washing performed?
How long was rinsing performed?
Were there gaps?
Was the required sequence followed?
How continuous was the activity?

It should NOT decide:

compliant
violation
alert

Those are RuleEvaluator responsibilities.

10. Temporal Metrics

Define a typed TemporalMetrics.

Conceptually:

@dataclass(frozen=True)
class TemporalMetrics:
    at_sink_duration: float
    water_on_duration: float
    soap_applied_duration: float
    washing_duration: float
    rinsing_duration: float

    sequence_valid: bool
    continuity_valid: bool

    observation_count: int
    time_gaps: tuple[float, ...]

Adapt based on actual requirements.

Do not calculate meaningless metrics for states that were never observed.

Use explicit values such as:

0
None

depending on the semantic meaning.

Do not silently conflate:

not observed

with:

observed for zero seconds

11. Duration Calculation

Use event timestamps, not frame count, for compliance duration.

Do NOT calculate:

duration = frame_count / fps

as the authoritative compliance duration.

Instead use:

observation.timestamp

or equivalent monotonic/event timestamps.

Why:

camera FPS may vary
frames may be dropped
sampling may change
inference latency may vary

The rule is temporal, so timestamps are authoritative.

12. State Machine

Implement or reuse a dedicated state machine.

Conceptually:

class HandwashStateMachine:

    def transition(
        self,
        current_state: HandwashState,
        observation: Observation,
    ) -> StateTransitionResult:
        ...

A transition result should contain at least:

previous_state
new_state
timestamp

and optionally:

person_id
reason

The state machine should be deterministic.

13. State Transition Examples

Examples:

UNKNOWN
  + person enters sink
  -> AT_SINK
AT_SINK
  + water detected
  -> WATER_ON
WATER_ON
  + soap applied
  -> SOAP_APPLIED
SOAP_APPLIED
  + hands interacting
  -> WASHING
WASHING
  + water/rinse condition
  -> RINSING
RINSING
  + person completes activity
  -> COMPLETED

These are examples.

Use actual repository/configuration semantics if they already exist.

Do not hardcode domain assumptions that are not supported by the existing project.

14. Invalid Sequence

The state machine must explicitly handle invalid sequences.

Example:

AT_SINK
   |
   +--> SOAP_APPLIED

when water is required before soap.

Do not automatically mark it compliant.

Possible result:

sequence_valid = False

The state machine should expose enough information for the temporal/rule layer to evaluate this.

15. State Reset

Define how state resets.

Typical condition:

person leaves handwash zone

may eventually return:

COMPLETED
   |
   v
UNKNOWN

or preserve a completed session until the next person appears.

Do not arbitrarily reset state every frame.

State must be associated with:

camera_id
zone_id
person_id

where required by the architecture.

16. State Identity

There are two related concepts:

Persistent zone state

The required StateStore is keyed by:

camera_id + zone_id
Person-level state

The state value may contain information for one or more tracked persons:

person_id -> current state/history

Do not incorrectly create a global state for all people if ByteTrack provides persistent person IDs.

Design the stored value to support the current single-person MVP while allowing multiple tracked people later.

17. StateStore Interface

Implement:

class StateStore(ABC):

    @abstractmethod
    async def get(
        self,
        key: str,
    ) -> dict | None:
        ...

    @abstractmethod
    async def set(
        self,
        key: str,
        value: dict,
    ) -> None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

Adapt to existing conventions.

The contract is:

get(key)
    -> state dict or None

set(key, value)
    -> None

The state store does not understand:

handwashing
compliance
violation
YOLO
ByteTrack

It is generic infrastructure.

18. State Key

The state key must identify:

camera_id + zone_id

Do not use only:

zone_id

because different cameras may contain zones with the same name.

Use a deterministic representation, for example:

camera_id:zone_id

or the repository's equivalent.

Create a helper if useful:

make_state_key(camera_id, zone_id)

Do not duplicate string concatenation throughout the codebase.

19. InMemoryStateStore

Implement:

InMemoryStateStore

using:

dict[str, dict]

It must implement the StateStore interface.

Requirements:

simple
async API
testable
no external dependency

Do not put business logic into the store.

19. InMemoryStateStore

Implement:

InMemoryStateStore

using:

dict[str, dict]

It must implement the StateStore interface.

Requirements:

simple
async API
testable
no external dependency

Do not put business logic into the store.

20. State Store Concurrency

Consider concurrent access.

Potential situation:

worker A -> get(state)
worker B -> get(state)
worker A -> set(state)
worker B -> set(state)

If the architecture guarantees one processing sequence per camera/zone, document that guarantee.

If not, protect state updates appropriately.

Do not silently allow lost updates.

For the single-camera MVP, serializing processing per state key is preferable to allowing uncontrolled concurrent updates.

21. State Serialization

The StateStore should store domain state data, not runtime objects such as:

asyncio.Task
YOLO object
Tracker instance
NumPy array
OpenCV object

Stored state should be:

JSON-like
serializable
small

except where the existing architecture intentionally uses typed in-memory objects.

This is important because a future Redis-backed StateStore should be possible.

22. StateStore Must Not Store Evidence

Do not put:

thumbnail bytes
full frame
JPEG
NumPy array

inside persistent compliance state unless explicitly required.

Evidence belongs to the temporary evidence buffer and event payload.

State should remain small.

23. RuleEvaluator

Implement:

RuleEvaluator

as the component responsible for applying compliance rules.

The RuleEvaluator receives:

state
detections/observations
timestamp
thumbnail
frame_id

and returns:

updated state
outcome
evidence payload if violation

Conceptually:

updated_state, outcome, evidence = evaluator.evaluate(
    state=state,
    detections=detections,
    timestamp=timestamp,
    thumbnail=thumbnail,
    frame_id=frame_id,
)

Adapt to repository conventions.

24. RuleEvaluator Must Not Own Persistence

Do NOT make:

RuleEvaluator

call:

StateStore.get()
StateStore.set()
MessageQueue.publish()

The evaluator is a pure/domain decision component.

The orchestrator owns persistence and publishing.

25. RuleEvaluator Responsibilities

The evaluator may:

update state
calculate rule conditions
track absence duration
create group_id
buffer evidence
discard evidence
freeze evidence
determine violation
construct evidence payload

It must NOT:

load state from storage
persist state
publish messages
access Redis
access Kafka
know about asyncio.Queue

26. Presence / Absence Rule

The current rule requirement is:

Apply a presence/duration rule. While absence is building, mint a group_id and buffer evidence. If compliance resumes, discard the whole buffer. Once a violation is confirmed, freeze the buffer.

Implement this explicitly.

Do not bury this logic inside ComplianceRuleEngine.

The evaluator owns the rule lifecycle.

27. Define "Absence"

Make the meaning of absence explicit in configuration/domain logic.

For handwashing, examples could include:

required handwashing activity absent
soap absent
water absent
required state not reached
required behavior not continuously observed

Do not arbitrarily choose one if the repository already defines the rule.

Use a configurable rule condition.

For example:

compliance:
  handwash:
    minimum_washing_duration_seconds: 20
    absence_threshold_seconds: 20

Adapt to the actual requirements.

28. Evidence Group Lifecycle

Each potential violation gets a group:

NO ACTIVE GROUP
      |
      | absence starts
      v
GROUP ACTIVE
      |
      +--> compliance resumes
      |       |
      |       v
      |    DISCARD
      |
      +--> absence continues
              |
              v
        threshold reached
              |
              v
       VIOLATION CONFIRMED
              |
              v
       GROUP FROZEN

The group represents one potential violation episode.

29. Mint group_id

When the absence condition begins, create a unique:

group_id

Do not create a new group on every frame.

Correct:

absence begins
    -> group_id = G123

absence continues
    -> group_id = G123

absence continues
    -> group_id = G123

Incorrect:

frame 1 -> G123
frame 2 -> G124
frame 3 -> G125

Use an appropriate unique ID mechanism such as UUID if the repository has no existing ID strategy.

30. Evidence Buffer

While a potential violation is building, buffer thumbnails:

group_id
    |
    +--> thumbnail/frame evidence

The maximum number of thumbnails must be bounded by:

EVIDENCE_BUFFER_MAX

Make this configurable.

Example:

compliance:
  evidence_buffer_max: 10

Do not allow unlimited evidence accumulation.

31. Evidence Buffer Contents

Each buffered evidence item should contain enough metadata to reconstruct the event:

@dataclass(frozen=True)
class EvidenceItem:
    frame_id: int
    timestamp: datetime
    thumbnail: bytes

Potentially:

camera_id
zone_id
person_id

if required.

Do not store full-resolution frames.

The FrameStore already handles full pixels.

32. Evidence Buffer Policy

When:

buffer size == EVIDENCE_BUFFER_MAX

define the behavior.

For example:

ring buffer
drop oldest
retain first N

For evidence, a bounded ring buffer is generally useful because it captures the most recent lead-up to the violation.

However, if the repository specifies a different policy, follow it.

Document the chosen behavior.

33. Compliance Resumes

If compliance resumes before the violation threshold:

potential violation
    |
    v
compliance resumes
    |
    v
discard entire evidence buffer
    |
    v
clear group_id
    |
    v
return to normal

Do NOT publish the buffered evidence.

Do NOT publish a violation.

This is a critical requirement.

34. Violation Confirmation

When the configured rule threshold is reached:

absence_duration >= configured_threshold

confirm:

violation

At that moment:

freeze evidence buffer

Do not continue mutating the evidence associated with that confirmed violation unless explicitly required.

35. Frozen Evidence

Once confirmed:

group_id
    |
    v
FROZEN
    |
    +--> evidence list cannot be modified

The evidence payload becomes immutable.

This prevents later compliance recovery from accidentally modifying or deleting evidence for an already confirmed violation.

36. Violation Idempotency

Avoid publishing duplicate violations for the same absence episode.

Example:

20 sec -> violation
21 sec -> still violation
22 sec -> still violation

must NOT produce:

3 violation events

unless repeat alerts are explicitly configured.

Default behavior should be:

one violation per group_id

The state must remember:

violation_confirmed = True

or equivalent.

37. Outcome Contract

The evaluator should return:

updated_state
outcome
evidence

where:

outcome = None

for normal processing.

And:

outcome = "violation"

when a new violation is confirmed.

Do not return "violation" on every subsequent frame after confirmation.

38. Evidence Payload

Evidence should only be returned when:

outcome == "violation"

Example:

evidence = {
    "group_id": group_id,
    "items": [
        {
            "frame_id": ...,
            "timestamp": ...,
            "thumbnail": ...,
        }
    ],
}

Use typed models if the project supports them.

Do not include evidence for normal compliant events.
39. ComplianceResult

Prefer a typed result rather than returning an unstructured tuple if the repository supports it.

Conceptually:

@dataclass(frozen=True)
class RuleEvaluationResult:
    state: dict
    outcome: str | None
    evidence: EvidencePayload | None

This makes the contract explicit.

40. ComplianceRuleEngine

Implement:

ComplianceRuleEngine

as the orchestrator.

Responsibilities:

receive DetectionEvent or observation input
derive/update observation/state
load state from StateStore
invoke RuleEvaluator
persist updated state
publish lightweight compliance event
publish evidence separately when violation occurs

It must NOT contain the actual rule logic.

41. ComplianceRuleEngine Flow

The desired flow is:

DetectionEvent
      |
      v
Observation / State transition
      |
      v
StateStore.get(camera_id + zone_id)
      |
      v
current state
      |
      v
SpatioTemporalAnalyzer
      |
      v
Temporal metrics
      |
      v
RuleEvaluator
      |
      +----------------------+
      |                      |
      v                      v
updated state            outcome
      |                      |
      v                      |
StateStore.set()             |
                             |
                    +--------+--------+
                    |                 |
                 None            violation
                    |                 |
                    v                 v
                 nothing       publish ComplianceEvent
                                      |
                                      v
                              publish EvidenceEvent

Adapt the exact ordering based on the existing pipeline.

42. State Load / Persist

The engine must:

1. construct state key
2. StateStore.get(key)
3. initialize state if absent
4. evaluate
5. StateStore.set(key, updated_state)

Always persist the updated state after successful evaluation.

Do not persist partially updated state if evaluation fails.

43. State Initialization

If:

state = await state_store.get(key)

returns:

None

create the correct initial state.

For example:

current_state = UNKNOWN

Do not store None as the active state unless the state machine explicitly uses it.

44. Spatio-Temporal Analyzer Integration

The engine should not calculate duration directly.

Instead:

state/history
     |
     v
SpatioTemporalAnalyzer
     |
     v
TemporalMetrics
     |
     v
RuleEvaluator

This preserves separation.

Example:

metrics = temporal_analyzer.analyze(
    state=state,
    timestamp=timestamp,
)

Then:

result = rule_evaluator.evaluate(
    state=state,
    metrics=metrics,
    ...
)

45. Pure Rule Evaluation

The following must be unit-testable without:

YOLO
ByteTrack
camera
FrameStore
MessageQueue

For example:

metrics = TemporalMetrics(
    washing_duration=23,
    sequence_valid=True,
    continuity_valid=True,
)

result = evaluator.evaluate(...)

Then:

assert result.outcome is None

or:

assert result.outcome == "violation"

depending on the configured rule.

This is a mandatory architectural requirement.

46. Handwash Compliance Rule

Implement the current handwash rule through configuration.

At minimum support concepts such as:

minimum washing duration
required sequence
continuity
completion

Example:

compliance:
  handwash:
    minimum_washing_duration_seconds: 20
    require_soap: true
    require_water: true
    require_sequence: true
    require_completion: true

Do not hardcode:

if washing_duration >= 20:

inside the rule evaluator.

Read from configuration/domain rule specification.

47. Rule Configuration

The evaluator should receive a typed rule configuration.

Conceptually:

@dataclass(frozen=True)
class HandwashRuleConfig:
    minimum_washing_duration_seconds: float
    require_soap: bool
    require_water: bool
    require_sequence: bool
    require_completion: bool
    absence_threshold_seconds: float
    evidence_buffer_max: int

Adapt to the project's configuration model.

Validate configuration at startup.

48. Compliance Logic Separation

Keep these concepts separate:

State
WASHING
Metric
washing_duration = 23.4
Rule
washing_duration >= 20
Decision
compliant / violation

Do not collapse them into one object.

49. ComplianceEvent

Create or reuse:

ComplianceEvent

The alert-facing event must be lightweight.

It should contain only what downstream alerting needs.

Conceptually:

@dataclass(frozen=True)
class ComplianceEvent:
    camera_id: str
    zone_id: str
    timestamp: datetime
    outcome: str
    group_id: str

Potentially include:

reason
person_id
rule_name

if required.

50. ComplianceEvent Must NOT Contain Evidence

Do NOT include:

thumbnail[]
full frames
large detection arrays

inside the alert-facing event.

The event must remain lightweight.

Example:

ComplianceEvent
    |
    +--> camera_id
    +--> zone_id
    +--> group_id
    +--> outcome
    +--> reason

51.Evidence Event

Create or reuse a separate:

EvidenceCaptureEvent

or equivalent event.

It should contain:

group_id
camera_id
zone_id
evidence[]

where evidence contains:

frame_id
timestamp
thumbnail

The evidence event is published only when:

violation

is confirmed.

52. Topic Separation

Use separate topics.

Conceptually:

topics:
  compliance_alert: compliance.alert
  evidence_capture: evidence.capture

The exact topic names must follow the repository's conventions.

The architecture must be:

ComplianceEvent
    |
    v
TOPIC_COMPLIANCE_ALERT

and:

EvidenceCaptureEvent
    |
    v
TOPIC_EVIDENCE_CAPTURE

Do not publish evidence on the alert topic.

53. Publish Ordering

When a violation is confirmed:

1. persist frozen state
2. publish ComplianceEvent
3. publish EvidenceCaptureEvent

or another explicitly documented ordering based on the application's reliability requirements.

The critical requirement is:

The evidence payload must be available as a consequence of the same confirmed violation group and must not be accidentally discarded after the alert is published.

If queue publishing fails, handle it explicitly.

Do not silently lose a confirmed compliance violation.

54. Publishing Failure

Distinguish:

rule evaluation succeeded

from:

event publication failed

A message publication failure must not cause the state machine to roll back unless the system explicitly implements transactional semantics.

For the MVP:

state persisted
publication attempted
failure logged/metric emitted

is acceptable.

Do not implement distributed transactions.

56. Evidence Publication Failure

Evidence is critical for compliance.

If:

ComplianceEvent published

but:

EvidenceCaptureEvent failed

the failure must be visible through:

structured logs
metrics
retry mechanism if existing

Do not silently swallow the failure.

If the existing queue supports retries, reuse it.

Do not invent a distributed retry subsystem for the MVP.

57. State vs Evidence Lifecycle

The state store contains:

current compliance state
active group_id
absence start
violation status
temporal information

The evidence buffer contains:

temporary thumbnails

The DetectionEvent contains:

detections
frame metadata
thumbnail for that frame

The ComplianceEvent contains:

lightweight violation metadata
group_id

The EvidenceCaptureEvent contains:

frozen evidence payload

Keep these lifecycles separate.

58. Suggested State Structure

Conceptually:

{
    "person_id": 7,
    "current_state": "WASHING",

    "state_started_at": "...",

    "absence": {
        "active": true,
        "started_at": "...",
        "group_id": "uuid"
    },

    "violation": {
        "confirmed": false,
        "group_id": null
    },

    "temporal": {
        "washing_duration": 12.4,
        "water_duration": 15.2,
        "soap_duration": 3.1,
        "sequence_valid": true
    }
}

Do not blindly use this exact schema.

Use typed domain objects where appropriate and serialize them at the StateStore boundary.

59. State Store Should Remain Small

Do NOT store:

all historical detections
all thumbnails
full video
all frames

The state store is not an event archive.

Keep only the state required to evaluate the current compliance episode.

60. Temporal History

Determine how much observation history is required.

Avoid retaining unlimited history.

Possible strategies:

state transition timestamps
rolling bounded observation history
aggregated durations

Prefer aggregated temporal metrics where sufficient.

If raw history is required, bound it.

60. Time Semantics

Be precise about:

captured_at
received_at
processed_at

Compliance duration should generally be based on:

captured_at

or the domain event timestamp.

Do not use processing latency to inflate washing duration.

For example:

captured_at = 10:00:00
processed_at = 10:00:02

must not make the activity appear two seconds longer.

61. Clock Handling

Use a consistent timestamp representation.

For elapsed durations, prefer a monotonic clock where the application already supports one.

For event/audit timestamps, use timezone-aware UTC timestamps if that matches repository conventions.

Do not mix naive and timezone-aware datetime values.

62. Multiple Persons

The current use case may involve one person.

However, ByteTrack produces:

person_id

Therefore, the architecture should not permanently assume:

one camera = one person

The state value should support:

camera_id + zone_id
    |
    +--> person_id 7
    +--> person_id 12

even if the MVP processes only one person.

Do not redesign the entire system for multi-person support unless necessary.

63. Multiple Zones

State must remain scoped to:

camera_id + zone_id

not globally.

Example:

camera_01:handwash_zone
camera_01:entry_zone

must have independent state.

64. RuleEvaluator State Isolation

Do not allow:

camera A / zone A

to influence:

camera B / zone B

State, evidence groups, and temporal metrics must remain correctly scoped.

65. Group ID Scope

A group_id represents one compliance episode.

It should be associated with:

camera_id
zone_id
person_id
rule/use_case

where appropriate.

Do not reuse one group across unrelated people/zones.

66. Group ID and State Persistence

If the application restarts, the MVP uses:

InMemoryStateStore

so active state will be lost.

That is acceptable for the MVP.

Document:

restart -> state reset

The interface must nevertheless allow a future persistent implementation.

67. InMemoryStateStore Factory

If the project already uses factories:

StateStoreFactory

should select:

in_memory

from configuration.

Conceptually:

state_store:
  backend: in_memory

Do not hardcode InMemoryStateStore inside ComplianceRuleEngine.

68. Dependency Injection

The engine should receive abstractions:

ComplianceRuleEngine(
    state_store: StateStore,
    rule_evaluator: RuleEvaluator,
    temporal_analyzer: SpatioTemporalAnalyzer,
    message_queue: MessageQueue,
)

Potentially:

state_machine
observation_builder

depending on the existing pipeline.

Do NOT instantiate these dependencies inside the engine.

69. ComplianceRuleEngine Should Be Thin

The desired engine is approximately:

receive event
    ↓
load state
    ↓
update domain state
    ↓
calculate metrics
    ↓
evaluate rule
    ↓
persist state
    ↓
publish outputs

Not:

500-line class containing:
    tracking
    geometry
    state transitions
    duration calculation
    compliance rules
    evidence management
    queue implementation

Keep it thin.

70. Unit Test RuleEvaluator Without Computer Vision

This is mandatory.

Example:

metrics = TemporalMetrics(
    washing_duration=23.0,
    sequence_valid=True,
    continuity_valid=True,
)

result = evaluator.evaluate(
    state=state,
    metrics=metrics,
    timestamp=timestamp,
    thumbnail=thumbnail,
    frame_id=42,
)

Verify the rule decision without:

YOLO
ByteTrack
OpenCV
camera
FrameStore
MessageQueue

71. Unit Test State Machine Without Camera

Use synthetic observations.

Example:

observation = Observation(
    person_id=7,
    timestamp=t0,
    inside_sink_zone=True,
    water_detected=True,
    soap_detected=True,
    hands_interacting=True,
)

Then:

result = state_machine.transition(
    current_state=HandwashState.AT_SINK,
    observation=observation,
)

Verify:

expected state
expected transition

72. Unit Test Temporal Analyzer

Provide synthetic timestamps:

10:00:00 AT_SINK
10:00:03 WATER_ON
10:00:05 SOAP_APPLIED
10:00:08 WASHING
10:00:31 RINSING

Verify:

washing_duration = 23 seconds

Do not use frame count.

73. Evidence Lifecycle Tests

Create explicit tests for:

Absence begins
group_id created
buffer contains thumbnail
Absence continues
same group_id
buffer grows
Buffer limit
buffer <= EVIDENCE_BUFFER_MAX
Compliance resumes
buffer cleared
group_id cleared
no violation
Violation confirmed
group_id preserved
buffer frozen
outcome = violation
evidence returned
Subsequent frames
same violation does not publish repeatedly

74. Evidence Immutability

Once violation is confirmed:

frozen evidence

must not be mutated.

Prefer immutable structures:

tuple[EvidenceItem, ...]

or equivalent.

This is important because the evidence payload is an audit artifact.

75. DetectionEvent to ComplianceRuleEngine

If the existing DetectionEvent contains:

camera_id
zone_id
frame_id
captured_at
detections
thumbnail

the compliance engine should use it directly or pass it through an ObservationBuilder.

The engine should not query the FrameStore merely to obtain a thumbnail if DetectionEvent already contains it.

The thumbnail is already part of the event evidence path.

76. Full Runtime Flow

The final architecture should be:

VIDEO / RTSP
     |
     v
StreamIngestionService
     |
     v
FrameStore.put(frame_id, frame)
     |
     v
MessageQueue
     |
     v
FrameEvent
     |
     v
YoloInferenceEngine
     |
     +--> ModelResolver
     +--> ModelRegistry
     +--> Detector
     |
     v
DetectionEvent
     |
     +--> detections
     +--> frame_id
     +--> thumbnail
     |
     v
ByteTrack
     |
     v
Track IDs
     |
     v
ObservationBuilder
     |
     v
Observation
     |
     v
SpatialAnalyzer
     |
     v
Spatial Metrics
     |
     v
StateMachine
     |
     v
State + Transition
     |
     v
SpatioTemporalAnalyzer
     |
     v
TemporalMetrics
     |
     v
RuleEvaluator
     |
     +--------------------------+
     |                          |
     v                          v
Updated State              Outcome
     |                          |
     v                          |
StateStore.set()               |
                                |
                         +------+------+
                         |             |
                       None       violation
                         |             |
                         |             v
                         |       group_id
                         |             |
                         |       ComplianceEvent
                         |             |
                         |             v
                         |       ALERT TOPIC
                         |
                         +------ EvidenceCaptureEvent
                                        |
                                        v
                               EVIDENCE TOPIC

77. Important Evidence Flow

The evidence lifecycle must be:

DetectionEvent.thumbnail
        |
        v
RuleEvaluator
        |
        v
Potential violation
        |
        v
bounded evidence buffer
        |
        +--> compliance resumes
        |       |
        |       v
        |    discard
        |
        +--> violation confirmed
                |
                v
             freeze
                |
                v
        EvidenceCaptureEvent

Do NOT retrieve the original frame from FrameStore after violation confirmation just to create evidence.

The thumbnail was already attached to DetectionEvent.

78. Message Topics

Use the existing MessageQueue abstraction.

Conceptually:

TOPIC_DETECTION
    |
    v
DetectionEvent

TOPIC_COMPLIANCE_ALERT
    |
    v
ComplianceEvent

TOPIC_EVIDENCE_CAPTURE
    |
    v
EvidenceCaptureEvent

Do not couple the rule engine to InMemoryMessageQueue.

79. Alert Event Example

Conceptually:

{
  "camera_id": "camera_01",
  "zone_id": "handwash_zone",
  "group_id": "7b9...",
  "outcome": "violation",
  "rule": "handwash_compliance",
  "timestamp": "..."
}

Keep it lightweight.

Do not put:

thumbnail
full detection history
full frame

inside this message.

80. Evidence Event Example

Conceptually:

{
  "camera_id": "camera_01",
  "zone_id": "handwash_zone",
  "group_id": "7b9...",
  "evidence": [
    {
      "frame_id": 120,
      "timestamp": "...",
      "thumbnail": "..."
    },
    {
      "frame_id": 121,
      "timestamp": "...",
      "thumbnail": "..."
    }
  ]
}

Use the project's serialization convention.

If binary JPEG bytes cannot be serialized directly, use the existing binary-safe representation.

Do not invent a new serialization protocol unless necessary.

81. No Evidence on Normal Compliance

For normal processing:

outcome = None
evidence = None

Do not publish:

EvidenceCaptureEvent

unless a violation is confirmed.

This prevents unnecessary message volume.

82. State Persistence Ordering

For a normal frame:

get state
   ↓
evaluate
   ↓
set updated state

For a newly confirmed violation:

get state
   ↓
evaluate
   ↓
freeze evidence
   ↓
set updated state
   ↓
publish ComplianceEvent
   ↓
publish EvidenceCaptureEvent

The persisted state should indicate that the violation has already been confirmed before publishing downstream events.

This helps prevent duplicate alerts after retries/reprocessing.

83. Idempotency Consideration

If the same DetectionEvent is accidentally delivered twice:

frame_id = 100

the rule engine should avoid producing duplicate violation events where practical.

Consider storing enough state to identify the last processed frame/event:

last_frame_id
last_timestamp

Do not build a full deduplication database for the MVP.

A simple state-level guard is sufficient if compatible with the existing delivery semantics.

84. Out-of-Order Events

If MessageQueue delivery can produce out-of-order events, determine whether the current architecture guarantees ordering per camera/zone.

If ordering is guaranteed:

document the assumption

If not:

detect timestamps/frame IDs
ignore or handle stale events

Do not silently corrupt temporal state.

For the MVP, per-camera/zone ordered processing is preferred.

85. Backpressure

The compliance engine must not create unlimited asynchronous tasks.

Do not do:

asyncio.create_task(process(event))

for every detection event without a bound.

Reuse the existing worker/queue architecture.

One logical camera/zone state should ideally be processed sequentially to avoid state races.

86. Per-Zone Serialization

If possible, ensure:

camera_01:handwash_zone

events are processed in order.

This greatly simplifies state correctness.

Conceptually:

camera_01:handwash_zone
    |
    v
ordered worker
    |
    +--> event 101
    +--> event 102
    +--> event 103

Do not allow:

event 103
event 101
event 102

to update the same state concurrently.

87. Observability

Add or reuse metrics.

At minimum:

compliance_evaluations_total
compliance_violations_total
compliance_evaluation_failures_total

state_store_get_total
state_store_set_total

evidence_groups_created_total
evidence_groups_discarded_total
evidence_groups_confirmed_total
evidence_buffer_items_total
evidence_publish_failures_total

temporal_analysis_duration_seconds
rule_evaluation_duration_seconds

Use low-cardinality labels:

camera_id
zone_id
rule_name

only if the project's metric cardinality is acceptable.

Do not label metrics with:

frame_id
group_id
person_id

unless there is a specific bounded-cardinality reason.

88. 88. Logging

Use structured logging.

Useful fields:

camera_id
zone_id
person_id
frame_id
group_id
current_state
new_state
outcome
rule_name
duration

Examples of meaningful events:

state_transition
absence_started
evidence_group_created
evidence_group_discarded
violation_confirmed
evidence_frozen
compliance_event_published
evidence_event_published

Do not log:

full thumbnail bytes
full NumPy frame
entire detection arrays
89. Error Handling

Classify failures.

StateStore failure

Potentially infrastructure failure.

Do not evaluate against unknown state and silently continue.

Temporal analyzer failure

Frame-level/domain processing failure.

Do not corrupt persisted state.

Rule evaluator failure

Do not persist partially mutated state.

Compliance event publication failure

Log/metric and apply repository retry semantics if available.

Evidence publication failure

Log/metric and preserve enough state to identify the failed evidence publication if practical.

Do not silently discard compliance evidence.

90. No Distributed Transaction

Do NOT implement:

distributed transaction
two-phase commit
Kafka transaction
Redis transaction

for the MVP.

Use:

state persistence
+
message publication
+
observability

with clear failure semantics.

91. Configuration

Integrate with existing configuration.

Conceptually:

state_store:
  backend: in_memory

compliance:
  handwash:
    minimum_washing_duration_seconds: 20
    absence_threshold_seconds: 20
    require_soap: true
    require_water: true
    require_sequence: true
    require_completion: true
    evidence_buffer_max: 10

topics:
  detection_events: detection.completed
  compliance_alert: compliance.alert
  evidence_capture: evidence.capture

Use the actual repository configuration style.

Do not hardcode business thresholds.

92. Configuration Validation

Validate:

minimum_washing_duration_seconds > 0
absence_threshold_seconds > 0
evidence_buffer_max > 0
topic names non-empty
state backend supported

Also validate:

required sequence configuration

where applicable.

Fail fast on invalid configuration.

93. State Machine Tests

Test at minimum:

UNKNOWN -> AT_SINK
AT_SINK -> WATER_ON
WATER_ON -> SOAP_APPLIED
SOAP_APPLIED -> WASHING
WASHING -> RINSING
RINSING -> COMPLETED

Also test:

invalid sequence
missing water
missing soap
person leaves zone
state reset
same-state observations
94. Temporal Analyzer Tests

Test:

duration calculation
sequence validation
continuity
time gaps
missing observations
irregular sampling
dropped frames

Example:

10:00:00
10:00:04
10:00:10

must calculate based on timestamps, not frame count.

95. RuleEvaluator Tests

Test:

Compliant
washing_duration = 23
sequence_valid = True
continuity_valid = True

Expected:

outcome = None

or the repository's explicit PASS representation.

Violation
washing_duration < required threshold

Expected:

outcome = violation

with evidence.

Compliance recovery
absence starts
absence continues
compliance resumes before threshold

Expected:

group discarded
no violation
Confirmed violation
absence reaches threshold

Expected:

group frozen
one violation
evidence returned
96. Evidence Buffer Tests

Test:

empty -> first item
first -> multiple items
max capacity
oldest item policy
discard
freeze
immutable after freeze

Ensure:

len(buffer) <= EVIDENCE_BUFFER_MAX

always.

97. StateStore Tests

Test:

get missing key -> None
set/get
overwrite
multiple camera/zone keys
close
operations after close

Test isolation:

camera_01:zone_a
camera_01:zone_b
camera_02:zone_a

must remain independent.

98. ComplianceRuleEngine Tests

Mock:

StateStore
SpatioTemporalAnalyzer
RuleEvaluator
MessageQueue

Verify:

state loaded
analyzer invoked
evaluator invoked
state persisted
no alert when outcome None
alert published on violation
evidence published on violation
evidence not published on normal evaluation
99. Critical Integration Test

Create:

DetectionEvent
    |
    v
ObservationBuilder
    |
    v
StateMachine
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
    +--> InMemoryStateStore
    |
    +--> InMemoryMessageQueue

Use synthetic data.

No:

YOLO
camera
RTSP
GPU

required.

Verify the complete handwash lifecycle.

100. Critical Evidence Integration Test

Simulate:

Frame 1
absence starts
thumbnail A
Frame 2
absence continues
thumbnail B
Frame 3
absence continues
thumbnail C

then:

compliance resumes

Expected:

group discarded
no ComplianceEvent
no EvidenceCaptureEvent

Then test:

absence starts
A
B
C
...
threshold reached

Expected:

one group_id
one ComplianceEvent
one EvidenceCaptureEvent
frozen evidence
101. Verify Alert Payload Size

The alert event must remain small.

Verify that:

ComplianceEvent

does NOT contain:

thumbnail
full frame
large detection history

Evidence belongs exclusively in:

EvidenceCaptureEvent
102. Verify Evidence Independence

After:

FrameStore

expires/deletes the original frame, the evidence event must still contain the thumbnail.

Test:

FrameStore frame expires
        |
        v
DetectionEvent already contains thumbnail
        |
        v
Compliance violation
        |
        v
EvidenceCaptureEvent

The evidence must not depend on the original frame still existing.

103. StateStore Future Migration

The interface should allow:

InMemoryStateStore
        |
        v
RedisStateStore

later.

Do not let:

ComplianceRuleEngine

know that the current backend is a dictionary.

104. Rule Extensibility

The current rule is:

handwash compliance

but the architecture should allow:

PPE compliance
social distancing
machine operation
safety zone compliance

later.

Therefore:

RuleEvaluator

should not become a hardcoded collection of unrelated rules.

Use a handwash-specific evaluator/configuration where appropriate.

The engine should orchestrate a generic evaluator interface.

105. Recommended Component Structure

Adapt to the repository, but conceptually:

compliance/
├── state/
│   ├── models.py
│   ├── machine.py
│   └── transitions.py
│
├── temporal/
│   ├── models.py
│   ├── spatial.py
│   └── analyzer.py
│
├── rules/
│   ├── base.py
│   ├── handwash.py
│   └── evaluator.py
│
├── evidence/
│   ├── models.py
│   └── buffer.py
│
├── engine.py
└── events.py

infrastructure/
└── state_store/
    ├── base.py
    ├── in_memory.py
    └── factory.py

Do not force this structure if the repository already has a better organization.

106. Do Not Over-Engineer

The current system is:

single process
single camera
single handwash use case

Do NOT implement:

distributed state machine
distributed locks
Kafka transactions
Redis transactions
event sourcing platform
rule DSL
complex workflow engine
generic CEP platform

The architecture should be:

simple
typed
testable
deterministic
replaceable
107. Final Dependency Direction

Maintain:

                 ComplianceRuleEngine
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
   StateStore      TemporalAnalyzer  RuleEvaluator
          |              |              |
          v              v              v
 InMemoryStateStore   Metrics       Handwash Rules
                                         
                         |
                         v
                  MessageQueue
                         |
              +----------+----------+
              |                     |
              v                     v
       ComplianceEvent      EvidenceCaptureEvent

Business/domain components depend on interfaces.

Infrastructure implementations remain replaceable.

108. Final Architectural Principle

Enforce this separation:

                 DETECTION
                    |
                    v
                ByteTrack
                    |
              "Who is this?"
                    |
                    v
              Observation
                    |
              "What is happening?"
                    |
                    v
             State Machine
                    |
              "What state?"
                    |
                    v
        Spatio-Temporal Analyzer
                    |
              "For how long?"
                    |
                    v
             Rule Evaluator
                    |
              "Is it compliant?"
                    |
                    v
          ComplianceRuleEngine
                    |
          +---------+---------+
          |                   |
          v                   v
    Alert Event          Evidence Event

The rule engine must never become the place where all of these questions are answered.

109. Required Implementation Workflow

Follow this exact sequence:

DISCOVER
   ↓
DEFINE STATE CONTRACT
   ↓
IMPLEMENT StateStore
   ↓
IMPLEMENT InMemoryStateStore
   ↓
DEFINE Observation
   ↓
IMPLEMENT/REUSE ObservationBuilder
   ↓
IMPLEMENT Spatial Analysis
   ↓
IMPLEMENT State Machine
   ↓
IMPLEMENT Temporal Metrics
   ↓
IMPLEMENT SpatioTemporalAnalyzer
   ↓
DEFINE RuleEvaluator CONTRACT
   ↓
IMPLEMENT Handwash RuleEvaluator
   ↓
IMPLEMENT EvidenceBuffer
   ↓
IMPLEMENT ComplianceEvent
   ↓
IMPLEMENT EvidenceCaptureEvent
   ↓
IMPLEMENT ComplianceRuleEngine
   ↓
INTEGRATE MessageQueue
   ↓
INTEGRATE STATE STORE
   ↓
INTEGRATE WITH DetectionEvent
   ↓
WRITE UNIT TESTS
   ↓
WRITE EVIDENCE LIFECYCLE TESTS
   ↓
WRITE END-TO-END IN-MEMORY TEST
   ↓
RUN EXISTING TEST SUITE
   ↓
RUN TYPE CHECKING
   ↓
RUN LINT / FORMAT
   ↓
PRODUCTION REVIEW
   ↓
REPORT

Do not skip repository discovery.

Do not make large speculative refactors.

110. Production Review Checklist
StateStore

Interface exists

get(key) returns state or None

set(key, value) persists state

InMemory implementation uses dict

Key includes camera_id + zone_id

No business logic in store

No frames/thumbnails stored in state

Async lifecycle is safe

Future Redis implementation is possible

State Machine

Separate from tracker

Deterministic

Handwash states represented

Same-state observations supported

Invalid sequence handled

Reset semantics defined

Person identity respected

Spatial Analysis

Separate from temporal logic

Uses configured zones

Produces spatial metrics

No compliance decisions

Spatio-Temporal Analyzer

Separate component

Uses timestamps

Duration calculations are timestamp-based

Sequence metrics supported

Continuity metrics supported

Time gaps handled

No compliance decision

RuleEvaluator

Pure/domain-oriented

Does not access StateStore

Does not publish messages

Applies configurable handwash rules

Handles absence lifecycle

Creates group_id once

Evidence buffer bounded

Compliance recovery discards buffer

Confirmed violation freezes buffer

Duplicate violation prevented

ComplianceRuleEngine

Loads state

Updates state

Runs temporal analysis

Runs RuleEvaluator

Persists state

Publishes lightweight ComplianceEvent

Publishes evidence separately

No full thumbnails in alert event

No full frames in messages

Graceful error handling

Dependency injection

Evidence

Thumbnail comes from DetectionEvent

No later FrameStore dependency

Bounded buffer

group_id attached

Buffer discarded on compliance recovery

Buffer frozen on violation

Evidence immutable after confirmation

Evidence topic separate from alert topic

Testing

StateStore tests

State machine tests

Spatial analyzer tests

Temporal analyzer tests

RuleEvaluator tests

Evidence buffer tests

ComplianceRuleEngine tests

Compliance recovery test

Violation confirmation test

Duplicate violation test

FrameStore expiration/evidence test

Full in-memory integration test

No camera/YOLO dependency in domain tests

Production Quality

Type hints

Immutable domain models where appropriate

Structured logging

Metrics

Bounded memory

No unbounded evidence

No duplicate violation alerts

No hidden state mutation

No hardcoded thresholds

No infrastructure coupling

Existing tests pass

111. Final Report

After implementation, provide:

Files Changed

List every modified/created file and explain why.

Architecture

Show the final:

Detection
   ↓
ByteTrack
   ↓
Observation
   ↓
State Machine
   ↓
SpatioTemporalAnalyzer
   ↓
RuleEvaluator
   ↓
ComplianceRuleEngine
   ↓
Alert + Evidence
State Model

Show the final handwash state transitions.

StateStore

Explain:

key format
stored state
InMemory implementation
future persistence path
Rule Semantics

Explain exactly:

what constitutes absence
when group_id is created
when evidence is buffered
when evidence is discarded
when violation is confirmed
when evidence freezes
how duplicate violations are prevented
Evidence Flow

Show:

DetectionEvent.thumbnail
       ↓
EvidenceBuffer
       ↓
Compliance violation
       ↓
EvidenceCaptureEvent
Topics

Show the final:

detection topic
compliance alert topic
evidence topic
Configuration

Show the actual configuration implemented.

Metrics

List metrics implemented.

Tests

Report:

tests added
tests executed
passed
failed
Verification

Report:

unit tests
integration tests
type checking
lint
format
existing test suite
Known Limitations

Explicitly identify MVP limitations, such as:

single process
InMemoryStateStore
single handwash use case
no persistent state across restart
Future Extension

Explain how the architecture can later support:

RedisStateStore
multiple cameras
multiple zones
multiple persons
additional compliance rules
distributed processing

without changing the fundamental domain boundaries.

Final Requirement

The implementation must preserve this exact conceptual separation:

ByteTrack
    |
    +--> Identity

ObservationBuilder
    |
    +--> Spatial/domain observation

State Machine
    |
    +--> State transitions

SpatioTemporalAnalyzer
    |
    +--> Duration
    +--> Sequence
    +--> Continuity
    +--> Time gaps

RuleEvaluator
    |
    +--> Compliance decision
    +--> Evidence episode lifecycle

StateStore
    |
    +--> Persist current state

ComplianceRuleEngine
    |
    +--> Orchestrate
    +--> Persist
    +--> Publish

MessageQueue
    |
    +--> ComplianceEvent
    +--> EvidenceCaptureEvent

Do not collapse these responsibilities into ComplianceRuleEngine.