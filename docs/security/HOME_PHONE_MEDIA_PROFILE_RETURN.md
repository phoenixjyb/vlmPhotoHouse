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
