# Browser boundary adversarial review — slice 11

Local synthetic checkpoint after `55f0c59`, 2026-09-09.

## Finding and change

A synthetic sibling-origin page could embed a thumbnail using an already valid
member cookie when Fetch Metadata and Origin were absent. The old request guard
accepted absent Fetch Metadata. This was a browser embedding defense gap, **not
anonymous access or a membership bypass**: the request still needed the valid
cookie and approved library mapping.

Cookie reads now require a positive `Sec-Fetch-Site: same-origin` signal or the
explicitly configured Origin. Untrusted same-site/cross-site origins, missing
signals and direct cookie media navigations lacking that signal fail closed.
Cookie mutations retain their Origin and session-bound CSRF requirements. Native
clients continue to use explicit bearer transport without browser metadata.
This requires compatible browser/proxy behavior; legacy browsers that omit these
signals are not silently allowed. Actual Safari/device/proxy acceptance is open.

Every closed-boundary response also carries `Cross-Origin-Resource-Policy:
same-origin`. The intercepted Chromium environment did **not** enforce that header
in isolation, so browser enforcement of CORP over a real network is not claimed.
The server-side fallback was implemented and tested independently of CORP.

## Test limits made explicit

DevTools-intercepted request headers in this environment omit network-generated
Fetch Metadata. The browser bridge now explicitly models it from the requesting
frame origin for normal same-origin requests, and records the modeled request
count in its results. The sibling probe deliberately omits it and receives 403.
The browser genuinely renders and executes the UI and handles HttpOnly cookies;
this fixture does not prove actual network header emission, TLS or CORP behavior.
The Python contract tests independently verify missing/wrong signals deny before
domain access, same-origin signals allow, and native bearer remains supported.

See the [successful pre-fix reproduction](evidence/browser-boundary-slice11/before.json)
and [post-fix browser evidence](evidence/browser-boundary-slice11/after.json).
All origins, identities, credentials, storage and images are synthetic.

## Additional reviewed bounds

All access routes reject query strings longer than 1024 bytes before domain/media
lookup. Account routes still reject any query string. The closed ASGI boundary
suppresses body bytes on HEAD responses, including denials, without depending on
an HTTP server or client to discard them. Privacy/resource headers also cover
unreviewed routes. The inventory's stale gap wording now distinguishes current
replacements from retired unsafe implementations and current unverified gates.

**146 Python security tests passed in 22.910 seconds** and **14 Chromium contract
checks passed**. The 152-entry inventory, runtime route identity and diff checks
pass. No skipped/expected-failure tests were added. The browser's modeled transport
signals and the remaining real-network gate are limitations, not hidden passes.

The runtime remains opt-in and the default application closed. No real host,
database/media, model, mobile edits, listener, deployment, push or merge occurred.
Next: reviewable offline provisioning/mapping planning and continued preservation
checks; actual grants and live application require their separate reviewed workflow.
