"""Compliance state display — current handwash state, duration, and progress."""
from __future__ import annotations

import streamlit as st

from components.styles import progress_bar
from domain.models import ComplianceStateInfo, HandwashState, HANDWASH_STATE_ORDER

_STATE_CHIP_CSS = {
    HandwashState.UNKNOWN:      ("neutral", "No activity"),
    HandwashState.AT_SINK:      ("warning", "At Sink"),
    HandwashState.WATER_ON:     ("accent",  "Water On"),
    HandwashState.SOAP_APPLIED: ("accent",  "Soap Applied"),
    HandwashState.WASHING:      ("accent",  "Washing"),
    HandwashState.RINSING:      ("accent",  "Rinsing"),
    HandwashState.COMPLETED:    ("success", "Completed"),
}

_STATE_COLOR = {
    HandwashState.UNKNOWN:      "gray",
    HandwashState.AT_SINK:      "warning",
    HandwashState.WATER_ON:     "accent",
    HandwashState.SOAP_APPLIED: "accent",
    HandwashState.WASHING:      "accent",
    HandwashState.RINSING:      "accent",
    HandwashState.COMPLETED:    "success",
}

_PROGRESS_KIND = {
    HandwashState.UNKNOWN:      "gray",
    HandwashState.AT_SINK:      "warning",
    HandwashState.WATER_ON:     "accent",
    HandwashState.SOAP_APPLIED: "accent",
    HandwashState.WASHING:      "accent",
    HandwashState.RINSING:      "success",
    HandwashState.COMPLETED:    "success",
}


def render_compliance_state(info: ComplianceStateInfo) -> None:
    """Render the current compliance state with progress and timeline."""
    state      = info.current_state
    chip_kind, chip_label = _STATE_CHIP_CSS.get(state, ("neutral", state.value))
    color      = _STATE_COLOR.get(state, "gray")
    prog_kind  = _PROGRESS_KIND.get(state, "gray")

    # Progress is only meaningful during WASHING
    if state == HandwashState.WASHING:
        pct = min(100.0, info.state_duration_seconds / info.required_duration_seconds * 100)
        pct_display = f"{pct:.0f}%"
        progress_label = f"{info.state_duration_seconds:.1f}s / {info.required_duration_seconds:.0f}s required"
    elif state in (HandwashState.RINSING, HandwashState.COMPLETED):
        pct = 100.0
        pct_display = "100%"
        progress_label = f"Washing complete ({info.washing_duration_seconds:.1f}s)"
    else:
        pct = 0.0
        pct_display = "—"
        progress_label = "Washing not yet started"

    bar_html = progress_bar(pct, prog_kind)

    html = f"""
    <div class="cv-state-box" style="margin-bottom:0.5rem;">
      <div>
        <span class="cv-state-chip cv-badge cv-badge-{chip_kind}">{chip_label}</span>
      </div>
      <div class="cv-state-name cv-state-{state.value}">{state.value.replace('_', ' ')}</div>
      <div class="cv-state-duration">
        Duration in state: <strong>{info.state_duration_seconds:.1f}s</strong>
        &nbsp;·&nbsp; Observations: {info.observation_count:,}
        {'&nbsp;·&nbsp; <span style="color:var(--cv-danger)">Sequence invalid</span>' if not info.sequence_valid else ''}
      </div>
      <div class="cv-progress-label">
        <span>{progress_label}</span>
        <span style="font-weight:700;color:var(--cv-text-primary);">{pct_display}</span>
      </div>
      {bar_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_state_timeline(info: ComplianceStateInfo) -> None:
    """Render the ordered state transition timeline for a given camera state."""
    current_idx = HANDWASH_STATE_ORDER.index(info.current_state) if info.current_state in HANDWASH_STATE_ORDER else 0

    rows = []
    for i, state in enumerate(HANDWASH_STATE_ORDER):
        is_active    = i == current_idx
        is_done      = i < current_idx
        is_last      = i == len(HANDWASH_STATE_ORDER) - 1

        circle_cls = "tl-active" if is_active else ("tl-done" if is_done else "tl-idle")
        icon       = "✓" if is_done else ("▶" if is_active else str(i + 1))
        connector  = "" if is_last else '<div class="cv-tl-connector"></div>'

        if is_active:
            dur_html = f'<div class="cv-tl-state-dur">{info.state_duration_seconds:.1f}s elapsed</div>'
        elif is_done:
            dur_html = '<div class="cv-tl-state-dur" style="color:var(--cv-success);">✓ Done</div>'
        else:
            dur_html = '<div class="cv-tl-state-meta">Pending</div>'

        rows.append(f"""
        <div class="cv-tl-row">
          <div class="cv-tl-line-col">
            <div class="cv-tl-circle {circle_cls}">{icon}</div>
            {connector}
          </div>
          <div class="cv-tl-content">
            <div class="cv-tl-state-name">{state.value.replace('_', ' ')}</div>
            {dur_html}
          </div>
        </div>
        """)

    html = '<div class="cv-timeline">' + "".join(rows) + '</div>'
    st.markdown(html, unsafe_allow_html=True)
