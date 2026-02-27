# OpenClaw Agent Guide (Task Trigger + Query Runbook)

This guide is for agents (OpenClaw or similar) that need to **query system state** and **trigger work** on the VLM Photo House stack.

It is written for the current Windows/local deployment profile.

---

## 1) Runtime profile (current default)

- Photo House API/UI: `http://127.0.0.1:8002`
- LLMyTranslate voice runtime: `http://127.0.0.1:8001`
- Caption service: `http://127.0.0.1:8102`
- RAM++ image-tag service: `http://127.0.0.1:8112`
- Ollama runtime (voice LLM): `http://127.0.0.1:11434`

Primary control surface for OpenClaw: **Photo House API on 8002**.

---

## 2) Agent safety rules (must follow)

1. **Query-first, mutate-second**  
   Always query IDs/states before posting mutating requests.
2. **No blind service restarts**  
   Do not restart backend/caption/voice/tag services unless explicitly requested.
3. **Use domain triggers, not direct DB writes**  
   Trigger work via API/CLI endpoints; do not write SQLite tables directly.
4. **Poll task completion**  
   After triggering work, poll `/tasks` until terminal state.
5. **Treat legacy voice-photo routes as non-canonical**  
   `/voice/describe-photo`, `/voice/search-photos`, `/voice/photo-demo`, `/voice/rtx3090-status` are legacy/demo routes.

---

## 3) Fast preflight (copy/paste)

```powershell
Invoke-RestMethod http://127.0.0.1:8002/health | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8002/health/caption | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8002/health/lvface | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8002/metrics | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8002/system/usage | ConvertTo-Json -Depth 6
```

Voice preflight:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/voice/health | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8002/voice/capabilities | ConvertTo-Json -Depth 6
```

---

## 4) Query surface (read operations)

### Health, metrics, usage
- `GET /health`
- `GET /health/caption`
- `GET /health/lvface`
- `GET /metrics`
- `GET /metrics.prom`
- `GET /system/usage`

### Task/queue inspection
- `GET /tasks?page=1&page_size=50&state=&type=`
- `GET /tasks/{task_id}`
- `GET /admin/tasks/dead?page=1&page_size=50`

### Asset/content queries
- `GET /assets?page=1&page_size=120`
- `GET /assets/detail/{asset_id}`
- `GET /assets/{asset_id}/captions`
- `GET /assets/{asset_id}/tags`
- `GET /assets/{asset_id}/thumbnail?size=512`
- `GET /assets/{asset_id}/media`
- `GET /assets/geo?media=all&limit=1000`

### Search
- `GET /search?q=...`
- `POST /search/captions`
- `POST /search/tags`
- `POST /search/smart`
- `POST /search/vector`
- `POST /search/person/vector`
- `GET /search/person/{person_id}`
- `GET /search/person/name/{name}`
- `POST /search/video`
- `POST /search/video-segments`

### People/faces/tags
- `GET /persons?page=1&page_size=240&include_faces=true&named_only=true`
- `GET /faces?unassigned=true&page=1&page_size=120`
- `GET /faces/{face_id}`
- `GET /faces/{face_id}/crop?size=256`
- `GET /faces/assignment-history?page=1&page_size=100`
- `GET /tags?q=&source=all&page=1&page_size=200`
- `GET /tags/{tag_id}/assets?media=all&source=all&page=1&page_size=120`

### Voice (read/proxy)
- `GET /voice/health`
- `GET /voice/capabilities`
- `POST /voice/command` (read-only orchestration)

---

## 5) Trigger surface (write operations)

There is no single generic enqueue endpoint. Use these domain triggers:

### Ingest / indexing / maintenance
- `POST /ingest/scan` with body: `{"roots":["E:\\01_INCOMING"]}`
- `POST /vector-index/rebuild`
- `POST /video-index/rebuild`
- `POST /video-seg-index/rebuild`

### Captions / tags
- `POST /assets/{asset_id}/captions/regenerate` body: `{"force":false}`
- `POST /assets/{asset_id}/tags` body: `{"names":["tag-a","tag-b"]}`
- `DELETE /assets/{asset_id}/tags` body: `{"tag_ids":[45],"block_auto":true}`
- `PATCH /captions/{caption_id}` body: `{"text":"...","user_edited":true}`
- `DELETE /captions/{caption_id}`

### People / faces
- `POST /faces/{face_id}/assign` body: `{"person_id":123}` or `{"create_new":true}`
- `POST /faces/assign` (bulk)
- `DELETE /faces/{face_id}?prune_empty_person=true`
- `POST /faces/delete` (bulk)
- `POST /persons` body: `{"display_name":"Name"}`
- `POST /persons/{person_id}/name` body: `{"display_name":"New Name"}`
- `POST /persons/merge` body: `{"target_id":1,"source_ids":[2,3]}`
- `POST /persons/{person_id}/delete`
- `POST /persons/recluster`

### Tasks / retries
- `POST /tasks/{task_id}/cancel`
- `POST /admin/tasks/{task_id}/requeue`

### Voice proxy (execution endpoints)
- `POST /voice/transcribe` (multipart form)
- `POST /voice/tts` (JSON)
- `POST /voice/conversation` (multipart form)

---

## 6) OpenClaw canonical polling loop

Use this pattern after every trigger:

1. Trigger action (API/CLI)
2. Query task list by relevant type/state
3. Loop until terminal (`finished`, `done`, `failed`, `dead`, `canceled`) or timeout
4. On failure: fetch task detail and optionally requeue dead tasks

PowerShell polling example (caption backlog):

```powershell
$base = "http://127.0.0.1:8002"
for ($i = 0; $i -lt 120; $i++) {
  $pending = Invoke-RestMethod "$base/tasks?page=1&page_size=50&type=caption&state=pending"
  $running = Invoke-RestMethod "$base/tasks?page=1&page_size=50&type=caption&state=running"
  $failed  = Invoke-RestMethod "$base/tasks?page=1&page_size=20&type=caption&state=failed"
  "{0}: pending={1}, running={2}, failed={3}" -f $i, $pending.total, $running.total, $failed.total
  if (($pending.total -eq 0) -and ($running.total -eq 0)) { break }
  Start-Sleep -Seconds 5
}
```

---

## 7) High-value recipes

### A) Trigger ingest and confirm queue movement

```powershell
$body = @{ roots = @("E:\\01_INCOMING") } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8002/ingest/scan" -ContentType "application/json" -Body $body
Invoke-RestMethod "http://127.0.0.1:8002/tasks?page=1&page_size=20&type=ingest"
```

### B) Requeue one dead task

```powershell
$dead = Invoke-RestMethod "http://127.0.0.1:8002/admin/tasks/dead?page=1&page_size=20"
$id = $dead.tasks[0].id
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8002/admin/tasks/$id/requeue"
```

### C) Kid voice flow ("show me photos of chuan")

Text-only orchestration test:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8002/voice/command" `
  -ContentType "application/json" `
  -Body '{"text":"show me the photos of chuan","language":"en","limit":10}' | ConvertTo-Json -Depth 6
```

Expected contract:
- `action = search.person.assets`
- returns `person_id`, `person_name`, `items`, `total`
- mutating voice intents are blocked as `mutate.request`

### D) Search by tags (read-only)

```powershell
$body = @{ tags = @("family","beach"); mode = "any"; media = "all"; k = 60 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8002/search/tags" -ContentType "application/json" -Body $body
```

### E) Person assets by name

```powershell
Invoke-RestMethod "http://127.0.0.1:8002/search/person/name/chuan?page=1&page_size=60" | ConvertTo-Json -Depth 6
```

---

## 8) CLI control channel (for batch operations)

Run from `vlmPhotoHouse\backend`:

```powershell
$py = ".\.venv\Scripts\python.exe"
```

Common batch triggers:

```powershell
& $py -m app.cli ingest-scan E:\01_INCOMING
& $py -m app.cli ingest-status E:\01_INCOMING --scan-fs --preview-limit 20
& $py -m app.cli captions-backfill --profile balanced --max-variants 1 --limit 500
& $py -m app.cli captions-tags-backfill --root E:\01_INCOMING --max-tags 8 --apply
& $py -m app.cli image-tags-backfill --root E:\01_INCOMING --max-tags 8 --only-missing-img --apply
& $py -m app.cli faces-auto-assign --reference-manual-only --include-dnn-assigned --limit 0 --apply
& $py -m app.cli recluster-persons
& $py -m app.cli list-dead --page 1 --page-size 50
& $py -m app.cli requeue 12345
```

Validation/warmup:

```powershell
& $py -m app.cli validate-caption
& $py -m app.cli validate-image-tag --strict
& $py -m app.cli validate-lvface
& $py -m app.cli warmup --do-face --do-caption --no-do-image-tag
```

---

## 9) OpenClaw execution strategy (recommended)

For each user request:

1. **Preflight**: health + queue snapshot.
2. **Plan**: identify whether request is query-only or trigger+poll.
3. **Execute**:
   - query-only: hit read endpoints and return normalized summary.
   - trigger: call domain endpoint/CLI and start poll loop.
4. **Verify**: return final counts, IDs touched, and any failed/dead tasks.
5. **Escalate**: if provider health is degraded, surface exact failing component (`caption`, `lvface`, `voice`, `image_tag`) before retrying.

---

## 10) Known current limits

- Voice orchestration is currently **read-only**; mutating intents require future confirmation flow.
- Legacy `voice_photo` routes exist but are not the canonical production control path.
- Some video/phash backlog behavior may require targeted operational handling outside standard ingest flow.

