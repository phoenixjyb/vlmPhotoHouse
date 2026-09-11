# Memories viewer deployment — 2026-09-11

## Delivered scope

UI source commit: `4f1ff1b0e1d13fa14b980e744f730b907407fdb9`.

The viewer now has whole-image Fit, original-resolution Actual size, wheel and
button zoom, drag/scroll pan, double-click reset, keyboard sizing controls, and
a separate browser fullscreen toggle. Controls and status text are bilingual.
Originals load only on demand; an unsupported original leaves the preview
available and explicitly disables Actual size. Each new photo starts fitted.

The clipping defect was reproduced with a synthetic portrait: an image grew to
1477 pixels inside a 479-pixel stage whose overflow was hidden. Explicit canvas
dimensions and a constrained grid row now give images correct fit and scroll
bounds. Captions retain their own scroll region.

## Windows delivery boundary

At 09:36 +08:00, only `backend/app/ui/{app.js,styles.css,index.html}` were
overlaid onto the active `photohouse-01ade47-reviewed-eight` API release.
This release therefore retains backend source `01ade47` with UI source
`4f1ff1b`; it is not an untouched source snapshot of either commit.

The old files and before/after manifests are retained under the Windows
PhotoHouse log directory in `viewer-ui-4f1ff1b0e1d1`. Rollback means restoring
those three `.before` files, verifying their served hashes, and refreshing the
browser. No database rollback or model restart is needed for this UI change.

Delivery verified HTTP 200 and byte-for-byte hashes from both Windows loopback
and the Mac viewing connection:

| File | SHA-256 |
| --- | --- |
| `app.js` | `50dba5a9f44843db38a10d393641aeea97bd1e53866b5ddb17e007469f5940c9` |
| `styles.css` | `673fea1590927c66daf63f9550a15151aad67fbaa28df6d12d5fc84bea176737` |
| `index.html` | `119af9ac15a2d2e9943ac4fa15a4bee594d9654f0ba1597d5c169a776e88cd9b` |

API listener PID `23284` and Qwen listener PID `10460` were unchanged across
the deployment. API/database/worker checks passed, and Qwen3-VL remained busy
with inference. No caption queue, model, face processing, wake schedule, or
monitoring configuration was changed.

## Private viewing

- On this Mac: <http://127.0.0.1:18002/ui>
- On Windows: <http://127.0.0.1:8002/ui>

The Mac mini relay and Mac viewing tunnel are now per-user launch agents:
`local.photohouse.api-relay` and `local.photohouse.web-tunnel`. Both bind only
loopback, start at login, and use SSH keepalives with a 30-second relaunch
throttle. Concrete hosts, accounts, and keys remain in private configuration.
Both agents and listeners were verified running. There is no public web
listener or newly introduced wake command.

This is login-persistent, not a system service before login: the respective
Mac accounts must be logged in, the overlay network must be reachable, and
Windows must be awake with its API running. Reconnection after a future
sleep, network loss, or reboot is configured, not yet an observed acceptance
test. The service does not make Windows content available while Windows sleeps.

## Validation

- JavaScript syntax and Git whitespace checks passed.
- Seven existing family UI source checks passed.
- Synthetic Chromium tests passed for portrait and landscape fit at six
  window sizes, long bilingual captions, lazy originals, actual-size pixel
  dimensions, drag pan, wheel zoom, keyboard and double-click reset, fullscreen,
  stale/failed original loads, video isolation, slideshow, focus, navigation,
  empty states, and bilingual controls.
- Synthetic desktop/mobile renderings were visually inspected.
- Through the Mac viewing URL, a real library photo opened completely within
  the Fit viewport; served HTML, JS, and CSS matched the deployed commit.
- The same real JPEG loaded at Actual size (6240 by 4160 pixels, 100%) with
  scrollable overflow, then returned to Fit and closed successfully. Its
  15,200,679-byte original took roughly two minutes over the private connection;
  the first 60-second test timed out, while a longer test completed. Windows
  returned the original's HTTP headers and initial bytes in 0.016 seconds.
  This is an observed transfer-latency limitation, not an instant-load claim.
- At 09:40 +08:00 the main caption refresh had 3330 finished, 17556 pending,
  one running, 55 failed, and four dead task records; Qwen3-VL was healthy and
  busy. Failed records remain retained for end-of-run review.

Safari/iOS/Android device acceptance remains separate from Chromium checks.
The full Qwen3 caption refresh and end-of-run failure review remain unfinished.

## Follow-up: saved-person picker (09:50 +08:00)

UI source `0aa4a04c91532463bb2d9b7cd12eedfb1b4836e3` supersedes the UI overlay
above; the backend remains `01ade47`. The face inspector now loads saved people
independently of People-tab navigation, fetches all pages in stable ID order,
refreshes names on reopening, and rejects stale inspector responses. Name-load
failure shows a retry control and disables assignment/new-person controls;
captions remain available and no partial list is offered as complete.

The updated browser regression suite passed, including 501 saved names across
two pages, an existing assignment, mocked assignment payload, renamed people,
second-page failure/retry, an empty list, and navigation races. The prior viewer
suite and seven UI source checks also passed.

Fresh-browser verification through the Mac URL showed all **30 saved names**
in an enabled face picker without visiting People. All names/IDs matched the
API response. Live verification blocked mutation requests and made zero
assignment writes, with zero uncaught browser errors.

The Windows deployment receipt and rollback files are in
`viewer-ui-0aa4a04c9153` under the PhotoHouse log directory. Served hashes match
the new source: JS `84c1b457f249034214daeb421edee37de681020e974cb7ab5586ff1cfe345a5f`,
HTML `c8a4e7777eea2902059791316896227d588fba56bb4685327ffc370cb17afa37`;
CSS is unchanged. API PID `23284` and Qwen PID `10460` remained unchanged,
API/database/worker checks passed, and Qwen3-VL remained busy. No people,
face assignments, queue contents, or schedules were edited.

This follow-up is committed locally; its GitHub publication remains pending.
