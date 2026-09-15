# Discovery delivery source return

Base: b9f7383ea8fcdbca86210463b7f5c674c68ea92f.
Branch: codex/home-discovery-v3. One writer; separate from the active Windows
preparation source and the dirty captioning checkout.

Added the optional discovery/v2 composition and actual synthetic response examples.
Search now returns current v3 media capabilities without changing discovery/v1,
existing media contracts, account access, caption selection, metadata review rules,
workers, runtime or live publication. Source and metadata admission share one
publication; tests prove both source-index change and disable fail closed.

Validation: 46 discovery/export/delivery tests pass, including seven new delivery
checks and unchanged frozen v1 examples. All 15 existing on-demand delivery checks
pass. These are CPU-only in-process tests, including actual synthetic image decode,
preview reuse, original bytes, prepared/direct Range and denied-peer tests.
No sockets, real database, models or Windows service changes. Test environment:
CPython 3.12, repository access-test and preparation dependency locks.

Next gates: native consumer replay, UI/device tests, a reviewed real metadata index
with measured coverage and confirmed people mappings/assignments, then separately
qualified deployment. Full-library metadata parsing, slow-client admission and
service memory/latency must be qualified before enabling this source candidate.
