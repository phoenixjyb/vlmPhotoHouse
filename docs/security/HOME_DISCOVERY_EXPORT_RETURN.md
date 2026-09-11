# PH-BACKEND-DISCOVERY-EXPORT-01 — source return

Implementation: `d8f20a073e42f93ad2b046c4ae01d0ccd68a05bf`.
Base: `00aa4ffb05b7c2c37e9f752dc0cd2aa74d439da8`.
Branch: `codex/backend-home-tv-feed`; owned worktree
`_worktrees/backend-home-tv-feed` in the PhotoHouse workspace. A later evidence
commit does not replace this implementation pin.

The [guide and commands](HOME_DISCOVERY_EXPORT.md),
[17-input source manifest](evidence/home-discovery-export/source-inputs.json),
[verification receipt](evidence/home-discovery-export/verification.json), and
[pinned synthetic replay/output hashes](evidence/home-discovery-export/pinned-replay.json)
form the review handoff. Android received the source pin for independent review.
All 19 frozen discovery source inputs remain byte-identical; Android's discovery
runtime pin and v1/v2/phone contracts are unchanged.

## Implemented and verified

Two-phase offline review/export binds the exact candidate, selection, snapshot,
request, private roster, separate manual-assignment evidence, region review,
caption/tag exclusions and prepared bytes. Production commands never approve
themselves. Publication requires all explicit review scopes and an unchanged
plan, and creates a new disabled directory only. Candidate files and input SQLite
remain unchanged. SQL queries operate on a bounded in-memory deserialization;
WAL/SHM/journal or incompatible inputs fail instead of touching a live database.

| Check | Result |
| --- | --- |
| Focused exporter tests | 23 passed, zero skips, 0.486 seconds |
| Combined home regression | 101 passed, zero skips, 6.608 seconds |
| Inventory tests | 19 passed, zero skips, 0.635 seconds |
| Inventory completeness | 162 method/path entries; no serving routes added |
| Exact Git-blob extraction | 17 files verified against implementation pin |
| Extracted-source tests | Same 23 passed, zero skips, 0.304 seconds |
| Extracted synthetic export/ASGI | 13 checks passed; exact original replay receipt reproduced |
| Fixture + publish CLI | Reproduced exact review digest and every output hash |
| Preservation/privacy | Candidate/DB unchanged, no sidecars, private aliases absent, frozen inputs unchanged |
| Documentation | Rendered guide/return HTML structure, tables, code and local links checked |

The SQL trace test initially failed on SQLite's internal in-memory attachment
performed during deserialization. Its assertion now recognizes that exact first
operation and verifies subsequent statements remain query-only. Android's early
review identified review-output containment; it was fixed and regression-tested
before the source pin. Both attempts are recorded, not counted as passing runs.
TestClient still emits its existing Starlette/httpx deprecation warning.

Synthetic coverage: four catalog/index rows (two photos, two videos). Two assets
have explicitly reviewed people; three each have dates, regions, tags and captions.
One DNN assignment and one blocked tag association are excluded. One photo has
both ready prepared JPEG variants; one video has a verified prepared MP4/chunk
manifest. Other descriptors remain unavailable. Counts establish fixture behavior
only, not real family metadata coverage or model completion.

The replay checks initial disabled discovery/catalog, explicit synthetic enable,
combined filters, reviewed identity separation, missing-date semantics, exact
prepared JPEG and MP4 Range, legacy-original denial, and shared disable. It
restores disabled control and verifies all original output hashes at completion.
It never exposes a port. Use the guide's commands or:

```sh
python docs/security/evidence/home-discovery-export/replay.py --source-root "$PWD"
```

## Remaining gates

No real ID mapping or coverage was resolved. This exporter accepts only bounded,
standalone snapshots and does not obtain a coherent live SQLite snapshot. Native
Windows snapshot support/resource limits, approved real publication selection,
private alias and assignment review, current hide/delete freshness, actual
caption/tag/metadata counts, prepared photo/video coverage and native quality
remain unverified. Hash/dimension checks do not prove codec behavior or projector
playback. Slow/blocking I/O and memory need native operational limits; a disk
failure can leave a new disabled partial directory requiring separate review.

Next is independent source review, followed only under separately scoped authority
by the operational gates in [the publication plan](HOME_DISCOVERY_PUBLICATION_PLAN.md).
The current v1 service/DNS/APK path is preserved. No Windows access, real-data
read, models/conversion, credentials, launcher/service change, network exposure,
Android edit, configured-origin build, device installation, push or merge occurred.

Changed implementation files:

- `scripts/export_home_discovery.py`
- `scripts/build_home_discovery_export_fixture.py`
- `tests/security/test_home_discovery_export.py`
- `docs/security/HOME_DISCOVERY_EXPORT.md`
- `docs/security/evidence/home-discovery-export/replay.py`

Evidence adds this return plus `source-inputs.json`, `verification.json` and
`pinned-replay.json` under the linked export evidence directory.
