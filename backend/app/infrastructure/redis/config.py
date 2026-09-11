"""RedisConfig — typed, validated configuration for all Redis components.

Loaded from the ``redis`` section of config.yaml.  All stream names,
timeouts, TTLs, and consumer parameters are centralized here so no other
file hard-codes a Redis key or stream name.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Topic names used by the rest of the application (must match the topics
# already used by InMemoryMessageQueue callers).
TOPIC_FRAME_INGESTED = "ingestion.frames"
TOPIC_DETECTION_CREATED = "inference.detections"
TOPIC_COMPLIANCE_ALERT = "compliance.alert"
TOPIC_EVIDENCE_CAPTURE = "evidence.capture"


@dataclass(frozen=True)
class RedisStreamsConfig:
    frame_ingested: str = "cv:frame:ingested"
    detection_created: str = "cv:detection:created"
    compliance_alert: str = "cv:compliance:alert"
    evidence_capture: str = "cv:evidence:capture"
    max_length: int = 10_000
    approximate_trim: bool = True

    def stream_for_topic(self, topic: str) -> str:
        """Return the Redis stream name for an application topic."""
        mapping = {
            TOPIC_FRAME_INGESTED: self.frame_ingested,
            TOPIC_DETECTION_CREATED: self.detection_created,
            TOPIC_COMPLIANCE_ALERT: self.compliance_alert,
            TOPIC_EVIDENCE_CAPTURE: self.evidence_capture,
        }
        return mapping.get(topic, f"cv:{topic}")

    def consumer_group_for_topic(self, topic: str) -> str:
        return f"{self.stream_for_topic(topic)}:workers"


@dataclass(frozen=True)
class RedisFrameStoreConfig:
    ttl_seconds: int = 30
    key_prefix: str = "cv:frame"


@dataclass(frozen=True)
class RedisConsumerConfig:
    pending_idle_timeout_ms: int = 60_000
    recovery_interval_seconds: float = 10.0


@dataclass(frozen=True)
class RedisConfig:
    url: str = "redis://localhost:6379/0"
    socket_timeout_seconds: float = 2.0
    socket_connect_timeout_seconds: float = 2.0
    health_check_interval_seconds: float = 30.0
    streams: RedisStreamsConfig = field(default_factory=RedisStreamsConfig)
    frame_store: RedisFrameStoreConfig = field(default_factory=RedisFrameStoreConfig)
    consumer: RedisConsumerConfig = field(default_factory=RedisConsumerConfig)

    @classmethod
    def from_cfg(cls, redis_section: dict) -> "RedisConfig":
        """Build from the ``redis:`` section of config.yaml."""
        streams_raw = redis_section.get("streams", {})
        fs_raw = redis_section.get("frame_store", {})
        consumer_raw = redis_section.get("consumer", {})
        return cls(
            url=redis_section.get("url", "redis://localhost:6379/0"),
            socket_timeout_seconds=float(redis_section.get("socket_timeout_seconds", 2.0)),
            socket_connect_timeout_seconds=float(redis_section.get("socket_connect_timeout_seconds", 2.0)),
            health_check_interval_seconds=float(redis_section.get("health_check_interval_seconds", 30.0)),
            streams=RedisStreamsConfig(
                frame_ingested=streams_raw.get("frame_ingested", "cv:frame:ingested"),
                detection_created=streams_raw.get("detection_created", "cv:detection:created"),
                compliance_alert=streams_raw.get("compliance_alert", "cv:compliance:alert"),
                evidence_capture=streams_raw.get("evidence_capture", "cv:evidence:capture"),
                max_length=int(streams_raw.get("max_length", 10_000)),
                approximate_trim=bool(streams_raw.get("approximate_trim", True)),
            ),
            frame_store=RedisFrameStoreConfig(
                ttl_seconds=int(fs_raw.get("ttl_seconds", 30)),
                key_prefix=fs_raw.get("key_prefix", "cv:frame"),
            ),
            consumer=RedisConsumerConfig(
                pending_idle_timeout_ms=int(consumer_raw.get("pending_idle_timeout_ms", 60_000)),
                recovery_interval_seconds=float(consumer_raw.get("recovery_interval_seconds", 10.0)),
            ),
        )
