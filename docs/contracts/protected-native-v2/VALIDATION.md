# Validation receipt — 2026-09-16

Source baseline: `4022a57f56e6b2f976931a20569e15c879871d93`.
Branch: `codex/protected-native-contract-v2`.
Changes are contract documentation, synthetic wire cases, probe, replay tests and
an offline hash verifier. Application/backend source is unchanged.

## Checks

Using the already available disposable Mac test environment (Python 3.13.15,
FastAPI 0.135.2, Starlette 1.3.1, httpx 0.28.1, SQLAlchemy 2.0.52,
Alembic 1.19.2), from repository root:

```sh
PYTHONPATH=tests/security:backend python -m unittest \
  test_protected_native_contract test_access_foundation test_access_transport \
  test_library_reads test_family_stories.FamilyStoryTests \
  test_protected_photo_delivery test_closed_application
```

**134 tests passed in 62.689 seconds**, no skips. This includes seven new contract
tests, a complete replay comparison of **60 captured ASGI exchanges**, and existing
account/admission/library/Stories/photo/closed-application tests. Test discovery
includes inherited library cases; 134 is the runner count, not 134 unique new
scenarios. These tests are synthetic and in-process; no network listener is used.

`python3 scripts/verify_protected_native_contract.py`: passes source and payload
hash closure, case count/IDs/version and off-by-default profile checks. All 98
source hashes were independently compared with `git show <source>:<path>` when
building the manifest. `backend/app/access/library.py` is byte-identical to the
frozen v1 backend; SHA-256:
`5c280e0047771a43274615b77617f896ef2ef075b4fa3f926ae05bf8c49372fe`.

Markdown links/whitespace/fences and staged diff whitespace checked. The first
replay exposed a wall-clock default in synthetic caption data; the probe now
sets deterministic fixture timestamps before calling the unchanged serializer.
The final full-wire comparison passes without masking response date fields.

## Boundaries

The test environment emits a Starlette/httpx deprecation warning; no packages
were installed or upgraded. Windows dependencies/runtime were not inspected.
On-demand JPEG rendering is stubbed in the contract probe; existing protected
photo tests exercise the authorization boundary. This receipt is not Windows
decoder, ACL, device, APK or live-service acceptance.

No production database/media/accounts, GPU/model operations, service changes,
network port exposure, mobile repository edits, push or merge. Android owns its
client verification/adoption. Integration owns configured deployment approval.
The pack remains a candidate requiring explicit coordinator adoption; immutable
commit and manifest digest are supplied in the task handoff after local commit.

No application deployment is needed for this documentation/test slice. Upload,
refresh tokens, native voice/STT and prepared-video access without original
permission are not implemented by this work.
