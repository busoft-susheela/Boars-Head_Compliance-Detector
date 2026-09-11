"""CSS injection for the CV Compliance Monitor dashboard.

Call inject_styles() at the top of every page to apply the shared
dark-monitoring theme.  All custom HTML components reference classes
defined here.
"""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
/* ═══════════════════════════════════════════════════════════════════════════
   CV Compliance Monitor — Dashboard Theme
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── CSS Variables ── */
:root {
    --cv-bg-card:        #1a1f2e;
    --cv-bg-card-hover:  #1e2436;
    --cv-bg-inner:       rgba(255,255,255,0.03);
    --cv-border:         #2a3154;
    --cv-border-light:   rgba(42,49,84,0.5);
    --cv-accent:         #4c9be8;
    --cv-success:        #22c55e;
    --cv-warning:        #f59e0b;
    --cv-danger:         #ef4444;
    --cv-neutral:        #6b7280;
    --cv-text-primary:   #f1f5f9;
    --cv-text-secondary: #94a3b8;
    --cv-text-muted:     #64748b;
    --cv-radius:         10px;
    --cv-shadow:         0 4px 12px rgba(0,0,0,0.35);
}

/* ── Global ── */
.stApp {
    background: #0d1117 !important;
}
.block-container {
    padding-top: 1.25rem !important;
    max-width: 1380px !important;
}
section[data-testid="stSidebar"] {
    background: #0a0f1a !important;
    border-right: 1px solid var(--cv-border) !important;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label {
    color: var(--cv-text-secondary) !important;
}
#MainMenu, footer { visibility: hidden; }
hr { border-color: var(--cv-border) !important; margin: 0.75rem 0; }

/* ── Dashboard Header ── */
.cv-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1.25rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--cv-border);
}
.cv-header-left {}
.cv-header-title {
    font-size: 1.4rem;
    font-weight: 800;
    color: var(--cv-text-primary);
    letter-spacing: -0.01em;
}
.cv-header-sub {
    font-size: 0.78rem;
    color: var(--cv-text-secondary);
    margin-top: 0.1rem;
}
.cv-header-right {
    text-align: right;
}
.cv-system-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0.3rem 0.8rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-bottom: 0.3rem;
}
.cv-system-badge.badge-healthy {
    background: rgba(34,197,94,0.12);
    border: 1px solid rgba(34,197,94,0.3);
    color: var(--cv-success);
}
.cv-system-badge.badge-error {
    background: rgba(239,68,68,0.12);
    border: 1px solid rgba(239,68,68,0.3);
    color: var(--cv-danger);
}
.cv-header-updated {
    font-size: 0.7rem;
    color: var(--cv-text-muted);
}

/* ── Section Label ── */
.cv-section-label {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--cv-text-muted);
    margin: 0 0 0.75rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--cv-border);
}

/* ── KPI Cards ── */
.cv-kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1.25rem;
}
.cv-kpi {
    background: var(--cv-bg-card);
    border: 1px solid var(--cv-border);
    border-radius: var(--cv-radius);
    padding: 1.1rem 1rem 0.9rem;
    position: relative;
    overflow: hidden;
    box-shadow: var(--cv-shadow);
    transition: border-color 0.2s, transform 0.15s;
}
.cv-kpi:hover { border-color: var(--cv-accent); transform: translateY(-1px); }
.cv-kpi::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2.5px;
    border-radius: var(--cv-radius) var(--cv-radius) 0 0;
}
.cv-kpi.kpi-healthy::before  { background: var(--cv-success); }
.cv-kpi.kpi-warning::before  { background: var(--cv-warning); }
.cv-kpi.kpi-danger::before   { background: var(--cv-danger); }
.cv-kpi.kpi-neutral::before  { background: var(--cv-neutral); }
.cv-kpi.kpi-accent::before   { background: var(--cv-accent); }
.cv-kpi-icon {
    font-size: 0.85rem;
    color: var(--cv-text-muted);
    margin-bottom: 0.3rem;
}
.cv-kpi-value {
    font-size: 1.9rem;
    font-weight: 800;
    color: var(--cv-text-primary);
    line-height: 1.05;
    margin-bottom: 0.2rem;
    letter-spacing: -0.02em;
}
.cv-kpi-value.val-sm { font-size: 1.35rem; }
.cv-kpi-label {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--cv-text-secondary);
}
.cv-kpi-sub {
    font-size: 0.65rem;
    color: var(--cv-text-muted);
    margin-top: 0.2rem;
}
.cv-kpi-healthy  { color: var(--cv-success) !important; }
.cv-kpi-warning  { color: var(--cv-warning) !important; }
.cv-kpi-danger   { color: var(--cv-danger) !important; }

/* ── Status Dots ── */
.cv-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.cv-dot.dot-green  { background: var(--cv-success); box-shadow: 0 0 6px var(--cv-success); animation: cv-pulse 2s infinite; }
.cv-dot.dot-amber  { background: var(--cv-warning); box-shadow: 0 0 5px var(--cv-warning); animation: cv-pulse 2.5s infinite; }
.cv-dot.dot-red    { background: var(--cv-danger);  box-shadow: 0 0 8px var(--cv-danger);  animation: cv-pulse-fast 1.2s infinite; }
.cv-dot.dot-gray   { background: var(--cv-neutral); }
.cv-dot.dot-blue   { background: var(--cv-accent);  box-shadow: 0 0 5px var(--cv-accent);  animation: cv-pulse 2s infinite; }

@keyframes cv-pulse      { 0%,100%{opacity:1} 50%{opacity:.45} }
@keyframes cv-pulse-fast { 0%,100%{opacity:1; box-shadow:0 0 8px var(--cv-danger)} 50%{opacity:.6; box-shadow:0 0 16px var(--cv-danger)} }

/* ── Badges ── */
.cv-badge {
    display: inline-flex; align-items: center;
    padding: 0.18rem 0.55rem;
    border-radius: 9999px;
    font-size: 0.65rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.cv-badge-success { background: rgba(34,197,94,0.13);  color: var(--cv-success); border: 1px solid rgba(34,197,94,0.25); }
.cv-badge-warning { background: rgba(245,158,11,0.13); color: var(--cv-warning); border: 1px solid rgba(245,158,11,0.25); }
.cv-badge-danger  { background: rgba(239,68,68,0.13);  color: var(--cv-danger);  border: 1px solid rgba(239,68,68,0.25); }
.cv-badge-neutral { background: rgba(107,114,128,0.13);color: var(--cv-neutral); border: 1px solid rgba(107,114,128,0.25); }
.cv-badge-accent  { background: rgba(76,155,232,0.13); color: var(--cv-accent);  border: 1px solid rgba(76,155,232,0.25); }

/* ── Camera Cards ── */
.cv-camera-card {
    background: var(--cv-bg-card);
    border: 1px solid var(--cv-border);
    border-radius: var(--cv-radius);
    padding: 1.1rem 1.25rem;
    margin-bottom: 0.9rem;
    box-shadow: var(--cv-shadow);
    transition: border-color 0.2s;
}
.cv-camera-card:hover { border-color: var(--cv-accent); }
.cv-camera-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    padding-bottom: 0.7rem;
    margin-bottom: 0.75rem;
    border-bottom: 1px solid var(--cv-border-light);
}
.cv-camera-title { font-size: 0.95rem; font-weight: 700; color: var(--cv-text-primary); }
.cv-camera-zone  { font-size: 0.75rem; color: var(--cv-text-secondary); margin-top: 0.1rem; }
.cv-metrics-row {
    display: flex; flex-wrap: wrap; gap: 0.5rem;
    margin-bottom: 0.75rem;
}
.cv-metric-chip {
    background: var(--cv-bg-inner);
    border: 1px solid var(--cv-border-light);
    border-radius: 7px;
    padding: 0.35rem 0.65rem;
    min-width: 90px;
}
.cv-metric-chip-label {
    font-size: 0.58rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--cv-text-muted);
}
.cv-metric-chip-value {
    font-size: 0.88rem; font-weight: 600; color: var(--cv-text-primary);
    margin-top: 0.1rem;
}

/* ── Progress Bar ── */
.cv-progress-wrap {
    background: rgba(255,255,255,0.06);
    border-radius: 9999px; height: 5px; overflow: hidden;
}
.cv-progress-fill {
    height: 100%; border-radius: 9999px;
    transition: width 0.4s ease;
}
.cv-fill-success { background: var(--cv-success); }
.cv-fill-warning { background: var(--cv-warning); }
.cv-fill-danger  { background: var(--cv-danger); }
.cv-fill-accent  { background: var(--cv-accent); }
.cv-fill-gray    { background: var(--cv-neutral); }

/* ── Pipeline Stages ── */
.cv-pipeline {
    display: flex; flex-direction: column; gap: 0;
    padding: 0.25rem 0;
}
.cv-stage {
    display: flex; align-items: center; gap: 0.65rem;
    padding: 0.38rem 0.6rem;
    border-radius: 6px;
    transition: background 0.1s;
}
.cv-stage:hover { background: rgba(255,255,255,0.03); }
.cv-stage-dot-wrap { display:flex; flex-direction:column; align-items:center; width:16px; }
.cv-stage-connector { width:1px; height:14px; background: var(--cv-border); margin:1px 0; }
.cv-stage-name { font-size: 0.8rem; font-weight: 500; color: var(--cv-text-primary); flex:1; }
.cv-stage-meta { font-size: 0.7rem; color: var(--cv-text-muted); text-align:right; }
.cv-stage-fps  { font-size: 0.7rem; color: var(--cv-text-secondary); margin-left:0.3rem; }

/* ── Compliance State Display ── */
.cv-state-box {
    text-align: center;
    background: var(--cv-bg-card);
    border: 1px solid var(--cv-border);
    border-radius: var(--cv-radius);
    padding: 1.25rem 1rem;
    box-shadow: var(--cv-shadow);
}
.cv-state-chip {
    display: inline-block;
    padding: 0.25rem 0.9rem;
    border-radius: 9999px;
    font-size: 0.65rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.07em;
    margin-bottom: 0.5rem;
}
.cv-state-name {
    font-size: 1.55rem; font-weight: 900;
    letter-spacing: 0.04em;
    margin-bottom: 0.25rem;
}
.cv-state-UNKNOWN       { color: var(--cv-neutral); }
.cv-state-AT_SINK       { color: var(--cv-warning); }
.cv-state-WATER_ON      { color: #38bdf8; }
.cv-state-SOAP_APPLIED  { color: #a78bfa; }
.cv-state-WASHING       { color: var(--cv-accent); }
.cv-state-RINSING       { color: #06b6d4; }
.cv-state-COMPLETED     { color: var(--cv-success); }
.cv-state-duration {
    font-size: 0.8rem; color: var(--cv-text-secondary);
    margin-bottom: 0.75rem;
}
.cv-progress-label {
    display: flex; justify-content: space-between;
    font-size: 0.65rem; color: var(--cv-text-muted);
    margin-bottom: 0.3rem;
}

/* ── Compliance Result ── */
.cv-result {
    border-radius: var(--cv-radius);
    padding: 1.1rem 1rem;
    text-align: center;
}
.cv-result.result-pass {
    background: rgba(34,197,94,0.07);
    border: 1px solid rgba(34,197,94,0.2);
}
.cv-result.result-violation {
    background: rgba(239,68,68,0.07);
    border: 1px solid rgba(239,68,68,0.2);
}
.cv-result-icon { font-size: 1.6rem; margin-bottom: 0.3rem; }
.cv-result-title { font-size: 1rem; font-weight: 800; letter-spacing: 0.05em; }
.cv-result-desc  { font-size: 0.75rem; color: var(--cv-text-secondary); margin-top: 0.25rem; }

/* ── Info Grid (key-value pairs) ── */
.cv-info-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.35rem 1rem;
    margin-top: 0.75rem;
}
.cv-info-label {
    font-size: 0.68rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em;
    color: var(--cv-text-muted); white-space: nowrap;
    padding-top: 0.1rem;
}
.cv-info-value {
    font-size: 0.82rem; font-weight: 500;
    color: var(--cv-text-primary);
}

/* ── Violation Notification ── */
.cv-alert {
    display: flex; gap: 0.75rem; align-items: flex-start;
    background: rgba(239,68,68,0.07);
    border: 1px solid rgba(239,68,68,0.25);
    border-left: 3px solid var(--cv-danger);
    border-radius: var(--cv-radius);
    padding: 0.9rem 1rem;
    margin-bottom: 0.6rem;
    animation: cv-slide-in 0.3s ease;
}
@keyframes cv-slide-in { from{opacity:0;transform:translateX(-8px)} to{opacity:1;transform:none} }
.cv-alert-icon  { font-size: 1.1rem; flex-shrink:0; margin-top:0.05rem; }
.cv-alert-title { font-size: 0.85rem; font-weight: 700; color: var(--cv-danger); }
.cv-alert-body  { font-size: 0.77rem; color: var(--cv-text-secondary); margin-top: 0.2rem; line-height:1.5; }

/* ── Violation Table ── */
.cv-vtable {
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.25rem;
}
.cv-vtable th {
    padding: 0.5rem 0.75rem;
    font-size: 0.63rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.07em;
    color: var(--cv-text-muted);
    border-bottom: 1px solid var(--cv-border);
    text-align: left; white-space: nowrap;
}
.cv-vtable td {
    padding: 0.6rem 0.75rem;
    font-size: 0.8rem;
    color: var(--cv-text-secondary);
    border-bottom: 1px solid var(--cv-border-light);
    vertical-align: middle;
}
.cv-vtable tr:last-child td { border-bottom: none; }
.cv-vtable tr:hover td { background: rgba(255,255,255,0.018); }
.cv-cell-cam  { color: var(--cv-text-primary) !important; font-weight: 600; }
.cv-cell-viol { color: var(--cv-danger)  !important; font-weight: 600; }
.cv-cell-pass { color: var(--cv-success) !important; font-weight: 600; }
.cv-cell-mono { font-family: 'Courier New', monospace; font-size: 0.72rem; color: var(--cv-text-muted); }

/* ── State Timeline ── */
.cv-timeline { padding: 0.3rem 0; }
.cv-tl-row {
    display: flex; align-items: flex-start; gap: 0.75rem;
    padding: 0;
}
.cv-tl-line-col {
    display: flex; flex-direction: column; align-items: center;
    width: 22px; flex-shrink:0;
}
.cv-tl-circle {
    width: 22px; height: 22px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.58rem; font-weight: 800;
    flex-shrink: 0;
}
.cv-tl-circle.tl-active    { background: var(--cv-accent);   color:#fff; box-shadow:0 0 10px rgba(76,155,232,.45); }
.cv-tl-circle.tl-done      { background: var(--cv-success);  color:#fff; }
.cv-tl-circle.tl-idle      { background: rgba(107,114,128,.15); color: var(--cv-neutral); border:1px solid var(--cv-neutral); }
.cv-tl-connector { width:1px; height:22px; background: var(--cv-border); }
.cv-tl-content { padding: 0 0 0.9rem 0; flex:1; }
.cv-tl-state-name  { font-size: 0.82rem; font-weight: 700; color: var(--cv-text-primary); line-height:1.3; }
.cv-tl-state-meta  { font-size: 0.7rem; color: var(--cv-text-secondary); }
.cv-tl-state-dur   { font-size: 0.7rem; color: var(--cv-accent); font-weight: 600; }

/* ── Evidence Viewer ── */
.cv-evidence-strip {
    display: flex; gap: 0.6rem;
    overflow-x: auto; padding: 0.4rem 0 0.6rem;
}
.cv-ev-thumb { flex-shrink:0; text-align:center; }
.cv-ev-thumb img {
    border-radius: 6px;
    border: 1px solid var(--cv-border);
    display: block;
}
.cv-ev-thumb-time { font-size: 0.6rem; color: var(--cv-text-muted); margin-top:0.25rem; }

/* ── Card container ── */
.cv-card {
    background: var(--cv-bg-card);
    border: 1px solid var(--cv-border);
    border-radius: var(--cv-radius);
    padding: 1.1rem 1.25rem;
    margin-bottom: 0.9rem;
    box-shadow: var(--cv-shadow);
}

/* ── Streamlit component fixes ── */
[data-testid="stMetric"] label { color: var(--cv-text-muted) !important; font-size: 0.72rem !important; }
[data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.4rem !important; color: var(--cv-text-primary) !important; }
button[kind="secondary"] { border: 1px solid var(--cv-border) !important; }
</style>
"""


def inject_styles() -> None:
    """Inject the shared dashboard CSS.  Call once per page at the top."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ── HTML builder helpers ───────────────────────────────────────────────────────

def dot(color: str = "green") -> str:
    """Return an inline status dot HTML span."""
    return f'<span class="cv-dot dot-{color}"></span>'


def badge(text: str, kind: str = "neutral") -> str:
    return f'<span class="cv-badge cv-badge-{kind}">{text}</span>'


def progress_bar(pct: float, kind: str = "accent") -> str:
    """pct: 0–100."""
    clamped = max(0.0, min(100.0, pct))
    return (
        f'<div class="cv-progress-wrap">'
        f'<div class="cv-progress-fill cv-fill-{kind}" style="width:{clamped:.1f}%"></div>'
        f'</div>'
    )
