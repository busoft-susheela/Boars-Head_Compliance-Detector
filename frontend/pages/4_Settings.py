"""Settings page — data source, refresh, and system configuration display."""
from __future__ import annotations

import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parent.parent
_ROOT     = _FRONTEND.parent
for p in (_FRONTEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st

st.set_page_config(page_title="Settings — CV Monitor", layout="wide", page_icon="⚙️")

from components.styles import inject_styles
from components.sidebar import render_sidebar

inject_styles()
render_sidebar()

st.markdown(
    '<div class="cv-header-title" style="margin-bottom:.1rem;">Settings</div>'
    '<div class="cv-header-sub" style="margin-bottom:1rem;">Dashboard configuration and system information</div>',
    unsafe_allow_html=True,
)

# ── Data source ────────────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Data Source</div>', unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])
with col1:
    src = st.radio(
        "Source",
        options=["Mock", "Live (API)"],
        index=0 if st.session_state.get("data_source", "Mock") == "Mock" else 1,
        help="Mock uses simulated data. Live connects to the FastAPI backend.",
    )
    st.session_state["data_source"] = src

with col2:
    if src == "Live (API)":
        url = st.text_input(
            "Backend URL",
            value=st.session_state.get("api_base_url", "http://localhost:8000"),
            help="The base URL of the running FastAPI backend.",
        )
        st.session_state["api_base_url"] = url
        st.markdown(
            f'<div class="cv-card" style="padding:.75rem;margin-top:.5rem;">'
            f'<div style="font-size:.72rem;color:var(--cv-text-secondary);">'
            f'Health endpoint: <code style="font-size:.68rem;">{url}/health</code></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="cv-card" style="padding:.75rem;">'
            '<div style="font-size:.72rem;color:var(--cv-text-secondary);">'
            'Mock data provides a realistic simulation of a single-camera handwash compliance system. '
            'State cycles through all handwash stages every 60 seconds.'
            '</div></div>',
            unsafe_allow_html=True,
        )

st.divider()

# ── Refresh settings ──────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Auto-Refresh</div>', unsafe_allow_html=True)

c1, c2 = st.columns([1, 2])
with c1:
    enabled = st.toggle("Enable auto-refresh", value=st.session_state.get("auto_refresh", True))
    st.session_state["auto_refresh"] = enabled
with c2:
    if enabled:
        interval = st.select_slider(
            "Refresh interval",
            options=[2, 5, 10, 30, 60],
            value=st.session_state.get("refresh_interval", 5),
            format_func=lambda x: f"{x}s",
        )
        st.session_state["refresh_interval"] = interval
        st.caption(f"Dashboard pages will reload every {interval} second(s).")
    else:
        st.caption("Auto-refresh is disabled. Use the 'Refresh Now' button in the sidebar.")

st.divider()

# ── System info ────────────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">System Information</div>', unsafe_allow_html=True)

st.markdown("""
<div class="cv-card">
  <div class="cv-info-grid">
    <div class="cv-info-label">Project</div>
    <div class="cv-info-value">BH_CV Compliance Detector</div>
    <div class="cv-info-label">Use Case</div>
    <div class="cv-info-value">Handwash compliance — meat-processing warehouse</div>
    <div class="cv-info-label">Deployment</div>
    <div class="cv-info-value">Single camera · Top-down · Handwash station</div>
    <div class="cv-info-label">Model</div>
    <div class="cv-info-value">YOLO11n (Ultralytics) — AGPL-3.0 licensed</div>
    <div class="cv-info-label">Backend</div>
    <div class="cv-info-value">FastAPI + threading (ingestion + inference + compliance workers)</div>
    <div class="cv-info-label">State Store</div>
    <div class="cv-info-value">InMemoryStateStore (per-person compliance state)</div>
    <div class="cv-info-label">Event Topics</div>
    <div class="cv-info-value cv-cell-mono">compliance.alert · evidence.capture · inference.detections · ingestion.frames</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Required backend contracts ─────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Required Backend Contracts (Not Yet Implemented)</div>', unsafe_allow_html=True)

contracts = [
    ("GET /api/cameras",                  "Per-camera status, ingestion metrics, compliance state",    "CameraStatusResponse[]"),
    ("GET /api/violations",               "Historical violations with filters",                        "ViolationResponse[]"),
    ("GET /api/violations/{group_id}/evidence", "Evidence payload (thumbnails) for a violation",      "EvidenceResponse"),
    ("GET /api/events/recent",            "Most recent N compliance events",                          "ViolationResponse[]"),
    ("GET /api/events/stream (SSE)",      "Real-time push of compliance_violation / evidence_available", "Server-Sent Events"),
]

rows = "".join(
    f"<tr><td class='cv-cell-mono'>{ep}</td><td>{desc}</td><td class='cv-cell-mono' style='font-size:.65rem'>{resp}</td></tr>"
    for ep, desc, resp in contracts
)

st.markdown(f"""
<table class="cv-vtable">
  <thead><tr><th>Endpoint</th><th>Purpose</th><th>Response</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
""", unsafe_allow_html=True)

st.info(
    "Until these endpoints are available, the dashboard uses the `/health` endpoint "
    "for system + camera status and returns empty lists for violations/evidence when in Live mode. "
    "Switch to **Mock** to see the full dashboard experience.",
    icon="ℹ️",
)

st.divider()

# ── Licensing note ────────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Licensing</div>', unsafe_allow_html=True)
st.warning(
    "YOLO11n ships under **AGPL-3.0** via the `ultralytics` package. "
    "Commercial / closed-source use of this detector in a warehouse compliance product "
    "requires either open-sourcing the project under AGPL-3.0 or an Ultralytics Enterprise License. "
    "Confirm the licensing path before deploying beyond internal testing.",
    icon="⚠️",
)
