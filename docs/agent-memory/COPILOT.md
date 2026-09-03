# Copilot Notes

This repo has stale docs in several older files. Use this folder first.

Read:

1. `docs\agent-memory\PROJECT_TRUTH.md`
2. `docs\agent-memory\STATUS_AND_PRODUCT_READINESS_2026-04-07.md`

Operational basics:

- app runtime Python: `vlmPhotoHouse\.venv\Scripts\python.exe`
- data root: `E:\VLM_DATA`
- originals root: `E:\01_INCOMING`
- API/UI: `http://127.0.0.1:8002` and `/ui`
- active providers on 2026-04-07: InsightFace detect, LVFace subprocess embed, Qwen2VL subprocess caption

Do not start from the assumption that the HTTP caption server on `8102` is the main active runtime path.
