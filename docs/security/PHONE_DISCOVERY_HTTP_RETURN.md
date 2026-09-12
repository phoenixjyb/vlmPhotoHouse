# Protected discovery HTTP candidate — source return

2026-09-12. Candidate implementation commit
`af8e0c8cf749f6e963dd8b196dce9aa842240387` on
`codex/phone-discovery-http-candidate`, isolated worktree
`_worktrees/phone-discovery-http-candidate` in the PhotoHouse workspace.
Base: `9881769baf8182536a0e9fbbe39648d534167970`.

The [interface guide](PHONE_DISCOVERY_HTTP_CANDIDATE.md),
[schema](phone-discovery-http-candidate-schema.json),
[producer examples](phone-discovery-http-candidate-examples.json),
[33-input manifest](evidence/phone-discovery-http-candidate/source-inputs.json) and
[verification receipt](evidence/phone-discovery-http-candidate/verification.json)
are ready for Android's independent review. Source remains unpublished.

`af8e0c8` supersedes `f2c8baf` after Android identified a schema-only canonical
string discrepancy: trailing `$` anchors could accept a final newline even though
the service rejected it. The schema now uses an absolute-end negative lookahead,
verified with both Python JSON Schema and ECMAScript regular expressions. New
HTTP/schema negatives cover LF, CRLF, tabs and Unicode line separators on IDs,
bindings and fingerprints. This was not an authorization bypass finding.

Added candidate-only facets/search transport, explicit composition and exact
handler registration, shared native/browser authentication and CSRF, bounded
nested JSON, authorization before disclosure and again after body receipt,
stale binding/fingerprint errors, 64-bit decimal-string IDs, cancellation and
synthetic producer/negative tests. The default application is unchanged.

151 selected regression tests passed without skips on the initial `f2c8baf`
implementation. After independent review, the corrected candidate passed 18
focused HTTP tests from extracted committed sources; all 14 producer examples reproduced
exactly and passed schema checks. The global inventory is complete at 164
method/path entries. Tests do not establish live deployment or repair retained
legacy/standalone authorization gaps.

All ten protected-phone source hashes remain unchanged. **18 of 19 old
home-discovery input hashes remain unchanged:** the shared global route inventory
intentionally changes to record the two candidate routes and explicit factory
topology. Home serving code, wire schemas/examples and the old source manifest
are unchanged. Do not claim all 19 hashes match or silently repin Android's home
contract. [Exact hash comparison](evidence/phone-discovery-http-candidate/frozen-inputs.json).

No live index, default-app mount, model, service restart, listener, Android edit,
persistent cache or new media grant was introduced. The separate Windows media
qualification continues on its pinned `ee5c06f` source; none of these candidate
files were copied into that job or a live service.

Before Android import, independently review the schema/examples/source manifest,
replay both operations and negative cases, and approve an opt-in candidate pin.
Then review protected prepared-derivative descriptors/Range access as a separate
capability. Existing original permission is not a substitute. Production-size
index admission, provider provenance, SQLite/busy/I/O cancellation limits, live
wiring and physical device acceptance remain open.

Find the evidence commit with
`git log -1 --format=%H -- docs/security/PHONE_DISCOVERY_HTTP_RETURN.md`.
