# Owner membership review and revocation — slice 9

Local synthetic checkpoint after `53b2eb6`, 2026-09-09. Continues the
[invitation web gallery](WEB_INVITATION_GALLERY.md).

An active approved owner can list members of the selected active library and
revoke a non-owner member. Readback is scoped before count/paging; it includes
phone login, role, status, expiry, availability and an exact decimal-string revision.
Passwords, session records and other libraries are never included. Viewer and
system-operator status alone do not grant access to this directory.

| Route | Contract |
| --- | --- |
| `GET /libraries/{library_id}/members` | Owner policy; bounded `page`/`page_size`, no query credentials |
| `POST /libraries/{library_id}/members/{account_id}/revoke` | Owner policy; exact string `revision`; web Origin + session-bound CSRF |

The UI displays the phone and library in a separate confirmation before sending
revocation. The server atomically checks the displayed revision, revokes access,
clears the original grant and writes an audit record. Stale confirmation returns
409 and cannot overwrite a newer decision; the UI refreshes and requires another
review. Owner/self/foreign-library targets cannot be revoked through this operation.
Role transfer, approval and original grants have no route in this interface.

A member's next protected read is denied; the account can still read its own
session and accept a future deliberately reissued invitation. Already downloaded
files or authorized in-flight responses cannot be recalled. The UI states this
limit at the review point. Pending member-list responses have independent generation
checks, so pagination and library changes cannot merge older lists.

## Verification

**132 Python security tests passed in 15.262 seconds**, including eight new tests
for owner-only scoped readback, redaction, CSRF, stale decisions, audit atomicity,
owner protection, changed account/library/membership state and strict request shape.
Inventory/runtime identity checks agree on **152 entries / 23 active routes**.

**13 real Chromium checks passed** through the port-free ASGI pipe bridge with
migrated synthetic SQLite. The new check changes membership after the owner opens
confirmation, verifies conflict without revocation, then confirms a fresh review
and observes the recipient lose gallery access. Failed-logout browser checks also
inject cross-tab/history events and verify photos stay hidden. No external page
requests or browser errors were observed. The owner review screenshot was rendered
and visually inspected.

See [browser results](evidence/member-slice9/result.json) and
[owner review](evidence/member-slice9/owner-revocation-review.png). All names, phone
labels and photos in this evidence are synthetic fixtures, not real family data.

Next: an explicit existing-database/runtime adapter with missing/wrong-schema denial
and no environment discovery, automatic schema creation or live connection during
imports. The default entry point stays closed. Deployment/TLS/proxy/logging,
bootstrap/mapping and recovery remain separately reviewed gates; no live host,
real database/media, model, mobile repository, listener, push or merge was used.
