# Home catalog readiness browsing v1

An opt-in extension of the selected home v3 catalog. No source files, preparation
queues, publication state, access grants or running services are changed by browsing.

`GET /home/v3/catalog` accepts `browse=1`, with optional:

| Field | Values | Default |
| --- | --- | --- |
| availability | all, ready | all |
| order | catalog, ready_first | catalog |
| media | all, photo, video | all |

The existing page/page_size/revision requirements apply. A page after the first
requires the current catalog revision. Changing a selection starts at page one.
Unknown/duplicate fields or enum values fail with 400. Selection fields without
`browse=1` fail, so an older server cannot silently pretend to apply a selection.
Requests without browse retain the byte shape and ordering of the old contract.

Opt-in responses add exactly `browse: {version:1, availability, order, media,
ready_total, matching_total}`. Values echo the applied request. Matching count is
after media selection and before availability; ready count uses the same scope.
The top-level total/has_more/items describe the final filtered, ordered pages.
Both counts refer only to the published selection and current original policy.

Ready means a delivery path is admitted by the pinned publication/source metadata:
photo with prepared display or indexed on-demand photo; video with a prepared
stream or an indexed compatible direct stream AND original permission. Video
thumbnails alone are not playable. Originals and direct video are never implicitly
granted. Files still being prepared, or finished but unpublished, are not included.
This is delivery admission, not proof that the file is still present or that a
particular device decoder succeeds. Byte reads retain their existing checks/errors.

Media and readiness predicates run before pagination. Ready-first groups ready
items before the remainder, retaining descending numeric asset ID within each group.
This is newest-added ordering, not a claim about capture dates. Iteration uses
bounded catalog metadata and source-index lookups; no source stat, media open,
decoder, cache population or job is started. Existing four-request admission limit
and 512 KiB JSON response limit remain in effect.

## Android compatibility and remaining parity

The matched TV build explicitly enables `photohouseTvBrowseEnabled=true` with v3.
The client checks echoed selection/counts, order, uniqueness, media kinds, readiness
and exact page size. Selection changes cancel previous work and reset the revision
and page. Stale responses cannot replace the new selection. Refresh and later pages
carry the same selection. Public default remains off pending deployment qualification.

This extension does NOT apply to protected `/assets` or protected discovery. Phone
currently lacks a prepared-derivative descriptor and authorized byte route for a
viewer without original permission. Anonymous home metadata/URLs cannot fill that
gap. A phone extension needs an explicit, library-scoped derivative provider and
readiness projection, current account/membership/source binding, authorized Range
reads, and revocation tests before the same controls can be enabled. Full phone
readiness parity and composition with people/date/tag search remain outstanding.
TV v3 discovery was already disabled; this change does not change its contract.

## Validation and deployment gates

`python -m unittest discover -s tests/security -p test_readiness_browse.py -v`
compares retained examples with actual synthetic ASGI responses, tests ready items
beyond page one, disjoint pagination, count/media intersections, permission changes,
invalid inputs and disabling the feed. Existing original/preview/Range tests remain
applicable. Fixture data is synthetic only.

Stage source and matched opt-in APK together only after existing Limited Windows
service-account checks. Preserve old launcher/source for rollback. No preparation
job restart or mutation is needed. This source change does not authorize deployment,
phone installation, push/merge, audience expansion or publication by itself.

The authorized Windows v13 rollout and its bounded evidence are recorded in
[TV v13 server qualification](TV_V13_SERVER_20260914.md). Physical TV acceptance
and protected-phone parity remain separate gates.
