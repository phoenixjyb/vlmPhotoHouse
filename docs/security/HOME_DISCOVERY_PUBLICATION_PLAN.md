# Discovery export and publication readiness plan

Plan only, prepared after Android source integration review on 2026-09-12.
It authorizes no real-data access, mapping resolution, service change, device
installation, push or merge. Preserve the existing v1 feed, DNS path, private
configuration and APK rollback artifacts. Do not repoint a v1 APK at discovery.

## Reviewed baseline

Backend discovery implementation: `54f68427058c45f6bcc5a863cc6d708f5b325e45`;
evidence: `35ebe8d465283244c0dae5aa87969ade54279379`.
Android source reviewed: `0e9ba816dc1cb0324744d7ad03351c1f1e39d311`;
evidence: `a2c48fb727402ccd6beead855a3faa78f552c973`.
The Android evidence commit changes evidence files only. Independent review
rechecked four contract/boundary verifiers, all 19 pinned backend input blobs and
the actual 11-check synthetic ASGI replay. Three v6 APK hashes/sizes match their
receipt and contain no packaged assets/MP4. Existing JVM XML hashes/counts match
80 home, 22 core and 65 live-core tests; those suites were not rerun here.

The reviewed adapter uses one explicit HTTPS origin, exact discovery/library and
catalog bindings, bounded response parsing, no automatic version fallback,
revision/fingerprint checks and an isolated result store. It reuses v2 prepared
photo/video transport. Discovery is opt-in and build-rejected with catalog v1.
The existing-home v6 APK remains v1 with discovery off; the discovery v6 APK is
origin-unset. Phone contracts remain unchanged.

The review found `choiceHint` mislabeled reviewed person/region provenance as
unknown. Android fixed this in `63feba99db6adf6ff328987c91428345a745cad3`. The
narrow diff and retained two passing label-test results were inspected; unknown
and caption sources remain distinct. Existing v6 APKs were not rebuilt for this
correction and still belong to the original source pin. No wire change was needed.
Two retained screenshots were inspected (normal advanced editor and enlarged
Chinese Explore); no device acceptance is implied. Emulator/Gradle results remain
Android-reported evidence, separate from the independently repeated ASGI checks.

## Readiness that is actually known

| Area | Current evidence | Required future evidence |
| --- | --- | --- |
| Seven family shortcuts | Private request file has seven entries and seven null person IDs; no names copied to public artifacts | Explicit private mapping approval, stable person IDs, reviewed assignments and operator order |
| Caption coverage | Schema supports text, edit/variant and superseded metadata; actual counts unmeasured here | Snapshot-specific selected/missing/ambiguous/oversized counts and reviewed selection rule |
| Tags | Source kinds and association provenance exist; block table exists | Eligible unblocked association counts by source/kind, unknown/duplicate/missing cases; no tag-completion inference |
| Dates | Nullable recorded capture dates | Valid/missing/invalid date counts; no import-date substitution |
| Places | No approved coarse-region mapping inspected | Reviewed region IDs/labels and asset links, or capability disabled |
| Photo preparation | Synthetic preparer and v2 preview serving tested | For approved IDs: grid-ready and display-ready counts separately, hashes, dimensions, normalization and actual image quality |
| Video preparation | Synthetic MP4 preparation/Range path tested | Approved-ID ready/missing/unsupported/failed counts, codec/duration/track/hash/chunk checks, native playback and seek |
| Origin | Source composition and TLS client contract agree | Approved private same-origin listener, certificate hostname/SNI trust, LAN route, peer restrictions and revocation checks |

Every current real coverage count is **unmeasured**, not zero. Historical whole
library counts or caption progress must not substitute for a new publication's
coverage. A catalog entry does not imply its media is prepared. A prepared file
without current catalog/hash validation does not count as ready.

## Next bounded source slice: PH-BACKEND-DISCOVERY-EXPORT-01

Write owner: backend task, existing `codex/backend-home-tv-feed` worktree.
Android remains read-only to this task. Use synthetic SQLite and fixture media only.
Keep frozen discovery/v1/v2 wire contracts and serving handlers unchanged.
Proposed files: a separate offline export/review module and CLI, focused synthetic
tests, a machine-readable coverage/review receipt and usage documentation. No
launcher, scheduled task, live path defaults or automatic publication enable.

Outcome: from an explicit candidate catalog and a synthetic coherent metadata
snapshot, produce a bounded private review package and, after an explicit matching
review input, a **new disabled** catalog/index bundle. Do not change the original
candidate directory. Copy/rebind only already verified prepared artifacts when
requested; perform no conversion and never fetch originals. Missing media stays
explicitly unavailable.

1. Validate exact direct input/output paths, candidate catalog digest/revision,
   selected visible asset-ID set, and required schema columns. Use read-only
   SQLite/query-only with a single read transaction, bounded rows/time/output.
   Do not import app settings, DB initialization, workers, face audit helpers or
   model modules. Missing/incompatible schema fails with a bounded report, never
   migration or table creation. Synthetic tests must prove no DB/schema changes.
2. Require explicit publication selection. The existing catalog exporter includes
   all active/legacy-null assets, so it is not proof that the owner approved that
   entire set for anonymous sharing. Bind a reviewed selection digest; never
   expand the publication from discovery queries. Hidden/deleted/foreign IDs
   invalidate the candidate or require a freshly reviewed catalog; do not silently
   retain or add them.
3. Draft metadata with explicit exclusions and reasons. Proposed initial caption
   rule: eligible non-superseded, nonblank rows only; use a sole eligible edited
   row, otherwise a sole eligible row. Multiple edited or unedited candidates are
   ambiguous and excluded until a reviewed selector resolves them. Do not infer
   freshness from maximum row ID, concatenate variants, silently truncate over
   4096 UTF-8 bytes, or claim locale/model coverage.
4. Preserve tag sources `cap -> caption`, `img -> image`, `cap+img -> caption_image`,
   `manual`, `rule`, and unknown separately. Blocked associations never enter the
   index. Duplicate/conflicting associations are reported and require a defined
   resolution; no invented confidence or generated theme taxonomy. A person-kind
   tag remains a tag. No tag generation is run.
5. Family shortcuts need two different reviews: alias-to-person ID mapping and
   the asset/person assignment set allowed to be disclosed. A roster mapping
   alone must not bless every automated assignment for that person. Bind private
   approval to explicit current assignment evidence, selected IDs and snapshot
   identity. DNN suggestions, captions, face-count totals, positional order and
   legacy manual flags alone are insufficient. Unresolved aliases do not become
   public roster entries. No face crops/embeddings/biometric material in reports.
6. Accept only explicit reviewed coarse region/asset associations. Never derive
   places from captions, expose raw coordinates, call geocoding, or guess regions.
   Missing mapping yields disabled location capability. Themes/topics stay off.
7. Emit review totals with catalog/index/metadata coverage, association provenance,
   reasons for exclusion, and media readiness by variant. Report complete row
   coverage separately from metadata values and from semantic correctness. Keep
   labels, captions and actual IDs in private artifacts; public evidence is
   synthetic or appropriately aggregate and contains no household alias list.
8. Bind the approved plan digest to the exact inputs, mappings, policy version,
   revisions and candidate asset set. Any mutation invalidates approval. A digest
   proves unchanged bytes, not operator consent; require explicit review input
   rather than self-approving generated output. Run frozen validators, serialize
   deterministically, write to a new directory and keep shared control disabled.
   Failure must not enable or replace a publication. Return output/source hashes
   and the coverage receipt, with no running service.

Acceptance: synthetic cases for hidden/foreign IDs, incomplete/incompatible schema,
caption ambiguity/supersession/oversize, blocked/duplicate/unknown-source tags,
unreviewed and changed assignments, seven unresolved shortcuts, absent dates and
regions, zero/partial/complete index rows, unavailable and hash-invalid media,
input mutation after review, output collision, and bounded resource failure.
Replay the resulting disabled bundle (403), then enable **only the temporary
synthetic fixture** and exercise the frozen discovery/v2 ASGI contract. Verify
no original fallback, SQL writes, ports, subprocess/model calls or source changes.
Stop with source/tests/evidence; do not run it on the real library.

## Subsequent gates, requiring their own operational scope

A. Read-only real inventory/review preparation: agree on the publication selection
and coherent SQLite snapshot method on Windows before access. Ordinary SQLite
read-only mode can still interact with WAL/shared-memory sidecars; prove the
chosen method and do not use `immutable=1` on a database with a live writer.
An approved consistent snapshot/backup, if needed, is a separate operation and
stays private on Windows. Do not copy real DB/media to this Mac. Measure the
actual requested coverage fields above; do not resolve private IDs implicitly.

B. Review identity/region mappings and disclosure: owner confirms the seven IDs,
aliases/order, exact assignment evidence and intended photo/video/metadata set.
Keep ambiguous entries unpublished. Inspect current hidden/deleted status again
before any release. A offline snapshot cannot provide continuous hide/revocation
freshness; define maximum publication age, refresh/review ownership and immediate
shared-disable procedure before deployment.

C. Native preparation canary: follow [the separate preparer plan](HOME_PREPARATION_CANARY_PLAN.md)
with Windows synthetic checks first, then a separately approved one-photo/one-short-
video canary. Report original integrity, prepared coverage, resource use and
caption-worker continuity. Do not bulk-convert or pause captioning as part of
export readiness. Existing ready artifacts require fresh validation.

D. Compatible origin: review a distinct private LAN origin for the composed v2 +
discovery app while preserving v1. The same HTTPS scheme, hostname and port must
serve discovery facets/search, v2 catalog, preview and MP4 Range. The Android
configured build must set catalog v2 and discovery true; optional app-scoped LAN
mapping changes only address resolution, preserving certificate hostname/SNI.
No TLS bypass, redirects, cookies or personal credentials. Do not point it at
v1-only or protected-phone endpoints. Bind reviewed actual-peer networks; do not
trust forwarded headers or add router/public forwarding. A previously proposed
port is not evidence of availability or approval. Validate memory, initial-load,
slow-body/client deadlines and publication disable before enabling a listener.

E. Only after backend evidence, build an approved-origin discovery APK and review
its hash/package/signer/profile. Preserve the configured v1 rollback APK. Physical
installation is a separate user action/authorization. Verify selected real media,
people/date/tag results, remote focus at normal/large font, fit/fill/zoom quality,
video play/pause/seek/fullscreen, network loss, denial, sleep/wake and release
revocation. Passing source tests or an origin-unset APK does not complete this gate.
