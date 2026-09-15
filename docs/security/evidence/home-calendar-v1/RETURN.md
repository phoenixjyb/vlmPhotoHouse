# Home calendar and people review source return

Base 52c3bac16c85d3b0f40d29cfa10c2e473756cfe1, branch codex/home-discovery-v3.
Calendar adds one opt-in read-only route over the existing metadata/media bindings.
The exporter accepts people only through a separate catalog-bound roster/assignment
review and approval. Real family data is kept out of source and fixtures.

Validation: full backend security suite passed 551 tests, four platform skips,
117.453 seconds. Affected calendar (5), people-review (4) and launcher (11) tests
passed again after final bounds and launcher checks. Inventory:179 method/path
entries, no drift. Examples are exact output from the synthetic producer.

Cases cover year/month/day counts, existing-media covers, unknown dates, metadata
binding, stale revisions/index, actual peers, unchanged older routes, explicit
manual-only assignment review, changed names/assignments/catalog and missing approval.

Native service qualification, approved real people publication and physical phone/
projector acceptance are separate gates. Source tests do not approve real mappings.
