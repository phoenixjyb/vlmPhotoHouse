# Secured WebUI prepared playback evidence

Base `7af4498e6a55b4c17f7223e815d145e4a595ce0c`.
Branch `codex/protected-playback-web-20260920`.

Chromium 151.0.7922.34: 58 browser checkpoints passed, no page errors or external
requests. Includes all prior 53 checkpoints and five prepared-playback checkpoints.
See result.json for exact assertions and transport limits. The existing pipe
bridge serves a migrated synthetic SQLite database, JPEG previews and the existing
small MP4 fixture; the captured report's older JPEG-only description predates the
final wording correction in the harness. Both rendered screenshots were inspected.

Run with existing Playwright core and Python dependencies:

```sh
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright-core \
PH_BROWSER_PYTHON=/path/to/test-environment/bin/python \
PH_BROWSER_ARTIFACTS=/path/to/new-artifacts \
node tests/security/test_web_browser.cjs
```

Positive evidence includes HEAD metadata validation, native MP4 decoding and
playback, midpoint seek completion, and protected GET. It is a tiny fixture;
long-duration browser playback and seek-triggered network ranges remain unproven.
HTTP status/header fault cases use explicit interception after real ASGI requests;
they are client recovery evidence, not another backend authorization proof.

Offline initial/repeated retries, native GET failure, 503/404/409/429 seconds and
date delays, malformed 200 and 403 restoration passed. Closing during a delayed
HEAD prevents reappearance. Original fallback is not introduced. See
../../WEB_PREPARED_PLAYBACK.md for native browser validator limitations.

Syntax checks and git diff whitespace checks passed. Four package unit tests
passed. Candidate.13 verifier still passes 70 captures / 115 source / 7 payload hashes;
this UI change leaves the backend-owned native contract unchanged. Android's
separate replay passed 27 backend tests including the entire 70-case capture.

No live server, real account/media, Windows service, worker, deployment or device
installation was used. Local browser interception does not establish real network
Fetch Metadata/CORP behavior. Package and physical acceptance remain separate.
