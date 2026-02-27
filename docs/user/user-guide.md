# User Guide

This guide is intentionally short for now and points to the current production UI flow.

## Access

- Open: `http://127.0.0.1:8002/ui`
- Language: switch EN/ZH from the top bar.

## Voice Command (Read-only)

- Use the **Voice Command** button in the top bar for short voice queries.
- Current kid-friendly example:
  - EN: `show me the photos of chuan`
  - ZH: `显示 chuan 的照片`
- Result: UI opens the `People` tab and loads the same person-assets gallery you get from clicking that person manually.
- Safety: mutating intents (rename/merge/delete/assign, etc.) are still blocked by the voice command orchestrator in current phase.

## Main Tabs

- `Library`: browse assets, open inspector, read/edit captions, and add/remove tags.
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

## Manual Commands (Operator Tutorial)

Run these in PowerShell from repo root:

```powershell
cd .\backend
$py = ".\.venv\Scripts\python.exe"
```

### 1) Ingest and check scan status

```powershell
& $py -m app.cli ingest-scan E:\01_INCOMING
& $py -m app.cli ingest-status E:\01_INCOMING
```

### 2) Caption pipeline

Queue/continue caption jobs:

```powershell
& $py -m app.cli captions-backfill --profile balanced --max-variants 1 --limit 0
```

Clean stub captions, then backfill:

```powershell
& $py -m app.cli captions-clean-stubs --root E:\01_INCOMING --apply
& $py -m app.cli captions-backfill --profile balanced --max-variants 1 --limit 0
& $py -m app.cli captions-tags-backfill --root E:\01_INCOMING --max-tags 8 --apply
& $py -m app.cli image-tags-backfill --root E:\01_INCOMING --max-tags 8 --apply
```

Tag extraction is canonical and capped (`<=8`), and removed auto tags can be blocked per asset.
When RAM++ image tagging is enabled, tag source metadata is persisted (`cap`, `img`, `cap+img`, `manual`, `rule`).

### 2.1) Manual tag remove/block (API)

View current tags for asset 123:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8002/assets/123/tags"
```

Remove tag ID 45 from asset 123 and block auto re-add:

```powershell
Invoke-RestMethod -Method Delete -Uri "http://127.0.0.1:8002/assets/123/tags" -ContentType "application/json" -Body '{"tag_ids":[45],"block_auto":true}'
```

Manual add clears the block for that tag:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8002/assets/123/tags" -ContentType "application/json" -Body '{"names":["indoor play area"]}'
```

### 3) Pause or resume Chinese translation

Pause:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'captions-backfill-zh' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Resume:

```powershell
Start-Process -FilePath $py -WorkingDirectory (Get-Location).Path `
  -ArgumentList @('-m','app.cli','captions-backfill-zh','--apply','--overwrite-existing-zh','--timeout-sec','120')
```

### 4) Face detection and auto-label

Re-detect only assets currently missing faces:

```powershell
& $py -m app.cli faces-redetect-enqueue --root E:\01_INCOMING --only-without-faces --limit 0
```

Auto-assign from manual labels:

```powershell
& $py -m app.cli faces-auto-assign --reference-manual-only --include-dnn-assigned --apply --limit 0
```

### 5) Backfill GPS

```powershell
& $py -m app.cli gps-backfill --root E:\01_INCOMING
```

### 6) Health and queue checks

```powershell
Invoke-RestMethod http://127.0.0.1:8002/health
Invoke-RestMethod http://127.0.0.1:8002/system/usage
Invoke-RestMethod "http://127.0.0.1:8002/tasks?page=1&page_size=20"
Invoke-RestMethod http://127.0.0.1:8102/health
```
