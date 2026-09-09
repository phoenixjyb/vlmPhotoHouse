# PhotoHouse family UI refinement — 8 September 2026

## Scope

Local source implementation on top of `3880f7e`. No Windows deployment,
service restart, scheduled-task change, model change, or GitHub push in this step.

The visual direction uses warm ivory, terracotta, restrained serif headings,
actual family thumbnails in keepsake frames, and a quieter navigation bar.
System tools remain available in Advanced mode. The homepage shows recent
photos, people, and up to four suggested albums (one per available category).

## Everyday interactions

- Photo cards open a full-screen viewer; editing is a separate Photo details action.
- Previous/next arrows, a windowed thumbnail strip, and an opt-in six-second
  slideshow support browsing the current group. Video playback remains manual.
- Existing bilingual captions remain complete and scrollable, without word limits.
  Out-of-order caption responses cannot replace the current photo's description.
- Escape closes the viewer; focus returns to its trigger. The background is inert
  while the viewer is open. Tab stays in the viewer; descriptions can be scrolled
  with the keyboard. Reduced-motion preferences are respected.
- Find a memory (or `/` outside text entry) focuses home search. Chinese suggestion
  chips submit Chinese text. Switching tabs preserves the current search results.
- Ready homepage sections render independently. Failed requests get a retry
  control without clearing successful sections. Missing thumbnails get fallbacks.
- Dates come from `taken_at`; missing dates are not invented from filenames.

## Review and verification

Start a loopback-only design preview against an existing localhost API tunnel:

```sh
PHOTOHOUSE_PREVIEW_API=http://127.0.0.1:18002 node scripts/preview-family-ui.mjs
```

Open `http://127.0.0.1:18003/ui` (or append `?lang=zh`). Local UI assets use the
current source, while API/media responses stream through the tunnel. This script
does not persist media or databases. Editing/maintenance requests are blocked;
only GET/HEAD and the two read-only POST search endpoints are forwarded.
The preview is not a production launcher or a public reverse proxy.

Browser regressions use synthetic data and never contact the live API:

```sh
node scripts/test-family-ui-browser.cjs
```

Requires an existing Playwright installation and Chromium. If not resolvable as
`playwright`, set `PLAYWRIGHT_MODULE_PATH` to its module directory. No application
Python environment, model download, or Windows database copy is required.

Observed checks: Chromium desktop and mobile rendering against the live tunneled
library; fixture-based retry, caption-response race, viewer/focus/keyboard,
slideshow cancellation, video non-autoplay, inspector return navigation,
Chinese query submission, search retention, missing images, empty library,
and 1440/768/390/320-pixel layouts. Existing seven family UI source checks,
JavaScript syntax, and whitespace checks also pass.

Not established by this step: deployed Windows UI acceptance, real iPhone/Safari
testing, screen-reader acceptance, live editing, or full backend regression tests.
Album naming and person-cover quality are still based on existing service data;
this redesign does not silently relabel people or regenerate captions.
