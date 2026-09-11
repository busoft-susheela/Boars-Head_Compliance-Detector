"""Violation detail view — renders inside a Streamlit modal/dialog or inline section."""
from __future__ import annotations

from typing import Optional

import streamlit as st

from components.styles import badge, progress_bar
from domain.models import EvidencePayload, EvidenceStatus, Violation


def render_violation_detail(
    violation: Violation,
    evidence: Optional[EvidencePayload],
    evidence_status: EvidenceStatus,
    on_close: Optional[callable] = None,
) -> None:
    """Render full violation detail including evidence thumbnails.

    Args:
        violation:       The violation to display.
        evidence:        EvidencePayload if loaded, None otherwise.
        evidence_status: Current evidence availability state.
        on_close:        Callback when user dismisses the detail.
    """
    v = violation

    # ── Header ───────────────────────────────────────────────────────────
    hdr_cols = st.columns([10, 1])
    with hdr_cols[0]:
        st.markdown(
            '<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
            'letter-spacing:.08em;color:var(--cv-danger);margin-bottom:.25rem;">⚠ VIOLATION DETAIL</div>',
            unsafe_allow_html=True,
        )
    with hdr_cols[1]:
        if on_close and st.button("✕", key="vd_close", help="Close"):
            on_close()

    wash_dur = f"{v.washing_duration_seconds:.1f}s" if v.washing_duration_seconds is not None else "—"
    req_dur  = f"{v.required_duration_seconds:.0f}s"

    st.markdown(f"""
    <div class="cv-result result-violation" style="text-align:left;margin-bottom:0.75rem;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <div style="font-size:0.8rem;font-weight:700;color:var(--cv-text-primary);">{v.camera_name}</div>
          <div style="font-size:0.72rem;color:var(--cv-text-secondary);">{v.zone_name}</div>
          <div style="font-size:0.68rem;color:var(--cv-text-muted);margin-top:0.1rem;">{v.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
        </div>
        <div style="text-align:right;">
          <div class="cv-result-icon">⚠</div>
          <div class="cv-result-title" style="color:var(--cv-danger);">VIOLATION</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Evidence section ─────────────────────────────────────────────────
    st.markdown('<div class="cv-section-label">Evidence</div>', unsafe_allow_html=True)

    if evidence_status == EvidenceStatus.LOADING:
        st.markdown(
            '<div class="cv-card" style="text-align:center;color:var(--cv-warning);padding:1.5rem;">'
            '⟳ Evidence loading…</div>',
            unsafe_allow_html=True,
        )
    elif evidence_status == EvidenceStatus.UNAVAILABLE or evidence is None:
        st.markdown(
            '<div class="cv-card" style="text-align:center;padding:1.5rem;">'
            '<div style="font-size:1.25rem;margin-bottom:.4rem;">⚠</div>'
            '<div style="color:var(--cv-warning);font-weight:600;font-size:.85rem;">Evidence Unavailable</div>'
            '<div style="color:var(--cv-text-muted);font-size:.73rem;margin-top:.25rem;">'
            'The violation event was received but evidence has not been retrieved.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    elif evidence and evidence.clip_bytes:
        _render_evidence_clip(evidence)
    elif evidence and evidence.frames:
        _render_evidence_strip(evidence)
    else:
        st.markdown(
            '<div class="cv-card" style="text-align:center;color:var(--cv-text-muted);padding:1.25rem;">'
            'No evidence frames available.</div>',
            unsafe_allow_html=True,
        )

    # ── Violation details ─────────────────────────────────────────────────
    st.markdown('<div class="cv-section-label" style="margin-top:0.75rem;">Details</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="cv-info-grid">
      <div class="cv-info-label">Reason</div>
      <div class="cv-info-value" style="color:var(--cv-danger);">{v.reason_display}</div>
      <div class="cv-info-label">Washing Duration</div>
      <div class="cv-info-value">{wash_dur}</div>
      <div class="cv-info-label">Required Duration</div>
      <div class="cv-info-value">{req_dur}</div>
      <div class="cv-info-label">Rule</div>
      <div class="cv-info-value cv-cell-mono">{v.rule_id}</div>
      <div class="cv-info-label">Group ID</div>
      <div class="cv-info-value cv-cell-mono">{v.group_id}</div>
      <div class="cv-info-label">Camera</div>
      <div class="cv-info-value">{v.camera_name} — {v.zone_name}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Washing progress visual ───────────────────────────────────────────
    if v.washing_duration_seconds is not None:
        pct = min(100.0, v.washing_duration_seconds / v.required_duration_seconds * 100)
        kind = "success" if pct >= 100 else "danger"
        st.markdown(f"""
        <div style="margin-top:0.75rem;">
          <div style="display:flex;justify-content:space-between;font-size:0.65rem;color:var(--cv-text-muted);margin-bottom:0.3rem;">
            <span>Washing progress</span>
            <span style="color:var(--cv-danger);font-weight:700;">{pct:.0f}% of required</span>
          </div>
          {progress_bar(pct, kind)}
        </div>
        """, unsafe_allow_html=True)


def _render_evidence_clip(evidence: EvidencePayload) -> None:
    """Display evidence as a video clip player with frame count info."""
    import io
    st.video(io.BytesIO(evidence.clip_bytes), format="video/x-msvideo")
    st.markdown(
        f'<div style="font-size:0.65rem;color:var(--cv-text-muted);margin-top:0.3rem;">'
        f'Evidence group: <span class="cv-cell-mono">{evidence.group_id}</span> · '
        f'{len(evidence.frames)} frame(s)</div>',
        unsafe_allow_html=True,
    )


def _render_evidence_strip(evidence: EvidencePayload) -> None:
    """Display evidence frames as a horizontal strip of thumbnails."""
    frames = evidence.frames[:10]  # cap at 10

    # Use Streamlit columns for image display
    cols = st.columns(min(len(frames), 4))
    for i, frame in enumerate(frames):
        col = cols[i % 4]
        with col:
            ts_str = frame.timestamp.strftime("%H:%M:%S")
            st.markdown(
                f'<div style="font-size:0.6rem;color:var(--cv-text-muted);margin-bottom:0.2rem;text-align:center;">{ts_str}</div>',
                unsafe_allow_html=True,
            )
            if frame.thumbnail_bytes:
                st.image(frame.thumbnail_bytes, use_container_width=True)
            else:
                st.markdown(
                    '<div style="background:var(--cv-bg-inner);border:1px solid var(--cv-border);'
                    'border-radius:6px;height:80px;display:flex;align-items:center;'
                    'justify-content:center;font-size:0.65rem;color:var(--cv-text-muted);">'
                    'No thumbnail</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<div style="font-size:0.6rem;color:var(--cv-text-muted);text-align:center;">Frame {frame.frame_id}</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<div style="font-size:0.65rem;color:var(--cv-text-muted);margin-top:0.4rem;">'
        f'Evidence group: <span class="cv-cell-mono">{evidence.group_id}</span> · '
        f'{len(evidence.frames)} frame(s)</div>',
        unsafe_allow_html=True,
    )
