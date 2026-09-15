# Home calendar and reviewed family shortcuts

Calendar browsing is opt-in alongside discovery/v3 and uses the same immutable
metadata index, media publication and source policy. No existing response schema
changes. No new media, original-byte, account or audience grants are introduced.

`GET /home/discovery/v3/calendar?revision=N` returns version 1, newest years first.
Optional `year` (1–9999) selects months; `year` plus `month` (1–12) selects days.
`page` defaults to 1 (maximum 1000); `page_size` defaults to 12 (maximum 12).
A revision is always required. Unknown parameters, credential/Range headers,
unapproved actual peers and mismatched metadata are rejected. Direct HTTPS/Host,
no-store, two matching slots, five-second cooperative calculation and 512 KiB
response bounds apply. No dates are inferred or shifted across time zones.

The envelope contains version, revision, catalog_revision, binding, library,
level, year, month, page, page_size, total, has_more, dated_assets, undated_assets,
and items. Each item has key, from_date, through_date, count and nullable cover.
The key is YYYY, YYYY-MM or YYYY-MM-DD; the inclusive range represents the complete
year/month/day. Counts cover the full dated catalog, before other user filters.
Missing dates are explicitly counted. Calendar selection fills the existing date
filter and preserves the draft's people, tags and other criteria until Apply.

The binding is SHA-256 of UTF-8 JSON with recursively sorted keys, no whitespace,
unescaped Unicode, comprising the same discovery/v3 facet envelope fields:
revision, catalog_revision, library, capabilities, pinned_person_ids, pinned_people.
Consumers compare this against their verified discovery snapshot. Covers use exact
existing v3 asset descriptors, choosing a preview-capable item from at most eight
newest candidates in the bucket. A missing cover never hides the bucket or its count.
Clients fetch covers through the same checked media transport and bounded in-memory
thumbnail store. Backgrounding, metadata replacement and denial clear this state.

`home_search_app.py --calendar-enabled` requires the tag index/checksum as well as
the legacy index. The background v3-search launcher forwards the flag. Android's
`photohouseHomeCalendarEnabled` defaults off and requires tag lookup; production
connection settings remain private build inputs. Real device testing is distinct
from synthetic UI and adapter checks.

## Explicit people review

`prepare_home_people_review.py` creates a catalog-bound proposal from an explicit
roster (person ID, exact stored name, display label, aliases, pinned IDs) and existing
manual face assignments within that catalog. It reads metadata only in a read-only
transaction, with row/time/byte limits. It never approves itself, infers identities,
reads image/embedding data, mutates the database or copies media.

`export_home_search_metadata.py --people-review FILE --people-approval FILE` adds
people to either supported metadata index only after checking a separate approval:
`version:1`, `review_sha256`, `approve_roster:true`, `approve_assignments:true`.
The review's catalog hash, each stored person name, and every exact face/asset/person/
manual-source tuple are rechecked inside the export transaction. Any drift refuses
the export. Newly discovered or automatic assignments are not silently included.
Aliases and person IDs must never be hardcoded into the public Android application.

A real review requires the owner's decision about the concrete proposed roster and
assignments. Native export/qualification must retain the existing memory envelope,
audience, rollback and independent legacy/tag metadata pins. A review file alone is
not publication authority. Future catalog changes require a new bound review.
