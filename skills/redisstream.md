You are working on an existing Computer Vision Compliance Detection project.

Your task is to introduce Redis Streams as the scalable infrastructure backend for:

1. StreamIngestionService
2. MessageQueue
3. FrameStore

The implementation must be production-oriented and must preserve the existing domain interfaces and CV processing pipeline.

==================================================
1. FIRST: INSPECT THE EXISTING CODEBASE
==================================================

Before making any changes:

- Inspect the complete repository structure.
- Identify the existing implementations/interfaces for:
  - StreamIngestionService
  - StreamConnector
  - VideoConnector
  - RTSPConnector
  - FrameSampler
  - FrameValidator
  - FrameEvent
  - MessageQueue
  - InMemoryMessageQueue
  - FrameStore
  - InMemoryFrameStore
  - StateStore
  - DetectionEvent
  - YoloInferenceEngine
  - CPUInferenceWorker
  - ComplianceRuleEngine
  - ComplianceWorker
- Identify application startup/shutdown lifecycle.
- Identify current configuration management.
- Identify current dependency management.
- Identify existing tests.
- Identify all places where MessageQueue and FrameStore are instantiated.

Do NOT start implementing before understanding the existing abstractions.

==================================================
2. EXISTING ARCHITECTURE TO PRESERVE
==================================================

The existing logical pipeline is:

Video / RTSP
    ↓
StreamIngestionService
    ↓
FrameEvent
    ↓
MessageQueue
    ↓
YOLO Inference
    ↓
DetectionEvent
    ↓
Tracking
    ↓
Observation
    ↓
State Machine
    ↓
Spatio-Temporal Analyzer
    ↓
Compliance Rule Engine
    ↓
Violation
    ↓
Evidence / Notification

The current MVP uses:

    InMemoryMessageQueue
    InMemoryFrameStore
    InMemoryStateStore

Do NOT remove the in-memory implementations.

The goal is to introduce Redis-backed implementations behind the existing interfaces.

==================================================
3. TARGET ARCHITECTURE
==================================================

Implement the following:

                    ┌──────────────────────┐
                    │ StreamIngestionService│
                    └──────────┬───────────┘
                               │
                         FrameEvent
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Redis Streams      │
                    │   frame.ingested     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ CPUInferenceWorker   │
                    └──────────┬───────────┘
                               │
                         DetectionEvent
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Redis Streams      │
                    │   detection.created  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ ComplianceWorker     │
                    └──────────────────────┘


Frame data:

StreamIngestionService
        │
        ├── frame metadata → Redis Stream
        │
        └── frame pixels → Redis FrameStore


Important:

Do NOT put raw image/frame bytes directly into Redis Stream messages.

Redis Streams should contain lightweight metadata/references.

==================================================
4. REDIS COMPONENTS
==================================================

Introduce these abstractions if they do not already exist:

RedisConnectionManager
RedisStreamMessageQueue
RedisFrameStore

The architecture should remain:

MessageQueue
    ├── InMemoryMessageQueue
    └── RedisStreamMessageQueue

FrameStore
    ├── InMemoryFrameStore
    └── RedisFrameStore

The application should select the implementation through configuration.

==================================================
5. REDIS STREAM DESIGN
==================================================

Use Redis Streams for durable asynchronous message transport.

Define configurable stream names:

redis:
  streams:
    frame_ingested: "cv:frame:ingested"
    detection_created: "cv:detection:created"
    compliance_alert: "cv:compliance:alert"
    evidence_capture: "cv:evidence:capture"

Do not hardcode these names throughout the code.

Create a centralized configuration object.

Use Redis consumer groups for worker processing.

Example:

Stream:
    cv:frame:ingested

Consumer group:
    inference-workers

Consumers:
    inference-worker-1
    inference-worker-2
    ...

Similarly:

cv:detection:created
    ↓
compliance-workers

==================================================
6. STREAM INGESTION INTEGRATION
==================================================

Update StreamIngestionService so that it can publish FrameEvents to Redis Streams.

The ingestion service remains responsible for:

- Reading the video/RTSP source
- Frame sampling
- Frame validation
- Assigning frame_id
- Assigning camera_id
- Capturing timestamps
- Storing frame data
- Publishing lightweight frame metadata

It must NOT contain Redis-specific business logic.

Use the MessageQueue and FrameStore interfaces.

Conceptually:

frame = connector.read()

validated_frame = validator.validate(frame)

frame_id = ...

frame_store.put(
    frame_id,
    frame
)

message_queue.publish(
    "frame.ingested",
    FrameEvent(...)
)

The ingestion service should not directly call redis-py.

==================================================
7. FRAME STORE DESIGN
==================================================

Implement RedisFrameStore behind the existing FrameStore interface.

Purpose:

Store short-lived frame pixels separately from message metadata.

Example:

Redis key:

cv:frame:{camera_id}:{session_id}:{frame_id}

Value:

JPEG bytes

OR another efficient serialized representation supported by the existing implementation.

Do not store full-resolution frames unless the existing architecture explicitly requires it.

Use the existing thumbnail/frame encoding strategy where appropriate.

Implement:

put()
get()
delete()
exists()

or whatever exact interface already exists.

Add configurable TTL:

redis:
  frame_store:
    ttl_seconds: 30

The FrameStore must automatically expire stale frames.

==================================================
8. FRAME KEY DESIGN
==================================================

Do NOT assume frame_id is globally unique.

The existing architecture treats frame_id as scoped to an ingestion session.

Therefore use a key structure similar to:

cv:frame:{camera_id}:{ingestion_session_id}:{frame_id}

This prevents collisions after:

- Application restart
- New video
- New ingestion session
- Multiple cameras

Use a helper for key generation.

Do not construct Redis keys manually in multiple components.

==================================================
9. MESSAGE PAYLOAD DESIGN
==================================================

Redis Stream messages must contain metadata only.

Example frame message:

{
    "camera_id": "...",
    "zone_id": "...",
    "ingestion_session_id": "...",
    "frame_id": 123,
    "captured_at": "...",
    "received_at": "...",
    "frame_store_key": "cv:frame:camera1:session1:123"
}

The inference worker should:

1. Read message from Redis Stream.
2. Deserialize metadata.
3. Retrieve frame using frame_store_key.
4. Run inference.
5. Delete frame when it is no longer needed, subject to evidence requirements.
6. ACK the Redis Stream message.

Do NOT embed image bytes in Redis Stream messages.

==================================================
10. CONSUMER GROUP SEMANTICS
==================================================

Implement Redis consumer groups correctly.

For each worker:

XGROUP CREATE

Then:

XREADGROUP GROUP <group> <consumer>

Messages must be ACKed only after successful processing.

Example:

read
  ↓
retrieve frame
  ↓
inference
  ↓
publish detection event
  ↓
XACK

If processing fails:

DO NOT ACK the message.

The message must remain pending and be recoverable.

==================================================
11. PENDING MESSAGE RECOVERY
==================================================

Implement production-safe recovery for abandoned/pending messages.

If a worker crashes after receiving a message but before ACK:

The message should not be permanently lost.

Use Redis pending-entry mechanisms such as:

XPENDING
XCLAIM
or
XAUTOCLAIM

Prefer XAUTOCLAIM where supported by the selected Redis client/version.

Implement configurable:

redis:
  consumer:
    pending_idle_timeout_ms: 60000
    recovery_interval_seconds: 10

Recovery behavior:

worker receives message
    ↓
worker crashes
    ↓
message remains PENDING
    ↓
another worker detects idle pending message
    ↓
claims message
    ↓
reprocesses
    ↓
ACK

Document the chosen recovery approach.

==================================================
12. IDEMPOTENCY
==================================================

Redis Stream processing must be designed for at-least-once delivery.

Do NOT assume exactly-once delivery.

A worker may process the same message more than once.

Therefore introduce idempotency where required.

Use a deterministic event identifier such as:

camera_id
+
ingestion_session_id
+
frame_id

or the existing event ID if the codebase already provides one.

Do not create duplicate persistent records or duplicate compliance effects when the same event is retried.

Use Redis only for transport-level deduplication if appropriate, but do not rely exclusively on Redis for business-level idempotency.

PostgreSQL should remain the durable system of record.

==================================================
13. BACKPRESSURE
==================================================

The current architecture has bounded processing queues.

Redis Streams introduce a potentially unbounded stream.

Do NOT allow Redis Streams to grow indefinitely.

Implement configuration for:

- Maximum stream length
- Retention
- Consumer lag monitoring
- Frame TTL
- Stream trimming

Example:

redis:
  streams:
    max_length: 10000
    approximate_trim: true

Use MAXLEN ~ where appropriate.

Explain the tradeoff between:

MAXLEN
and
MAXLEN ~

Do not trim messages before consumers have a reasonable opportunity to process them.

The design must prevent Redis memory growth.

==================================================
14. FRAME EXPIRATION
==================================================

FrameStore TTL and Redis Stream retention are separate concerns.

Example:

FrameStore:

30 seconds TTL

Stream:

10,000 messages

Do not assume stream retention controls frame data retention.

If a stream message references an expired frame:

The inference worker should:

- detect missing frame
- increment a metric
- ACK the message if retry cannot succeed
- log the condition
- avoid crashing the worker

Example metric:

frame_store_miss_total

Do not retry indefinitely when the frame is already expired.

==================================================
15. REDIS FAILURE HANDLING
==================================================

Redis is infrastructure and must not bring down the entire application unexpectedly.

Handle:

- Connection failure
- Timeout
- Redis restart
- Network interruption
- Authentication failure
- Serialization failure
- Stream creation failure
- Consumer group creation failure

Implement:

- Connection pooling
- Timeouts
- Retry with exponential backoff
- Reconnection
- Health checks
- Clear error logging

Do not implement infinite blocking retries.

==================================================
16. REDIS CONNECTION MANAGEMENT
==================================================

Create a centralized Redis connection manager.

Requirements:

- One configurable connection pool per process.
- Async/sync mode should match the existing application architecture.
- Explicit socket/connect/read timeouts.
- Health check.
- Graceful close.
- Configuration-driven Redis URL.
- Optional username/password.
- Optional TLS.

Example:

redis:
  enabled: true
  url: redis://localhost:6379/0
  socket_timeout_seconds: 2
  socket_connect_timeout_seconds: 2
  health_check_interval_seconds: 30

Never hardcode credentials.

Credentials must come from environment variables/secrets.

==================================================
17. CONFIGURATION
==================================================

Support both:

runtime.backend: memory

and:

runtime.backend: redis

Example:

runtime:
  message_queue_backend: redis
  frame_store_backend: redis

redis:
  enabled: true
  url: ${REDIS_URL}

  streams:
    frame_ingested: cv:frame:ingested
    detection_created: cv:detection:created
    compliance_alert: cv:compliance:alert
    evidence_capture: cv:evidence:capture
    max_length: 10000
    approximate_trim: true

  frame_store:
    ttl_seconds: 30

  consumer:
    pending_idle_timeout_ms: 60000
    recovery_interval_seconds: 10

Make sure the existing memory configuration continues to work.

==================================================
18. MULTI-CAMERA SCALABILITY
==================================================

The implementation must support multiple cameras.

Messages must always contain:

camera_id

and where relevant:

zone_id
ingestion_session_id
frame_id

Do NOT create a global stream/state assumption.

Example:

Camera A
    ↓
cv:frame:ingested
    ↓
inference-worker-1

Camera B
    ↓
cv:frame:ingested
    ↓
inference-worker-2

Multiple workers should be able to consume from the same consumer group.

==================================================
19. ORDERING
==================================================

Document Redis Stream ordering semantics.

Do not assume global ordering across all cameras.

Ordering should be considered within the appropriate camera/session scope.

If the compliance state machine requires ordered observations for a person:

Ensure the downstream processing model preserves the ordering required by the existing state architecture.

Do not blindly parallelize messages for the same camera/person if that can cause state transitions to be processed out of order.

==================================================
20. MESSAGE SCHEMA VERSIONING
==================================================

Introduce a schema version field.

Example:

{
    "schema_version": 1,
    "event_type": "frame.ingested",
    ...
}

Do not rely on Python pickle serialization.

Use JSON or another explicit interoperable serialization format.

The message schema should be independent of Python class implementation details.

==================================================
21. SERIALIZATION
==================================================

Do NOT use pickle for Redis messages.

Implement explicit serialization/deserialization.

The serializer should handle:

- datetime
- enums
- IDs
- nested metadata

Ensure serialization is deterministic and testable.

Invalid messages should:

- be logged
- increment a metric
- not crash the worker

==================================================
22. METRICS
==================================================

Add operational metrics for Redis.

At minimum:

redis_connection_status

redis_publish_total

redis_publish_failure_total

redis_stream_read_total

redis_stream_ack_total

redis_stream_processing_failure_total

redis_stream_pending_messages

redis_stream_lag

frame_store_put_total

frame_store_get_total

frame_store_miss_total

frame_store_expired_total

redis_operation_latency

Also preserve all existing ingestion/inference/compliance metrics.

Expose important metrics through the existing /health endpoint or existing metrics mechanism.

==================================================
23. LOGGING
==================================================

Use structured logging.

Every relevant log should include where available:

camera_id
zone_id
ingestion_session_id
frame_id
event_id
consumer_group
consumer_name

Example:

{
    "event": "frame_processing_failed",
    "camera_id": "...",
    "frame_id": 123,
    "consumer": "inference-worker-2"
}

Do not log:

- credentials
- Redis passwords
- raw frame bytes
- sensitive connection strings

==================================================
24. STARTUP
==================================================

Update application startup so Redis-backed components are initialized in the correct order.

Expected conceptual order:

1. RedisConnectionManager
2. RedisFrameStore
3. RedisStreamMessageQueue
4. StreamIngestionService
5. ModelRegistry
6. YOLO inference
7. Compliance components
8. Workers
9. Ingestion

Create Redis streams and consumer groups during startup if they do not exist.

Startup must fail clearly if Redis is configured as required but unavailable.

If the application supports optional Redis fallback, make that behavior explicit and configuration-driven.

Do NOT silently fall back from Redis to memory in production.

==================================================
25. SHUTDOWN
==================================================

Implement graceful shutdown.

Expected:

1. Stop ingestion.
2. Stop publishing new messages.
3. Allow workers to finish in-flight work within timeout.
4. ACK successfully processed messages.
5. Close Redis consumers/connections.
6. Close FrameStore.
7. Close remaining application resources.

Do not terminate workers while they are midway through processing without handling pending messages correctly.

==================================================
26. MESSAGE QUEUE INTERFACE
==================================================

Preserve the existing MessageQueue contract.

Do not change callers unnecessarily.

If the current interface is insufficient for Redis Streams, extend it carefully.

Possible operations:

publish()
subscribe()
ack()
close()

or the exact methods already used by the project.

The Redis implementation must be substitutable for InMemoryMessageQueue.

The business logic must not contain:

redis.xadd(...)
redis.xreadgroup(...)
etc.

Redis-specific operations belong inside the infrastructure implementation.

==================================================
27. FRAME STORE INTERFACE
==================================================

Preserve the existing FrameStore contract.

RedisFrameStore must be substitutable for InMemoryFrameStore.

Business components should continue to call:

frame_store.put(...)
frame_store.get(...)
frame_store.delete(...)

rather than Redis directly.

==================================================
28. TESTING
==================================================

Add unit tests for:

1. Redis key generation.
2. Message serialization.
3. Message deserialization.
4. Invalid message handling.
5. FrameStore put/get/delete.
6. FrameStore TTL.
7. FrameStore missing frame.
8. Stream publish.
9. Consumer group creation.
10. Message consumption.
11. ACK.
12. Failed processing.
13. Pending message recovery.
14. Idempotent processing.
15. Stream trimming.
16. Redis connection failure.
17. Redis reconnect.
18. Multiple consumers.
19. Multiple cameras.
20. Graceful shutdown.

Add integration tests using a real Redis instance, preferably through Testcontainers if the project already uses containers.

Do not mock all Redis behavior and claim Redis integration is tested.

At least one integration test must validate:

Ingestion
    ↓
Redis Stream
    ↓
Worker
    ↓
FrameStore
    ↓
Processing
    ↓
ACK

==================================================
29. PERFORMANCE TESTING
==================================================

Add a basic load test/benchmark for:

- 1 camera
- 5 FPS
- 10 FPS
- Multiple cameras
- Multiple inference workers

Measure:

- Stream publish latency
- Stream consumption latency
- FrameStore latency
- Queue lag
- Worker throughput
- Pending messages
- Frame expiration
- Redis memory usage

The goal is to verify that Redis is not becoming the bottleneck.

==================================================
30. IMPORTANT CV PROCESSING CONSTRAINT
==================================================

Do not break the existing CPU inference optimization.

The current system has already addressed frame backlog and expiration problems.

Redis integration must NOT simply move the unlimited queue problem from:

Python Queue

to:

Redis Stream

The architecture must preserve bounded processing behavior.

For live RTSP workloads, prioritize fresh frames over processing an arbitrarily old backlog where the existing application semantics allow it.

If frame freshness requires a special strategy, document it explicitly rather than silently changing behavior.

==================================================
31. COMPLIANCE PROCESSING
==================================================

Do not change the existing:

- State Machine
- Spatio-Temporal Analyzer
- Compliance Rule Engine
- Violation grouping
- Evidence lifecycle

Redis is an infrastructure change.

The following behavior must remain unchanged:

Detection
    ↓
Observation
    ↓
State Transition
    ↓
Temporal Analysis
    ↓
Compliance Evaluation
    ↓
Violation
    ↓
Evidence

Verify existing compliance tests still pass.

==================================================
32. POSTGRESQL COMPATIBILITY
==================================================

The existing architecture is moving toward PostgreSQL as the durable system of record.

Redis must NOT replace PostgreSQL.

Use:

Redis
    = transport + ephemeral frame storage

PostgreSQL
    = durable business/system record

Do not persist business truth only in Redis.

Important records such as:

- compliance evaluations
- violations
- evidence metadata
- notifications
- audit logs

must continue to follow the existing PostgreSQL architecture.

==================================================
33. OBSERVABILITY
==================================================

Expose enough information to diagnose:

Ingestion:
    frames produced
    frames dropped
    stream status

Redis:
    stream length
    consumer lag
    pending messages
    publish failures
    processing failures

Inference:
    processed frames
    inference latency
    expired/missing frames

Compliance:
    evaluations
    violations
    processing latency

This must integrate with the existing /health endpoint and metrics design rather than creating a second unrelated monitoring mechanism.

==================================================
34. DO NOT OVER-ENGINEER
==================================================

Do NOT introduce:

- Kafka
- Celery
- RabbitMQ
- Kubernetes
- unnecessary microservices
- unnecessary distributed locks

The objective is:

Current single-process MVP
        ↓
Redis-backed scalable runtime
        ↓
Multiple workers / multiple cameras
        ↓
Future horizontal scaling

Keep the implementation modular so future infrastructure changes remain possible.

==================================================
35. DOCUMENTATION
==================================================

Update the technical documentation with:

1. Redis architecture.
2. Stream names.
3. Consumer groups.
4. Message schemas.
5. FrameStore key structure.
6. TTL strategy.
7. Stream retention strategy.
8. Pending message recovery.
9. At-least-once delivery semantics.
10. Idempotency.
11. Backpressure.
12. Failure handling.
13. Configuration.
14. Local development setup.
15. Production deployment considerations.
16. Monitoring/metrics.
17. Scaling strategy.

Include an architecture diagram.

==================================================
36. DOCKER / LOCAL DEVELOPMENT
==================================================

If the project uses Docker/docker-compose, add Redis to the local development environment.

Example:

redis:
  image: redis:<supported-version>
  ports:
    - "6379:6379"

Do not hardcode a Redis version without checking the project's dependency/runtime compatibility.

Add health checks where appropriate.

Local development should support:

runtime.backend = memory

and:

runtime.backend = redis

==================================================
37. ACCEPTANCE CRITERIA
==================================================

The implementation is complete only when:

[ ] Existing in-memory MessageQueue still works.

[ ] Existing in-memory FrameStore still works.

[ ] RedisStreamMessageQueue implements the MessageQueue interface.

[ ] RedisFrameStore implements the FrameStore interface.

[ ] StreamIngestionService can publish through the abstraction without Redis-specific code.

[ ] Frame pixels are stored separately from Stream metadata.

[ ] Redis Stream messages contain only lightweight metadata.

[ ] Consumer groups are used for scalable workers.

[ ] Messages are ACKed only after successful processing.

[ ] Pending messages can be recovered.

[ ] At-least-once delivery is handled safely.

[ ] Duplicate processing does not create duplicate business events.

[ ] Frame TTL is implemented.

[ ] Stream retention/trimming is implemented.

[ ] Redis failures are handled gracefully.

[ ] Redis connection pooling is implemented.

[ ] Metrics are available.

[ ] Structured logging is available.

[ ] Multiple cameras are supported.

[ ] Multiple workers can consume from the same consumer group.

[ ] Existing state machine behavior is unchanged.

[ ] Existing temporal analyzer behavior is unchanged.

[ ] Existing compliance rule behavior is unchanged.

[ ] PostgreSQL remains the durable system of record.

[ ] Existing tests continue to pass.

[ ] Redis integration tests pass.

[ ] Graceful startup/shutdown works.

[ ] Documentation is updated.

==================================================
38. IMPLEMENTATION APPROACH
==================================================

Follow this order:

PHASE 1
Inspect existing architecture and interfaces.

PHASE 2
Implement Redis configuration and connection manager.

PHASE 3
Implement RedisFrameStore.

PHASE 4
Implement RedisStreamMessageQueue.

PHASE 5
Implement serialization/schema versioning.

PHASE 6
Integrate Redis backend selection into application startup.

PHASE 7
Integrate StreamIngestionService through existing abstractions.

PHASE 8
Integrate inference and compliance workers.

PHASE 9
Implement pending-message recovery and idempotency.

PHASE 10
Implement metrics, health checks and structured logging.

PHASE 11
Add integration and failure tests.

PHASE 12
Run the complete existing test suite.

PHASE 13
Run an end-to-end test:

RTSP/video
    ↓
StreamIngestionService
    ↓
RedisFrameStore
    ↓
Redis Stream
    ↓
CPUInferenceWorker
    ↓
DetectionEvent
    ↓
Tracking
    ↓
Observation
    ↓
State Machine
    ↓
Spatio-Temporal Analyzer
    ↓
Compliance Rule Engine
    ↓
Violation
    ↓
PostgreSQL

PHASE 14
Update architecture and deployment documentation.

==================================================
39. FINAL REPORT
==================================================

After implementation, provide a concise engineering report containing:

1. Files created.
2. Files modified.
3. Redis components implemented.
4. Redis stream names.
5. Consumer groups.
6. FrameStore key strategy.
7. TTL/retention strategy.
8. Failure/retry strategy.
9. Pending message recovery strategy.
10. Idempotency strategy.
11. Configuration changes.
12. Metrics added.
13. Tests added.
14. Test results.
15. End-to-end validation result.
16. Known limitations.
17. Recommended next production-hardening steps.

IMPORTANT:

Do not merely create Redis classes without integrating them into the actual runtime.

Do not rewrite the existing CV architecture.

Do not remove the in-memory implementations.

Do not introduce Redis-specific code into domain/business logic.

Do not put raw frame bytes into Redis Streams.

Do not use Redis as the durable compliance database.

The objective is to make the existing architecture scalable while preserving the current behavior and clean separation of concerns.