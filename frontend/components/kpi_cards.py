"""KPI cards — top-of-dashboard summary metrics."""
from __future__ import annotations

import streamlit as st

from components.styles import badge, dot
from domain.models import SystemStatus


def render_kpi_cards(status: SystemStatus) -> None:
    """Render the six KPI cards using custom HTML."""

    # ── Derived values ───────────────────────────────────────────────────
    cam_frac    = f"{status.cameras_online} / {status.cameras_total}"
    proc_frac   = f"{status.processing_active} / {status.processing_total}"
    comp_pct    = f"{status.compliance_rate * 100:.1f}%"
    viol_str    = str(status.violations_today)
    fps_str     = f"{status.system_fps:.1f} FPS"

    sys_color   = "healthy" if status.healthy and status.backend_connected else "danger"
    sys_dot_col = "green"  if status.healthy and status.backend_connected else "red"
    sys_label   = "HEALTHY" if status.healthy and status.backend_connected else "DEGRADED"

    cam_color   = "healthy" if status.cameras_online == status.cameras_total else "warning"
    proc_color  = "healthy" if status.processing_active == status.processing_total else "warning"

    comp_color  = (
        "healthy" if status.compliance_rate >= 0.95
        else "warning" if status.compliance_rate >= 0.80
        else "danger"
    )
    viol_color  = "danger"  if status.violations_today > 0 else "healthy"
    fps_color   = "accent"

    cards = [
        _card_sys(sys_color, sys_dot_col, sys_label, status),
        _card_simple(cam_color,  cam_frac,  "Cameras",    "Online"),
        _card_simple(proc_color, proc_frac, "Processing", "Active"),
        _card_simple(comp_color, comp_pct,  "Compliance", "Rate Today"),
        _card_simple(viol_color, viol_str,  "Violations", "Today"),
        _card_simple(fps_color,  fps_str,   "Processing", "Throughput", val_sm=True),
    ]

    html = '<div class="cv-kpi-grid">' + "".join(cards) + '</div>'
    st.markdown(html, unsafe_allow_html=True)


def _card_sys(color: str, dot_color: str, label: str, status: SystemStatus) -> str:
    conn_label = "Connected" if status.backend_connected else "Disconnected"
    conn_dot   = "green" if status.backend_connected else "red"
    return f"""
    <div class="cv-kpi kpi-{color}">
        <div class="cv-kpi-icon">System Status</div>
        <div class="cv-kpi-value cv-kpi-{color}" style="font-size:1.15rem;letter-spacing:.04em;">
            <span class="cv-dot dot-{dot_color}" style="margin-right:6px"></span>{label}
        </div>
        <div class="cv-kpi-sub"><span class="cv-dot dot-{conn_dot}" style="margin-right:4px"></span>Backend {conn_label}</div>
    </div>
    """


def _card_simple(
    color: str,
    value: str,
    label: str,
    sub: str,
    val_sm: bool = False,
) -> str:
    val_class = "cv-kpi-value val-sm" if val_sm else "cv-kpi-value"
    color_class = f"cv-kpi-{color}" if color in ("healthy", "warning", "danger") else ""
    return f"""
    <div class="cv-kpi kpi-{color}">
        <div class="cv-kpi-icon">{label}</div>
        <div class="{val_class} {color_class}">{value}</div>
        <div class="cv-kpi-label">{sub}</div>
    </div>
    """
