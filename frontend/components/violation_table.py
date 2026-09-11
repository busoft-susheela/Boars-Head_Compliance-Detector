"""Violation history table with inline filters."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from domain.models import EvidenceStatus, Violation


def render_violation_table(
    violations: list[Violation],
    on_view: Optional[callable] = None,
    show_filters: bool = True,
    compact: bool = False,
) -> None:
    """Render a sortable, filterable violation history table.

    Args:
        violations: List of violations (newest first).
        on_view:    Callback when 'View' button is clicked; receives group_id.
        show_filters: Whether to show filter controls.
        compact:    If True, renders a condensed table without extra controls.
    """
    if not violations:
        st.markdown(
            '<div class="cv-card" style="text-align:center;color:var(--cv-text-muted);padding:2rem;">'
            'No violations recorded.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    filtered = violations

    if show_filters and not compact:
        # ── Filters ──────────────────────────────────────────────────────
        f1, f2, f3 = st.columns([2, 2, 2])
        with f1:
            cameras = sorted({v.camera_name for v in violations})
            cam_filter = st.selectbox("Camera", ["All"] + cameras, key="vt_cam")
        with f2:
            zones = sorted({v.zone_name for v in violations})
            zone_filter = st.selectbox("Zone", ["All"] + zones, key="vt_zone")
        with f3:
            reasons = sorted({v.reason for v in violations})
            reason_labels = {v.reason: v.reason_display for v in violations}
            reason_opts = {v.reason: v.reason_display[:45] + "…" if len(v.reason_display) > 45 else v.reason_display for v in violations}
            reason_filter = st.selectbox(
                "Reason",
                ["All"] + list(dict.fromkeys(r for r in reason_opts.values())),
                key="vt_reason",
            )

        if cam_filter != "All":
            filtered = [v for v in filtered if v.camera_name == cam_filter]
        if zone_filter != "All":
            filtered = [v for v in filtered if v.zone_name == zone_filter]
        if reason_filter != "All":
            filtered = [v for v in filtered if v.reason_display.startswith(reason_filter[:30])]

        st.markdown(
            f'<div style="font-size:0.72rem;color:var(--cv-text-muted);margin-bottom:0.5rem;">'
            f'Showing {len(filtered)} of {len(violations)} violations</div>',
            unsafe_allow_html=True,
        )

    if not filtered:
        st.markdown(
            '<div style="text-align:center;color:var(--cv-text-muted);padding:1.5rem;">No violations match the current filters.</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Table header ─────────────────────────────────────────────────────
    header = """
    <table class="cv-vtable">
      <thead>
        <tr>
          <th>Time</th>
          <th>Camera</th>
          <th>Zone</th>
          <th>Reason</th>
          <th>Wash / Required</th>
          <th>Evidence</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
    """

    rows = []
    view_targets: dict[str, Violation] = {}

    for v in filtered:
        ts_str   = v.timestamp.strftime("%H:%M:%S")
        wash_str = f"{v.washing_duration_seconds:.1f}s" if v.washing_duration_seconds is not None else "—"
        req_str  = f"{v.required_duration_seconds:.0f}s"
        reason   = v.reason_display[:50] + "…" if len(v.reason_display) > 50 else v.reason_display

        ev_str = {
            EvidenceStatus.AVAILABLE:   '<span style="color:var(--cv-success)">✓ Available</span>',
            EvidenceStatus.LOADING:     '<span style="color:var(--cv-warning)">⟳ Loading</span>',
            EvidenceStatus.UNAVAILABLE: '<span style="color:var(--cv-neutral)">— N/A</span>',
        }.get(v.evidence_status, "—")

        view_targets[v.group_id] = v

        rows.append(f"""
        <tr>
          <td>{ts_str}</td>
          <td class="cv-cell-cam">{v.camera_name}</td>
          <td>{v.zone_name}</td>
          <td class="cv-cell-viol">{reason}</td>
          <td>{wash_str} / {req_str}</td>
          <td>{ev_str}</td>
          <td data-group-id="{v.group_id}"><button-placeholder-{v.group_id}></button-placeholder-{v.group_id}></td>
        </tr>
        """)

    st.markdown(header + "".join(rows) + "</tbody></table>", unsafe_allow_html=True)

    # Streamlit buttons cannot be inside raw HTML — render them below the table
    # using a column per row approach for compact or hidden buttons in compact mode.
    if on_view is not None and not compact:
        st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)
        for v in filtered:
            cols = st.columns([6, 1])
            with cols[1]:
                if st.button("View", key=f"view_{v.group_id}", use_container_width=True):
                    on_view(v.group_id)


def render_recent_events_table(violations: list[Violation], on_view: Optional[callable] = None) -> None:
    """Compact recent events list — used on main dashboard."""
    if not violations:
        st.markdown(
            '<div style="text-align:center;color:var(--cv-text-muted);padding:1.25rem;font-size:0.8rem;">'
            'No recent violations.</div>',
            unsafe_allow_html=True,
        )
        return

    header = """
    <table class="cv-vtable">
      <thead>
        <tr>
          <th>Time</th>
          <th>Camera</th>
          <th>Zone</th>
          <th>Result</th>
          <th>Duration</th>
        </tr>
      </thead>
      <tbody>
    """
    rows = []
    for v in violations[:8]:
        ts_str   = v.timestamp.strftime("%H:%M:%S")
        wash_str = f"{v.washing_duration_seconds:.1f}s" if v.washing_duration_seconds else "—"
        rows.append(f"""
        <tr>
          <td>{ts_str}</td>
          <td class="cv-cell-cam">{v.camera_name}</td>
          <td>{v.zone_name}</td>
          <td class="cv-cell-viol">⚠ VIOLATION</td>
          <td>{wash_str}</td>
        </tr>
        """)

    st.markdown(header + "".join(rows) + "</tbody></table>", unsafe_allow_html=True)

    if on_view is not None:
        st.markdown('<div style="height:0.4rem"></div>', unsafe_allow_html=True)
        btn_cols = st.columns(len(violations[:8]))
        for i, v in enumerate(violations[:8]):
            with btn_cols[i]:
                if st.button("View", key=f"rec_{v.group_id}", help=f"View violation {v.group_id}"):
                    on_view(v.group_id)
