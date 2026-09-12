# Protected API CPU environment

This slice pins the dependencies for the protected API, direct-TLS launcher and
explicit offline database/operator tools. It does not install or deploy them on
Windows, change authorization code, migrate a real database, or open a listener.
The existing model/worker requirements and environments are separate.

## Dependency contract

- Target: CPython 3.12, Windows x64. The prerequisite probe currently accepts
  3.12.10 or later 3.12 patches; this is a compatibility floor, not a security
  attestation of the interpreter, OpenSSL, SQLite or Windows patch level.
- [Runtime input](../../backend/requirements-access.in) resolves to the
  [18-package runtime lock](../../backend/requirements-access.lock).
- [Test input](../../backend/requirements-access-test.in) resolves to the
  [21-package test lock](../../backend/requirements-access-test.lock). It retains
  identical runtime pins and adds only HTTPX, httpcore and certifi for synthetic
  in-process ASGI checks. Do not install this profile into the serving environment.
- Both locks contain exact transitive versions and SHA-256 distribution hashes.
  Installs must require hashes and wheels only. Hashes include published wheels
  for other platforms (and source archive hashes emitted by the resolver); the
  installation command forbids source builds. Hashes identify artifacts, not their
  safety. Re-resolve and review updates deliberately; do not silently upgrade.
- No FastAPI/Uvicorn extras, Torch, Transformers, NumPy, Pillow, CUDA, model weights,
  .env loader, reload watcher, alternate event loop or WebSocket package is included.
  Cached previews must already exist; this runtime cannot generate missing ones.

The old security-test file pinned Starlette **1.0.0**, which has published
advisories. This candidate pins **1.3.1**, including fixes for
[URL hostname construction](https://github.com/Kludex/starlette/security/advisories/GHSA-jp82-jpqv-5vv3)
and [form resource limits](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq).
This identifies a vulnerable dependency baseline; it does not assert that every
advisory is reachable through PhotoHouse's closed routes. Historical test results
remain historical. `requirements-security-test.txt` now points to the new test lock.
The rest of the previous direct API pins are retained; Uvicorn is pinned to 0.52.4.

## Later authorized Windows installation

Use a **new immutable release directory**, with its own repo-root `.venv`, after
reviewing the source manifest, runtime lock, Python installer and target machine.
Never sync this lock into the live inference environment: a sync removes extra
packages. Do not reuse a previously populated environment or enable system site
packages. The following are reviewable instructions, not executed Windows steps:

```powershell
# In the approved new extracted release; confirm .venv does not already exist.
if (Test-Path .venv) { throw 'Preserve existing environment' }
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -I -m pip --isolated install `
  --index-url https://pypi.org/simple --require-hashes --only-binary=:all: `
  -r backend/requirements-access.lock
.\.venv\Scripts\python.exe -I -m pip check
.\.venv\Scripts\python.exe -I scripts/check_access_environment.py --target windows-amd64
```

The selected Python must be the reviewed x64 CPython 3.12 installation. `py -3.12`
is an example selector, not proof of which installation is selected. Retain the
actual interpreter/installer identity and installed wheel receipts. An offline
wheelhouse may be used with `--no-index --find-links` and the same hash/binary flags.
Do not bypass certificate validation or fall back to an unreviewed package mirror.

For a disposable Mac ARM64 validation environment, use the same lock with the
explicit `--target macos-arm64-test` selector. For the synthetic suite, install the
test lock in a separate fresh venv and add `--profile test` to the probe. A Mac pass
sets `windows_execution_verified=false`; it is not permission to start serving.

## What the offline probe establishes

[check_access_environment.py](../../scripts/check_access_environment.py) reads only
the selected repository lock and installed distribution metadata. It refuses a
non-isolated/global interpreter, wrong Python family/platform/bitness, missing or
wrong package versions, duplicate distribution metadata, packages outside the venv,
and unexpected packages. Optional `pip` bootstrap tooling is allowed but not pinned
or vouched for by this runtime lock. Use `-I` to ignore PYTHONPATH/user site settings.

After inventory passes, it tests an RFC 7914 scrypt known-answer vector, the actual
application KDF cost (128 MiB working memory; 256 MiB allowance), SQLite foreign-key
rejection in memory, and creation of a TLS 1.2-capable server context. It imports no
PhotoHouse/model modules, reads no real database/config/media/TLS key, and opens no
socket. It reports its interpreter, SQLite and OpenSSL versions.

It is a **prerequisite check, not an enforced launcher hook or security attestation**.
It does not re-hash installed wheel contents, validate dependency metadata against
all Python/platform combinations, detect malicious site customization/filesystem
administrators, prove absence of vulnerabilities, test TLS handshakes/certificates,
check Windows ACL/reparse behavior, or establish deployment approval. Run `pip check`
and retained synthetic acceptance separately. The launcher remains a distinct,
explicit operator action; no automatic environment installation was added.

## Reproduction and next gate

Locks were resolved with uv 0.8.12 against PyPI using:

```sh
uv pip compile backend/requirements-access.in --python-version 3.12 \
  --python-platform x86_64-pc-windows-msvc --generate-hashes --only-binary :all: \
  --no-header --no-annotate -o backend/requirements-access.lock
uv pip compile backend/requirements-access-test.in -c backend/requirements-access.lock \
  --python-version 3.12 --python-platform x86_64-pc-windows-msvc \
  --generate-hashes --only-binary :all: --no-header --no-annotate \
  -o backend/requirements-access-test.lock
```

See the [validation receipt](evidence/android-readiness/cpu-environment-validation.json)
for exact results and limitations (repository evidence is not bundled in the source ZIP).
Wheel downloads/resolution are not execution on
Windows. No inference environment, real database, service, mobile repository or
network ingress was changed in this slice. Next local work is the explicit
existing-database migration/apply/recovery procedure. Later Windows synthetic-only
installation, protected TLS serving, renewal reload integration, ingress isolation
and real-phone acceptance remain separate gates. Do not expose the legacy UI merely
because DNS and certificate preparation have been completed separately.
