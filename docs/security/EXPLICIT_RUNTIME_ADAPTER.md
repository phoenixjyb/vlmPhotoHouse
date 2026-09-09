# Explicit existing-database runtime adapter — slice 10

Local synthetic checkpoint following `b448424`, 2026-09-09. The default
`app.main:app` remains closed. This slice supplies a deliberately constructed
adapter, not environment discovery or a deployment configuration.

`RuntimeConfiguration` requires an explicit canonical absolute database `Path`,
HTTPS web origin, original roots and derived root. `build_app()` opens no files,
database, network listener or worker. It does not read `.env`, DATABASE_URL, model
settings, proxy headers or machine-specific defaults. Storage is opened lazily
inside the request's worker thread through `ExistingDatabase`.

Each connection:

1. Requires the explicitly selected regular file, refuses symlinks/noncanonical
   paths and uses SQLite URI `mode=rw` so a typo cannot create an empty database.
2. Checks file identity around opening, enables foreign keys and disables trusted
   schema functions. It uses a bounded lock timeout and a fresh connection.
3. Requires exactly migration head `a5d2e8f4b610`, the required access/read tables,
   and an existing 32-byte BLOB admission key. Missing, old, multiple-head or
   malformed storage fails closed with a generic response. Nothing is repaired,
   regenerated, migrated, bootstrapped or implicitly assigned.
4. Leaves transaction commits to the domain operation. It rolls back forgotten or
   failed uncommitted work and always closes the connection.

The schema revision/table check is a compatibility gate, not verification of an
untrusted administrator-controlled database. SQLite files/directories and media
writers remain trusted deployment inputs. File identity checks do not establish a
Windows filesystem security guarantee; migrations/replacements require quiesced,
reviewed offline procedures. No live database has been opened to validate them.

## Evidence

**143 Python security tests passed in 17.559 seconds**, including eleven adapter
tests using only temporary migrated SQLite. They cover actual login/gallery via
the adapter, no I/O during import/build, missing-file noncreation, old/multiple
heads, missing tables, missing/wrong-type admission keys, symlinks/directories/
corruption, rollback/closure, actual migration-head agreement and rejection of
HTTP/host spoofing through untrusted forwarding headers.

The browser bridge now constructs this exact adapter. **13 real Chromium checks
passed** against the real UI/ASGI/migrated SQLite path with no listener, external
page requests or browser errors. See [results](evidence/runtime-slice10/result.json).
The inventory remains **152 entries / 23 active routes**; no new API is added.

Reproduce with the commands in [the web checkpoint](WEB_INVITATION_GALLERY.md).
No real TLS certificate/proxy, Windows file sharing, live migration, user acceptance,
mobile build, original asset mapping, or operational deployment is implied.

Next reviewed implementation: deliberate offline owner/bootstrap and asset-mapping
workflow, with explicit target/manifest review, no default grants, conflict detection,
audited application and synthetic backup/restore rehearsal. Recovery, password/phone
changes, owner transfer, scoped albums/search and authorized worker/voice integration
remain separate. This adapter is not authority to run any of those on real data.
