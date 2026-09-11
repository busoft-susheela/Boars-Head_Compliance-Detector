"""Violations page — full history table with filters and detail view."""
from __future__ import annotations

import sys
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parent.parent
_ROOT     = _FRONTEND.parent
for p in (_FRONTEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import streamlit as st

st.set_page_config(page_title="Violations — CV Monitor", layout="wide", page_icon="⚠️")

from components.styles import inject_styles
from components.sidebar import render_sidebar
from components.violation_detail import render_violation_detail
from components.violation_table import render_violation_table
from domain.models import EvidenceStatus
from repository.api import ApiDashboardRepository
from repository.mock import MockDashboardRepository

inject_styles()
render_sidebar()


def _get_repo():
    src = st.session_state.get("data_source", "Mock")
    if src == "Live (API)":
        return ApiDashboardRepository(st.session_state.get("api_base_url", "http://localhost:8000"))
    return MockDashboardRepository()


def _handle_view(group_id: str) -> None:
    st.session_state["vp_selected"] = group_id
    st.rerun()


def _clear() -> None:
    st.session_state["vp_selected"] = None
    st.rerun()


# ── Initialise session state ──────────────────────────────────────────────────
if "vp_selected" not in st.session_state:
    st.session_state["vp_selected"] = None

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(
    '<div class="cv-header-title" style="margin-bottom:.1rem;">Violation History</div>'
    '<div class="cv-header-sub" style="margin-bottom:1rem;">All confirmed compliance violations with evidence</div>',
    unsafe_allow_html=True,
)

repo       = _get_repo()
violations = repo.get_violations()

# ── Summary strip ─────────────────────────────────────────────────────────────
total = len(violations)
cameras_affected = len({v.camera_id for v in violations})

st.markdown(f"""
<div style="display:flex;gap:1rem;margin-bottom:1rem;">
  <div class="cv-card" style="flex:1;text-align:center;padding:.75rem;">
    <div class="cv-kpi-value cv-kpi-danger" style="font-size:1.6rem;">{total}</div>
    <div class="cv-kpi-label">Total Violations Today</div>
  </div>
  <div class="cv-card" style="flex:1;text-align:center;padding:.75rem;">
    <div class="cv-kpi-value" style="font-size:1.6rem;">{cameras_affected}</div>
    <div class="cv-kpi-label">Cameras Affected</div>
  </div>
  <div class="cv-card" style="flex:1;text-align:center;padding:.75rem;">
    <div class="cv-kpi-value" style="font-size:1.6rem;">{len({v.zone_id for v in violations})}</div>
    <div class="cv-kpi-label">Zones Affected</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Violation detail (when selected) ─────────────────────────────────────────
selected_id = st.session_state.get("vp_selected")
if selected_id:
    v        = next((x for x in violations if x.group_id == selected_id), None)
    evidence = repo.get_evidence(selected_id) if v else None
    status   = EvidenceStatus.AVAILABLE if evidence else EvidenceStatus.UNAVAILABLE

    st.markdown('<div class="cv-section-label">Violation Detail</div>', unsafe_allow_html=True)
    with st.container():
        if v:
            render_violation_detail(
                violation=v,
                evidence=evidence,
                evidence_status=status,
                on_close=_clear,
            )
        else:
            st.warning("Violation not found.")
            if st.button("Back to list"):
                _clear()
    st.divider()

# ── Violations table ──────────────────────────────────────────────────────────
st.markdown('<div class="cv-section-label">Violations</div>', unsafe_allow_html=True)
render_violation_table(violations, on_view=_handle_view, show_filters=True)
