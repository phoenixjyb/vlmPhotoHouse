# Family Stories and Home/calendar integration

Source commit: `0a6e036489dd8af5d0e0d7c0afcc82f3675258b4` on `codex/family-stories-integration`.
This merges the reviewed Family Stories evidence head `2ad064fb845fc077bb4ecfdb38494023022e3c0a` with the default branch after Home/calendar PR 9. The original Family Stories and captioning worktrees were not edited.

The only conflict was the route inventory. Reconciliation retains both branches' reviewed capability definitions, protected story routes and separate Home app topology; no application logic changed. The resulting inventory validates 185 entries. It grants no new anonymous story route.

Validation on the combined source: 592 security tests run, 588 passed and four native-Windows tests skipped (134.727 seconds); all 13 focused migration tests and 22 Chromium-to-ASGI scenarios passed. Existing resource/deprecation warnings and expected negative-CLI messages remain in test output. No live Windows, database, GPU, service or network listener was accessed.

A 65-file immutable source package was built from the exact source commit and every member hash checked. Package SHA-256: `d4d055b382626989a57be7fb13b0f4657826976968d19198d9a9b81847d7bd29`. Fresh-process smoke passed seven ASGI checks, nine operator commands and eight database-preparation commands using only synthetic SQLite at schema `c7f4a9e2b610`, with socket binds/connects and external subprocesses forbidden. The packager requires a full commit and canonical output path; preliminary HEAD/symlinked-output invocations were refused without writing a package.

[Aggregate receipt](verification.json) records exact source parents and log hashes. The existing Family Stories producer pin remains immutable; the coordinator still owns any mobile shared-contract adoption. This integration changes Git source only. Protected runtime migration/deployment, live library performance, private-story TV publication and physical device acceptance remain separate gates. Existing Home service and media preparation must retain their currently approved source/configuration until a separately qualified rollout.
