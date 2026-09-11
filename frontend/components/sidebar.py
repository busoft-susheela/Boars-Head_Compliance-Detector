"""Shared sidebar component — renders data source selector on every page."""
from __future__ import annotations

import streamlit as st


def render_sidebar() -> None:
    """Render the shared sidebar: data source selector + refresh controls."""
    with st.sidebar:
        st.markdown(
            '<div style="font-size:1.05rem;font-weight:800;color:#f1f5f9;margin-bottom:0.15rem;">🎯 CV Compliance</div>'
            '<div style="font-size:0.7rem;color:#64748b;margin-bottom:1.25rem;">Handwash Monitoring</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown(
            '<div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
            'letter-spacing:.08em;color:#64748b;margin-bottom:.5rem;">Data Source</div>',
            unsafe_allow_html=True,
        )
        current = st.session_state.get("data_source", "Mock")
        st.session_state["data_source"] = st.radio(
            "Source", ["Mock", "Live (API)"],
            index=0 if current == "Mock" else 1,
            label_visibility="collapsed",
            key=f"sidebar_source_{_page_key()}",
        )
        if st.session_state["data_source"] == "Live (API)":
            st.session_state["api_base_url"] = st.text_input(
                "API URL",
                value=st.session_state.get("api_base_url", "http://localhost:8000"),
                key=f"sidebar_api_url_{_page_key()}",
            )

        st.divider()
        if st.button("Refresh Now", use_container_width=True, key=f"sidebar_refresh_{_page_key()}"):
            st.rerun()


def _page_key() -> str:
    """Return a short unique key based on the current script path to avoid Streamlit key conflicts."""
    import traceback
    for line in traceback.extract_stack():
        if "pages" in line.filename or "app.py" in line.filename:
            return line.filename.replace("\\", "/").split("/")[-1].replace(".py", "")
    return "main"
