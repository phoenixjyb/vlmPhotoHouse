# One-photo / one-video canary and v1/v2 coexistence plan

**Reviewable plan only. Not executed.** The preparation source is ready for native
verification; real media and live v2 remain operational gates. Preserve all current
services, credentials, router settings, originals, database and caption work.

## Stage 1 — native synthetic replay, with no listeners

1. Refresh Windows identity, date/free disk/available memory, canonical originals
   and database paths, current caption/API process IDs/start times, and owned v1/DNS
   task state. Check the protected task's current state and preserve it. Do not
   call `/health`, start a stopped protected task, pause captions or change workers.
2. Stage exact committed preparation/serving source and fixtures in a new private
   release directory and verify every hash against the return receipt. Keep the
   existing v1 release/config/publication untouched. Create a separate CPU Python
   3.12 preparation venv; install the hash-locked CPU dependencies plus the reviewed
   Pillow Windows wheel. Do not install into a serving/caption environment.
3. Capture native FFmpeg/ffprobe version, canonical executable path and hash. The
   prior read-only inspection found FFmpeg 7.1.1; the source tests used 9.0.1 on Mac.
   Do not assume native flags/rotation/metadata behavior is identical. Run all 20
   preparer tests and the synthetic benchmark with the native tools, plus v1/v2
   focused tests and the 160-entry inventory. No socket bind is needed.
4. Require every test to execute and pass with **zero skips**. If tools are missing,
   codecs/options differ, output tags fail verification, or Windows path/locking
   behavior differs, stop at source/tooling review. Do not loosen the frozen profile
   or turn off validation to pass the canary.

## Stage 2 — select exactly two real IDs, still offline

Use an explicit read-only metadata query and keep IDs/paths in private operator
evidence. All existing visible catalog items remain the user's intended final
scope, but this conversion trial is exactly:

- One current active JPEG with existing source, known dimensions up to 12MP and
  source size <=20 MiB. Prefer an EXIF-rotated photo if available so orientation can
  be checked. Do not inspect or select captions/faces/person/GPS fields.
- One current active short MP4/MOV <=60 seconds, <=512 MiB, within the tool's 8-bit,
  square-pixel input profile. A short H.264 MOV with extra tracks is the first
  compatibility canary; the two previously sampled MOVs are candidates only after
  current path/ID/hash/status readback. The earlier sample names stay Windows-local.
  Do not start with the sampled 8K HEVC videos or assume their CPU cost from Mac data.

Capture source SHA-256, file identity, byte size, dimensions, duration/codecs and
current active status privately. A header-only probe is allowed before conversion.
If either fails the reviewed budget/profile, choose a different qualifying ID and
record why; do not silently raise the budgets or clip the source. No originals are
copied off Windows. No source/database schema/membership write is involved.

Create a new disabled full-catalog base with `build_home_catalog.py`. This preserves
all visible IDs with unavailable states. Put working derivatives on Drive E in a
new operator-owned preparation directory, outside the originals tree. Keep the
venv/source on the private access root; do not put the ~564 GB source library on C.

Concrete command sequence after private variables are verified:

```powershell
& $prepPython $exportScript --database $catalogDatabase --output $newBase --revision $newRevision
& $prepPython $prepareScript prepare --database $catalogDatabase --source-root $originalsRoot --base-catalog (Join-Path $newBase 'catalog.json') --workspace $prepWorkspace --asset-ids "$photoId,$videoId" --ffmpeg $prepFfmpeg --ffprobe $prepFfprobe
& $prepPython $prepareScript prepare --database $catalogDatabase --source-root $originalsRoot --base-catalog (Join-Path $newBase 'catalog.json') --workspace $prepWorkspace --asset-ids "$photoId,$videoId" --ffmpeg $prepFfmpeg --ffprobe $prepFfprobe
& $prepPython $prepareScript publish --workspace $prepWorkspace --output $newDisabledPublication
```

The second preparation invocation must verify and resume without re-encoding.
Variables are private operator bindings, not ambient defaults. Check each exit
code **and** journal ready/unavailable result. A successful CLI run can deliberately
contain unavailable items; exit zero alone is not canary acceptance. The new
publication must remain disabled throughout this stage. No Windows command above
has been executed by the current source slice.

## Stage 3 — measurements and acceptance

Observe one conversion at a time. Before starting, require >=8 GiB available RAM
and >=2 GiB free disk plus budgeted workspace/publication copies. Retain resource
samples at one-second intervals for only the owned preparation processes and
existing caption/API processes. Record CPU time deltas, working/peak working set,
wall duration, source/output byte counts and disk deltas. Do not dump command-line
secrets or alter scheduling/priority of existing services.

Stop only the owned preparation child/parent if working set exceeds 1 GiB, available
RAM falls below 4 GiB, the existing service becomes unresponsive, or the owned run
exceeds a five-minute operator deadline. These are external canary gates, not a
claim that the script enforces an OS memory quota. Its native child timeout is 120
seconds, its per-asset stage deadline 180 seconds, and a synchronous hash read has
a separate budget. Never terminate arbitrary Python/FFmpeg processes by name.

Acceptance requires:

- Original and database content are not modified by preparation; before/after
  original hashes match. The live DB may legitimately change from captioning, so
  do not claim unchanged whole-DB hash; instead verify the preparer used read-only
  mode and did not change schema, selected asset metadata or job submission state.
- Both IDs are ready, previews are correctly oriented and normalized, the video
  probe/full decode/metadata checks pass, hashes/chunks match, and durations match
  within the reviewed tolerance. Review photo/poster/video locally on Windows;
  do not export family media to a public evidence document.
- Resume performs no conversion; publishing creates a separate disabled candidate
  with the complete metadata catalog and only the two canary IDs prepared. This
  is a **partial media-coverage candidate**, not all-library completion.
- Caption/API identity and responsiveness are retained. Process existence alone
  is insufficient: use an already-approved non-model-loading progress/read signal
  to check caption continuity. If that signal cannot be observed, report the impact
  gate as unverified rather than calling it passed. Do not requeue work.

If successful, return exact native tool/source pins, elapsed/CPU/memory/disk data,
private publication/hash reference and scoped next conversion budget. Stop before
an unattended loop. A later batch may use up to 16 explicit IDs per invocation;
large/long/HDR/unsupported files need a reviewed preparation expansion. This canary
does not authorize bulk conversion of the 564 GB video corpus.

## Stage 4 — v1 and v2 can coexist without repointing the old APK

Recommended arrangement: keep the current v1 task, port, origin, DNS and publication
exactly as they are. Introduce a separate v2 task and private-interface TLS listener
using the same certified hostname and a **different unused port**. The private
operator plan proposes 8445; availability and any existing rule/task collision
must be checked live before approval. The port is a proposal, not a running origin.

Use the v2 standalone launcher with explicit private configuration. Suggested new
task identity: `PhotoHouse-HomeCatalog-V2-Canary`; manual start, limited user, no
startup trigger for the canary. Use distinct v2 logs/config/media roots. Keep actual
addresses, CIDRs and certificate/key paths in the private handoff. Reuse the
existing certificate only after chain/hostname/expiry/key-access review; no new
credential or global certificate permission change is proposed.

Prepare only new v2-specific allow/block firewall rules for the verified wired
address/port and the existing pilot TV/operator peers. No router forwarding, DMZ,
UPnP, VPN/public ingress, wildcard server bind or legacy `/assets` proxy is permitted.
There must be no change to v1/DNS/protected/caption rules or task state. App-scoped
address mapping keeps the hostname/SNI/trust intact. No TV-wide DNS change is needed
for the mapped APK. Leave the old resolver in place until the TV's saved DNS state
is verified; its dependency has not been disproved by app-scoped mapping.

Only after a separate reviewed deployment action, enable the intended v2 candidate,
start that new task, and perform actual allowed/denied-peer HTTPS checks, Range
seek/full/HEAD/hash checks, and scoped disable/restart/rollback. Recheck legacy,
account, voice and operational route denial. From Android, use explicit **v2 build
selection and the new origin**, with no automatic fallback to v1 or legacy routes.
Keep the existing v3 v1 APK available as the rollback client. Android owns the APK,
player and physical fit/zoom/fullscreen/play/pause/seek/remote/lifecycle acceptance.

Rollback stops only the new v2 task/process by verified ownership and removes only
new v2 firewall rules; keep publications/configs for inspection. The old APK/v1
feed continues to work throughout. No v1 service restart or DNS teardown is needed.
A live v2 deployment, public-network acceptance and physical real-media playback
are **not** completed or authorized by this source-only return.
