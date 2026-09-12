# Media cancellation ownership — slice 14

Local synthetic checkpoint after `2d22c53`, 2026-09-09.

The final review reproduced a descriptor leak when a request task was cancelled
while its worker was opening an authorized file. The worker could return the open
file after the awaiting coroutine had already exited; the coroutine's local
`opened` variable was never assigned, so its previous finally block could not close
that descriptor. This was an observed resource-ownership failure, not an access
policy bypass.

A thread-safe file lease now owns the result before it crosses the await boundary.
Cancellation closes the lease immediately; a late worker result closes in that
worker. A normally returned descriptor remains pinned for streaming and closes on
success, denial/range failure or disconnect. No path is reopened and the existing
current membership/parent/root checks remain in place. This does not claim to
interrupt an already-running filesystem call or recall previously delivered bytes.

The regression test pauses the real authorized open after it creates a descriptor,
cancels the actual response task, releases the worker, and requires the descriptor
to be closed with no response sent. It failed before this fix and passes afterward.
Existing descriptor/disconnect/range/root and revocation tests also pass.

Observed: **162 Python security tests passed in 20.239 seconds**, including all
26 closed-application checks; **14 Chromium UI/ASGI contract checks passed**. See
[browser results](evidence/media-cancellation-slice14/browser-result.json), including
the explicit modeled Fetch Metadata / unverified real-network limitation.
Inventory remains **152 entries / 23 active routes**. No skips or xfails were added.

The retired ledger remains 84/84 failed denial requirements and is intentionally
separate from these active-entrypoint tests. No live runtime, database/media, model,
mobile edit, network listener, deployment, push or merge occurred.
