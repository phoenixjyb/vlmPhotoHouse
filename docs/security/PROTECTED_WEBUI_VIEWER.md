# Protected WebUI: photo controls and face-assignment feedback

The protected WebUI has its own viewer; it does not automatically inherit the
legacy WebUI or Android TV viewer implementation.

## Photo controls

The protected viewer supports fit, fit width, fit height, actual size, zoom
buttons, mouse-wheel zoom, drag panning, and browser fullscreen. With the preview
focused, `+` / `-` zoom, arrow keys pan, `0` fits, and `1` selects actual size.
Fullscreen contains the photo and its controls; exit fullscreen to return to the
Stories and face-review panels. Browser refusal is reported without changing
access permissions.

This viewer still uses the authorized thumbnail endpoint. The quality notice is
deliberate: **actual size means decoded preview pixels**, not original photo
resolution. Enlargement never fetches originals, enables PhotoCache, falls back
to legacy media endpoints, or changes native-client contracts. Protected larger
display media is a separate backend/runtime qualification.

Opening another asset resets zoom and pan. Closing, signing out, changing
libraries, or hiding the page clears the media through the existing privacy
lifecycle. Late image-load events cannot repopulate the closed viewer.

Previous/next and slideshow are bounded to the loaded gallery page or album order;
there is no cross-page fetch. A step commits to the requested item as soon as it is
requested: the previous photo is dropped before the new detail is read, so a step
that fails reports *that* item's error state rather than silently keeping the photo
the user just left. A failed step stops the slideshow, does not advance past the
requested item, does not retry, and stays recoverable with Previous. This is the
covered behaviour — it is a deliberate choice, not an accident of ordering.

## Saved people that cannot be assigned

Story editing is not proof of face-management permission. Face management is
owner-only, and an owner must also satisfy the source and target person's
ownership constraints. The current API returns `face.can_assign` and
`person.can_rename`; under this contract both must permit the correction.

Some legacy people are visible through their in-library faces but have references
to unmapped or differently owned assets. The picker keeps those choices disabled
and displays an ownership-review explanation beside them. It does not disclose
hidden asset counts or library identities. Eligible selections require a visible
face/person review and explicit confirmation; choosing a search result alone is
not a save.

Do not remove the exclusivity guard to make a button work. The assignment endpoint
also updates global person aggregates, embedding state and ownership. Suppressed
status by itself is not the restriction: unmapped or foreign references are.
Unblocking a restricted legacy person requires a separately reviewed ownership
repair or a library-local mutation design, preserving suppression and existing
labels. No automatic repair, reassignment, retry, propagation or permission
expansion is part of this UI change.

## Verification and delivery

- `node tests/security/test_web_browser.cjs` exercises the protected UI against
  the real ASGI application with synthetic SQLite/media over a pipe. Set
  `PLAYWRIGHT_MODULE` and `PH_BROWSER_PYTHON` to existing local installations.
- `python -m unittest discover -s tests/security -p test_people_management.py`
  verifies the owner, library, revision and assignment restrictions.
- `python scripts/verify_protected_native_contract.py` checks that the adopted
  native API pack remains unchanged.

Synthetic browser evidence is not live deployment or family/device acceptance.
Deployment, any runtime media configuration, and ownership repair remain separate
authorized operations. No caption or face worker change is required by this UI
source patch.
