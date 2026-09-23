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

## Worker lanes and resource policy

Use one persistent, single-instance Windows scheduled task per qualified lane,
with boot and recovery triggers, a separate stop flag, and a dedicated log. The
CPU image lane handles only approved-upload thumbnails and perceptual hashes;
the video preparation lane handles only probe and bounded keyframe extraction.
The existing caption-only task remains its own lane. Image and face inference
need strict local model identity, a verified effective CUDA provider on the
RTX 3090, a RAM/VRAM guard, bounded input decoding, and no stub fallback. The
Quadro P2000 is available for a measured secondary workload, but it is not a
default provider. GPU indices must be resolved on the Windows host before
pinning; do not infer CUDA index from the order in `nvidia-smi`.

An idle worker polls for new approved tasks; families never have to ask for a
one-off processing command. Each lane must refuse a task if its upload was
unassigned, its library is inactive, the source hash/size changed, or the
installed database revision is different. Processing errors use bounded
retries followed by a visible terminal state. Stop or memory pressure must
never turn a partial derivative into a ready asset. The target host had roughly
64 GiB RAM, an RTX 3090 and a Quadro P2000 at the September 23 read-only check;
these are observations, not a qualified concurrency or model-load budget.

Confident automatic face identification is a separate post-embedding lane. It
must use active, checksum-bound, versioned references from manually labeled
faces in the same library. The `person_auto_match` source handler is scoped to
one approved upload and leaves uncertain matches unassigned for review; it
never makes an unnamed person or overrides a manual positive or manual-null
decision. The current database's large legacy face-vector sets have unknown
model provenance, while the known LVFace cohort is still shadow-only. Thus the
automatic identification producer/worker stays disabled until a reviewed
reference cohort and conservative threshold are calibrated on Windows. Face
detection and embedding may be qualified independently of identification.

At the September 23 read-only Windows inventory, the InsightFace SCRFD and
recognition files and the LVFace ONNX model were present, but a local
OpenCLIP/CLIP checkpoint was not found in the current app checkout, model root,
or user model cache. The strict image/video embedding lanes require an
explicit checkpoint path, SHA-256, model version, and selected GPU UUID, and
therefore stay off until one is installed and natively verified. The current
face lane provides a read-only preflight and deliberately refuses `--execute`:
its model-inference step still needs a hard child-process memory and time
envelope. Source-only checks cannot substitute for that native gate.

`scripts/build_approved_worker_package.py` builds an immutable-commit,
source-only ZIP with a fixed worker allowlist and SHA-256 for each file. It does
not install dependencies, configure Scheduled Tasks, or activate any lane. An
operator must first verify the extracted manifest and native interpreter,
database revision, roots, model checksums, exact GPU UUID/provider, queue
ownership, stop flags, and a synthetic Windows canary. Only then should the
continuously polling CPU and video-preparation workers be registered as
separate startup/recovery tasks. The existing caption task stays separate.

Source tests cover the approval release and scoped CPU, video,
image-embedding, and video-embedding workers. Face detection/embedding, CLIP
image/video embeddings, and confident-person matching remain disabled until
their specific gates above pass. A `pending` queue row alone does not prove a
derivative was made.

## September 23 Windows activation record

The final source revision is `ff6d2de1a1419aa8ad5792ceafbbb3bf75309e22`.
The approved-worker source ZIP has SHA-256
`1a5d3f9f36dd16133ead4408031cdb71cf42c3347518483c199d6204c25a1cf5`;
the protected API source ZIP has SHA-256
`7762bad3876513820ff6d42e872313ee9ce4890880d13964632c9a6f75d1d794`.
Every extracted manifest member was checked on Windows before use. The API
candidate passed its configuration syntax check, then the existing protected
API task switched to the pinned release. Its old task XML was saved beside the
candidate for rollback. The unauthenticated protected endpoint continued to
return 403 after the switch; this does not establish authenticated family
acceptance. The caption task remained on its existing release and running.

The synthetic Windows canary generated its own image, two-second video and
SQLite database. Under the installed interpreter and real ffmpeg it finished
`thumb`, `phash`, `video_probe`, and `video_keyframes`, and enqueued `caption`
and `video_embed`; it opened no family media or production database. A separate
`--once` CPU live canary finished one approved `phash` task. The persistent
`PhotoHouse Approved CPU v37 SYSTEM` and
`PhotoHouse Approved Video Prep v37 SYSTEM` tasks now run at startup, poll for
new approved work, and have five-minute failure restart settings. At the
post-activation read, both tasks and the API/caption tasks were running; no
`thumb`, `phash`, `video_probe`, or `video_keyframes` task remained pending or
running. Old failed/dead task records were preserved.

This activation covers CPU image derivatives and video preparation only.
Image/video vector embedding is still held for a local checkpoint and exact
GPU/provider canary. Face detection/embedding is still blocked by its hard
child budget and provenance review, and confident person matching by the
active reference cohort and threshold calibration. At the same read, four
`embed` and three `face` tasks remained pending. No claim of full media
processing or automatic identity assignment is made by this activation.

## September 23 GPU embedding activation follow-up

The approved GPU worker source is now pinned to
`65976f6f05076ae14b104972a11a86de754fbcda`. Its 18-file source package has
SHA-256 `4a252fcebbc27bc3704a4c8a1c3b4fa72f1e52f96bf36e0fb1eb8df9afda1a95`;
all extracted member hashes were verified on Windows. The CPU and video-preparation
tasks, protected API, and caption task remain on their earlier installed releases.

The local CLIP checkpoint is bound by SHA-256
`f807d82432eb6c926694b401cb55d5e40fad5a7df507e6a12cf9a83e7ac81ab0`.
It was derived locally from the SHA-verified OpenAI ViT-B-32 TorchScript archive
by extracting its tensor state dictionary and removing three TorchScript-only
metadata entries. The original archive and intermediate conversion were retained
separately. No model weights are in the source ZIP. Strict Windows preflight
verified the OpenCLIP provider and physical RTX 3090 UUID
`GPU-0095f55f-02a4-be5c-dfd0-01da4c727729`; the isolated child sees logical
`cuda:0`. The GPU child has a hard 4 GiB Windows Job Object memory ceiling, a
task deadline, a host free-RAM floor, and a shared lock across image and video
embedding lanes.

One live `--once` image embedding canary finished, then the persistent image
task drained the remaining three approved items. All four new 512-dimensional
files matched their database checksums. A synthetic native video embedding
canary finished a 512-dimensional normalized vector using generated frames and
a disposable database; it opened no family media or production database. The
video lane had no approved pending item at activation. Both persistent tasks,
`PhotoHouse Approved Image Embed v37 SYSTEM` and
`PhotoHouse Approved Video Embed v37 SYSTEM`, are registered for startup with
five-minute failure restart and were running after their shared-lock update.
The previous actions were saved as task XML for rollback. An image-worker exit
code 2 observed during initial concurrent startup led to an explicit bounded
Windows lock wait; the updated tasks require a later stability read and a new
approved-video live test for full runtime acceptance.

Face detection and face embedding remain **off**. Their preflight now requires
the approved upload receipt and exactly one active library, but `--execute`
still refuses because inference lacks an isolated child with a hard time and
memory boundary, atomic publication/recovery, and verified physical-to-logical
CUDA mapping. Three approved face tasks remained pending at the GPU activation
read. Confident named-person assignment additionally needs a reviewed,
same-library reference cohort and threshold calibration; uncertain faces will
be left for manual review. Historical failed/dead records were not retried.

The next face-lane candidate must parse exact task payloads without letting
malformed legacy JSON stop polling; claim only an approved, uniquely assigned
asset; and pin the detector pack and LVFace model by local checksum. The parent
must supervise one inference child under a Windows Job Object and deadline.
That child may decode and infer into private staging but must not open the
production database. For the physical RTX 3090 selected as `cuda:1`, the child
must see logical CUDA device zero and pass the provider's effective-device
check. After inference, the parent must recheck source, approval, cancellation,
and task ownership in a short transaction before publishing crops or vectors
and follow-up tasks. It also needs a single-owner crash-recovery rule for
`running` tasks and orphaned files. Native synthetic detection-to-embedding,
timeout, memory-cap, and rollback tests are required before activation. The
older mixed executor must remain off so it cannot race this lane.
