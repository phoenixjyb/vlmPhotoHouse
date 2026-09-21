# Admin upload review

The secured WebUI now has an **Upload review / 上传审核** button beside the library
selector and Refresh. Select the destination family library, open the inbox,
review a photo and its uploader, then choose **Approve upload / 批准上传**. The
confirmation shows the target library, current reader count and how many members
already have original-download permission. The interface works in a desktop or
phone browser. It does not add a native Android admin screen.

Approval moves one JPEG/PNG from the private member incoming area into the single
configured originals root and assigns it to the selected library. Normal family
library/gallery access then applies, without granting original-download permission.
Refresh the family gallery to see it. Pending uploads stay invisible to normal
member media routes. Anonymous TV publication remains a separate operation.

## Authorization and scope

- Review requires **both** a registered operator and current approved owner
  membership in the target library. Owner status alone does not grant review.
- The uploader must still be an active approved member of that target library.
  Uploads currently carry no chosen target library. Consequently, an upload can
  be reviewed in any library for which both these conditions hold; the first
  successful approval assigns it to exactly one library.
- Review creates a short-lived signed plan bound to the actor, library, asset,
  upload provenance and current audience revisions. The browser treats it as
  opaque. It sends no filesystem paths or account credentials in URL parameters.
- Applying rechecks the session, operator, owner and uploader inside the same
  SQLite writer reservation as the existing promotion operation. Fresh checks
  run again before commit. Failed file moves are compensated before releasing
  the reservation. Process death/storage failure still requires operator recovery.
- A retry of the exact successful plan returns success only after current
  authorization and checking that the upload is still assigned to this library.
  It creates no second file, mapping or receipt. A stale plan or later offline
  unassignment/reassignment requires a new review.
- Cookie writes retain origin/CSRF checks; bearer authentication remains explicit.
  Responses are private/no-store. No deletion, rejection, job retry, account grant,
  raw incoming download or automatic TV publish route is added.

## Explicit activation

Existing configurations keep the feature disabled. Add the boolean
`"upload_review_enabled": true` to an explicitly reviewed staging configuration.
It requires the existing `incoming_root` and **exactly one** original root, so
there is no implicit destination choice across multiple roots. No schema change
is needed. Continue supplying the existing `--photo-cache` launcher option for
private previews. The launcher shares one bounded `PhotoCache` instance between
normal photo delivery and incoming previews; it retains its worker timeout,
memory/disk admission and single-worker bound. The UI loads previews serially.

The initial reviewed routes are:

| Method | Route | Result |
| --- | --- | --- |
| GET | `/admin/uploads?library=…&page=1` | Ten pending member uploads per page |
| GET | `/admin/uploads/{asset_id}/preview?library=…` | Bounded JPEG derivative, never incoming original bytes |
| POST | `/admin/uploads/{asset_id}/review?library=…` | Signed single-photo plan and audience counts; body `{}` |
| POST | `/admin/uploads/{asset_id}/approve?library=…` | Apply reviewed plan; body `{"plan":"opaque JSON string"}` |

An ordinary owner receives an empty inbox with `can_review=false`. Members cannot
read the inbox. Rendering rechecks actor/uploader authorization and source identity
before returning a preview. No membership means no metadata, preview or approval.

Only registered uploads appear. Complete files left by older failed uploads are
not silently imported or removed. Approval does not mean all ingestion, face,
embedding or caption tasks have finished; it neither starts extra workers nor
changes their state. The installed phone upload format is unchanged. Its existing
accepted/pending receipt is not a live approval-status subscription.

After successful approval, the WebUI refreshes the first, unfiltered gallery page
and focuses the approved photo when it is on that page. This also clears a prior
story search; the inbox still shows the approval result. For uploaded photos with
no capture date, protected gallery ordering uses the upload receipt time as its
fallback. A real capture date always takes precedence, and the response still
returns the actual `taken_at` (including null); no capture metadata is invented or
rewritten. Unregistered undated assets keep their prior relative ordering.
This shared gallery behavior applies to protected WebUI and phone clients without
a new APK. It does not change anonymous TV catalogs or make pending uploads visible.

## Verification and delivery

Run the focused Python tests with the approved CPU test environment:

```
PYTHONPATH=tests/security python -m unittest test_upload_review test_upload \
  test_upload_retry test_promotion test_promotion_transfer test_closed_application \
  test_inventory test_staging_config test_staging_launcher test_staging_package \
  test_protected_photo_delivery
```

`tests/security/test_upload_review_browser.cjs` uses actual Chromium, the protected
ASGI app and a temporary migrated SQLite database through a pipe bridge. It checks
private previews, audience confirmation, mobile layout, lost-response retry,
post-approval gallery access and stale-session cleanup. The tiny synthetic JPEGs
use the real isolated decoder; this browser harness supplies synthetic resource
admission and Fetch Metadata. Live Windows admission/TLS and real family acceptance
remain separate checks. `test_web_browser.cjs` covers the existing member/owner UI.

The initial local qualification passed 176 Python checks and 58 existing browser
checkpoints. The upload-specific browser flow and contract replay are recorded in
the accompanying delivery handoff. Activation requires a reviewed package, the
explicit configuration opt-in, protected API restart and a real admin browser
check. Creating the package does not approve any real pending upload.
