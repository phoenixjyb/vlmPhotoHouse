# Member-upload processing after approval

Source candidate. This document does not authorize a Windows deployment, task
restart, queue rewrite, or media processing run.

New uploads write their asset and provenance outside every library and create
starter tasks in `awaiting_review`. Task executors claim only `pending` tasks, so
the member's bytes remain unprocessed while an operator reviews the upload.
Approval moves the file into the originals root, assigns one library, and changes
only that asset's staged starter tasks to `pending` in the same database
transaction. A failed approval rolls the task change back; replay does not
enqueue or reset work. Existing pending, finished, failed, and dead tasks are
left untouched.

The image starters are `embed`, `phash`, `thumb`, `caption`, and `face`. A successful
`face` handler can enqueue `face_embed` for detected faces. A video starts with
`video_probe`, which can enqueue `video_keyframes`; that handler can enqueue
`video_embed` and `caption`. Image SHA-256 is calculated during upload, so `phash`
is a separate perceptual hash, not the integrity hash. Video scene and segment
jobs, image tags, dimension backfill, and library-scoped person assignment have
separate producers or policies; approval does not enqueue them.

This change schedules work but does not qualify an executor. The active caption
worker can claim captions only. The existing mixed executor has unsafe fallback
embeddings and unbounded image decoding, so it must not be enabled on live family
media as a shortcut. A separately reviewed worker needs an exact task allowlist,
bounded input/decoder and memory budgets, a qualified face/embedding provider,
failure visibility, and Windows native tests before activation. Thumbnail and
perceptual-hash work can be qualified independently of face and vector work.

Before a cutover, stop the relevant old workers, verify the installed source and
schema, and read the current queue. An older build can leave `pending` jobs for
unapproved uploads; this source change holds only tasks it creates. Refuse media
worker activation until such legacy rows are absent or are scoped and held under
a separately reviewed migration. Already-running legacy tasks require a separate
drain review. Preserve failed/dead task states; do not silently retry them.
