# Offline discovery export — synthetic implementation

`PH-BACKEND-DISCOVERY-EXPORT-01` implements the next source slice from the
[publication readiness plan](HOME_DISCOVERY_PUBLICATION_PLAN.md). It provides
`scripts/export_home_discovery.py`, an offline review/publish CLI. It does not
change frozen serving code, Android pins, live services or publication pointers.
No real snapshot, actual identity mappings or deployed origin is included.

## Inputs and explicit review

Supply every path explicitly. Inputs are a standalone SQLite snapshot, a disabled
candidate v2 directory, and a private request JSON. Paths must be absolute and
direct, with no symlink components. The candidate supplies `catalog.json`, disabled
`control.json`, and optionally exact prepared JPEG/MP4/chunk paths. The request
must match the complete candidate asset-ID set; it cannot broaden or silently
filter that catalog. Hidden/deleted/missing IDs invalidate the candidate.

The request has these exact keys; the synthetic fixture supplies a complete example:

| Key | Meaning |
| --- | --- |
| `version` | Integer 1 |
| `catalog_sha256` | Exact input catalog bytes |
| `selected_asset_ids` | Unique ascending approved-selection candidate IDs; exactly the catalog IDs |
| `indexed_asset_ids` | Unique ascending subset; zero/partial rows permitted and reported |
| `discovery_revision` | Explicit positive discovery revision |
| `copy_prepared` | Boolean opt-in to copy hash-verified prepared variants |
| `roster_review` | `people` records `{id,label,aliases}`, ordered `pinned_person_ids`, and `unresolved_shortcut_count` |
| `assignment_review` | Explicit `{face_id,asset_id,person_id,label_source}` rows matching the snapshot; only manual source is eligible |
| `region_review` | `locations` records `{id,label}` plus explicit `{asset_id,location_id}` assignments |

A roster name does not approve any asset/person association. Each accepted face
row must also appear in the separately reviewed assignment list and still match
its exact current IDs/source. Manual markers alone are insufficient; DNN rows
remain excluded even when names are reviewed. Regions are operator-reviewed
coarse associations, with no geocoding/GPS/name inference. All seven real shortcut
IDs remain unresolved outside this synthetic slice. An unresolved entry is counted,
never published with a guessed ID.

`review` generates a private package containing the proposed catalog/index,
coverage, policy identifier, exact snapshot/catalog/control/request digests,
selection digest and prepared-input/output hashes. It creates no approval file.
`publish` requires that saved package plus a separate approval JSON with exactly:

```json
{"version":1,"plan_sha256":"<review digest>","approve_selection":true,"approve_roster":true,"approve_assignments":true,"approve_regions":true,"approve_metadata":true}
```

These booleans are explicit operator attestations, not cryptographic identity or
a substitute for consent. Hashes bind reviewed bytes; they do not prove review.
`publish` rebuilds the candidate and requires an identical plan before creating a
new directory. Existing paths are never replaced. Both review and publication
outputs must be outside the original candidate directory. The first output file
is disabled control; an I/O failure may leave a new disabled partial attempt,
which must not be reused or served. No existing release is cleaned up or activated.

## SQLite and deterministic metadata policy

The CLI reads bounded snapshot bytes and deserializes them into an in-memory
SQLite connection. It never asks SQLite to open the input path. Only standalone
rollback-journal headers are accepted; any WAL/SHM/journal sidecar is refused.
The source must already be a coherent offline snapshot; these checks do not create
one or prove a running database is coherent. Input bytes are rechecked after the
build. No live DB copy/backup operation is provided.

Deserialization internally attaches the byte buffer as `main`. Then query-only
mode, a denying SQL authorizer, a single read transaction and a progress deadline
permit only the fixed read queries. No database/schema writes, migrations,
initializers, model calls or face-audit helpers run. Required ordinary tables and
columns must exist; views, virtual tables, missing schema and excess rows fail.
SQLite extensions/SQL functions are not enabled. Synthetic tests check original
DB bytes, absence of sidecars, SQL trace and unchanged candidate files.

Caption eligibility excludes superseded, invalid-flag and blank rows. A sole
eligible edited caption wins over unedited variants; otherwise only a sole
eligible caption is selected. Multiple competing captions are ambiguous, not
ranked by row ID. Oversized/invalid selected text is excluded with a reason,
never truncated or replaced with a lower-priority caption. No locale, quality or
model completeness is inferred.

Tag blocks take precedence. Duplicate/conflicting links and missing tag targets
are excluded and counted. Sources remain separate: `cap` → caption, `img` → image,
`cap+img` → caption/image, manual, rule and unknown. Unsupported kinds become
unknown; person-kind tags never become reviewed identities. Tags are not generated.
Dates preserve a valid recorded ISO calendar day, optionally from a valid ISO
timestamp; no ingest-date fallback or timezone conversion. Missing regions disable
locations; missing roster disables people; themes/topics remain contract-disabled.

Output serialization and selection order are deterministic. The receipt separates
catalog rows, indexed rows, metadata with/without values, caption/tag exclusions,
tag sources/kinds, unreviewed face evidence and media readiness by variant. Missing
metadata includes unindexed assets and is not proof of absence. Row completeness
is not model/tagging completeness.

## Prepared media and resource limits

Only named prepared variants are read. With copying off, ready descriptors become
unavailable; originals are never fetched. With copying on, byte sizes/hashes must
match; JPEG dimensions/metadata markers and every MP4 chunk hash are checked. Bad
ready artifacts fail the whole review rather than being silently omitted. No new
image/video conversion or native codec validation runs. `bytes_verified_ready`
means exactly that; prior preparation evidence and physical image/playback quality
remain separate gates. A full catalog is not full prepared-media coverage.

Current caps: 64 MiB snapshot, 100,000 rows per required table and 300,000 rows
total, 2 MiB request, 16 MiB catalog/index JSON, 32 MiB review package, 64 MiB per
prepared file and 128 MiB total prepared bytes. A 30-second cooperative deadline
covers build checkpoints and SQLite progress. Output contains bounded metadata
plus the bounded prepared set, with files mode 0600 and new directories mode 0700.
There is no hard RSS quota or interruptible deadline on filesystem reads/writes.
Memory includes deserialized SQLite, Python rows, output buffers and repeat reads;
these caps are not a measured Windows performance claim. Native snapshot APIs,
permissions, durability, resource usage and safe release switching remain untested.
Large libraries/long videos may exceed this first exporter scope; fail, do not
truncate or silently raise caps.

## Reproduce only synthetic work

Use the isolated CPU access-test Python. These commands create a new synthetic
snapshot and approved fixture only; no existing DB or media paths are needed:

```sh
scratch=$(python -c 'import tempfile; from pathlib import Path; print(Path(tempfile.mkdtemp(prefix="discovery-export-")).resolve())')
python scripts/build_home_discovery_export_fixture.py --output "$scratch/fixture"
python scripts/export_home_discovery.py publish \
  --database "$scratch/fixture/snapshot.sqlite" \
  --candidate "$scratch/fixture/candidate" \
  --request "$scratch/fixture/request.json" \
  --review "$scratch/fixture/review.json" \
  --approval "$scratch/fixture/synthetic-approval.json" \
  --output "$scratch/published"
python docs/security/evidence/home-discovery-export/replay.py --source-root "$PWD"
python -m unittest discover -s tests/security -p 'test_home_discovery_export.py' -v
```

The fixture CLI generates approval only after it successfully creates the new
synthetic tree itself; it has no entry point to approve an existing input tree.
Production review/publish never create approval. The replay creates its own fresh
synthetic fixture, verifies output initially disabled, enables only that temporary
bundle for combined-filter/JPEG/MP4 Range checks, restores disabled control and
verifies the original output hashes. Socket bind/connect and process launch are
guarded. No network listener, real-data access or installation occurs.

Next gates remain those in the publication plan: source review; separately scoped
coherent real snapshot and disclosure review; actual coverage inventory; native
preparation canary; compatible v2/discovery origin; configured APK and physical TV
acceptance. Preserve the existing v1 service/DNS/APK throughout. This source return
does not authorize any of those operations.
