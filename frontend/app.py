"""CV Compliance Monitor — Main Dashboard.

Entry point: streamlit run frontend/app.py

Ensure the project root is on PYTHONPATH so backend packages resolve:
    PYTHONPATH=. streamlit run frontend/app.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup — must come before any local imports ───────────────────────────
_FRONTEND = Path(__file__).resolve().parent
_ROOT     = _FRONTEND.parent
for p in (_FRONTEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st

st.set_page_config(
    page_title="CV Compliance Monitor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.styles import inject_styles
from components.sidebar import render_sidebar
from components.camera_card import render_camera_card
from components.kpi_cards import render_kpi_cards
from components.notifications import register_notification, render_notifications
from components.violation_detail import render_violation_detail
from components.violation_table import render_recent_events_table
from domain.models import EvidenceStatus
from repository.api import ApiDashboardRepository
from repository.mock import MockDashboardRepository

inject_styles()


# ── Repository selection ──────────────────────────────────────────────────────

def _get_repo():
    mode = st.session_state.get("data_source", "Mock")
    if mode == "Live (API)":
        base = st.session_state.get("api_base_url", "http://localhost:8000")
        return ApiDashboardRepository(base_url=base)
    return MockDashboardRepository()


# ── Session state initialisation ──────────────────────────────────────────────

def _init_session() -> None:
    defaults = {
        "data_source":        "Mock",
        "api_base_url":       "http://localhost:8000",
        "auto_refresh":       True,
        "refresh_interval":   5,
        "cv_notifications":   [],
        "selected_violation": None,
        "seen_groups":        set(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div style="font-size:1.05rem;font-weight:800;color:#f1f5f9;margin-bottom:0.15rem;">🎯 CV Compliance</div>'
            '<div style="font-size:0.7rem;color:#64748b;margin-bottom:1.25rem;">Handwash Monitoring</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown('<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin-bottom:.5rem;">Data Source</div>', unsafe_allow_html=True)
        st.session_state["data_source"] = st.radio(
            "Source", ["Mock", "Live (API)"],
            index=0 if st.session_state["data_source"] == "Mock" else 1,
            label_visibility="collapsed",
        )
        if st.session_state["data_source"] == "Live (API)":
            st.session_state["api_base_url"] = st.text_input(
                "API URL", value=st.session_state["api_base_url"],
                label_visibility="visible",
            )

        st.divider()

        st.markdown('<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin-bottom:.5rem;">Auto-Refresh</div>', unsafe_allow_html=True)
        st.session_state["auto_refresh"] = st.toggle(
            "Enabled", value=st.session_state["auto_refresh"]
        )
        if st.session_state["auto_refresh"]:
            st.session_state["refresh_interval"] = st.select_slider(
                "Interval (s)", options=[2, 5, 10, 30, 60],
                value=st.session_state["refresh_interval"],
            )

        st.divider()

        if st.button("Refresh Now", use_container_width=True):
            st.rerun()

        st.divider()

        # Navigation hint
        st.markdown(
            '<div style="font-size:0.65rem;color:#64748b;">'
            'Navigate using the pages in the sidebar above.</div>',
            unsafe_allow_html=True,
        )


# ── Selected violation detail (inline) ────────────────────────────────────────

def _show_violation_detail(group_id: str) -> None:
    repo = _get_repo()
    violations = repo.get_violations()
    v = next((x for x in violations if x.group_id == group_id), None)
    if v is None:
        return

    evidence = repo.get_evidence(group_id)
    status   = EvidenceStatus.AVAILABLE if evidence else EvidenceStatus.UNAVAILABLE

    with st.container():
        render_violation_detail(
            violation=v,
            evidence=evidence,
            evidence_status=status,
            on_close=lambda: _clear_selected(),
        )
    st.divider()


def _clear_selected() -> None:
    st.session_state["selected_violation"] = None
    st.rerun()


def _handle_view(group_id: str) -> None:
    st.session_state["selected_violation"] = group_id
    st.rerun()


# ── Main dashboard ────────────────────────────────────────────────────────────

def main() -> None:
    _init_session()
    render_sidebar()

    repo = _get_repo()

    # ── Load data ─────────────────────────────────────────────────────────
    with st.spinner(""):
        system   = repo.get_system_status()
        cameras  = repo.get_cameras()
        recent   = repo.get_recent_events(limit=8)

    # ── Check for new violations → notifications ──────────────────────────
    seen = st.session_state["seen_groups"]
    for v in recent:
        if v.group_id not in seen:
            seen.add(v.group_id)
            register_notification(v)

    # ── Dashboard header ─────────────────────────────────────────────────
    sys_badge_cls = "badge-healthy" if system.healthy and system.backend_connected else "badge-error"
    sys_badge_lbl = "● System Healthy" if system.healthy and system.backend_connected else "● System Degraded"
    updated_str   = system.last_updated.strftime("%H:%M:%S UTC") if system.last_updated else "—"

    st.markdown(f"""
    <div class="cv-header">
      <div class="cv-header-left">
        <div class="cv-header-title">CV Compliance Monitoring</div>
        <div class="cv-header-sub">Handwash Compliance · Single Camera Deployment</div>
      </div>
      <div class="cv-header-right">
        <div><span class="cv-system-badge {sys_badge_cls}">{sys_badge_lbl}</span></div>
        <div class="cv-header-updated">Last updated: {updated_str}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI Cards ────────────────────────────────────────────────────────
    render_kpi_cards(system)

    # ── Active notifications ──────────────────────────────────────────────
    render_notifications(on_view=_handle_view)

    # ── Violation detail (inline when selected) ──────────────────────────
    selected = st.session_state.get("selected_violation")
    if selected:
        st.markdown('<div class="cv-section-label" style="margin-top:0.25rem;">Violation Detail</div>', unsafe_allow_html=True)
        _show_violation_detail(selected)

    # ── Camera / Zone status ──────────────────────────────────────────────
    st.markdown('<div class="cv-section-label">Camera & Zone Status</div>', unsafe_allow_html=True)

    if not cameras:
        st.markdown(
            '<div class="cv-card" style="text-align:center;color:var(--cv-text-muted);padding:2rem;">'
            'No cameras found.</div>',
            unsafe_allow_html=True,
        )
    else:
        for cam in cameras:
            render_camera_card(cam)

    # ── Recent violations ─────────────────────────────────────────────────
    st.markdown('<div class="cv-section-label" style="margin-top:0.5rem;">Recent Violations</div>', unsafe_allow_html=True)
    render_recent_events_table(recent, on_view=_handle_view)

    # ── Auto-refresh ─────────────────────────────────────────────────────
    if st.session_state.get("auto_refresh"):
        interval = st.session_state.get("refresh_interval", 5)
        st.markdown(
            f'<div style="font-size:0.65rem;color:var(--cv-text-muted);text-align:right;margin-top:1rem;">'
            f'Auto-refreshing every {interval}s</div>',
            unsafe_allow_html=True,
        )
        time.sleep(interval)
        st.rerun()


if __name__ == "__main__":
    main()
else:
    main()
