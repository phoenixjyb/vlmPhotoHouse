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

Current qualification state: source tests cover the approval release and
scoped CPU, video, image-embedding, and video-embedding workers. There is no
Windows native canary or active new media Scheduled Task in this source
candidate. Face detection/embedding, CLIP image/video embeddings, and
confident-person matching must remain disabled until their specific gates
above pass. A `pending` queue row alone does not prove a derivative was made.
