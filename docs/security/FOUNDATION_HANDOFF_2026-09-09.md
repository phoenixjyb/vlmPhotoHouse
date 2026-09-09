# PhotoHouse backend-security foundation handoff — 2026-09-09

**Historical 14:00 checkpoint.** Following the user's renewed request, the
[slice 15 continuation](OFFLINE_PROVISIONING_APPLY.md) adds a verified offline apply
service and receipt migration. Its evidence supersedes the test totals and "no
apply path" status below; earlier implementation history remains intact.

Local work window ends at **14:00 Asia/Shanghai (06:00 UTC)**. Implementation is
complete; the remaining window is final artifact/preservation review. This record
is source/test evidence, not a deployment or a claim about current live services.

## Exact workspace and preservation

| Item | Verified value |
| --- | --- |
| Repository | `vlmPhotoHouse`, isolated worktree of the backend repository |
| Worktree | `/Users/yanbo/Projects/vlm-photo-engine/_worktrees/mobile-access-foundation` |
| Branch | `codex/mobile-access-foundation` |
| Base `origin/master` | `932263504ac5fcc3ed178e951991619d8ee87049` |
| Latest implementation commit | `ae5c4e9358d42a98000a69e73a522d8617f813c7` |
| Original backend checkout | `codex/insightface-cuda-runtime` at `752ab3bfb2ec48558bae747948185ceabb66a229`, clean and unchanged |
| Mobile checkout | `codex/mobile-foundation-plan` at `6088a35dde86d24b0cc64faba31c71d867293420`, clean and unchanged |

The final handoff-only commit follows the implementation commit above. No push or
merge occurred. Legacy main-handler bytes and the original three web UI files were
compared against the base and remain intact; old handlers are preserved in
`legacy_main.py` behind immediate retirement refusal. The workspace root itself is
not a Git repository. No Windows/Mac mini, real database/media, models, live
credentials, deployment, mobile changes or network listener was used.

## Delivered locally

- Owner-delivered, phone-bound single-use invitations; phone/password returning
  login. Phone is an unverified login label, with an internal stable account ID.
  Valid invitation redemption grants viewer membership in that library. No open
  signup, first-signup owner, SMS, WeChat, reset-through-invitation or automatic
  legacy-photo access.
- Shared current account/session/membership/library authorization; separate original
  permission, owner member review/revocation, durable admission, web CSRF and explicit
  native bearer transport. Expiry/revocation is checked again on each protected read.
- Closed default HTTP entry point; explicitly configured runtime; scoped gallery,
  detail/captions, cached thumbnails/face crops and originals with GET/HEAD/Range.
  File descriptors stay pinned and close even after cancellation during opening.
- English/Chinese invitation/sign-in and scoped gallery web screen, with safe text
  rendering, stale-response isolation and failed-logout privacy. Legacy operations
  remain unavailable in this screen.
- Real synthetic migration/ORM reconciliation and an opt-in existing-DB adapter.
  Read-only sealed owner/asset-mapping plans record explicit targets, audience and
  stale-state expectations. **No provisioning apply path is implemented.**

## Final validation and limits

| Check | Observed result |
| --- | --- |
| Python security suite | **162 passed in 20.239 s**, no skips/xfails |
| Chromium UI/ASGI contract | **14 passed**, zero external page requests/page errors |
| Inventory | **152 entries**: 23 active, 97 retired, 32 standalone |
| Active runtime identity | Exact method/path/endpoint set agrees with inventory |
| Retired denial ledger | **84/84 FAIL**, intentionally exits **1**; historical unsafe handlers, not current active route bypasses |
| ORM/migrations | Real SQLAlchemy/Alembic, temporary SQLite; access defaults/constraints and fresh full structural parity verified |
| Preservation | Original backend/mobile status and legacy source-byte comparisons passed |
| Documentation | 17 rendered documents / 15 HTML tables; all local links resolve |

Commands: `.venv/bin/python -m unittest discover -s tests/security -q`,
`.venv/bin/python scripts/security_inventory.py`,
`node tests/security/test_web_browser.cjs` with an existing Playwright module,
and `.venv/bin/python tests/security/harness.py` (expected exit 1).

The final browser uses the real rendered UI and real ASGI/SQLite adapter over pipes,
with **modeled Fetch Metadata from the request frame** because DevTools interception
omits those network-generated headers here. Real TLS, proxy/header emission and
CORP enforcement remain unverified. This is not a browser/device deployment pass.

Runtime used: Python 3.14.7 / SQLite 3.53.4, SQLAlchemy 2.0.52, Alembic 1.19.2,
FastAPI 0.135.2, Starlette 1.0.0, HTTPX 0.28.1, Pydantic 2.12.5, test-only Pillow
12.1.1, Node 22.17.0 and existing Playwright 1.62.1. The ignored root `.venv` is a
local overlay using host packages; it is not a hermetic production/Windows lock.

Latest evidence: [media/cancellation and browser](MEDIA_CANCELLATION_REVIEW.md),
[full retired ledger](evidence/final-20260909/retired-denial-ledger.txt),
[inventory guard](INVENTORY_GUARD_REVIEW.md),
[real migration rehearsal](ORM_REHEARSAL.md), and
[read-only provisioning plans](OFFLINE_PROVISIONING_PLANS.md).

## Unresolved security and acceptance gates

1. **Live systems unchanged/unverified.** This local branch secures its selected
   entry point; it does not retroactively change existing deployments. The 97 old
   handlers remain unsafe implementations and must never be remounted. The 32
   standalone LVFace/diagnostic/RAM++ routes remain unprotected if independently
   exposed; they require separate service-identity/isolation work.
2. **No live owner/bootstrap or asset mapping.** Default runtime remains absent and
   closed. Plans do not grant authority or access. Backup/restore, exact target
   identity, audited atomic application and replay rejection remain prerequisites.
3. **Deployment boundary unverified.** TLS, trusted proxy configuration, Fetch
   Metadata preservation, logs/caches, filesystem permissions, Windows behavior,
   multi-process resource limits and clean dependency/CI execution need separate
   acceptance. Cookie clients lacking positive same-origin signals fail closed.
4. **Recovery and operational work incomplete.** Password/phone recovery/change,
   owner transfer, account deletion, crashed KDF-slot recovery and ongoing resource
   admission are separate work. A crashed admission worker intentionally leaves
   login closed until reviewed offline recovery; there is no automatic slot theft.
5. **Features remain closed.** Albums, global/vector/caption search, uploads/curation,
   destruction, jobs/operational diagnostics and voice/provider conversations are
   not reopened. Native Android/iOS builds and device acceptance are unverified;
   the mobile repository was not edited.
6. **Tests are scoped.** The legacy backend suite was not run: its fixtures import
   removed startup/executor/SessionLocal helpers, use schema fallback and assume
   anonymous APIs. No SKIP_ALL_TESTS bypass or legacy-suite pass is claimed.
7. **Revocation has an in-flight limit.** Previously authorized requests may finish
   and downloaded files cannot be recalled. Source inventory is a completeness
   guard for reviewed forms, not proof of arbitrary Python behavior or security.

## Next reviewed implementation

Review and implement the offline apply workflow in
[OFFLINE_PROVISIONING_PLANS.md](OFFLINE_PROVISIONING_PLANS.md): protected password
entry for deliberate bootstrap, explicit database/plan confirmation, verified
backup/restore, revalidation under BEGIN IMMEDIATE, exact selected asset assignments,
audited one-time receipts and rollback/race/replay tests. Mapping must account for
all current readers and any existing original grants. Keep live application,
service exposure and deployment separate from local implementation authorization.

## Implementation commits

| Commit | Bounded checkpoint |
| --- | --- |
| `b652ffcb3481bc8c8c8a227de7875f9c3c27e2c0` | Inventory mobile access capabilities and reproduce authorization gaps |
| `4764b7fed3862befafda366dbdd2188f402c5b7b` | Add manual invitation and phone-password account foundation |
| `03ec1ba1dba92940a530984e79c9d52ae445a421` | Add durable account admission and shared session transport |
| `158725f5cb08c921d1625af60916cb8a5331cfc1` | Close default HTTP entry point and authorize media reads |
| `04c0bcb4971ba648e473b9041dc693eb0f7e19ae` | Reconcile access metadata and rehearse real SQLite migrations |
| `0013a8a052c172f49771cba8f8eed786cc7f9cf9` | Repair legacy read schema with additive preservation checks |
| `712a27d337d08177e8a87228f7e2df6daa207c35` | Add membership-scoped gallery detail and caption reads |
| `53b2eb62b42035fab34765926ef83715483481e1` | Connect invitation sign-in and scoped web gallery with browser proof |
| `b44842405fd50d2fa6a714edc5360361cb3baeb6` | Add owner member review and revision-bound access revocation |
| `55f0c5989f3412626e2f31fc34bce6e7a444f7b7` | Add explicit existing-database adapter with fail-closed rehearsal |
| `0cb58cf66b506cbaa8445abfc9ab9157164f33c3` | Require same-origin cookie read signals and verify boundary limits |
| `82318e54828fc49ef44b4e8215ff42fc1899a3d0` | Add read-only sealed provisioning plans with stale-state checks |
| `2d22c53438d1548df6a6542de87f35a30bdcd74b` | Reject opaque route registration and retain final denial evidence |
| `ae5c4e9358d42a98000a69e73a522d8617f813c7` | Close media descriptors returned after request cancellation |

## Complete changed-file manifest (74 files including this handoff)

Paths are repository-relative; A = added, M = modified.

| Change | File |
| --- | --- |
| M | [backend/alembic.ini](../../backend/alembic.ini) |
| M | [backend/app/__init__.py](../../backend/app/__init__.py) |
| A | [backend/app/access/__init__.py](../../backend/app/access/__init__.py) |
| A | [backend/app/access/admission.py](../../backend/app/access/admission.py) |
| A | [backend/app/access/bootstrap.py](../../backend/app/access/bootstrap.py) |
| A | [backend/app/access/boundary.py](../../backend/app/access/boundary.py) |
| A | [backend/app/access/credentials.py](../../backend/app/access/credentials.py) |
| A | [backend/app/access/library.py](../../backend/app/access/library.py) |
| A | [backend/app/access/media.py](../../backend/app/access/media.py) |
| A | [backend/app/access/members.py](../../backend/app/access/members.py) |
| A | [backend/app/access/metadata.py](../../backend/app/access/metadata.py) |
| A | [backend/app/access/provisioning.py](../../backend/app/access/provisioning.py) |
| A | [backend/app/access/runtime.py](../../backend/app/access/runtime.py) |
| A | [backend/app/access/schema.py](../../backend/app/access/schema.py) |
| A | [backend/app/access/service.py](../../backend/app/access/service.py) |
| A | [backend/app/access/transport.py](../../backend/app/access/transport.py) |
| M | [backend/app/cli.py](../../backend/app/cli.py) |
| M | [backend/app/db.py](../../backend/app/db.py) |
| A | [backend/app/legacy_main.py](../../backend/app/legacy_main.py) |
| M | [backend/app/main.py](../../backend/app/main.py) |
| M | [backend/app/routers/ui.py](../../backend/app/routers/ui.py) |
| A | [backend/app/ui/access/app.js](../../backend/app/ui/access/app.js) |
| A | [backend/app/ui/access/index.html](../../backend/app/ui/access/index.html) |
| A | [backend/app/ui/access/styles.css](../../backend/app/ui/access/styles.css) |
| M | [backend/migrations/env.py](../../backend/migrations/env.py) |
| A | [backend/migrations/versions/a5d2e8f4b610_legacy_read_schema.py](../../backend/migrations/versions/a5d2e8f4b610_legacy_read_schema.py) |
| A | [backend/migrations/versions/e3a9b1c7d402_access_foundation.py](../../backend/migrations/versions/e3a9b1c7d402_access_foundation.py) |
| A | [backend/migrations/versions/f4c1a8d2e703_access_admission.py](../../backend/migrations/versions/f4c1a8d2e703_access_admission.py) |
| A | [backend/requirements-security-test.txt](../../backend/requirements-security-test.txt) |
| A | [docs/security/ACCOUNT_TRANSPORT.md](../../docs/security/ACCOUNT_TRANSPORT.md) |
| A | [docs/security/BROWSER_BOUNDARY_REVIEW.md](../../docs/security/BROWSER_BOUNDARY_REVIEW.md) |
| A | [docs/security/CLOSED_APPLICATION.md](../../docs/security/CLOSED_APPLICATION.md) |
| A | [docs/security/EXPLICIT_RUNTIME_ADAPTER.md](../../docs/security/EXPLICIT_RUNTIME_ADAPTER.md) |
| A | [docs/security/FOUNDATION_HANDOFF_2026-09-09.md](../../docs/security/FOUNDATION_HANDOFF_2026-09-09.md) |
| A | [docs/security/INVENTORY_GUARD_REVIEW.md](../../docs/security/INVENTORY_GUARD_REVIEW.md) |
| A | [docs/security/LEGACY_READ_SCHEMA.md](../../docs/security/LEGACY_READ_SCHEMA.md) |
| A | [docs/security/MANUAL_INVITATION_ACCOUNTS.md](../../docs/security/MANUAL_INVITATION_ACCOUNTS.md) |
| A | [docs/security/MEDIA_CANCELLATION_REVIEW.md](../../docs/security/MEDIA_CANCELLATION_REVIEW.md) |
| A | [docs/security/MOBILE_ACCESS_FOUNDATION.md](../../docs/security/MOBILE_ACCESS_FOUNDATION.md) |
| A | [docs/security/OFFLINE_PROVISIONING_PLANS.md](../../docs/security/OFFLINE_PROVISIONING_PLANS.md) |
| A | [docs/security/ORM_REHEARSAL.md](../../docs/security/ORM_REHEARSAL.md) |
| A | [docs/security/OWNER_MEMBERSHIP_REVIEW.md](../../docs/security/OWNER_MEMBERSHIP_REVIEW.md) |
| A | [docs/security/SCOPED_LIBRARY_READS.md](../../docs/security/SCOPED_LIBRARY_READS.md) |
| A | [docs/security/WEB_INVITATION_GALLERY.md](../../docs/security/WEB_INVITATION_GALLERY.md) |
| A | [docs/security/evidence/browser-boundary-slice11/after.json](../../docs/security/evidence/browser-boundary-slice11/after.json) |
| A | [docs/security/evidence/browser-boundary-slice11/before.json](../../docs/security/evidence/browser-boundary-slice11/before.json) |
| A | [docs/security/evidence/final-20260909/browser-result.json](../../docs/security/evidence/final-20260909/browser-result.json) |
| A | [docs/security/evidence/final-20260909/retired-denial-ledger.txt](../../docs/security/evidence/final-20260909/retired-denial-ledger.txt) |
| A | [docs/security/evidence/media-cancellation-slice14/browser-result.json](../../docs/security/evidence/media-cancellation-slice14/browser-result.json) |
| A | [docs/security/evidence/member-slice9/owner-revocation-review.png](../../docs/security/evidence/member-slice9/owner-revocation-review.png) |
| A | [docs/security/evidence/member-slice9/result.json](../../docs/security/evidence/member-slice9/result.json) |
| A | [docs/security/evidence/provisioning-slice12/asset-plan.example.json](../../docs/security/evidence/provisioning-slice12/asset-plan.example.json) |
| A | [docs/security/evidence/provisioning-slice12/owner-plan.example.json](../../docs/security/evidence/provisioning-slice12/owner-plan.example.json) |
| A | [docs/security/evidence/runtime-slice10/result.json](../../docs/security/evidence/runtime-slice10/result.json) |
| A | [docs/security/evidence/web-slice8/gallery-desktop.png](../../docs/security/evidence/web-slice8/gallery-desktop.png) |
| A | [docs/security/evidence/web-slice8/gallery-mobile-zh.png](../../docs/security/evidence/web-slice8/gallery-mobile-zh.png) |
| A | [docs/security/evidence/web-slice8/result.json](../../docs/security/evidence/web-slice8/result.json) |
| A | [docs/security/evidence/web-slice8/sign-in-desktop.png](../../docs/security/evidence/web-slice8/sign-in-desktop.png) |
| A | [docs/security/route_capabilities.json](../../docs/security/route_capabilities.json) |
| A | [scripts/security_inventory.py](../../scripts/security_inventory.py) |
| A | [tests/security/browser_bridge.py](../../tests/security/browser_bridge.py) |
| A | [tests/security/harness.py](../../tests/security/harness.py) |
| A | [tests/security/test_access_foundation.py](../../tests/security/test_access_foundation.py) |
| A | [tests/security/test_access_transport.py](../../tests/security/test_access_transport.py) |
| A | [tests/security/test_closed_application.py](../../tests/security/test_closed_application.py) |
| A | [tests/security/test_current_gaps.py](../../tests/security/test_current_gaps.py) |
| A | [tests/security/test_inventory.py](../../tests/security/test_inventory.py) |
| A | [tests/security/test_legacy_read_migration.py](../../tests/security/test_legacy_read_migration.py) |
| A | [tests/security/test_library_reads.py](../../tests/security/test_library_reads.py) |
| A | [tests/security/test_member_management.py](../../tests/security/test_member_management.py) |
| A | [tests/security/test_orm_migrations.py](../../tests/security/test_orm_migrations.py) |
| A | [tests/security/test_provisioning_plans.py](../../tests/security/test_provisioning_plans.py) |
| A | [tests/security/test_runtime_adapter.py](../../tests/security/test_runtime_adapter.py) |
| A | [tests/security/test_web_browser.cjs](../../tests/security/test_web_browser.cjs) |
