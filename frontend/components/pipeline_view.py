"""Pipeline stage visualization."""
from __future__ import annotations

import streamlit as st

from domain.models import PipelineStage, PipelineStageStatus

_STATUS_DOT = {
    PipelineStageStatus.OK:       "green",
    PipelineStageStatus.DEGRADED: "amber",
    PipelineStageStatus.ERROR:    "red",
    PipelineStageStatus.STOPPED:  "gray",
    PipelineStageStatus.STARTING: "amber",
}

_STATUS_LABEL = {
    PipelineStageStatus.OK:       "Running",
    PipelineStageStatus.DEGRADED: "Degraded",
    PipelineStageStatus.ERROR:    "Error",
    PipelineStageStatus.STOPPED:  "Stopped",
    PipelineStageStatus.STARTING: "Starting",
}


def render_pipeline(stages: list[PipelineStage]) -> None:
    """Render a vertical pipeline diagram with status, FPS, and latency."""
    rows = []
    for i, stage in enumerate(stages):
        is_last = i == len(stages) - 1
        dot_col = _STATUS_DOT.get(stage.status, "gray")
        label   = _STATUS_LABEL.get(stage.status, stage.status.value)

        meta_parts = []
        if stage.throughput_fps is not None:
            meta_parts.append(f"{stage.throughput_fps:.1f} FPS")
        if stage.avg_latency_ms is not None:
            meta_parts.append(f"avg {stage.avg_latency_ms:.0f} ms")
        if stage.error_message:
            meta_parts.append(f"⚠ {stage.error_message}")
        meta_str = " · ".join(meta_parts) if meta_parts else label

        connector = "" if is_last else '<div class="cv-stage-connector"></div>'

        rows.append(f"""
        <div class="cv-stage">
          <div class="cv-stage-dot-wrap">
            <span class="cv-dot dot-{dot_col}"></span>
            {connector}
          </div>
          <span class="cv-stage-name">{stage.name}</span>
          <span class="cv-stage-meta">{meta_str}</span>
        </div>
        """)

    html = '<div class="cv-pipeline">' + "".join(rows) + '</div>'
    st.markdown(html, unsafe_allow_html=True)
