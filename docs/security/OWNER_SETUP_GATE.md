# First owner password and protected WebUI cutover

Current source now requires the [library-management migration](LIBRARY_MANAGEMENT.md).
Its native qualification and legacy ownership import are still cutover gates.

The first owner password is entered **during the approved Windows cutover
maintenance window, before protected traffic is enabled**. It need not wait for
the caption refresh campaign to finish. It must not be pasted into chat, a script,
a command argument, an environment variable or a repository file.

The existing [operator tool](OPERATOR_TOOL.md) creates the selected new account as
both a system operator and an approved owner of the selected family library.
System-operator status alone does not bypass library membership. The phone is a
login label, not SMS verification. The WebUI defaults bare 11-digit input to +86.
Keep the real phone and exact host paths in the separately reviewed private request,
not in this document or example fixtures.

## Sequence

1. Complete agreed protected management coverage and local checks. Identify the
   exact Windows release, serving configuration, database, selected audience and
   rollback approach. Confirm the owner is ready at the Windows keyboard; do not
   begin an outage while waiting for password input.
2. In an explicitly approved window, drain and fence all database writers, including
   the independent caption worker. Capture queue state and make/verify a fresh
   matching private backup with host ACLs. Do not use an older rehearsal snapshot.
3. Review/apply the additive [access schema](SCHEMA_APPLICATION.md), preserving
   existing media and caption records. Inspect receipts and actual state after
   interruption; never blindly rerun or restore over newer work.
4. Prepare a fresh post-schema matching backup and unexpired `plan-owner`; validate
   and review it using `scripts/provision_access.py`. Only then execute `apply`
   interactively on Windows. It prompts twice with echo disabled, refuses insecure
   input fallback, and stores a password hash. Use a unique 15–128-character
   passphrase. The operator tool does not choose or output the password.
5. Review/apply the selected asset-to-library mapping separately. Bootstrap creates
   no session, asset mapping or automatic original-download grant. The owner must
   sign in normally before testing library and management permissions.
6. Verify HTTPS, anonymous denial, owner login and approved management operations;
   test member access separately. Isolate the legacy unauthenticated UI and media
   paths so they cannot bypass the protected application. Merely adding a password
   to the database does not secure the old server.
7. Re-enable the reviewed serving/worker configuration and confirm actual caption
   queue progress. Face-processing jobs have a separate compatibility gate. Test
   Mac/Windows browser and family-device behavior, not just HTTP health.

The protected management WebUI requires login on Windows too; localhost is not an
admin identity. Anonymous selected TV/LAN feeds and read-only SMB are separate
audiences and should not be silently broadened or removed by this transition.

This is a source-reviewed procedure, **not evidence that the real password has
been set or that production is protected**. Current host/account state must be
rechecked before provisioning. Forgotten-owner recovery is the separate, reviewed
[offline owner-recovery procedure](OWNER_RECOVERY.md), not a public reset shortcut.
