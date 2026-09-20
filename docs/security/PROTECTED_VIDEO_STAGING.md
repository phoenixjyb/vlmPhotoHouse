# Selected protected-video staging

When an existing preparation workspace is inside the configured thumbnail root,
it cannot be used as a protected playback root. Keep the launcher's independent
root checks. `scripts/stage_protected_videos.py` creates a separate, bounded copy
of selected ready playback files for qualification; it does not change a service.

The tool requires an existing staging configuration, a ready preparation
workspace, explicit asset IDs, a new destination and a separate new index path.
There is no implicit all-library selection. At most 100 assets and 32 GiB per
invocation are accepted; the default byte budget is 2 GiB with a 2 GiB disk reserve.
Both destination parents must already exist and be direct paths. Index, media,
original, thumbnail, database, incoming, configuration and key boundaries are
checked before writing. Windows ACL qualification remains an operator step.

Use `--plan` first with absolute platform-native paths:

```sh
python scripts/stage_protected_videos.py \
  --config /private/server.json --workspace /private/derived/ready \
  --destination /private/protected-sample --out /private/protected-sample.json \
  --asset-id 101 --asset-id 102 --plan
```

Planning reads only bounded preparation metadata, selected row receipts, file
sizes and disk space. It does not hash original/video contents or prove decoder
compatibility. Its report explicitly says `source_hashes_verified: false`.
After reviewing the exact paths, IDs and disk budget, `--stage` in place of
`--plan` authorizes the local copy operation for that invocation. A command in
this document is not authorization to run it on the live Windows host.

Staging copies MP4 and chunk files into fresh attempt directories using bounded
4-MiB reads and a per-file time budget. It snapshots only selected ready receipts
and job rows into a new private SQLite file. No original bytes are copied. The
unchanged exporter then verifies those selected original hashes, asset metadata,
preparation receipts, video hashes and every chunk hash before producing an index.
It retains the real original's filesystem identity, never the copy's identity.
Live databases are read-only and no live read transaction spans copying/hashing.

The final index appears only after successful export/validation, through exclusive
publication from a sibling `.pending` file. Only the tiny owned index is briefly
hard-linked; playback bytes are independent copies, never hard links to active
preparation outputs. Existing outputs or pending files are refused. A failure
leaves the new destination marked `INCOMPLETE` and is not retried over that folder.
Do not activate an incomplete folder. Inspect and explicitly clean up owned partial
artifacts before choosing fresh names. No automatic cleanup can remove user data.
If only removal of the intermediate index fails after successful publication,
the tool reports success with `pending_index_retained: true`; that small file can
be removed by the operator later. Failure to remove `INCOMPLETE` happens before
final index publication and prevents it. Hard-link support for the selected index
volume must be qualified on Windows; an unsupported filesystem is refused.

The source workspace and destination must remain trusted-operator writable only.
The checks detect ordinary replacement, symlink and provenance changes; they do
not claim isolation from a malicious administrator racing filesystem operations.
Free space is checked before staging and reserved conservatively, not locked
against other processes. Disk failures refuse the operation without publishing
an unverified index. The deadline cannot interrupt a stalled OS filesystem read.

## Delivery and qualification

This is a separate operator helper. It is not added to the pinned candidate 14
runtime manifest and does not change its API contract or installed Android build.
Distribute it with its own checksum alongside the unchanged qualified runtime
package; use that package's exporter/provider dependencies. The operator Python
environment must satisfy the package dependencies. Do not import legacy workers.

After staging, qualify the actual Windows service principal's read permissions,
the exported index pin, a longer video (start/seek/end), revocation and changed-file
refusals. Activation requires the new candidate package and explicit prepared-root,
index and digest launcher arguments. Retain the prior launcher for rollback. No
schema migration, account grant or original permission change is needed. Home/TV
publication, captioning and encoding remain separate operations.

## Local verification

17 staging tests and eight exporter regression tests pass with synthetic media.
They cover independent-copy playback, preserved input hashes, original identity,
read-only planning, no live DB read lock during copying, corruption and source
change refusal, selection/disk limits, path aliases/overlap, incomplete-copy
handling, racing existing output and publication/cleanup fault ordering.
Windows service-principal ACLs, filesystem hard-link support and physical playback
are separate checks; no local test claims those gates are complete.
