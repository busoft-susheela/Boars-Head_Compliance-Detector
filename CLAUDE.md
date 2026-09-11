# CLAUDE.md

Guidance for Claude (or any developer) working in this repository.

## Project overview

**BH_CV_Compliance_Detector** is a computer-vision compliance monitoring system for a meat-processing warehouse. It watches surveillance camera footage and automatically flags staff hygiene/PPE compliance violations —
currently: incomplete handwashing.

**Current scope (do not expand without being asked):** one fixed
surveillance camera, mounted with a top-down angle over the handwash station, capturing the handwash action only. This is a single-camera and single-station deployment. Keep
that in mind before adding complexity aimed at scale this project doesn't have yet.

The detection model is already trained and its weights are checked in under `artifacts/` — this project does include a training pipeline.
Treat the model as a fixed input, not something this codebase builds.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Streamlit 
| Backend | Python, FastAPI |
| Detection model | YOLO11n (Ultralytics, nano variant), weights in `artifacts/` |
| Compliance logic | Custom state-transition + temporal-analyzer rule engine (no ML) |
| Notification | Triggered by the rule engine's output, channel(s) TBD |

See `skills.md` for a deeper breakdown of each layer's responsibilities.

## ⚠️ Licensing note — read before touching the model

YOLO11 (the `n` variant included) ships under **AGPL-3.0** by default via
the `ultralytics` package. Commercial, closed-source use of this
detector — which a warehouse compliance product is — requires either:

1. Open-sourcing this entire project under AGPL-3.0, or
2. An Ultralytics **Enterprise License**.

This applies even though the model was trained on private/custom data —
it's the code/architecture that's licensed, not just the pretrained
weights. Confirm which path this project is taking before shipping past
internal testing. See https://www.ultralytics.com/license.

## Architecture

The pipeline is event-driven: a frame comes in, gets run through the model, the result is evaluated against a compliance rule, and a confirmed violation triggers a notification. 

| Component | Sub-component | Description | Maps to in this project |
|---|---|---|---|
| **StreamIngestionService** | RTSPConnector | Opens the RTSP stream, reads frames one at a time | Connects to the single handwash-station camera |
| | FrameSampler | Throttles native camera FPS down to a target processing FPS | Keeps inference load bounded on a single-camera setup |
| | (orchestrator) | Runs read → sample → publish for one camera | One instance is sufficient at current scope |

## Project structure (expected — adjust as the code is actually built)

```
BH_CV_Compliance_Detector/
├── CLAUDE.md
├── skills.md
├── artifacts/              trained YOLO11n weights (already produced — not built here)
├── backend/                FastAPI app: ingestion, inference, rule engine, notification
│   └── app/
├── frontend/                Streamlit app: live view, alerts, evidence review
├── config/                  zone/rule config (trigger class, min_seconds, debounce_frames)
└── evidence/                 LocalDiskEvidenceStore output, one folder per group_id
```

