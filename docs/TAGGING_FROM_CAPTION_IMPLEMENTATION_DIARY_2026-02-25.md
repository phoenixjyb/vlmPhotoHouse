# Tagging from Caption - Implementation Diary (2026-02-25)

## Overview

This diary records what was implemented for the tagging-from-caption feature in `vlmPhotoHouse`.

Primary goals delivered:
- Move from lightweight token tags to deterministic canonical caption tagging.
- Keep content tags constrained (`<= 8`) with type-aware selection.
- Support per-asset removal of auto tags and prevent immediate auto re-add.
- Expose the behavior in API, UI, CLI workflow, tests, and docs.

## Implemented Scope

### 1) Canonical caption tagging engine

Added `backend/app/tagging.py`:
- Canonical bilingual tag mapping (EN/ZH synonyms to canonical names).
- Deterministic candidate extraction and quota-based selection.
- Type-aware output to keep tags useful and consistent.
- Compatibility wrapper (`extract_caption_tags`) retained for existing callers.
- Fallback keyword extraction remains available if no canonical mapping is matched.

### 2) Auto-tag integration points

Updated:
- `backend/app/tasks.py` (caption task path)
- `backend/app/cli.py` (`captions-tags-backfill`)

Behavior:
- Caption-generated tags are derived via canonical extractor.
- Tag type metadata is passed through and stored.
- Existing backfill and automatic tagging workflows remain compatible.

### 3) Data model and persistence

Updated:
- `backend/app/db.py`
- `backend/app/dependencies.py`

Added table:
- `asset_tag_blocks` (per-asset blocked auto-tag IDs).

Purpose:
- When an auto-generated tag is removed, it can be blocked for that asset so background/automatic tagging does not re-add it.

### 4) API behavior

Updated `backend/app/main.py`:
- `POST /assets/{asset_id}/tags` now also clears matching block entries when manually adding the tag again.
- Added `DELETE /assets/{asset_id}/tags`:
  - removes selected tags from an asset;
  - optionally sets `block_auto=true` (default true) to block auto re-add.

### 5) UI behavior

Updated:
- `backend/app/ui/app.js`
- `backend/app/ui/styles.css`

Library inspector tag section now supports:
- Inline remove button on each tag chip.
- Calls tag delete API with `block_auto=true`.
- Refreshes tag list and shows user feedback toast.

### 6) Tests and validation

Added:
- `backend/tests/test_caption_tagging.py`

Coverage of new behavior:
- Canonical extraction/selection constraints.
- Remove + block flow.
- Manual re-add unblocks behavior.

Validation run:
- `pytest tests/test_caption_tagging.py tests/test_ingest_and_tasks.py -q` -> passed.
- Python compile checks and UI JS syntax checks also passed for changed files.

## Documentation updates completed

Updated:
- `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md`
- `README.md`
- `docs/user/user-guide.md`

These updates document:
- canonical tagging behavior,
- remove/block API and UI flow,
- operational usage examples.

## Commit reference

Implementation commit:
- `285fa4b0cc0b930b60525426397b57c6029c8900`
- Subject: `feat: add canonical caption tagging flow`

Files included in that commit:
- `backend/app/tagging.py`
- `backend/app/cli.py`
- `backend/app/db.py`
- `backend/app/dependencies.py`
- `backend/app/main.py`
- `backend/app/tasks.py`
- `backend/app/ui/app.js`
- `backend/app/ui/styles.css`
- `backend/tests/test_caption_tagging.py`
- `README.md`
- `docs/architecture/SYSTEM_ARCHITECTURE_CURRENT_2026-02-24.md`
- `docs/user/user-guide.md`

## Operational note

During implementation, active captioning services/jobs were not intentionally stopped or restarted.

## 2026-02-26 Verified Update

This section reflects a direct code-level recheck after additional integration work.

### Current implementation status (verified)

- Canonical extraction entrypoint in active use:
  - `extract_caption_tag_candidates(...)` in `backend/app/tagging.py`
- Backward-compatible wrapper still present:
  - `extract_caption_tags(...)` in `backend/app/tagging.py`
- Upsert path includes source/model/score metadata and block checks:
  - `upsert_asset_tags(...)` in `backend/app/tagging.py`

### Runtime integration points (verified)

- Caption worker auto-tag hook:
  - `backend/app/tasks.py` (`_handle_caption`)
  - env controls:
    - `CAPTION_AUTO_TAG_ENABLE`
    - `CAPTION_AUTO_TAG_MAX_TAGS`
    - `CAPTION_AUTO_TAG_TYPE`
- Image-tag fusion path:
  - `backend/app/tasks.py` (`_handle_image_tag`)
  - merges `cap` and `img` sources into `cap+img` where applicable.

### CLI/API/UI status (verified)

- Backfill command:
  - `python -m app.cli captions-tags-backfill ...`
  - implemented in `backend/app/cli.py`
- Optional image-tag backfill queue:
  - `python -m app.cli image-tags-backfill ...`
  - implemented in `backend/app/cli.py`
- Tag remove+block API:
  - `DELETE /assets/{asset_id}/tags` in `backend/app/main.py`
- Manual add unblocks previously blocked auto-tag:
  - `POST /assets/{asset_id}/tags` in `backend/app/main.py`
- UI remove action and refresh:
  - `backend/app/ui/app.js` + `backend/app/ui/styles.css`

### Data model status (verified)

- `asset_tags` includes:
  - `source`, `score`, `model`
- `asset_tag_blocks` exists and is created for backward-compatible DBs by:
  - `backend/app/dependencies.py`

### Test coverage status (verified)

- `backend/tests/test_caption_tagging.py` currently covers:
  - canonical quota selection
  - remove + block behavior
  - manual re-add unblock behavior
  - cap/img source merge behavior
