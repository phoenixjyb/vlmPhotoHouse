# Incremental intake — 8 September 2026

## Authority and scope

The user requested another INCOMING photo/video intake and asked to ignore and
move clearly repeated originals to a separate folder named `repeative ones`.
Only exact SHA-256 matches with a currently readable, verified keeper qualify.
Perceptually similar images, edits, and different encodings are not duplicates.
Existing database-linked paths, including deleted records, are protected from
moves. A deleted or unavailable registered asset is not a valid keeper for a
new copy. Sidecars and unsupported formats remain untouched.

The quarantine is outside INCOMING, on the same volume, with the original
relative directory structure. Moves never overwrite a destination or fall back
to copy/delete. A flushed JSONL intent/completion manifest records each source,
destination, keeper, size, and hash. Both copies are rehashed before moving.
No model/media/database files are copied to the development Mac.

## Implementation and validation

CLI source release: `5f7a441` (`photohouse-intake-5f7a441`). The live API stays
on `1248e5e`; neither it nor the caption service is restarted. Scheduled tasks
and model installations are unchanged.

`scripts/intake_incremental.py` audits by default. Applying a saved plan requires
explicit `--apply`, `--quarantine`, and `--receipt` arguments. Recently created
or modified files settle for ten minutes. Reparse points and changing files are
refused. Size filtering avoids hashing files that cannot possibly be duplicates.

The project importer now accepts explicit files and commits each file separately,
avoiding one large folder transaction while the live worker is processing.
The same ORM/schema and normal metadata/task creation path are reused.
The live Web UI's general scan remains path-based; use this guarded CLI for
subsequent duplicate-aware intakes until a separately reviewed API integration.

Ten focused tests passed in the Windows project environment, covering protected
originals, exact-vs-similar content, changed files, recently copied files, stale
database hashes, deleted/missing keepers, collisions, symlinks, explicit-file
photo/video ingestion, repeat idempotence, and deferred similarity embeddings.
Nine standard-library checks also pass on the Mac; its runtime dependency check
is skipped rather than installing the ML environment there.

One Windows fixture run failed conservatively before real-file writes. A clean
rerun, 100 repeated fixture audits, and the final pre-apply suite passed. The
real audit had zero changing-file errors. A consistent SQLite backup was taken
on Windows with `quick_check=ok` and 27,689 asset records before applying.

## Audit results

The first audit found 663 unregistered files in `Jane/janeMay2026-Sept2026`:

- 167 exact extra copies, totaling 17,911,871,059 bytes.
- 496 novel files: 346 photos and 150 videos.
- Zero deferred or unreadable files at the completed audit. The 66 recently
  created files seen in the initial inventory had settled by then.

A completion rescan found another 21 photos copied into a different folder
during the run. A separate saved-plan audit found all 21 novel and settled,
with zero duplicates or errors. The follow-up apply registered all 21 without
errors. Combined intake: 517 new assets (367 photos and 150 videos), plus
167 recoverable extra copies moved out of INCOMING.

## Important processing boundary

The live general embedding endpoint reports `stub-clip` for both image and text.
This is separate from real Qwen3-VL captioning and InsightFace/LVFace face work.
This intake uses `--defer-embeddings` so it does not generate new placeholder
image/video similarity vectors. Photo thumbnail, perceptual hash, caption, and
face jobs remain enabled; videos receive probe/keyframe jobs. The receipt records
asset IDs and the deferred embedding flag for a later real-model backfill.

Registering assets and queueing jobs is not completion of caption or face work.
The existing video-keyframe handler may time out on long videos and has a legacy
fallback; this intake does not establish full video-model acceptance.

## Execution status

Audit, database backup, and registration complete. The final apply receipt
reports 496 new assets, zero skipped files, and 496 deferred general similarity
embedding jobs, with no ingestion errors. All 167 duplicate copies have been
moved and checked for destination/keeper existence and preserved sizes; all
previous asset paths and recorded hashes match the backup. The run-specific
quarantine folder is `repeative ones/intake-20260908-5f7a441`, and its
`moves-and-intake.jsonl` records recovery and ingestion results. Background
caption/face/video preparation is separate from completed registration.

The follow-up uses its own plan and receipt under
`repeative ones/intake-20260908-5f7a441-followup`, and reports 21 new assets,
zero skipped files, zero moves, and 21 deferred general similarity embeddings.
The pre-intake database backup covers both passes. Moving the 17.9 GB of extra
copies does not free disk space; nothing was deleted.

Final inventory: 28,206 database asset rows and 28,204 supported media files
present in INCOMING, all registered. The two previously missing originals
remain a pre-existing discrepancy. No unregistered supported media remained
at the final scan; unsupported formats and sidecars were not moved or ingested.
The 21 follow-up originals and their database records were verified present.

The Windows-local UI returned HTTP 200 at `http://127.0.0.1:8002/ui`.
API/database health was green with the worker enabled, 1,238 pending tasks
and one running at the final health sample. The 365 existing failed tasks
were unchanged. These queue totals are a snapshot, not a completion claim.

All source changes and this operational receipt are committed locally only;
no GitHub push or live API deployment was performed for this intake.
