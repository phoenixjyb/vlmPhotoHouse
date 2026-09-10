# Caption response budget — Android readiness follow-up

2026-09-09. Implemented locally at **`0cf5058acdb25224b26847fb55670307f8113181`**
on `codex/backend-android-readiness`. No deployment, mobile edits, credential/data
access, network listener, push or merge. Update on 2026-09-11: Android completed
the coordinated repin to `87a60b475b37b1d6873cd977bcb6e7254472da7e` in its isolated
worktree at `1d4fc49c043d553df510c52b9a368ee0313398c6`.
The first staging candidate includes the later [launcher](STAGING_LAUNCHER.md)
at `87a60b475b37b1d6873cd977bcb6e7254472da7e`. Its caption/application and frozen
fixture source hashes match the tested caption commit; no Kotlin rerun is claimed
for the launcher, which adds no API or contract changes.

## Behavior and limits

`GET /assets/{asset_id}/captions?library=…` retains its existing authorization,
ordering and JSON fields. After authorizing the parent asset in the same SQLite
snapshot, it returns an ordered prefix of up to 20 captions whose **complete
encoded JSON response is at most 524288 bytes**. Size uses the same JSONResponse
serializer as the endpoint, including UTF-8, JSON escaping, metadata and envelope.

- A row is included only if the complete candidate response fits; an exact-limit
  response is allowed. No partial JSON, split UTF-8, skipped priority row or client
  limit increase is used.
- `has_more` is true whenever current rows were omitted for either row or byte
  limits. It is false for an empty result or when all current rows fit.
- `truncated` keeps its existing per-text meaning: stored text exceeds the 8192
  character excerpt. Dropping a whole row does not mark other rows truncated.
- The database contents are not shortened. Superseded captions and private model,
  path or diagnostic metadata remain excluded. Denials still precede child reads.

This is a bounded caption preview. The endpoint already has no caption cursor or
next-page operation; `has_more` signals omitted content and does not make that
content retrievable. A later full-caption feature needs an explicit contract.
This change does not claim an aggregate budget for every other JSON endpoint or
establish real-media thumbnail sizes, TLS, deployment or phone readiness.

## Fresh synthetic evidence

| Check | Result |
| --- | --- |
| Focused library tests | 13 pass, including ASCII/CJK/emoji/quotes/backslashes/control characters, exact byte limit and one-byte-over, ordering, empty results and omission versus truncation |
| Backend security suite | 201 pass, no failures or skips; existing authorization and closed-default checks retained |
| Route completeness | 152 method/path entries; no new API routes |
| Actual Kotlin adapter | 14 pass: six actual ASGI payloads plus oversized rejection, each with known and unknown content length |
| Previously failing Unicode case | 493328 bytes, 15 intact captions, `has_more=true`; previously 657749 bytes and rejected by Android |
| Escape-heavy case | 492748 bytes, 10 intact captions, `has_more=true` |
| Exact boundary | 524288 bytes accepted; valid JSON with one extra whitespace byte rejected as TOO_LARGE |

[Machine-readable evidence](evidence/android-readiness/caption-budget-candidate.json)
records the exact candidate commit, clean checked source, changed source hashes,
unchanged contract/source hashes, mobile source hashes and compiler/runtime hashes.
The original [failing probe](evidence/android-readiness/source-asgi-probe.json) and
[initial verification](evidence/android-readiness/verification.json) remain historical
evidence. Their failure and earlier 38-case baseline replay have not been rewritten.

The Kotlin check compiles the **unchanged current mobile protocol/API sources** with
the backend-owned check into a temporary directory using existing cached dependencies.
It feeds actual temporary SQLite/ASGI response bytes to an OkHttp application
interceptor and exercises the real adapter's read/deserialization paths. Java 17
network/listen checks deny socket access; no Gradle daemon or server is launched.
Temporary generated JSON/classes are removed. This is not a TLS or Android-device
test, nor a claim that the mobile frozen pin has been updated.

## Reproduction and Android owner handoff

From this backend checkout, use the existing **repo-root security environment**:

```sh
"$PHOTOHOUSE_PYTHON" -m unittest discover -s tests/security -p test_library_reads.py -v
"$PHOTOHOUSE_PYTHON" -m unittest discover -s tests/security -q
"$PHOTOHOUSE_PYTHON" scripts/security_inventory.py
"$PHOTOHOUSE_PYTHON" scripts/android_caption_budget_check.py \
  --mobile-root "$PHOTOHOUSE_MOBILE_SOURCE" \
  --java "$PHOTOHOUSE_JAVA_17" \
  --maven-cache "$PHOTOHOUSE_EXISTING_MAVEN_CACHE" \
  --evidence-output "$PHOTOHOUSE_SYNTHETIC_RESULT"
```

These variables are explicit local paths, not discovery defaults. Select the
Gradle `modules-2/files-2.1` cache containing the versions in the script; missing or
ambiguous dependencies fail without downloading anything. The JVM test requires
Java 17 for its no-network guard. The probe's explicit `--candidate` mode permits
only the reviewed caption module/test checksum delta; all other frozen source and
contract checks stay enforced. It records a candidate review, never a repin.

The Android owner reviewed caption fix **`0cf5058acdb25224b26847fb55670307f8113181`**
and staging candidate **`87a60b475b37b1d6873cd977bcb6e7254472da7e`**, updated the
shared pin/checksums and replayed the 38 baseline cases unchanged. Its return also
records 14 Kotlin boundary cases and eight verifier regressions, retaining one
strict accepted backend pin. The pre-repin probe above still deliberately requires
the original consumer snapshot; its historical `consumer_repin_completed=false`
does not describe the completed mobile repin. See the current backend return for
new operator/package source identity; those additions leave frozen API hashes intact.

The explicit launcher and [operator/source package](OPERATOR_TOOL.md) are now
implemented, along with [new-file initialization, backup and in-memory migration
rehearsal](DATABASE_PREPARATION.md). Existing-database migration apply/recovery, target/origin/audience,
CPU Windows runtime lock, host/ingress isolation, backup/restore rehearsal and
physical-phone authorization/acceptance remain open. The closed default remains.
