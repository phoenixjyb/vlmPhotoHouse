# User Guide

This guide is intentionally short for now and points to the current production UI flow.

## Access

- Open: `http://127.0.0.1:8002/ui`
- Language: switch EN/ZH from the top bar.

## Main Tabs

- `Library`: browse assets, open inspector, read/edit captions.
- `People`: review faces, assign identities, run person cleanup workflows.
- `Map`: view geo-tagged assets.
- `Tasks`: monitor queue and system usage (CPU/RAM/GPU).
- `Admin`: health checks and maintenance actions.

## Recommended Workflow

1. Ingest new media from `E:\01_INCOMING`.
2. Wait for caption/face/embedding tasks to finish.
3. Review unassigned faces in `People`.
4. Correct labels manually where needed.
5. Run auto-assign propagation from the latest manual labels.

## Notes

- Captions are generated locally through the caption service (`qwen3-vl` path).
- All production data is expected on `E:\VLM_DATA`.
