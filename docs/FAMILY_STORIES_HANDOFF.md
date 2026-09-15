# Family stories: focused-task handoff

Prepared 2026-09-15 after user requested continuation through the existing API and
phone/TV tasks. This document is a work capsule, not proof of message delivery,
deployment or device acceptance.

The ownership handoff below is historical. The API owner has completed a local
independent review; use [FAMILY_STORIES_REVIEW.md](FAMILY_STORIES_REVIEW.md) for
review repairs, current evidence and immutable source/package identity. The original
uncommitted status and counts below describe what was received, not the reviewed return.

## Source and original evidence

Worktree: `/Users/yanbo/Projects/vlm-photo-engine/_worktrees/family-stories`
Branch: `codex/family-stories`
Base: `470f42cf6ea0cc9c1a0885d1e7f8da0eb99c2eca`

All feature changes are currently uncommitted, including untracked files. Preserve
them; do not reset, clean, stash or substitute the older captioning checkout.
Start with `AGENTS.md` and `docs/FAMILY_STORIES.md`, then inspect the actual diff.

Retained evidence:

- `/tmp/photohouse-family-stories-security-final.log`: 552 tests run, 548 passed,
  four native-Windows skips, no failures.
- `tests/security/test_family_stories.py`: focused writes/history/search/permissions
  and existing library regression fixture. Narrow run: 36 passed.
- `tests/security/test_orm_migrations.py`: expanded run 12 passed, including existing
  caption preservation and interrupted migration rollback.
- `tests/security/test_web_browser.cjs`: 19 actual Chromium-to-ASGI scenarios passed.
  Latest synthetic result and screenshots:
  `/var/folders/wc/gxp1f06557g53q8dgsf_64mc0000gn/T/photohouse-web-proof-dNuS19/`.
- Source-only route inventory, JavaScript syntax, staging manifest tests, and
  worktree startup/migration smoke passed; no deployed or immutable-ZIP claim.

Temporary evidence may expire; commands and scenarios are recorded in the feature
document for reproduction. The new migration is `c7f4a9e2b610`; runtime schema pins
and staging source allowlist were updated. Existing caption rows/worker policies
were not rewritten. No Windows connection or caption-job action occurred.

## Ownership after message handoff

**API task — “Inventory PhotoHouse API access”:** sole writer of this feature
worktree, including backend, protected WebUI, schema migration, tests and these
documents. Review the diff independently; fix concrete source/test issues; check
current integration base and deployment lineage read-only before proposing rollout.
Do not claim the feature works on the older served legacy UI. Return reviewed source
identity, contract compatibility, evidence and exact next gate. Coordinate with the
Android task on the additive story contract. No other task should edit this worktree
until the API owner returns it.

**Phone/TV task — “Implement Android fixture app”:** retain its current mobile
worktree and current-operation safety boundary. At a safe checkpoint, review the
feature contract and take the next bounded Android phone/TV slice. Own Android
implementation/tests only, not backend source or shared contract snapshots. Start
with synthetic read/search/story presentation and permission/conflict states; only
wire networking after the shared contract is reviewed and adopted. Return proposed
contract deltas to the coordinator, rather than editing frozen fixtures silently.
Keep TV publication separate: no private-library story content in the anonymous
feed without an explicit approved-story export policy.

**Coordinator (this originating task):** integration decisions, mobile shared
contract/fixture adoption and cross-platform parity gates. No concurrent backend
or Android writes while those owners work. iOS and installed-APK acceptance remain
separate follow-ups, not implied by an Android fixture or green API test.

## Acceptance and authority

Backend acceptance: long EN/ZH stories survive save/edit/history/reload, AI refresh
cannot overwrite them, stale/duplicate saves behave correctly, wrong-library or
revoked access cannot disclose story text/history/search, and migration preserves
all original data. Rerun relevant checks after repairs.

Phone acceptance: view/search stories alongside AI, source labels and literal text,
viewer versus contributor controls, retry/conflict states, no stale content after
logout/library switch. TV acceptance: explicit published audience, D-pad focus,
readable long text and predictable Back/scrolling; backend success is not device proof.

This handoff authorizes continuing bounded local engineering. It does not newly
authorize push/merge, Windows migration/deployment/restarts, changing caption jobs,
publishing private stories, real backend access, APK installation, signing or store
distribution. Preserve separately established authority only for the exact same
operation; ask for any missing release authority. Do not load models or change GPU
schedules. Read the private remote-access instructions before any separately
authorized Mac mini/Windows access; never include credentials in a handoff.
