# Resumable video-only preparation with optional NVENC

The library coordinator accepts `run --kind video`, preserving pending photos
and its existing per-asset checkpoints. A finished video selection reports
`video_queue_drained`; it does not claim the full mixed library is ready or
published. Existing ready derivatives are verified and reused on resume.

New jobs may select `create --encoder h264_nvenc --gpu 0`. CPU/libx264 remains the
default. The encoder and numeric GPU index are pinned in job.json. Changing source,
encoder, GPU or profile requires a fresh job with a hash-pinned carry checkpoint;
do not modify an existing job to change encoders. Historic CPU checkpoints remain
usable as read-only carry inputs, including verified videos.

The NVENC output is still H.264 High/4.1, 8-bit 4:2:0, limited range, at most
1920x1080/30fps plus AAC audio, with the same metadata stripping, faststart,
full decode, duration, source identity, preview and chunk-hash checks. NVENC uses
p4/HQ, VBR/CQ23, 8 Mbit/s video maximum rate and a 16 Mbit buffer. CQ23 and CPU
CRF23 are different controls; equal visual quality or byte size is not implied.
Decoded dimensions/aspect/orientation and sample-range conversion remain in the
existing CPU filter path. This accelerates encoding, not 8K CPU decoding or hashes.

Use one session on an explicitly verified idle GPU. Disable AQ and lookahead for
this profile; the operator should verify device identity, driver/encoder support,
available VRAM and coexistence before activation. RAM/RSS/disk/time/stop-file guards
remain active. An NVENC encode failure stops the job as `nvenc_encode_failed`,
retaining its working entry; it never silently switches to CPU or marks unchecked
bytes ready. A resume retries the stopped item with the same pinned configuration.

Qualification must include actual native NVENC encoding and the unchanged media
verification chain. Synthetic/source tests do not establish GPU support, speed,
perceptual quality or projector playback. Keep live publication and protected phone
activation separate. No original is replaced and no application database is written.
