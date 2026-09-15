# Protected owner face assignment

Follow-up: [library management](LIBRARY_MANAGEMENT.md) adds new-person creation,
unassignment and durable library ownership under a newer schema. The evidence
below describes the earlier single-face-assignment slice.

Local implementation, 2026-09-15. Extends [people review](OWNER_PEOPLE_REVIEW.md).
This is a manual, single-face correction to an existing person, not migration or
deployment of the full legacy management interface.

## User flow and contract

An active approved library owner opens a photo, expands **Review face assignments**,
chooses a detected face, searches/pages through saved people, then confirms the
specific person ID and displayed name beside a repeated face preview. Both the face list and person picker use
25-row pages. Unassigned faces are included. Shared-person targets remain visible
but disabled; names not linked to active faces in this library remain excluded.
No new person, unassignment, merge, bulk relabel or automatic propagation is offered.

| Route | Scope and request |
| --- | --- |
| `GET /admin/assets/{asset_id}/faces?library=...&page=1` | Owner, active mapped parent, bounded faces and opaque revisions |
| `POST /admin/faces/{face_id}/assignment?library=...` | Exact string fields `person_id`, `revision`, `person_revision`; cookie Origin/CSRF |

Saving rechecks current owner membership, active parent mapping, source person,
target person and both revisions in one write transaction. Both affected people
must have exclusively in-library face references, including inactive references.
The target must already be visible in this library. An unmapped, orphan or
cross-library ID cannot be used to import or disclose a person implicitly.

The face revision binds its parent, bounding rectangle, creation time, current
assignment/provenance, latest assignment-history event and current displayed-name
revision. The separate target revision protects against choosing a name that was
changed after display. Revision mismatches return 409 with no mutation. Existing
legacy writers remain an operational isolation concern, not made safe by a token.

## Atomic effects and worker boundary

The transaction changes the selected face's person ID, sets `label_source=manual`,
clears its automated score, records old/new provenance and actor in
`face_assignment_events`, updates both affected global person counts and appends
an access audit. A failed audit/history/aggregate update rolls back the assignment.

Person aggregates become stale after membership changes: the affected persons'
legacy centroid pointers are cleared and versioned person artifacts marked
`stale`. Files are retained, not deleted or rewritten. Face embeddings, crops and
originals are unchanged. Aggregate recomputation needs a separately qualified
workflow; this slice does not silently reuse the old centroids or enqueue work.
The source person remains in the database even if its last face moves away; such
an orphan needs a future explicit ownership workflow to become selectable again.

Known pending/running `face`, `face_embed`, `person_cluster`, `person_recluster`
or `person_label_propagate` jobs cause 409. The check and write share a SQLite write
reservation. Caption tasks do not block this operation and are not changed.
This is not an OS fence against unmanaged writers, jobs whose type/state is wrong,
or future tasks. Before deployment, isolate legacy management/face writers and
qualify worker behavior with the new aggregate-invalidating metadata. Do not start
automatic face work under this source-only authorization.

The browser ignores results for a closed or replaced viewer and clears picker
confirmation when search/page selection changes. A lost save response is not
retried automatically: refresh the face from the server and review the result.
Names are rendered as text. Private data is not persisted in browser storage.

## Verification and remaining delivery gates

Synthetic ASGI tests cover scoped/unassigned/paged reads, denied roles/IDs,
stale face/name/history revisions, atomic history/counts/aggregate invalidation,
audit rollback, CSRF, strict request shape, face-worker refusal and unchanged
caption tasks. Chromium exercises actual UI/API calls through the isolated pipe
bridge, not a live network deployment. Real family media and credentials are not
used. Native Windows, full-library performance, live TLS and device acceptance
remain unverified for this slice.

The full local security run completed **685 tests, OK with five skips** (four
native-Windows checks and one separate legacy-worker dependency check). The
dedicated people/assignment module passed 21 tests. Final browser evidence and
render checks are recorded separately from native/runtime qualification: all
30 Chromium checks passed, the desktop/Chinese mobile confirmation views were
visually inspected, and both document and dialog horizontal-overflow checks
passed. The three source-package tests passed after the final UI adjustment.

The protected app has 37 routes and the inventory has 190 method/path entries.
No schema migration or additional package module is needed. No live account,
password, database, caption job, service, schedule, push or merge was changed.

Next management gaps include new-person/orphan ownership, explicit unassignment,
album management and their user acceptance. Keep the live cutover gated on the
agreed management coverage and the [first-owner setup sequence](OWNER_SETUP_GATE.md).
