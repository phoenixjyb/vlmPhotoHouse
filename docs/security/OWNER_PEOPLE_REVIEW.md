# Owner people review and safe renaming

Follow-up: [library management](LIBRARY_MANAGEMENT.md) retains explicitly owned
zero-face people. Legacy unowned orphans still need a reviewed import; the
original active-face-only directory contract below describes the earlier slice.

Local source slice, 2026-09-15. This extends the protected WebUI; it is not a
deployment or completion of the legacy management-tool transition.

## Available behavior

The selected library's active, approved owner can open **Manage people**, search
saved names, page through results, review face crops and open the corresponding
asset. The panel has English and Chinese labels and a narrow-screen layout.
Viewer, contributor and system-operator status alone do not grant this capability.

| Route | Contract |
| --- | --- |
| `GET /admin/people?library=...&page=1&q=...` | Owner-only directory, literal substring search, 25 people per page |
| `GET /admin/people/{id}/faces?library=...&page=1` | Owner-only scoped face references, 25 per page |
| `PUT /admin/people/{id}?library=...` | Exact string fields `display_name` and `revision`; cookie requests require Origin and session-bound CSRF |

Counts, paging and face references are computed only from active assets mapped
to the selected library. They do not expose global face counts, embedding paths,
vectors, bounding boxes or source paths. Crop and parent-asset requests retain
their existing protected-media checks. Search handles Chinese text and treats
`%` and `_` literally. Responses are not cacheable.

The directory intentionally excludes orphan person records, people with no active
mapped faces, and unassigned detections. It is not a global saved-name dropdown.
Making those records available needs an explicit ownership/import workflow.

## Rename safeguards

Person records are currently global legacy records. A name may be changed only
when **every face reference** is mapped exclusively to the chosen library.
Shared or unmapped references make the name read-only, including references on
inactive assets. A user-visible name is never used as an identity or merged with
another person automatically.

Saving rechecks owner authorization, visibility, exclusivity and an opaque
revision in one write transaction. A stale revision returns 409 without changing
the name. Protected rename audit sequence numbers prevent a rename-away-and-back
from making an older revision valid again. External writers must still maintain
the legacy `updated_at` field; this slice does not qualify concurrent legacy
management writers for production.

Only `persons.display_name`, `persons.updated_at` and an audit event change.
The audit records the person ID in the action, not the private name. An audit
failure rolls back the update. Face assignments, cached counts, embeddings,
caption tasks and media files are not modified. Names must be nonblank, trimmed,
at most 128 characters and contain no control characters or surrogate codepoints.
That is a name-field bound, not a caption/story word limit. Long legacy names are
flagged as shortened previews and are not silently truncated on save.

The UI renders names as text. Independent request generations prevent old search
results from replacing a newer search or reappearing after logout/library change.
A save whose response is lost is not automatically retried; the user must refresh
and review the current name. SQLite work has a three-second progress deadline;
this is not a full-library latency qualification or an operating-system resource cap.

## Local verification and remaining gates

The dedicated ASGI tests use migrated synthetic SQLite and cover scoped visibility,
paging, literal search, authorization, CSRF, stale revisions, shared/unmapped
references, atomic audit failure and closed unreviewed mutations. The Chromium
suite uses a port-free ASGI bridge and synthetic images. It also checks face crop
opening, Chinese names, stale-edit conflicts, HTML-as-text, delayed searches and
logout cleanup. English desktop and Chinese narrow-screen renders were inspected.
Fetch Metadata headers are modeled by that bridge, not proven on a live proxy.

Final local run: **677 security tests run, OK with 5 skips** (four native-Windows
checks and one separate legacy-worker dependency check); **27 Chromium checks
passed**, including the new people flows. The route inventory and whitespace
checks also passed. These results do not establish native Windows or GPU behavior.

The protected staging source allowlist includes the new `people` module. There
is no new schema migration. The capability inventory contains 188 method/path
entries; the protected application has 35 registered routes.

No Windows connection, live database write, password setup, service restart,
caption-worker change, push, merge or deployment was performed for this slice.
Live full-size mapping/performance, actual credentials/TLS, and family-device
acceptance remain separate gates. Face assignment, new-person creation, merging,
album management and the protected WebUI cutover are **not implemented here**.

Follow-up: [protected single-face assignment](OWNER_FACE_ASSIGNMENT.md) is now
implemented locally in a separate slice. Its atomic aggregate invalidation and
additional worker-isolation gates do not change this original rename contract.
