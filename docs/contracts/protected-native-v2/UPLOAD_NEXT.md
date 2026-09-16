# Next proposed slice: authenticated resumable contribution core

Proposal only. No upload route is implemented or advertised by this pack. The
existing legacy upload/transcription routes remain closed. This narrows the
September 15 phone-family-contributions plan to a reviewable backend-first slice.

Before adding routes, review a distinct `media.upload` permission and owner grant
workflow; viewer access, story.write and anonymous TV access do not imply upload.
Use one current authenticated account/library scope at every operation. Propose
operations before freezing endpoint names: create batch/item, query received
offset, append bounded chunk, finalize, read processing state, cancel incomplete
item. Return typed machine errors and authoritative server limits in that new
contract. These capabilities must stay off until their implementation is adopted.

Suggested pilot: one active transfer per phone and at most 4 MiB per chunk. Exact
file/batch/account/global storage quotas, incomplete-item expiry and duration
limits need review; they are not approved production defaults. No one-minute
video limit is assumed. An authenticated limits response must not reserve storage
or create an upload. Quotas must also be enforced independently on the server.

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
