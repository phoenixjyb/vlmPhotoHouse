# Candidate.25: resumable photo and video contribution

The proposal below is retained as historical planning context. Candidate.25
implements the resumable core with the exact wire shape in CONTRACT.md and
14 frozen synthetic cases. The phone accepts multi-file and SAF-folder JPEG,
PNG, MP4 and MOV selection; it reviews count, bytes and skipped files before
sending, warns on metered networks, and has a private persistent queue with
explicit resume, pause, retry and confirmed cancellation. The app hashes and
transfers files in bounded streams. The server writes at most 4 MiB chunks to a
persisted account-bound ledger; the old 25 MiB one-shot photo route stays for
older clients. The backend migration head is `a8d4c2e6f901`.

Arrival means a private incoming receipt, not library admission. A current
owner/operator must approve and assign the asset. Video probe/keyframe/caption
work is queued after intake, while prepared H.264 playback and TV publication
remain separate operational pipelines. Offline reviewed backup and migration,
Windows package installation, worker qualification, HTTPS endpoint rollout and
a real-phone journey are still delivery gates; none is implied by the source
or emulator checks. Abandoned partial transfers need a reviewed cleanup policy.

## Historical proposal through candidate.24

# Next proposed slice: authenticated resumable contribution core

Proposal only for the **resumable** core. It is no longer true that no upload route exists: a
first, deliberately narrower slice shipped in candidate.7, and it is described here so the
remaining proposal is read against what is actually built.

## What candidate.7 implements

`POST /uploads` — one whole-file request, no chunks and no resume. It is mounted in the default
application but answers `503` until a deployment opts in with an explicit incoming root, so no
existing deployment gains a write surface by accident.

- **Not library-scoped.** The photo is written into the uploader's own incoming folder and into
  **no** library, so it is invisible to every member until an operator promotes and assigns it.
  That is what makes accepting uploads from any approved member safe, and it is why the route
  carries no library in its path.
- **The incoming root must sit outside every original root**, enforced at construction, so an
  unassigned upload is unservable by construction rather than by an authorization check.
- **Type comes from the leading bytes, not the declared filename.** Only JPEG and PNG are
  accepted, because the protected renderer supports those two. A per-file byte cap and a
  header-declared pixel cap are enforced before anything is written, from a bounded header parse with no
  decoder for a decompression bomb to target.
- **Provenance** is recorded per upload (account, label, batch, original name, SHA-256, bytes) and
  an audit row is written. Dedup is scoped to the uploader's own incoming uploads, so a hash that
  matches an asset already in a library never returns that asset's ID.
- **Promotion is a separate reviewed operation** (`promote_and_assign_uploads`) that moves the
  bytes into the originals root and writes the mapping in one step — assigning without promoting
  would leave `assets.path` outside `original_roots`, so the photo would be in a library and
  unviewable. `unassign_library_assets` reverses it, including the file move, and
  `reassign_library_assets` moves a photo between libraries.

**Deliberately absent, and still unbuilt:** resumable chunks, offset/hash negotiation, cancel of
an incomplete item, quotas, incomplete-item expiry, batch-to-many-assets Stories linking, and
audio/transcription. The owner has explicitly declined caps and quotas for now, so the per-file
byte cap and the audit row are the only controls.

## Retry repair in candidate.16

Same-account incoming retries return the original stored batch and label, even
when the caller selected the file again in a new batch or renamed their account.
They preserve one canonical file and enqueue no duplicate work. Publication and
promotion compensation share a writer reservation. Partial/changed files and
redirected paths are refused; a matching complete orphan can be adopted. Automatic
historical orphan cleanup and crash reconciliation are not included.

## What the rest of this proposal still asks for

The remaining work is the resumable core. Before adding routes, review a distinct upload grant
workflow; viewer access, story.write and anonymous TV access do not imply upload. Use one current
authenticated account scope at every operation. Propose operations before freezing endpoint
names: create batch/item, query received offset, append bounded chunk, finalize, read processing
state, cancel incomplete item. Return typed machine errors and authoritative server limits in that
new contract. These capabilities must stay off until their implementation is adopted.

Suggested pilot: one active transfer per phone and at most 4 MiB per chunk. Exact
file/batch/account/global storage quotas, incomplete-item expiry and duration limits need review;
they are not approved production defaults. No one-minute video limit is assumed. An authenticated
limits response must not reserve storage or create an upload. Quotas must also be enforced
independently on the server.

Implement with synthetic SQLite and temporary files first:

1. Reserve bounded storage; receive into staging outside watched media roots.
   Server selects safe paths/account IDs; never use phone numbers, arbitrary
   client filenames, traversal, alternate streams or reparse points as paths.
2. Serialize each item's chunk writes; require expected offset and chunk digest.
   Exact retry is idempotent, conflicting replay is a typed conflict. Check
   revocation/expiry again for every chunk and finalize.
3. Finalize only after byte length, full SHA-256 and bounded content/type checks.
   Journal intent before a same-volume no-overwrite move. Reconcile every crash
   point across filesystem move, asset insertion, library mapping and receipt.
4. In one database transaction record authorized asset mapping, contribution
   attribution and a durable intake outbox. At-least-once delivery must have one
   effective registration/task per item. Deduplication is scoped; never reveal
   another library's private asset ID or create an unauthorized mapping.
5. Expose saved, processing, ready and stage-failed separately. Inference/encoding
   happens outside the HTTP request. Cancel of an incomplete upload must not
   delete an already finalized original. Do not automatically retry GPU jobs.

Acceptance tests: traversal/Windows names, cross-account/library access, replay,
offset/hash conflict, concurrent finalize, disk full/quota, expired/revoked
membership, process crash at each finalize boundary, partial batches and scoped
deduplication. Start from fake intake events: no models, GPU or real watchers.

Before live rollout, separately qualify the Windows service principal's staging
and final ACLs, same-volume move/reparse protection, watcher registration and
SMB/anonymous TV audience. Uploaded originals/stories must not silently inherit
an unintended public/share audience. Native Android needs persisted selection
access, cancellation/resume, same-account reauthentication and explicit metered
data consent; LAN and remote operation need their own device evidence.

Batch-to-many-assets Stories linking is a later schema slice. Audio ingestion,
speech-to-text and optional polishing are deferred. Preserve original audio/text,
raw transcript, proposed polish and accepted revision separately. Any future
inference stays on the home Windows machine with explicit resource admission;
no third-party processing or hidden cloud fallback.

## Candidate.17 admin review

The secured WebUI now offers an explicitly enabled operator/owner upload inbox.
The same phone upload is still accepted privately; only a confirmed admin review
moves it into the selected family library. See `docs/security/ADMIN_UPLOAD_REVIEW.md`
for activation, authorization and the still-separate native admin/status UI scope.

## Candidate.24: my uploads

The implemented account-only `GET /uploads?page=N` read exposes honest receipt states
for manual refresh. It does not add resumable transfer, video upload, transcription,
job retry or inferred processing progress. See CONTRACT.md for the exact wire shape.
