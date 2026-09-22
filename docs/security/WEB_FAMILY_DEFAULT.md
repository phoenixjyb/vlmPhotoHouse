# Family as the default web library

The secured web client opens the available library whose stable ID is `family`
on a fresh sign-in or page load. Family also appears first in the picker. This
does not depend on translated labels or alphabetical server response order.

An accessible library selected manually remains selected on refresh and session
revalidation. A change of account clears that selection. If Family is absent,
closed or otherwise unavailable, the existing first-accessible fallback applies;
with no available memberships, no gallery request is sent. Catalogue labels do
not grant access beyond the authenticated session's available memberships.

Source base: `00c848f6e498372d1644a4ecf739ff3a09a6dd46` in isolated branch
`codex/web-family-default-v34`. The separate pending people-merge candidate is
not part of this branch. No API, database, membership or contract change.

Validation on 22 September 2026: all 63 actual Chromium/ASGI browser checkpoints
passed, including three new Family-selection checkpoints. Covered fresh login,
cookie restoration on reload, manual selection, EN/ZH presentation, inaccessible
Family fallback, and no-access media denial. Desktop English and narrow Chinese
rendered screenshots were inspected. All HTTP was intercepted into a local pipe
bridge backed by migrated synthetic SQLite; no listener or live account used.

Run `tests/security/test_web_browser.cjs` with existing `PLAYWRIGHT_MODULE` and
`PH_BROWSER_PYTHON` dependencies. Serving this change requires a separately
authorized protected web package deployment; these checks do not establish live
service or physical phone acceptance.
