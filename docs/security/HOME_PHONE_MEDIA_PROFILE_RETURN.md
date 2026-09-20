# Phone SDR preparation profile

`phone-sdr-v1` is an explicit offline preparation option for phone delivery.
It preserves the existing source hash, checkpoint, originals and publication
validator while encoding video at a maximum 1280×720 frame size, a 2 Mbps target
and 3 Mbps video cap. AAC-LC stereo uses 96 kbps at 48 kHz. The output remains
the existing faststart MP4/H.264/yuv420p/AAC wire format; no cloud, adaptive
streaming or HLS path is introduced.

Select it when creating a fresh job:

```text
python scripts/prepare_home_library.py create ... --profile phone-sdr-v1
```

The resolved quality fields are stored in `job.json` and validated on every
load, resume and publication pass. A changed quality definition is rejected as
an invalid pinned job, and carry-forward requires the seed to use the same
quality. Existing ready attempts are only reused after their source and
derivative hashes pass the normal checks; selecting this profile never
implicitly re-encodes an existing workspace. A phone profile therefore needs a
new job (with an explicitly compatible carry checkpoint when applicable).

The legacy `pilot` and `library-sdr-v1` profiles retain their existing encoder
arguments and dimensions. The profile is CPU-safe with `libx264`; explicit
`h264_nvenc` remains available and still fails closed on encoder failure.

## Validation and delivery boundary

Local replay: 51 tests pass across `test_home_media_profiles`,
`test_home_library` and `test_video_batch_encoder`, including an actual synthetic
1080p-to-720p encode, default-profile compatibility, job tamper rejection, matching
phone seed reuse and rejection of a default-quality seed for a phone job.
The first aggregate command used a nonexistent encoder module name; the corrected
command above passed. These are disposable Mac source checks, not Windows GPU or
family-media acceptance.

The profile commit is `7a194568b4c42dab8ccf3c23e2619fa3d0f37a7f`.
It follows prepared-gallery source `789bdf0ca9f69787fa3e5d13db3d666f4931e0a3`
and contract pack `98d87f3df7cbfdb78367e60fcfa8fa0a117a2e25`.
The contract replay passes 86 captures, 116 source hashes and seven payload hashes;
all 78 prior captured cases are unchanged. Related prepared-gallery, media-filter,
native-contract and prepared-video tests pass (34 tests). The extracted candidate
15 API package passes seven ASGI, 19 operator and nine disposable database checks.

A separate operator staging pass copied and verified 100 prepared videos for a
future protected index. It did not activate that index, change the running API,
replace original media or restart caption/preparation workers. It used existing
prepared renditions, not this new phone quality. Real-media phone-profile
qualification, service-principal checks, activation and physical Android playback
remain separate delivery gates. The API package is pinned to the contract-pack
commit; the new offline profile requires its own operator payload.
