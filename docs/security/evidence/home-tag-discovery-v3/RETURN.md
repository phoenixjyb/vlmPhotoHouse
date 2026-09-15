# Home tag lookup source return

Base 590cc52ceeb7cdef1d2cae0bbc6aa36c16d75cd6, branch codex/home-discovery-v3.
Adds explicit discovery/v3 routes and an opt-in v2 metadata index with a 10,000-tag
bound. Legacy discovery/v2 and media/source-policy files remain unchanged.

Validation on macOS, existing disposable Python 3.12 environment:
- Full security suite: 542 tests, zero failures, four Windows-only skips, 118.958s.
- Includes full 6,002-tag export (legacy disables, opt-in preserves), Unicode query,
  final-page tag selection, actual producer golden responses, legacy coexistence,
  stale pins/revisions, actual-peer/credential denial, slow-body admission/release,
  and paired launcher inputs. Inventory: 178 method/path entries, no drift.
- No media, model, live database or identity inference used in source tests.

Separate runtime gates: native Limited-account export/composition resource checks,
unchanged catalog/media/audience verification, saved rollback and service identity.
Real projector/phone navigation remains separate from API and fixture evidence.
