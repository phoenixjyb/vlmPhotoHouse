# Invitation sign-in and scoped web gallery — slice 8

Local synthetic checkpoint following `712a27d`, 2026-09-09. The safe web shell uses
the same account, membership, gallery and media endpoints as native clients.

## Implemented behavior

- Phone/password sign-in and phone/password/invitation registration. Phone numbers
  are unverified login labels; include the country code. No SMS, WeChat or delivery
  service. Registration requires an owner-created, phone-bound code and joins only
  the selected library as a viewer. Existing accounts accept invitations after login.
- Owner code creation/cancellation in the selected library. Codes are displayed for
  manual private delivery, expire in 24 hours and grant no original downloads.
- Library selection, paged thumbnails, safe caption viewing and separately granted
  original download links. No original fallback for a missing cached thumbnail.
- English/Chinese interface text; responsive phone/desktop layout. UI language does
  not claim to translate caption content. Unfinished albums/search/voice/admin
  features are not exposed in this screen.
- HttpOnly Secure SameSite=Strict session cookie, in-memory CSRF, same-origin fetch,
  no persistent browser token/data storage, third-party assets or external fonts.
  CSP restricts resources to this origin, prohibits framing, inline scripts, objects
  and workers. Legacy search/admin links drop query text and reach the safe shell.
- Logout/library switches invalidate pending reads and clear visible media/codes.
  A separate viewer generation prevents delayed captions from overwriting a later
  asset. Failed logout hides photos and permits retry, without claiming revocation
  succeeded. Cross-tab messages contain no credentials and cannot unlock that state.
  Background/page-history events clear media; returning views recheck the session.
- Failed session checks clear stale HttpOnly cookies so expired sessions do not trap
  returning users in a login loop. Profile `available` reflects current server time,
  membership and library state; it remains a UI hint, never authorization authority.
- Asset/caption IDs use decimal strings in JSON to preserve full SQLite integer IDs
  in JavaScript. The server still parses/range-checks numeric path IDs.

The old `backend/app/ui` files remain byte-for-byte preserved. `/ui` now serves
`backend/app/ui/access/`; the retired interface is not publicly mounted.
The default application still has no connection/media runtime and stays closed.

## Actual evidence

**124 Python security tests passed in 14.363 seconds**; the 150-entry inventory and
JavaScript syntax/diff checks passed. Three transport/UI security tests and one
full-width SQLite-ID test were added. There are no skips or xfails.

**12 Chromium browser checks passed**, with the real rendered UI, actual ASGI
handlers and fully migrated synthetic SQLite. Browser HTTP requests are fulfilled
through a stdin/stdout bridge; no HTTP listener or deployed server is started.
Unknown hosts are aborted, browser background networking/DNS is disabled, and the
Python fixture blocks network sockets/process execution. All photos are generated
JPEG test cards. The browser reports zero external page requests and page errors.

Checks cover invitation registration/cancellation, HttpOnly cookie/storage state,
caption HTML as text, original denial, Chinese mobile layout, stale viewer/gallery
races, logout/retry, revocation and expired-session recovery. Screenshots were
visually inspected. See [machine-readable results](evidence/web-slice8/result.json),
[sign-in](evidence/web-slice8/sign-in-desktop.png),
[desktop gallery](evidence/web-slice8/gallery-desktop.png), and
[Chinese phone layout](evidence/web-slice8/gallery-mobile-zh.png).

Reproduce with the root `.venv` security dependencies, test-only Pillow 12.1.1, and
an existing Node Playwright 1.62.1/Chromium installation:

```sh
.venv/bin/python -m unittest discover -s tests/security -q
.venv/bin/python scripts/security_inventory.py
node --check backend/app/ui/access/app.js
# PLAYWRIGHT_MODULE may name an already installed Playwright module directory.
node tests/security/test_web_browser.cjs
```

The browser harness installs/downloads nothing. It writes synthetic screenshots and
results to a temporary directory, or to an explicit `PH_BROWSER_ARTIFACTS` directory.

## Remaining gates

This is local browser/ASGI/SQLite evidence, not a deployed account system. Reviewed
connection/media configuration, offline bootstrap and deliberate asset mapping,
TLS/proxy/logging, backup/recovery, Windows filesystem checks and real mobile
acceptance remain outstanding. Owner membership review/revocation still needs HTTP
and UI integration; the domain operation exists. Password/phone recovery, owner
transfer, authorized jobs/voice, albums/search and standalone services remain closed
or unprotected as individually recorded in the inventory. Never remount old handlers.

No Windows/Mac mini, real database/media, model, mobile edit, deployment, listener,
push or merge occurred. The web test uses browser-generated Origin/cookie behavior,
but does not claim real TLS certificates or proxy acceptance.
