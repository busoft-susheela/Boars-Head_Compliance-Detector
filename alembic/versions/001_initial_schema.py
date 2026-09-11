"""Initial PostgreSQL schema for BH_CV Compliance Detector.

Creates all 18 tables:
  cameras, streams, zones,
  ingestion_sessions, processing_sessions,
  frames, detections, tracks,
  observations, state_transitions, temporal_metrics,
  compliance_rules, compliance_evaluations,
  violations, evidence_groups, evidence_items,
  notifications, audit_logs

Revision ID: 001
Revises:
Create Date: 2026-09-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── cameras ───────────────────────────────────────────────────────────────
    op.create_table(
        "cameras",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("camera_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("location", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("camera_key", name="uq_cameras_camera_key"),
    )
    op.create_index("ix_cameras_camera_key", "cameras", ["camera_key"])

    # ── streams ───────────────────────────────────────────────────────────────
    op.create_table(
        "streams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("stream_type", sa.String(16), nullable=False),
        sa.Column("source_reference", sa.String(1024), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("configuration", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_streams_camera_id", "streams", ["camera_id"])

    # ── zones ─────────────────────────────────────────────────────────────────
    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("zone_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("zone_type", sa.String(32), nullable=False, server_default="HANDWASH"),
        sa.Column("geometry", postgresql.JSONB, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_zones_camera_id", "zones", ["camera_id"])

    # ── ingestion_sessions ────────────────────────────────────────────────────
    op.create_table(
        "ingestion_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=True),
        sa.Column("stream_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("streams.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="RUNNING"),
        sa.Column("frames_read", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("frames_dropped", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("frames_published", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("frames_failed", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("reconnect_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_frame_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ingestion_sessions_camera_id", "ingestion_sessions", ["camera_id"])
    op.create_index("ix_ingestion_sessions_started_at", "ingestion_sessions", ["started_at"])

    # ── processing_sessions ───────────────────────────────────────────────────
    op.create_table(
        "processing_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("camera_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="RUNNING"),
        sa.Column("model_name", sa.String(256), nullable=True),
        sa.Column("model_version", sa.String(128), nullable=True),
        sa.Column("model_path", sa.String(1024), nullable=True),
        sa.Column("configuration", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_processing_sessions_camera_id", "processing_sessions", ["camera_id"])
    op.create_index("ix_processing_sessions_started_at", "processing_sessions", ["started_at"])

    # ── frames ────────────────────────────────────────────────────────────────
    op.create_table(
        "frames",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingestion_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_sessions.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("frame_id", sa.BigInteger, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("frame_store_key", sa.String(256), nullable=True),
        sa.Column("processing_status", sa.String(32), nullable=False, server_default="RECEIVED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ingestion_session_id", "frame_id", name="uq_frame_session_frame_id"),
    )
    op.create_index("ix_frames_camera_zone_captured", "frames", ["camera_id", "zone_id", "captured_at"])
    op.create_index("ix_frames_ingestion_session_id", "frames", ["ingestion_session_id"])

    # ── detections ────────────────────────────────────────────────────────────
    op.create_table(
        "detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("frame_db_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("frames.id"), nullable=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("class_id", sa.Integer, nullable=False),
        sa.Column("class_name", sa.String(256), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("x1", sa.Float, nullable=False),
        sa.Column("y1", sa.Float, nullable=False),
        sa.Column("x2", sa.Float, nullable=False),
        sa.Column("y2", sa.Float, nullable=False),
        sa.Column("use_case", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_detections_camera_zone", "detections", ["camera_id", "zone_id"])
    op.create_index("ix_detections_processing_session_id", "detections", ["processing_session_id"])

    # ── tracks ────────────────────────────────────────────────────────────────
    op.create_table(
        "tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tracks_camera_zone_track_id", "tracks", ["camera_id", "zone_id", "track_id"])

    # ── observations ──────────────────────────────────────────────────────────
    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("frame_db_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("frames.id"), nullable=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inside_sink_zone", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("water_detected", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("soap_detected", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("hands_interacting", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("track_bbox", postgresql.JSONB, nullable=True),
        sa.Column("observation_type", sa.String(16), nullable=False, server_default="REAL"),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observations_camera_zone_track", "observations", ["camera_id", "zone_id", "track_id"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])

    # ── state_transitions ─────────────────────────────────────────────────────
    op.create_table(
        "state_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("previous_state", sa.String(64), nullable=False),
        sa.Column("new_state", sa.String(64), nullable=False),
        sa.Column("transition_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("sequence_valid", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_state_transitions_camera_zone_track", "state_transitions", ["camera_id", "zone_id", "track_id"])
    op.create_index("ix_state_transitions_correlation_id", "state_transitions", ["correlation_id"])

    # ── temporal_metrics ──────────────────────────────────────────────────────
    op.create_table(
        "temporal_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_state", sa.String(64), nullable=False),
        sa.Column("at_sink_duration", sa.Float, nullable=False, server_default="0"),
        sa.Column("water_on_duration", sa.Float, nullable=False, server_default="0"),
        sa.Column("soap_applied_duration", sa.Float, nullable=False, server_default="0"),
        sa.Column("washing_duration", sa.Float, nullable=False, server_default="0"),
        sa.Column("rinsing_duration", sa.Float, nullable=False, server_default="0"),
        sa.Column("sequence_valid", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("continuity_valid", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("observation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_gap_seconds", sa.Float, nullable=False, server_default="0"),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_temporal_metrics_camera_zone_track", "temporal_metrics", ["camera_id", "zone_id", "track_id"])
    op.create_index("ix_temporal_metrics_evaluated_at", "temporal_metrics", ["evaluated_at"])

    # ── compliance_rules ──────────────────────────────────────────────────────
    op.create_table(
        "compliance_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("use_case", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, server_default="1.0"),
        sa.Column("configuration", postgresql.JSONB, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rule_key", name="uq_compliance_rules_rule_key"),
    )

    # ── compliance_evaluations ────────────────────────────────────────────────
    op.create_table(
        "compliance_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("temporal_metrics_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("temporal_metrics.id"), nullable=True),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_rules.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(128), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_compliance_evaluations_camera_zone", "compliance_evaluations", ["camera_id", "zone_id"])
    op.create_index("ix_compliance_evaluations_result_time", "compliance_evaluations", ["result", "evaluated_at"])
    op.create_index("ix_compliance_evaluations_correlation_id", "compliance_evaluations", ["correlation_id"])

    # ── violations ────────────────────────────────────────────────────────────
    op.create_table(
        "violations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", sa.String(128), nullable=False),
        sa.Column("compliance_evaluation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_evaluations.id"), nullable=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_rules.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("violation_type", sa.String(128), nullable=False, server_default="HANDWASH_ABSENCE"),
        sa.Column("reason_code", sa.String(128), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="CONFIRMED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", name="uq_violations_group_id"),
    )
    op.create_index("ix_violations_group_id", "violations", ["group_id"])
    op.create_index("ix_violations_camera_zone_confirmed", "violations", ["camera_id", "zone_id", "confirmed_at"])

    # ── evidence_groups ───────────────────────────────────────────────────────
    op.create_table(
        "evidence_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", sa.String(128), nullable=False),
        sa.Column("violation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("violations.id"), nullable=True),
        sa.Column("processing_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_sessions.id"), nullable=True),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", name="uq_evidence_groups_group_id"),
    )
    op.create_index("ix_evidence_groups_group_id", "evidence_groups", ["group_id"])
    op.create_index("ix_evidence_groups_violation_id", "evidence_groups", ["violation_id"])

    # ── evidence_items ────────────────────────────────────────────────────────
    op.create_table(
        "evidence_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_groups.id"), nullable=False),
        sa.Column("frame_db_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("frames.id"), nullable=True),
        sa.Column("frame_id", sa.BigInteger, nullable=False),
        sa.Column("sequence_number", sa.Integer, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("thumbnail_reference", sa.String(1024), nullable=True),
        sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_items_evidence_group_id", "evidence_items", ["evidence_group_id"])

    # ── notifications ─────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("violation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("violations.id"), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False, server_default="DASHBOARD"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
    )
    op.create_index("ix_notifications_violation_id", "notifications", ["violation_id"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False, server_default="SYSTEM"),
        sa.Column("actor_id", sa.String(256), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(128), nullable=True),
        sa.Column("entity_id", sa.String(256), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("source", sa.String(256), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False, server_default="SUCCESS"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("evidence_items")
    op.drop_table("evidence_groups")
    op.drop_table("violations")
    op.drop_table("compliance_evaluations")
    op.drop_table("compliance_rules")
    op.drop_table("temporal_metrics")
    op.drop_table("state_transitions")
    op.drop_table("observations")
    op.drop_table("tracks")
    op.drop_table("detections")
    op.drop_table("frames")
    op.drop_table("processing_sessions")
    op.drop_table("ingestion_sessions")
    op.drop_table("zones")
    op.drop_table("streams")
    op.drop_table("cameras")
