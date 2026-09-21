# Server discovery and upload qualification — v21

Date: 2026-09-21. Source under qualification:
`b61a20896ea1f45dca34954e70af0cdf49dbaae9` on
`codex/discovery-review-v21`. Android client candidate remains
`0a7599ccb90ec98c41f3f845822a6f9cc2842b6f` (Phone/TV v21).

## Result: neither feature is approved for live activation

The current Windows protected API still runs candidate14 source
`4d1de0f06bae4f2e5342134db6a4b847657d2484`. Its 105 package file hashes verified.
The active configuration has no incoming root and no discovery indexes. Its
source selection and configuration digest stayed unchanged during qualification.
No production account, session, library mapping, media or task row was created.

Live HTTPS chain/hostname checks passed: UI 200, anonymous session/discovery 401,
and disabled upload POST 503. These are availability/denial checks, not an
owner-authenticated upload or Android acceptance result.

## Windows evidence

103 synthetic tests passed under SYSTEM using the existing protected Python
runtime and isolated test-only HTTP client dependencies. Production site-packages
were not changed. Suites:

- `test_discovery_index_producer`
- `test_discovery_wiring`
- `test_upload`
- `test_promotion`
- `test_promotion_transfer`

[Sanitized machine-readable evidence](evidence/server-discovery-upload-v21/qualification.json) records the measurements.

Initial attempts exposed two harness limitations: the minimal runtime lacks the
test HTTP client, and long nested test paths exceeded Windows path limits during
promotion. A separate test dependency directory and short private synthetic temp
root resolved these; no global Windows path setting was changed. Final suite:
103 run, zero failures/errors/skips. Synthetic tests do not prove real-library scale.

The proposed incoming root is outside all served media roots, with inherited ACLs
removed and SYSTEM/Administrators full control only. A valid synthetic PNG was
accepted under SYSTEM with matching SHA-256 and byte count. An upload-only candidate
configuration validates, but is not selected by the live service. Actual synthetic
C: to E: and E: to C: transfers preserved bytes. All four generated probe copies
were removed after hash/ownership checks; the proposed incoming root is empty.

## Discovery blocker

The real library has 27,842 mapped assets. The unchanged producer refused its
first asset projection after 2.016 seconds under the default 2-second budget.
No real discovery artifact was published.

The query plan uses the existing covering index on `(library_id, asset_id)` and
asset primary-key lookup, plus a temporary B-tree for `ORDER BY a.id`. A separate
read-only qualification variant using `ORDER BY m.asset_id` completed the asset
projection in 1.907 seconds but exceeded the same total budget during captions at
2.047 seconds. That variant was not installed or committed as a product change.
Adding a duplicate composite index is not the remedy. Total row/byte budget fit
was not established because time expired first.

There is also a freshness issue: date/media-only indexes still digest captions,
faces and tags. The active caption worker can invalidate such an index; the service
then returns changed/unavailable rather than stale results. Stopping captioning
would not solve future metadata edits. A scalable projection and explicit refresh
strategy need qualification before enabling this feature. Budgets were not raised.
Reviewed people/place input is still a separate requirement for those facets.

## Upload blocker

A different-batch retry of identical bytes creates two files but only one asset
and provenance record. The second response identifies the first asset, enqueues
zero new tasks, and echoes the new batch even though database provenance retains
the first batch. The extra file has no database reference. This was independently
reproduced in disposable local state and on the proposed Windows incoming volume.
The existing same-batch duplicate test does not catch this case.

Repair must prevent unreferenced duplicate copies and keep receipts consistent
with authoritative provenance. Any cleanup must distinguish a newly created
unreferenced candidate from the canonical file, same-batch reuse and racing
writers. Do not simply unlink every path when `tasks_enqueued == 0`: that can
remove the stored file. Preserve the separately documented recoverable-orphan
behavior on database failure. Add different-batch, same-batch and concurrent retry
regressions before repeating native qualification.

## Delivery boundary

A source-only 105-file package was built and all manifest hashes verified locally:
archive SHA-256 `57eecf8509034cfdca2da70551c7c49f96527a70fcbdf47f64ff819672eaed70`.
This package is not deployed. The one-shot qualification task and empty short
temp root were removed after completion. No recurring monitor was installed.
Available system RAM at cleanup was 48.92 GiB. Production tasks were untouched. Windows test artifacts and private
configuration receipts stay in the private workspace handoff, not this repository.

Next work is the duplicate-file repair and discovery scale/freshness design,
followed by another server qualification. Candidate15 activation, a real signed-in
member journey, processing/publication and physical-device testing remain separate.
No API restart, caption/encoding control, publication, push or merge was performed.
