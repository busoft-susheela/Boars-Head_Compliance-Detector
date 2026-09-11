"""Real-time violation notification banners.

In Streamlit, true push notifications require a polling loop (st.rerun) or
SSE/WebSocket integration.  This module:
  1. Renders pending notifications from st.session_state.
  2. Uses st.toast() for transient pop-up alerts on newly detected violations.
  3. Provides a function to register a new violation for notification.

The notification lifecycle:
  register_notification(violation)  → adds to session state queue
  render_notifications()            → shows banners + dismisses old ones
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

from domain.models import Violation

_NOTIFICATION_TTL_SECONDS = 300  # show notifications for 5 minutes


def register_notification(violation: Violation) -> None:
    """Add a violation notification to the session state queue."""
    if "cv_notifications" not in st.session_state:
        st.session_state["cv_notifications"] = []

    # Deduplicate by group_id
    existing = {n["group_id"] for n in st.session_state["cv_notifications"]}
    if violation.group_id not in existing:
        st.session_state["cv_notifications"].append({
            "group_id":   violation.group_id,
            "camera":     violation.camera_name,
            "zone":       violation.zone_name,
            "timestamp":  violation.timestamp,
            "reason":     violation.reason_display,
            "added_at":   datetime.now(timezone.utc),
        })
        # Streamlit toast for transient pop-up
        ts_str = violation.timestamp.strftime("%H:%M:%S")
        st.toast(
            f"⚠ Violation — {violation.camera_name} / {violation.zone_name} at {ts_str}",
            icon="🚨",
        )


def render_notifications(on_view: Optional[callable] = None) -> None:
    """Render all active notification banners from session state."""
    if "cv_notifications" not in st.session_state:
        return

    now = datetime.now(timezone.utc)
    active = [
        n for n in st.session_state["cv_notifications"]
        if (now - n["added_at"]).total_seconds() < _NOTIFICATION_TTL_SECONDS
    ]
    st.session_state["cv_notifications"] = active

    if not active:
        return

    st.markdown('<div class="cv-section-label">Active Alerts</div>', unsafe_allow_html=True)

    to_dismiss = []
    for n in active:
        ts_str = n["timestamp"].strftime("%H:%M:%S")
        cols   = st.columns([10, 1, 1])

        with cols[0]:
            st.markdown(f"""
            <div class="cv-alert">
              <div class="cv-alert-icon">⚠</div>
              <div>
                <div class="cv-alert-title">Compliance Violation</div>
                <div class="cv-alert-body">
                  <strong>{n['camera']}</strong> · {n['zone']}<br>
                  {n['reason']}<br>
                  <span style="color:var(--cv-text-muted)">{ts_str}</span>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        with cols[1]:
            if on_view and st.button("View", key=f"notif_view_{n['group_id']}", use_container_width=True):
                on_view(n["group_id"])

        with cols[2]:
            if st.button("✕", key=f"notif_dismiss_{n['group_id']}", help="Dismiss", use_container_width=True):
                to_dismiss.append(n["group_id"])

    if to_dismiss:
        st.session_state["cv_notifications"] = [
            n for n in active if n["group_id"] not in to_dismiss
        ]
        st.rerun()
