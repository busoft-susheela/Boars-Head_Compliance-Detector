"""System Health page — ingestion, inference, queue, and compliance metrics."""
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

st.set_page_config(page_title="System Health — CV Monitor", layout="wide", page_icon="🩺")

from components.styles import inject_styles, progress_bar, badge
from components.sidebar import render_sidebar
from repository.api import ApiDashboardRepository
from repository.mock import MockDashboardRepository

inject_styles()
render_sidebar()


def _get_repo():
    src = st.session_state.get("data_source", "Mock")
    if src == "Live (API)":
        return ApiDashboardRepository(st.session_state.get("api_base_url", "http://localhost:8000"))
    return MockDashboardRepository()


def _metric_card(label: str, value: str, sub: str = "", color: str = "primary") -> str:
    col_style = {
        "primary":  "var(--cv-text-primary)",
        "success":  "var(--cv-success)",
        "warning":  "var(--cv-warning)",
        "danger":   "var(--cv-danger)",
        "muted":    "var(--cv-text-muted)",
    }.get(color, "var(--cv-text-primary)")
    return f"""
    <div class="cv-card" style="text-align:center;padding:1rem;">
      <div style="font-size:1.5rem;font-weight:800;color:{col_style};line-height:1;">{value}</div>
      <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--cv-text-secondary);margin-top:.3rem;">{label}</div>
      {'<div style="font-size:.62rem;color:var(--cv-text-muted);margin-top:.15rem;">' + sub + '</div>' if sub else ''}
    </div>
    """


# ── Page header ───────────────────────────────────────────────────────────────

st.markdown(
    '<div class="cv-header-title" style="margin-bottom:.1rem;">System Health</div>'
    '<div class="cv-header-sub" style="margin-bottom:1rem;">Ingestion · Inference · Queue · Compliance metrics</div>',
    unsafe_allow_html=True,
)

repo   = _get_repo()
system = repo.get_system_status()
cameras = repo.get_cameras()
cam = cameras[0] if cameras else None

# ── Overall health ────────────────────────────────────────────────────────────
is_healthy = system.healthy and system.backend_connected
health_col = "success" if is_healthy else "danger"
health_lbl = "● HEALTHY" if is_healthy else "● DEGRADED"

connected_lbl  = "Connected"    if system.backend_connected else "Disconnected"
connected_col  = "success"      if system.backend_connected else "danger"

st.markdown(f"""
<div class="cv-card" style="display:flex;align-items:center;gap:1.5rem;padding:.9rem 1.25rem;margin-bottom:.9rem;">
  <div>
    <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--cv-text-muted);margin-bottom:.2rem;">Overall Status</div>
    <div style="font-size:1.15rem;font-weight:800;color:var(--cv-{health_col});">{health_lbl}</div>
  </div>
  <div style="width:1px;height:40px;background:var(--cv-border);"></div>
  <div>
    <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--cv-text-muted);margin-bottom:.2rem;">Backend</div>
    <div style="font-size:.85rem;font-weight:600;color:var(--cv-{connected_col});">{connected_lbl}</div>
  </div>
  <div style="width:1px;height:40px;background:var(--cv-border);"></div>
  <div>
    <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--cv-text-muted);margin-bottom:.2rem;">Last Updated</div>
    <div style="font-size:.85rem;color:var(--cv-text-secondary);">{system.last_updated.strftime('%H:%M:%S UTC') if system.last_updated else '—'}</div>
  </div>
  <div style="width:1px;height:40px;background:var(--cv-border);"></div>
  <div>
    <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--cv-text-muted);margin-bottom:.2rem;">Uptime</div>
    <div style="font-size:.85rem;color:var(--cv-text-secondary);">{int(system.uptime_seconds // 3600):02d}:{int((system.uptime_seconds % 3600) // 60):02d}:{int(system.uptime_seconds % 60):02d}</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Ingestion metrics ─────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Video Ingestion</div>', unsafe_allow_html=True)

if cam:
    ing = cam.ingestion
    drop_pct = (ing.dropped_frames / ing.frames_received * 100) if ing.frames_received else 0.0
    drop_col = "danger" if drop_pct > 5 else ("warning" if drop_pct > 1 else "success")

    cols = st.columns(5)
    metrics = [
        ("FPS",            f"{ing.fps:.2f}",            "frames per second", "primary"),
        ("Frames Received",f"{ing.frames_received:,}",  "total ingested",    "primary"),
        ("Frames Processed",f"{ing.frames_processed:,}","after sampling",    "primary"),
        ("Dropped Frames", f"{ing.dropped_frames:,}",   f"{drop_pct:.1f}% drop rate", drop_col),
        ("Connection",     ing.connection.value,         "",                  "success" if cam.connection.value == "ONLINE" else "danger"),
    ]
    for i, (lbl, val, sub, col) in enumerate(metrics):
        with cols[i]:
            st.markdown(_metric_card(lbl, val, sub, col), unsafe_allow_html=True)

    # Drop-rate progress bar
    st.markdown(f"""
    <div style="margin-top:.25rem;">
      <div style="display:flex;justify-content:space-between;font-size:.63rem;color:var(--cv-text-muted);margin-bottom:.25rem;">
        <span>Frame drop rate</span>
        <span style="color:var(--cv-{drop_col});font-weight:700;">{drop_pct:.2f}%</span>
      </div>
      {progress_bar(drop_pct, drop_col)}
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("No camera data available.")

st.divider()

# ── Inference metrics ─────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Inference Pipeline</div>', unsafe_allow_html=True)

if cam and cam.pipeline_stages:
    yolo = next((s for s in cam.pipeline_stages if "YOLO" in s.name or "Detection" in s.name), None)
    cols2 = st.columns(4)
    with cols2[0]:
        fps_val = f"{yolo.throughput_fps:.1f}" if yolo and yolo.throughput_fps else "—"
        st.markdown(_metric_card("Inference FPS", fps_val, "detections/sec", "primary"), unsafe_allow_html=True)
    with cols2[1]:
        lat_val = f"{yolo.avg_latency_ms:.0f} ms" if yolo and yolo.avg_latency_ms else "—"
        lat_col = "danger" if yolo and yolo.avg_latency_ms and yolo.avg_latency_ms > 500 else "primary"
        st.markdown(_metric_card("Avg Latency", lat_val, "per frame", lat_col), unsafe_allow_html=True)
    with cols2[2]:
        active_stages = sum(1 for s in cam.pipeline_stages if s.status.value == "ok")
        st.markdown(_metric_card("Active Stages", f"{active_stages}/{len(cam.pipeline_stages)}", "pipeline", "success" if active_stages == len(cam.pipeline_stages) else "warning"), unsafe_allow_html=True)
    with cols2[3]:
        err_stages = sum(1 for s in cam.pipeline_stages if s.status.value in ("error", "degraded"))
        st.markdown(_metric_card("Error Stages", str(err_stages), "degraded or error", "danger" if err_stages else "success"), unsafe_allow_html=True)

st.divider()

# ── Compliance metrics ────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Compliance Engine</div>', unsafe_allow_html=True)

rate_pct = system.compliance_rate * 100
rate_col = "success" if rate_pct >= 95 else ("warning" if rate_pct >= 80 else "danger")

cols3 = st.columns(4)
with cols3[0]:
    st.markdown(_metric_card("Compliance Rate", f"{rate_pct:.1f}%", "events today", rate_col), unsafe_allow_html=True)
with cols3[1]:
    st.markdown(_metric_card("Violations Today", str(system.violations_today), "confirmed", "danger" if system.violations_today > 0 else "success"), unsafe_allow_html=True)
with cols3[2]:
    st.markdown(_metric_card("Cameras Online", f"{system.cameras_online}/{system.cameras_total}", "active", "success" if system.cameras_online == system.cameras_total else "warning"), unsafe_allow_html=True)
with cols3[3]:
    st.markdown(_metric_card("Processing Active", f"{system.processing_active}/{system.processing_total}", "workers", "success" if system.processing_active == system.processing_total else "warning"), unsafe_allow_html=True)

st.markdown(f"""
<div style="margin-top:.5rem;">
  <div style="display:flex;justify-content:space-between;font-size:.63rem;color:var(--cv-text-muted);margin-bottom:.25rem;">
    <span>Compliance rate</span>
    <span style="color:var(--cv-{rate_col});font-weight:700;">{rate_pct:.1f}%</span>
  </div>
  {progress_bar(rate_pct, rate_col)}
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Backend connectivity note ──────────────────────────────────────────────────
src = st.session_state.get("data_source", "Mock")
if src == "Mock":
    st.info(
        "Using mock data. Switch to **Live (API)** in the sidebar to connect to the running FastAPI backend at `/health`.",
        icon="ℹ️",
    )
else:
    if not system.backend_connected:
        st.error(
            f"Cannot reach backend at {st.session_state.get('api_base_url', 'http://localhost:8000')}. "
            "Ensure the FastAPI server is running.",
            icon="🔴",
        )
    else:
        st.success("Backend connected and responding.", icon="✅")

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if st.session_state.get("auto_refresh", True):
    interval = st.session_state.get("refresh_interval", 5)
    st.markdown(
        f'<div style="font-size:.65rem;color:var(--cv-text-muted);text-align:right;margin-top:.75rem;">Auto-refresh every {interval}s</div>',
        unsafe_allow_html=True,
    )
    time.sleep(interval)
    st.rerun()
