"""Cameras page — per-camera detail with pipeline and compliance state."""
from __future__ import annotations

import sys
import time
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parent.parent
_ROOT     = _FRONTEND.parent
for p in (_FRONTEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st

st.set_page_config(page_title="Cameras — CV Monitor", layout="wide", page_icon="📷")

from components.styles import inject_styles, dot, badge, progress_bar
from components.sidebar import render_sidebar
from components.compliance_state import render_compliance_state, render_state_timeline
from components.pipeline_view import render_pipeline
from domain.models import CameraConnectionStatus, HandwashState, ProcessingStatus, StreamSourceType
from repository.api import ApiDashboardRepository
from repository.mock import MockDashboardRepository

inject_styles()
render_sidebar()


def _get_repo():
    src = st.session_state.get("data_source", "Mock")
    if src == "Live (API)":
        return ApiDashboardRepository(st.session_state.get("api_base_url", "http://localhost:8000"))
    return MockDashboardRepository()


def _fmt_s(s: float) -> str:
    s = int(s)
    m, sec = divmod(s, 60)
    h, m   = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


# ── Page header ───────────────────────────────────────────────────────────────

st.markdown(
    '<div class="cv-header-title" style="margin-bottom:.1rem;">Camera Monitoring</div>'
    '<div class="cv-header-sub" style="margin-bottom:1rem;">Per-camera ingestion, pipeline, and compliance state</div>',
    unsafe_allow_html=True,
)

repo    = _get_repo()
cameras = repo.get_cameras()

if not cameras:
    st.warning("No cameras available from the selected data source.")
    st.stop()

# ── Camera selector (multi-camera future-proofing) ────────────────────────────
cam_names  = {c.camera_id: f"{c.name} — {c.zone_name}" for c in cameras}
selected   = st.selectbox("Select camera", options=list(cam_names.keys()), format_func=lambda k: cam_names[k])
cam        = next((c for c in cameras if c.camera_id == selected), cameras[0])

st.divider()

# ── Camera header ─────────────────────────────────────────────────────────────
conn_dot   = "green" if cam.connection == CameraConnectionStatus.ONLINE else "red"
conn_badge = "success" if cam.connection == CameraConnectionStatus.ONLINE else "danger"
proc_badge = "success" if cam.processing == ProcessingStatus.PROCESSING else "neutral"

st.markdown(f"""
<div class="cv-camera-card">
  <div class="cv-camera-header">
    <div>
      <div class="cv-camera-title" style="font-size:1.1rem;">{cam.name}</div>
      <div class="cv-camera-zone" style="font-size:0.8rem;">{cam.zone_name} · Zone {cam.zone_id}</div>
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
      {badge(cam.connection.value, conn_badge)}
      {badge(cam.processing.value, proc_badge)}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Two-column detail ─────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="medium")

# Left: Ingestion detail
with left:
    st.markdown('<div class="cv-section-label">Video Ingestion</div>', unsafe_allow_html=True)
    ing = cam.ingestion

    if ing.source_type == StreamSourceType.VIDEO and ing.video_duration_seconds:
        pos  = ing.video_position_seconds or 0.0
        dur  = ing.video_duration_seconds
        pct  = min(100.0, pos / dur * 100)
        src_label = f"Video · {ing.video_filename or 'file'}"
        progress_html = f"""
        <div style="margin-top:0.5rem;">
          <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--cv-text-muted);margin-bottom:.3rem;">
            <span>{_fmt_s(pos)}</span><span>{_fmt_s(dur)}</span>
          </div>
          {progress_bar(pct, 'accent')}
          <div style="font-size:.65rem;color:var(--cv-text-muted);margin-top:.25rem;text-align:right;">{pct:.1f}%</div>
        </div>
        """
    else:
        src_label    = "RTSP · Live"
        elapsed      = ing.elapsed_seconds or 0.0
        progress_html = f"""
        <div style="margin-top:.5rem;display:flex;align-items:center;gap:8px;">
          <span class="cv-dot dot-green"></span>
          <span style="font-size:.8rem;font-weight:700;color:var(--cv-success);">LIVE</span>
          <span style="font-size:.72rem;color:var(--cv-text-muted);">Elapsed {_fmt_s(elapsed)}</span>
        </div>
        """

    st.markdown(f"""
    <div class="cv-card">
      <div class="cv-info-grid">
        <div class="cv-info-label">Connection</div>
        <div class="cv-info-value"><span class="cv-dot dot-{conn_dot}" style="margin-right:5px"></span>{cam.connection.value}</div>
        <div class="cv-info-label">Source</div>
        <div class="cv-info-value">{src_label}</div>
        <div class="cv-info-label">FPS</div>
        <div class="cv-info-value">{ing.fps:.2f}</div>
        <div class="cv-info-label">Frames Received</div>
        <div class="cv-info-value">{ing.frames_received:,}</div>
        <div class="cv-info-label">Frames Processed</div>
        <div class="cv-info-value">{ing.frames_processed:,}</div>
        <div class="cv-info-label">Dropped Frames</div>
        <div class="cv-info-value" style="{'color:var(--cv-danger)' if ing.dropped_frames > 100 else ''}">
          {ing.dropped_frames:,}
          {' &nbsp;<span style="font-size:.65rem;color:var(--cv-danger);">▲ HIGH</span>' if ing.dropped_frames > 100 else ''}
        </div>
        <div class="cv-info-label">Last Frame</div>
        <div class="cv-info-value">{ing.last_frame_at.strftime('%H:%M:%S UTC') if ing.last_frame_at else '—'}</div>
      </div>
      {progress_html}
    </div>
    """, unsafe_allow_html=True)

# Right: Compliance state
with right:
    st.markdown('<div class="cv-section-label">Compliance State</div>', unsafe_allow_html=True)
    if cam.compliance_state:
        render_compliance_state(cam.compliance_state)
        with st.expander("State Transition Timeline"):
            render_state_timeline(cam.compliance_state)
    else:
        st.markdown(
            '<div class="cv-card" style="text-align:center;color:var(--cv-text-muted);padding:2rem;">'
            'Compliance state not available — live backend required.</div>',
            unsafe_allow_html=True,
        )

# ── Pipeline ──────────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="cv-section-label">Processing Pipeline</div>', unsafe_allow_html=True)

st.markdown("""
<div style="font-size:.72rem;color:var(--cv-text-muted);margin-bottom:.75rem;">
Each stage shows real-time throughput and average processing latency.
</div>
""", unsafe_allow_html=True)

render_pipeline(cam.pipeline_stages)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if st.session_state.get("auto_refresh", True):
    interval = st.session_state.get("refresh_interval", 5)
    st.markdown(
        f'<div style="font-size:.65rem;color:var(--cv-text-muted);text-align:right;margin-top:.75rem;">Auto-refresh every {interval}s</div>',
        unsafe_allow_html=True,
    )
    time.sleep(interval)
    st.rerun()
