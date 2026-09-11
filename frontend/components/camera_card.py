"""Camera status card — renders one camera's live operational state."""
from __future__ import annotations

import streamlit as st

from components.compliance_state import render_compliance_state
from components.pipeline_view import render_pipeline
from components.styles import badge, dot, progress_bar
from domain.models import (
    CameraConnectionStatus,
    CameraStatus,
    HandwashState,
    ProcessingStatus,
    StreamSourceType,
)


# ── Status → visual mappings ──────────────────────────────────────────────────

_CONN_DOT = {
    CameraConnectionStatus.ONLINE:       "green",
    CameraConnectionStatus.CONNECTING:   "amber",
    CameraConnectionStatus.DEGRADED:     "amber",
    CameraConnectionStatus.DISCONNECTED: "red",
    CameraConnectionStatus.ERROR:        "red",
    CameraConnectionStatus.STOPPED:      "gray",
}
_CONN_BADGE = {
    CameraConnectionStatus.ONLINE:       "success",
    CameraConnectionStatus.CONNECTING:   "warning",
    CameraConnectionStatus.DEGRADED:     "warning",
    CameraConnectionStatus.DISCONNECTED: "danger",
    CameraConnectionStatus.ERROR:        "danger",
    CameraConnectionStatus.STOPPED:      "neutral",
}
_PROC_DOT = {
    ProcessingStatus.STARTING:      "amber",
    ProcessingStatus.WARMING_UP:    "amber",
    ProcessingStatus.PROCESSING:    "green",
    ProcessingStatus.BACKPRESSURED: "amber",
    ProcessingStatus.ERROR:         "red",
    ProcessingStatus.STOPPED:       "gray",
}


def render_camera_card(cam: CameraStatus, expanded: bool = False) -> None:
    """Render a full camera status card with optional expandable detail."""
    conn_dot   = _CONN_DOT.get(cam.connection, "gray")
    conn_badge = _CONN_BADGE.get(cam.connection, "neutral")
    proc_dot   = _PROC_DOT.get(cam.processing, "gray")
    ing        = cam.ingestion

    # ── Card header HTML ─────────────────────────────────────────────────
    header_html = f"""
    <div class="cv-camera-card">
      <div class="cv-camera-header">
        <div>
          <div class="cv-camera-title">{cam.name}</div>
          <div class="cv-camera-zone">{cam.zone_name}</div>
        </div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end;">
          {badge(cam.connection.value, conn_badge)}
          {badge(cam.processing.value, "success" if cam.processing == ProcessingStatus.PROCESSING else "neutral")}
        </div>
      </div>

      <div class="cv-metrics-row">
        {_metric_chip("Connection", f'<span class="cv-dot dot-{conn_dot}" style="margin-right:5px"></span>{cam.connection.value}')}
        {_metric_chip("Source", ing.video_filename or ing.source_type.value)}
        {_metric_chip("FPS", f'{ing.fps:.1f}')}
        {_metric_chip("Frames Received", f'{ing.frames_received:,}')}
        {_metric_chip("Frames Processed", f'{ing.frames_processed:,}')}
        {_metric_chip("Dropped", f'{ing.dropped_frames:,}')}
        {_metric_chip("Inference", f'<span class="cv-dot dot-{proc_dot}" style="margin-right:5px"></span>{cam.processing.value}')}
      </div>

      {_ingestion_progress(cam)}
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

    # ── Compliance state (native Streamlit for progress bar interaction) ─
    if cam.compliance_state:
        with st.container():
            render_compliance_state(cam.compliance_state)

    # ── Expandable pipeline detail ────────────────────────────────────────
    with st.expander("Pipeline stages", expanded=expanded):
        render_pipeline(cam.pipeline_stages)


def _metric_chip(label: str, value: str) -> str:
    return f"""
    <div class="cv-metric-chip">
      <div class="cv-metric-chip-label">{label}</div>
      <div class="cv-metric-chip-value">{value}</div>
    </div>
    """


def _ingestion_progress(cam: CameraStatus) -> str:
    ing = cam.ingestion
    if ing.source_type == StreamSourceType.VIDEO and ing.video_duration_seconds:
        pos  = ing.video_position_seconds or 0.0
        dur  = ing.video_duration_seconds
        pct  = min(100.0, pos / dur * 100) if dur else 0.0
        pos_s = _fmt_seconds(pos)
        dur_s = _fmt_seconds(dur)
        bar_html = progress_bar(pct, "accent")
        return f"""
        <div style="margin-top:0.6rem;">
          <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
            <span style="font-size:0.65rem;color:var(--cv-text-muted);">Video Progress</span>
            <span style="font-size:0.65rem;color:var(--cv-text-secondary);">{pos_s} / {dur_s} &nbsp; {pct:.0f}%</span>
          </div>
          {bar_html}
        </div>
        """
    elif ing.source_type == StreamSourceType.RTSP:
        elapsed = _fmt_seconds(ing.elapsed_seconds or 0.0)
        return f"""
        <div style="margin-top:0.5rem;display:flex;align-items:center;gap:8px;">
          <span class="cv-dot dot-green"></span>
          <span style="font-size:0.75rem;font-weight:700;color:var(--cv-success);">LIVE</span>
          <span style="font-size:0.72rem;color:var(--cv-text-muted);">Elapsed: {elapsed}</span>
        </div>
        """
    return ""


def _fmt_seconds(s: float) -> str:
    s = int(s)
    m, sec = divmod(s, 60)
    h, m   = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"
