# Home tag lookup v3

An explicitly enabled addition to Home discovery. Existing discovery/v1 and /v2,
media catalogs and original/prepared delivery contracts are unchanged. No protected
account routes are exposed. All requests retain the exact HTTPS origin, Host,
actual-peer allowlist, credential denial and no-store boundary of Home delivery.

`GET /home/discovery/v3/facets` and `POST /home/discovery/v3/search` retain the
v2 fields, limits, revision/catalog binding and media v3 descriptors. Responses
have `version: 3`. Facets additionally require a `query` string echo. The optional
`q` query parameter defaults to empty, is trimmed, at most 128 UTF-8 bytes, and
contains no control characters. Nonempty q is valid only for the tags facet.
Tag matching is NFKC casefold literal substring over tag labels, not an asset
caption search. Results remain sorted by numeric tag ID; total and has_more refer
to matching tags. Pages default to 50, at most 100 items. No automatic all-tag fetch.

The separately checksum-bound metadata index has `version: 2` and at most 10,000
tags, with the existing 100 links per asset, exact ID references/provenance and
all other original index constraints. `export_home_search_metadata.py --tag-lookup`
exports this version. The default still exports frozen v1 with a 5,000-tag bound.
Overflow disables the whole tag capability with a coverage receipt; no truncation.
Caption/tag ambiguity and blocked assignments retain the existing exclusion rules.
No person/region inference, raw GPS, live DB serving or taxonomy generation is added.

Android uses `photohouseHomeTagLookupEnabled=true` only with explicitly configured
Home discovery. Both phone and TV load the first page, offer tag-name lookup, and
retain up to 20 selected tags across queries under the same metadata binding.
Loaded-match counts exclude retained selections outside the current query. Old
responses, changed revisions/query echoes and inconsistent pagination are rejected.
Backgrounding discards the editor and late responses. No lookup silently broadens
an asset search into the full catalog.

Deployment: `home_search_app.py` or background `--kind v3-search` requires both
`--tag-index` and `--tag-sha256` to enable the new routes, alongside the separately
pinned legacy discovery index. Missing pairs fail before serving. A fresh catalog
publication requires separately bound fresh legacy and tag indexes. Keep rollback,
the existing audience, and media/source-policy pins; qualify native resource use
under the 2 GiB process-tree envelope and 8 GiB available-memory floor. Real-device
navigation and playback remain acceptance checks beyond API/fixture evidence.
