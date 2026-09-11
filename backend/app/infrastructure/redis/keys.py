"""Redis key generation helpers.

All Redis keys must be constructed through these helpers — never by
concatenating strings ad-hoc in other components.

Frame key structure (§8 of redisstream.md)
-------------------------------------------
``{prefix}:{camera_id}:{frame_id}``

The prefix is set at construction time (e.g. ``"cv:frame"``).
camera_id scopes frame_id to a specific camera so that after restart or
when multiple cameras are running, old frame_ids do not collide.

Note: A full ``ingestion_session_id`` scope is intentionally omitted at the
FrameStore interface level because the existing FrameStore.put/get API only
accepts ``frame_id``.  The camera_id prefix provides sufficient isolation
for the single-camera MVP and short-TTL eviction handles the rest.
For multi-camera deployments one ``RedisFrameStore`` instance per camera
should be used (each with its own prefix).
"""
from __future__ import annotations


def frame_key(prefix: str, camera_id: str, frame_id: int) -> str:
    """Return the Redis key used to store one raw frame.

    Args:
        prefix:    Key namespace prefix (e.g. ``"cv:frame"``).
        camera_id: Source camera identifier.
        frame_id:  Monotonic frame counter (scoped to this camera).

    Returns:
        Redis key string, e.g. ``"cv:frame:handwash-camera-01:1234"``.
    """
    return f"{prefix}:{camera_id}:{frame_id}"


def stream_consumer_group(stream_name: str) -> str:
    """Conventional consumer group name for a stream.

    Args:
        stream_name: Redis stream name (e.g. ``"cv:frame:ingested"``).

    Returns:
        Consumer group name, e.g. ``"cv:frame:ingested:workers"``.
    """
    return f"{stream_name}:workers"
