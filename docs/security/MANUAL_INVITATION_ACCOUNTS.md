# Manual invitations and phone/password accounts — slice 2

Status: **local domain implementation and synthetic tests; HTTP/worker enforcement
is not integrated and the application is not safe to deploy as authenticated.**

## Confirmed product decision

The owner will manually send invitation codes to a small number of family members.
A member uses their phone number as the login name and sets a password during
registration. Later sign-ins use phone number + password. No SMS, email delivery,
WeChat application or third-party identity service is required for this design.
This user decision supersedes the earlier provider-first/email recommendation for
the initial family release. It does not implement an OAuth server.

1. An explicitly bootstrapped owner selects a library and the recipient's phone
   login, generates a code, and sends it through a channel they already trust.
2. The recipient enters phone number, password and code. Valid redemption creates
   the account and approved **viewer** membership atomically. No second approval
   is needed: the owner-issued invitation is that approval.
3. A code grants only its selected library. It is single-use, expires, and can be
   cancelled. An existing account logs in before accepting another invitation;
   an invitation can never replace that account's password.
4. Returning members log in with phone + password. The owner can revoke membership;
   the next domain-policy check denies library access even if the session is valid.

The phone number is an unverified login label, not proof of telephone ownership.
The server stores a canonical `+country-code` representation. The UI may default
the country selector to +86; the service never guesses a missing country code.
Internal immutable account UUIDs preserve identity if a later reviewed phone-change
flow is added. No phone number, including the first signup, implicitly becomes owner.
Do not auto-link accounts or transfer access based on matching/recycled phone numbers.

## Implementation and boundaries

The `backend/app/access` package receives a caller-owned SQLite connection to the
**same PhotoHouse database**. It never opens a database, imports runtime settings,
loads providers/models or touches media files. No parallel mobile-only auth database
or API is introduced. HTTP, web cookies, mobile bearer transport, workers and voice
must eventually call these shared services.

- `credentials.py`: explicit phone normalization, standard scrypt password hashing,
  random invitation/session values and SHA-256 digests of high-entropy tokens.
- `service.py`: invite-only account creation, login/logout, owner invitations,
  approval/revocation, current session/account/membership checks, separate original
  access and operator authority, scoped asset metadata and paginated IDs/counts.
- `bootstrap.py`: **offline operator-only** creation of a deliberately selected new
  owner account/library. Never mount this as signup, infer ownership from first
  registration, or accept a client-supplied bootstrap/operator flag.
- `schema.py` and Alembic revision `e3a9b1c7d402`: additive access tables following
  `d2b7e4f6a901`. No existing asset IDs, paths or media files change. No rows are
  automatically mapped to a library, so legacy assets remain denied by the new
  policy until an explicit, validated assignment is implemented.

The current application still uses its original unguarded routes. A successful
`require()` call is a point-in-time check, not a reusable grant. Media open/decode,
model invocation and delayed jobs must reauthorize at their actual service boundary.
This slice's `asset_metadata()` returns internal metadata only; paths must not become
public response fields. It does not exercise authenticated FileResponse or search
indexes. Unknown, upload, curation, destructive and voice capabilities are denied
by the new initial-release policy.

## Concrete security behavior

Invitation codes contain 128 random bits displayed as four groups of eight hex
characters for copy/paste. They are not six-digit SMS PINs. Default validity is
24 hours, with an explicit 1-second to 7-day bound. Issuing a replacement cancels
previous unused codes for the same phone/library. Only digests are stored.
Redemption checks the intended phone, code state/expiry, current owner authority,
current library/account state and membership revision. Concurrent redemption is
serialized in a SQLite write transaction: only one account/membership is created.
A stale invitation cannot undo a later owner decision. Explicitly re-inviting a
revoked member is a new owner approval; old codes cannot restore revoked access.

Passwords accept 15–128 characters without composition rules or silent trimming.
They use per-password random salt and scrypt with N=131072, r=8, p=1 (128 MiB work
memory, 256 MiB implementation limit), using Python/OpenSSL's maintained primitive.
Unknown-account password checks use the same KDF path. Corrupt/unsupported hash
formats fail closed. Parameters follow the [OWASP password-storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
This is deliberately a first-party password/session service, not a deployed
identity provider or an implementation of OAuth/OIDC.

Opaque session tokens contain 256 random bits, exceeding OWASP's recommended
minimum for newly generated session identifiers. Only a digest, account association,
expiry and revocation state are stored. Sessions have a fixed 24-hour lifetime in
this slice and no refresh protocol. Logout revokes the stored session; disabling
an account or revoking membership takes effect on subsequent checks. See the
[OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
Database backups still contain private phone labels and must be protected.

Original bytes/downloads require an explicit grant in addition to membership.
Even owners do not receive that grant implicitly. Owner membership management and
system-operator authority are separate records. New invitations grant viewer only.
Owner transfer, last-owner recovery, password recovery/change, phone changes and
account deletion require subsequent reviewed workflows; ordinary invitations must
never be reused as password-reset codes.

## Synthetic evidence and remaining gates

Run from this worktree root:

```sh
python3 -m unittest discover -s tests/security -v
python3 scripts/security_inventory.py
python3 tests/security/harness.py
```

The new tests execute real SQLite transactions and real scrypt checks, with only
newly generated synthetic databases and reserved fictional phone numbers. They
cover registration, repeat login, wrong recipient, expired/cancelled/replayed codes,
concurrent redemption, stale approvals, cross-library reads/counts, unassigned and
deleted IDs, original grants, operator separation, expired/revoked sessions,
account disable, secret-at-rest checks, and rollback when an audit insert fails.
Network listeners/connections and child-process execution are blocked during the
domain scenarios. No packages, accounts, actual credentials, SMS or external
identity integrations were installed or changed.

The Alembic wrapper is exercised against a minimal binding double that executes
its actual SQL on SQLite. **Installed SQLAlchemy/Alembic migration execution is
still unverified** because those packages are absent here and were not installed.
The revision explicitly begins the SQLite transaction when legacy driver behavior
would otherwise autocommit DDL. An authorized migration rehearsal must verify the
real driver, revision ledger, backups and restore together. Downgrade refuses to
drop security history; recovery requires reviewed offline backup restoration with
access kept closed. Access tables are not yet in `db.Base` ORM metadata: do not run
autogenerate against this branch until metadata reconciliation is reviewed.

The original 134-entry route inventory remains applicable. The separate legacy
denial gate still reports **84 security failures**, intentionally returning exit 1.
Passing new domain tests does not close those HTTP bypasses.

Observed local result on 2026-09-09: **45 tests passed** (24 new domain/credential/
migration tests plus the original 21 inventory/characterization tests), no skips or
xfails. The suite used host Python 3.14.7; no dependency files changed. Original
checkout and mobile repository were preserved; all source changes belong to
`codex/mobile-access-foundation`, continuing local commit `b652ffc`.

Before route integration/deployment, complete all of the following:

- Bounded global/source/account admission and durable attempt limits for login and
  registration, with uniform external errors and no secret/request-body logging.
  The dormant services are **not** a publicly usable login endpoint; scrypt's cost
  makes pre-KDF concurrency admission necessary, even for a small family.
- HTTPS; secure HttpOnly cookie/session and CSRF handling for the existing web UI;
  authenticated native bearer requests; origin/redirect policy and logout privacy.
- A reviewed synthetic legacy-data assignment covering every face/person, caption,
  album/cover/item, tag, video, task and index relationship. Close every old route
  and service bypass; partition search before top-k. Reconcile runtime `app.routes`.
- A real ORM/Alembic rehearsal, denial-before-files/providers/writes tests, and
  approved web/mobile reads including original/thumbnail/crop/video Range.
- Deliberate recovery, password change, owner transfer and account-deletion flows
  before a family pilot, along with session-duration and refresh decisions.

Next bounded implementation: reconcile access storage with the existing ORM and
build an isolated full-app transport harness with default-deny authentication,
login admission, shared session handling and the first media-route closure. Keep
the legacy failure ledger explicit until every endpoint is closed. No deployment,
push, mobile-repository change, Windows/Mac mini access or real-library use is part
of this slice.
