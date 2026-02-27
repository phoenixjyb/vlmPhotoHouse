# Architecture Documentation

## Current Reference

**[SYSTEM_ARCHITECTURE_2026-02-27.md](./SYSTEM_ARCHITECTURE_2026-02-27.md)**

This is the single authoritative architecture document. It covers:
- Multi-project topology and why the stack is split this way
- All AI components (LVFace, InsightFace/SCRFD, Qwen3-VL, RAM++, CLIP, LLMyTranslate)
- Backend architecture (FastAPI, inline worker, task queue, provider pattern)
- Frontend architecture (single-page vanilla JS)
- Database model and provenance tracking
- All pipeline flows (ingestion, captioning, face detection/recognition, tagging, search)
- Hardware topology (RTX 3090 / Quadro P2000 assignment)
- Startup topology and operational commands
- Current status snapshot (2026-02-27)
- Design rationale for every major choice
- Known gaps and issues

## Archive

Older topic-specific documents (ai-components.md, face-recognition.md, data-model.md,
hardware-architecture.md, etc.) and the previous SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md
are preserved in `./archive/` for historical reference.
