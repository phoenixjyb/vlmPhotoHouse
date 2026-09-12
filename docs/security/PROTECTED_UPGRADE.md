# Protected backend upgrade and worker isolation

The protected release uses `scripts/staging_app.py` with explicit private JSON
configuration. Updating source does not configure a library, upgrade a database,
start workers or deploy the server. Bare `uvicorn app.main:app` stays closed.

## Retired combined entry points

The following scripts now stop immediately with a retirement error, including when
old cleanup, GPU, detached, Tailscale or preflight flags are supplied:

- `scripts/start-dev.ps1`
- `scripts/start-dev-multiproc.ps1`
- `scripts/start-dev-tmux.sh`
- `scripts/start-photohouse-api.ps1`
- `scripts/run-runtime-canary.ps1`
- `tools/morning-intake-and-start.ps1`

They do not read `.env`, stop processes, load models, ingest originals, migrate a
database or fall back to `legacy_main`. The earlier implementations remain in Git
history and already installed releases. Caption-only tools are not a protected
web deployment path. Old drive-integration instructions are historical workflows;
do not use them to configure this release.

## First deployment: independent synthetic staging

1. Record the immutable source/package/CPU-lock hashes and current process,
   listener and scheduled-task identities. Preserve the running caption release
   and every dirty checkout. Select a new private release and data directory.
2. Verify the source archive and every manifest member before execution. Install
   only the locked CPU wheels in a new environment. Run `pip check` and
   `check_access_environment.py --target windows-amd64 --profile runtime` with
   isolated Python. Never reuse the GPU environment or install ML requirements.
3. Initialize a new synthetic database at schema `b6e3f9a5c721`. Provision an
   explicitly selected synthetic owner/library and finite generated previews.
   Invite viewers by phone-bound invitation; keep all original grants off.
   Protect all credentials privately. Never put them in task arguments or logs.
4. Select one private bind address/port and the matching canonical HTTPS origin.
   Validate the private config, directory/certificate ACLs and certificate identity.
   Start only the new protected process, using the explicit launcher. Verify real
   TLS trust/hostname, denied unauthenticated and legacy routes, and authenticated
   synthetic reads. Check the original caption process remains healthy.
5. Record service identity, narrow ingress and rollback. Stopping only the new
   staging task/process is rollback; preserve its database for review. Certificate
   renewal on disk needs an explicit restart/reload of this process. A completed
   ACME renewal alone does not prove the serving process presents the new chain.

No caption pause is needed for this separate CPU-only synthetic environment.
Private Windows HTTPS evidence is distinct from LAN, public-router and Android
phone evidence. Do not claim outside-home reachability from a server-local check.

## Later real-library cutover

First establish a safe caption pause/drain procedure and identify every writer.
Record queue state at a safe boundary, then create and verify a separate backup.
Rehearse the existing-database migration into a new quarantined candidate; recover
only the reviewed owner/library and map assets deliberately. Keep restored viewer
accounts closed until their separate recovery is reviewed. Preserve the original
database and release, including pending/failed work. Review restart/rollback against
the actual installed process and database paths before switching traffic.

Do not replace a running checkout, point synthetic staging at the real database,
or expose legacy/standalone services as a shortcut. The protected HTTP service has
no caption-worker runner; migration does not establish continued legacy-writer
compatibility. That compatibility and caption restart require their own checks.

## Verification

Run the existing synthetic security suite. On Windows, run
`powershell.exe -NoProfile -File tests/security/test_retired_launchers.ps1`.
It first parses all five PowerShell stubs and refuses to invoke a body containing
commands; then verifies refusal with representative former operational flags.
Run the shell stub with a fake `tmux`/Python in `PATH` and confirm neither runs.
