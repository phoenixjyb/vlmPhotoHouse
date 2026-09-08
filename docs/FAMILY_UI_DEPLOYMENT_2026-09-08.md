# Family UI Windows deployment — 8 September 2026

Deployed source: `1248e5ee7be187c85936c9a564b6c0eef0f696b8`.
Release directory name: `photohouse-1248e5e-warm-ui`.
Previous release retained: `photohouse-3880f7e-family-ui`.
The user explicitly approved deployment after reviewing the local UI preview.

## Scope and provenance

The code-only archive was transferred through the existing private Mac mini
relay. Its SHA-256 was verified on Windows:
`c96721123598e5abdc743c392ad7c26cbf521a3364a39276b945c65b367924be`.

All 44 API Python/runtime PowerShell files compared identical to the previous
release. Only UI source changed at runtime. The release reuses the existing
Windows Python environment through a junction, and retains the existing
database, originals, derived media, model directories, and caption endpoint.

The existing SYSTEM-owned API task now points to the new versioned launcher.
Its triggers, principal, and settings were compared against the exported
pre-cutover XML and remained identical. Caption task/actions were not changed.
No GitHub push was performed as part of this deployment.

## Cutover observation

Stopping the scheduled task alone left the Python API child alive. The initial
cutover guard refused to start an overlapping worker; the old API remained
healthy. The second attempt verified the API port owner and its parent command
line against the expected old release, then stopped only that exact API process
tree before starting the replacement task.

The replacement was ready at approximately 19:05 China time. API listener PID
changed from 21584 to 492. Qwen3-VL listener PID 11604 was unchanged throughout.
Private execution scripts, exported task XML, health snapshots, and a cutover
receipt remain beside the Windows release, outside its source directory.

## Acceptance evidence

- Startup preflight passed before stopping the old API.
- Windows-served HTML, JavaScript, and CSS hashes matched the tested source;
  this was independently repeated through the Mac's live API tunnel.
- API/database/inline worker remained healthy. InsightFace reports CUDA
  execution; LVFace remains the configured 128-dimensional embedding provider.
- Qwen3-VL remained model-ready and idle; no model reload or inference job was
  requested. Post-cutover GPU snapshot: RTX 3090 at 44 C, 0% utilization.
- The memory index initially reported zero while deferred startup loaded it.
  The startup log confirmed 13,621 image embeddings loaded at 19:06:52,
  matching the pre-cutover index count. Readiness is distinct from completed
  background initialization.
- Queue snapshots remained 0 pending / 0 running / 365 pre-existing failures.
- Real-data Chromium checks passed: homepage, media, complete bilingual
  description, viewer navigation/focus return, Chinese mobile layout and live
  smart search. No editing request or uncaught browser error occurred.
- Synthetic browser regressions, seven existing UI source checks, JavaScript
  syntax, and whitespace checks passed before deployment.

Existing unavailable thumbnails remain a data issue; the UI now handles them
with fallbacks. This release does not repair missing originals, regenerate
captions, rename people, or resolve historical failed tasks. Real-device Safari,
screen-reader acceptance, and live editing were not tested in this deployment.

## Access and rollback

The API remains loopback-bound on Windows port 8002. Use the existing private
tunnel from the Mac (`http://127.0.0.1:18002/ui`); port 18003 is only the local
read-only source preview. Private routing instructions remain outside Git.

For a separately authorized rollback: confirm no running/pending work, verify
the current API process ancestry, stop the exact API task/process tree, restore
only the previous API launcher action from the exported task backup, then start
and verify the previous release. Do not restart the independent caption task,
change triggers, restore a database, or delete either release. Do not assume
stopping the task wrapper also stopped its child API.
