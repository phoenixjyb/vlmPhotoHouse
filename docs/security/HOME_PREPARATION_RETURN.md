# PH-BACKEND-HOME-PREPARATION-01 — verified source return

Completed the requested bounded offline-preparer source slice. Implementation pin:
`0c3230a71a23bdc74b4f913a3f92c360268edbca`, branch `codex/backend-home-tv-feed`,
worktree `_worktrees/backend-home-tv-feed` in the PhotoHouse workspace. Started
from clean `868cbb48aec50fa9c01689ee071c9d999e0b8e0d`. A later return-document
commit does not replace the implementation pin.

[Preparation guide](HOME_PREPARATION.md), [exact canary/deployment plan](HOME_PREPARATION_CANARY_PLAN.md),
[source hashes](evidence/home-preparation/source-inputs.json), and
[verification receipt](evidence/home-preparation/verification.json) are the handoff.
All six pinned preparer source/document inputs were independently checked against
Git blobs. No v1/v2 wire or serving code changed. V2 contract hash remains
`13cf10892dc4e91631ad71b5ee4bed21baa44697f1e779851c19026dbe606120`.
Android can continue using its frozen catalog/player adapter without a schema change.

Results: **62 tests passed, zero skipped** (20 preparer, 24 v2, 18 v1) in 6.052 s.
Inventory remains complete at **160 entries**, with no new routes. Markdown HTML
structure and local links checked. New preparation tooling is isolated from all
serving/caption environments; failed/skipped tooling attempts are recorded in the
guide, not counted as success.

The final measured synthetic run prepared a 12MP rotated photo and six-second
1080p H.264/AAC video in **6.511 s**; hash-verified resume took **0.020 s**.
Child CPU accounting reported 6.709 user / 0.235 system seconds. Reported maximum
child RSS was 380,452,864 bytes on macOS and includes fixture generation; it is not
an isolated preparation peak or Windows prediction. The disabled publication was
9,965,804 bytes. Original/synthetic DB hashes were unchanged, and actual ASGI
catalog/photo/HEAD plus a valid MP4 Range crossing the 4 MiB boundary passed.
[Detailed measurement](evidence/home-preparation/benchmark.json).

No Windows connection, install, real conversion, live database/service change,
port exposure, push or merge occurred. The real library, caption/API and v1/DNS
were left untouched by this source slice; no new live-health claim is made.

Next operational gates, in order:

1. Native Windows synthetic replay with the separate locked environment and exact
   FFmpeg/ffprobe identity; require all preparation tests to run, zero skips.
2. Exactly one qualifying real photo and one short video, source hash/status
   readback, resource telemetry, verified resume and a new disabled publication.
   Observe caption continuity; do not infer it from unchanged PIDs alone.
3. Separately reviewed v2 listener/task/firewall deployment. Proposed coexistence
   uses the existing certified hostname on a distinct port (private proposal 8445,
   not verified free), preserving the current v1 APK/feed/DNS. No public forwarding.
4. Android physical real-media fit/zoom/fullscreen/play/pause/seek/lifecycle tests.
   Then review a bounded expansion of derivative coverage; no bulk loop is supplied.

Remaining limits include unsupported HDR/10-bit/long/oversized sources, Windows
native codec/path/locking verification, lack of a hard OS RSS quota, live snapshot
hide/import freshness, slow-client/network isolation and the existing legacy
original-route authorization gaps. Full-catalog metadata is not full-media
coverage or physical playback acceptance. Source and native/real/deployment/device
results remain separate.

Changed files:

- `scripts/prepare_home_catalog.py`
- `tests/security/test_home_preparer.py`
- `backend/requirements-home-preparation.lock`
- `docs/security/HOME_PREPARATION.md`
- `docs/security/HOME_PREPARATION_CANARY_PLAN.md`
- `docs/security/HOME_PREPARATION_RETURN.md`
- `docs/security/evidence/home-preparation/benchmark.py`
- `docs/security/evidence/home-preparation/benchmark.json`
- `docs/security/evidence/home-preparation/pillow-wheels.json`
- `docs/security/evidence/home-preparation/source-inputs.json`
- `docs/security/evidence/home-preparation/verification.json`
