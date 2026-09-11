# Explicit protected staging launcher — local implementation

`scripts/staging_app.py` supplies the deliberate runtime wiring missing from the
initial Android staging proposal. It is implemented and tested locally; it has
**not been used to start a listener or access any host, database, media or TLS key**.
It does not install a service, migrate/provision a database, load a model, discover
an origin, or make an account eligible to view photos.

## Configuration and execution boundary

The launcher requires a separately selected JSON file and one explicit mode:

```sh
"$PHOTOHOUSE_PYTHON" scripts/staging_app.py \
  --config "$PHOTOHOUSE_PRIVATE_STAGING_CONFIG" --check-config
```

`--check-config` reads only that file (at most 64 KiB), validates syntax and prints
a generic result with storage/certificate/network checks explicitly false. It
does not stat/open the paths contained in the JSON, perform DNS, read `.env` or
import the application/Uvicorn. Selected config files must be regular, directly
addressed files with no symlink path at validation, outside the declared media.
Duplicate/unknown JSON keys, invalid shapes and missing inputs are refused.

`--serve` is a separate deliberate command mode for a later authorized deployment.
It constructs `RuntimeConfiguration` from the supplied values and passes the
resulting protected app to Uvicorn. **No `--serve` invocation was performed here**;
tests use a mocked server function. Calling the script without a mode does not
serve. The default `app.main:app` remains closed.

The [example file](staging-config.example.json) is deliberately incomplete and
fails validation. It is not an approved configuration or deployment manifest.
The operator fills a private file outside the repository only after target review.

| Field | Required value |
| --- | --- |
| `format_version` | Integer `1`; no version fallback |
| `database` | Explicit absolute native path to the selected existing SQLite file |
| `web_origin` | Canonical lower-case ASCII DNS HTTPS origin, with listener port if nondefault; omit explicit `:443`; no trailing slash, path, userinfo, query or fragment |
| `original_roots` | One to eight absolute native local paths, mutually disjoint and disjoint from the derived root |
| `derived_root` | Explicit absolute native path to cached synthetic previews |
| `bind_host` | Canonical literal address in RFC1918, private CGNAT/VPN, IPv6 ULA or loopback ranges; no wildcard, public address, DNS lookup, link-local zone or IPv4-mapped IPv6 form |
| `port` | Explicit integer 1–65535 matching the HTTPS origin; no automatic unused-port selection |
| `tls_certificate` | Explicit absolute native local certificate-chain file path |
| `tls_private_key` | Explicit absolute native local key file path, distinct from certificate and database |

Path checks are lexical and native to the running OS: no relative/parent/UNC/root
paths, and no database/key/certificate/config inside declared media paths. They do
not establish actual filesystem isolation. Native Windows paths must be checked
on Windows after authority; a Mac syntax pass does not prove Windows path/ACL,
reparse-point, certificate, SQLite or service behavior. The selected configuration
and its parent directory must be controlled by the operator, not writable by viewers.

## Fixed server settings

The configuration cannot override these settings: direct TLS certificate/key,
one worker, asyncio/h11, no websockets, reload, proxy-header trust, forwarded-peer
trust, access log, Server header, `.env` load or URL path prefix. Initial limits
are 16 concurrent requests, 8192 bytes for incomplete h11 events, 5-second keepalive
and 10-second graceful shutdown. No real workload sizing claim is made.

Ambient `WEB_CONCURRENCY`, `FORWARDED_ALLOW_IPS`, `UVICORN_HOST` or database variables
do not substitute for these explicitly supplied values. The launcher uses the
existing protected entry point and lazy database adapter: a configured app object
is **not a readiness check**. Missing/wrong database state remains unavailable at
request time; launching does not create, migrate, repair or provision it.

The selected certificate/key are opened by Uvicorn only when serving. Syntax
validation does not verify their existence, key match, chain, renewal, Android
trust, hostname or phone reachability. Logging/service isolation and certificate
file ACLs remain operator responsibilities; no secrets belong in CLI arguments,
config examples, Git, public builds or logs.

## Evidence and remaining implementation

**10 focused launcher tests and all 211 backend security tests pass.**
Focused synthetic tests cover strict JSON/origin/port/path validation, missing-mode
refusal, sanitized output, ambient environment isolation and protected app wiring
with a mocked server. Socket binding/connect, process spawning and SQLite opens
are blocked. Fixed options were checked against the locally installed Uvicorn
**0.42.0** signature; this is not a reviewed Windows dependency lock.

Run with the existing repo-root security environment:

```sh
"$PHOTOHOUSE_PYTHON" -m unittest discover -s tests/security -p test_staging_launcher.py -v
```

No live runtime, TLS, Windows, emulator or device acceptance was run. In particular,
this launcher does not establish a service account, backup, owner/library mapping,
certificate or ingress boundary. It does not reopen quarantined restored access.
The [operator provisioning/source package](OPERATOR_TOOL.md) is now implemented,
and Android completed the local caption-fix repin. The next local backend step is
reviewed owner recovery, selective library reopening and service cutover/rollback.
New-file quarantined migration candidates are now covered by
[database preparation](DATABASE_PREPARATION.md); they do not activate an existing library.
[Database preparation](DATABASE_PREPARATION.md) now supports new empty initialization,
private backup and in-memory rehearsal, with synthetic evidence only.
The [staging proposal](ANDROID_STAGING_PROPOSAL.md) retains the external authority,
target, backup/migration/provisioning, rollback and phone gates.

## CPU dependency prerequisite

The [CPU environment lock and offline probe](CPU_ENVIRONMENT.md) now define the
minimal dependency set. Verify a fresh release environment before the separate
launcher step. This is not an automatic launcher hook or Windows deployment proof.
