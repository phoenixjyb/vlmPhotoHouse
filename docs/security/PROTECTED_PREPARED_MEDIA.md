# Protected viewing candidate (20 September 2026)

Local source candidate only. No Windows service, account permission, media file,
preparation job, Home publication or installed APK is changed by this work.

## Playback contract

`GET` and `HEAD /assets/{id}/playback?library={library}` use the existing protected
cookie/Bearer transport and require current `library.read` for an active mapped
asset. `media.original.read` is not needed or granted. The existing `/media`
original route is unchanged. Anonymous Home URLs are never returned or followed.

When explicitly configured, this route returns an already prepared H.264/AAC
(or silent H.264) SDR MP4, within the existing 1080p/24-hour/32-GiB publication
metadata envelope. It performs no encoding, GPU work, model call or full-file
preload. Codec validity comes from the preparation receipt's qualified output;
physical playback remains a device gate.

Successful responses are `video/mp4`, `Cache-Control: no-store`, `Accept-Ranges:
bytes`, a strong SHA-256 ETag and exact Content-Length. Single byte ranges return
206 and Content-Range; suffix/open-ended ranges work. Invalid/multipart ranges
return 400; out-of-file ranges return 416 with `bytes */N`. A matching strong
If-Range permits 206; other validators return the complete 200 representation.
HEAD verifies the first requested chunk and sends headers without a body.

Errors use `{ "detail": "..." }`, never paths or alternate media URLs:

| Status | Meaning | Client behavior |
| --- | --- | --- |
| 401 | Missing/expired/revoked identity or asset/library access | Clear affected viewing state; do not retry anonymously |
| 404 | Video not prepared, source missing, or unsupported source | Show unavailable; keep the library usable |
| 409 | Source, pinned index or prepared bytes changed | Close reader and require refreshed/requalified preparation |
| 429 | All four prepared readers in use | Respect Retry-After: 2; bounded user-visible retry |
| 503 | Provider absent, filesystem/permission failure or invalid runtime | Show unavailable; no original fallback |

First-chunk integrity and authorization are checked before success headers.
During a stream each next 4-MiB chunk is hashed and current access/source identity
is checked before and after the read. Revocation/corruption then aborts the stream;
HTTP cannot replace headers already sent. Clients must show an interruption and
close the player. No later chunk is read under a retained login authorization. One already admitted
chunk may finish if revocation happens between its final check and network send;
revocation cannot retract bytes already authorized/in flight.
Each reader holds bounded chunks; four slots limit concurrency. No persistent
Android/browser cache is introduced. Access checks use short DB transactions;
none spans client transfer or a hash operation.

## Private offline index

`scripts/export_protected_videos.py --database DB --workspace READY_WORKSPACE
--out NEW_PRIVATE_INDEX` reads existing full-library preparation receipts and
checks the selected job digest, ready-row/receipt agreement, current asset metadata,
source SHA-256, prepared SHA-256 and every chunk digest. Hash reads are bounded to
4 MiB, with a per-file elapsed-time budget (default 900 seconds); this is not an OS
interrupt for a stalled filesystem read. The tool neither re-encodes nor copies
media. It writes one new file, mode 0600 on POSIX, and refuses overwrite. It fails
on inconsistent ready entries rather than silently publishing stale media. It
exports only selected `ready` video rows; pending/failed rows remain unavailable.
It materializes a bounded ID list, then releases each SQLite read before hashing.
It rechecks each source/ready row afterwards, avoiding a long-lived snapshot that
would block writers or WAL checkpointing while large files are hashed.

The index contains asset IDs, source filesystem identity, relative attempt directory
and prepared video metadata. It is private operator state, never a public catalog
or source-controlled artifact. Source identity is checked against the currently
authorized original descriptor on each request/chunk. Index replacement requires
an explicit new provider/service configuration; it is not hot-reloaded. Prepared
files may be shared read-only with the existing preparation workspace; replacing
an attempt invalidates that entry. Restrict all index/workspace writers to trusted
operators. Metadata identity detects ordinary changes, not a hostile administrator
preserving inode/size/timestamps; prepared bytes additionally have per-chunk hashes.

## Reviewable activation steps (not executed)

1. Select the current Windows source DB and ready preparation workspace. Run the
   exporter under the intended service/operator identity, record coverage/digest,
   and protect the index with a Windows ACL. Do not stop/restart captioning.
2. Add `--prepared-index INDEX --prepared-root WORKSPACE --prepared-sha256 DIGEST`
   to the reviewed `staging_app.py` launcher. These flags are all required together.
   Existing launchers remain off. `--check-config` checks syntax only; it does not
   open media, validate service permissions or start a listener.
3. For photo quality, independently add `--photo-cache NEW_PRIVATE_CACHE`. Keep
   cache/index/prepared roots separate from originals, thumbnail roots, incoming
   uploads, config, database, keys and discovery indexes. The launcher now checks
   all these overlaps. Photo rendering retains its 4-GiB available-RAM floor,
   1-GiB sampled RSS ceiling, one worker, deadline and bounded disk cache.
4. Qualify an extracted package and the actual Windows service identity with a
   rotated/large photo (cache miss and hit), a long video (start/seek/end), denied
   originals, revocation and changed-file cases. Source tests are not this proof.
5. Adopt the new contract in the protected phone/WebUI before enabling the feature.
   Phone v12 remains usable on its current contract but does not call `/playback`.
   Enable high-quality photo delivery only against a qualified backend. Test the
   resulting physical phone; Home/TV playback remains a separate access surface.

Rollback: restore the previous launcher/package and remove the new optional flags.
No schema migration, original modification or grant change is required.

## Prepared gallery filter (candidate 15)

`GET /assets?library=...&media=prepared_video` lists only active, authorized video
IDs in the configured immutable prepared index. Filtering precedes counting and
pagination. It does not probe video bytes, encode files, add permissions or expose
paths. Membership authorization happens before catalog inspection. No provider
returns 503; a changed index returns 409 rather than a misleading empty library.
An empty valid index returns an empty page. Existing all/image/video requests are
unchanged. This is preparation catalog membership, not a promise of uninterrupted
playback: source identity, file access, hashes and authorization are rechecked by
the existing playback route. Clients must still handle its refusal states.

The phone control is a separate off-by-default build option, enabled only after
candidate 15 is deployed. Earlier configured apps remain compatible.
