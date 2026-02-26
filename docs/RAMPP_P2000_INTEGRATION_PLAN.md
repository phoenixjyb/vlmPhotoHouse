# RAM++ Integration Plan (Windows + Quadro P2000)

## Objective

Add an image-tagging path (RAM++) to complement caption-derived tags, with explicit source provenance in DB and operational startup integration via `scripts/start-dev-multiproc.ps1`.

## Delivered in this iteration

1. **DB provenance fields for tags**
   - `asset_tags.source` (`cap|img|cap+img|manual|rule`)
   - `asset_tags.score` (float confidence)
   - `asset_tags.model` (provider/model label)
   - backward-compatible column migration added in `backend/app/dependencies.py`

2. **Source-aware tag upsert**
   - `backend/app/tagging.py` now merges source provenance:
     - caption + image -> `cap+img`
     - manual remains authoritative

3. **Image-tag provider path**
   - `backend/app/image_tag_service.py` added
   - supports `stub` and `http` provider modes

4. **Task + ingest + CLI integration**
   - new task type: `image_tag` in `backend/app/tasks.py`
   - optional ingest auto-enqueue controlled by `IMAGE_TAG_AUTO_ENQUEUE`
   - new CLI command: `image-tags-backfill` (enqueue pipeline tasks)

5. **Launcher integration**
   - `scripts/start-dev-multiproc.ps1` now supports RAM++ startup path:
     - configures backend image-tag env vars
     - validates image-tag provider wiring
     - starts RAM++ service pane/tab when enabled

6. **RAM++ service scaffold inside project**
   - `rampp/service.py` (FastAPI endpoint)
   - `rampp/adapter_rampp.py` (script-mode RAM++ adapter)
   - `rampp/setup-venv-rampp.ps1` / `rampp/install-rampp-p2000.ps1`
   - `rampp/requirements.txt`
   - `rampp/adapter_template.py` (minimal fallback template)
   - `rampp/README.md`

---

## Runtime topology

- Backend API/worker: `vlmPhotoHouse/backend`
- Caption service: existing `vlmCaptionModels` path
- Image-tag service (RAM++ path): `vlmPhotoHouse/rampp` on `http://127.0.0.1:8112`

Backend env knobs:
- `IMAGE_TAG_PROVIDER` = `http|stub|auto`
- `IMAGE_TAG_SERVICE_URL` = `http://127.0.0.1:8112`
- `IMAGE_TAG_MODEL` = `ram-plus`
- `IMAGE_TAG_AUTO_ENABLE` = `true|false`
- `IMAGE_TAG_AUTO_ENQUEUE` = `true|false`

---

## Provenance policy

Each asset-tag row carries source metadata:

- `cap`: caption-derived
- `img`: RAM++ image-derived
- `cap+img`: confirmed by both paths
- `manual`: user manually added
- `rule`: rule-based / dictionary pipeline

Merge rules:
- `manual` takes precedence (authoritative).
- `cap` + `img` merge to `cap+img`.
- higher confidence score is retained when re-upserting same tag.

---

## Quadro P2000 (Windows) third-party requirements

For real RAM++ inference (beyond scaffold/stub):

1. **Dedicated Python environment** for RAM++ (recommended Python 3.10/3.11).
2. **CUDA-enabled PyTorch build** compatible with installed NVIDIA driver.
3. **RAM/RAM++ code + model checkpoints** installed in that environment.
4. **Adapter script** that accepts `--image` / `--max-tags` and prints JSON tags.

Recommended wiring:
- `RAMPP_MODE=script`
- `RAMPP_TAG_SCRIPT=<your adapter path>` (default scaffold: `rampp/adapter_rampp.py`)
- `RAMPP_PYTHON_EXE=<rampp venv python.exe>` (default scaffold: `rampp/.venv-rampp/Scripts/python.exe`)
- `RAMPP_CUDA_DEVICE=1` (P2000 in this machine's PyTorch index order)
- `RAMPP_ALLOW_STUB_FALLBACK=true` until Torch+RAM+checkpoint are fully ready

---

## Rollout checklist

1. Create venv and base service deps:
   - `cd rampp`
   - `.\setup-venv-rampp.ps1`
2. Install RAM++ runtime stack:
   - `.\install-rampp-p2000.ps1` (or local wheelhouse/repo options)
3. Start RAM++ service and verify `/health`.
2. Set backend image-tag env vars and run:
   - `python -m app.cli validate-image-tag`
4. Enqueue backfill:
   - `python -m app.cli image-tags-backfill --apply --limit 0`
5. Validate tags via:
   - `GET /assets/{id}/tags` (`source`, `score`, `model` fields)
6. Compare retrieval quality and tune thresholds/tag limits.

---

## Next step (recommended)

Add a small evaluation script to compare retrieval quality before/after enabling `img` tags, then tune `max_tags`, source merge thresholds, and category suppression rules.
