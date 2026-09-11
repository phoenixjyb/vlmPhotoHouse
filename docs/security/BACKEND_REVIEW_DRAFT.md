# Review draft: protected PhotoHouse account and library foundation

PhotoHouse's old application exposed library and operational routes without a
shared account boundary. This foundation makes the normal API entry point closed
by default and supplies an explicitly configured protected application for the web
and future mobile clients. A new phone login gains library access only through an
owner-issued phone-bound invitation. Phone labels are not SMS verification.

The protected slice supports sessions, scoped membership, gallery/detail/captions
and authenticated cached media reads. Originals require a separate grant and stay
off in the first pilot. Retired legacy routes fail closed, including operational,
search, album and voice paths outside this slice. The old handlers remain in
historical/legacy code; the inventory and retained failed denial ledger describe
that exposure rather than claiming those handlers were fixed.

The web entry point is the new protected UI. The former family viewer, caption
workers and model services are not automatically launched by this release. Six
combined launch/coordinator scripts now refuse before cleanup, ingestion, model
loading or runtime work. Follow `PROTECTED_UPGRADE.md`; an ordinary checkout update
is not a service cutover. Existing installed releases and real databases must be
preserved until their separate migration, writer compatibility and rollback review.

Offline tools provide explicit new-file initialization, backup verification,
quarantined migration candidates and first-owner recovery. No public owner signup,
implicit database migration or automatic restored-viewer reopening is added.
A fixed source-package allowlist and exact CPU dependency locks separate the
protected service from the ML runtime. Configuration, credentials and media remain
outside the source archive and repository.

Validation at the launch-integration checkpoint: 277 synthetic security tests,
five native Windows PowerShell retirement checks, one shell refusal check, three
archive tests, and extracted-package smoke (seven ASGI checks, nine operator and
eight database-preparation invocations). [Windows staging evidence](WINDOWS_STAGING_RETURN.md) is separate from
source tests: 26 HTTPS checks, scoped rollback/restart, seven post-restart checks
and a verified second-machine LAN request. No CI workflow is configured here.

Integration target is GitHub **master**, observed at
`b886aca9344c8f9e838f28e2a1b380caad0ec40e`. A dry merge of the preceding candidate
completed without textual conflicts. Nine master commits include caption and
legacy viewer work that must remain in the integrated result. Do not force-update
master or describe the earlier fast-forward assessment as current. This draft is
a local review artifact; it is not a published or approved pull request.
