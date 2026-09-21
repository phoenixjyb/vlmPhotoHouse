# Local bilingual place search

The protected locations facet accepts optional `q` (at most128 UTF-8 bytes):

`GET /libraries/{library}/discovery/v1/facets?facet=locations&q=Beijing`

The existing response, place IDs and asset-search filters are unchanged. Names
are normalized locally for Unicode width, case, accents and whitespace, then
matched as substrings against the place label and explicitly supplied aliases.
Blank queries list the catalogue. Query text is accepted only for locations,
never interpreted as SQL, regex or an online geocoder request. Pagination uses
filtered counts. Clients reset page1 when submitting another query and retain
that query on subsequent pages; selected IDs remain explicit and removable.
There is no automatic selection even for a single suggestion. Ambiguous names
return separate parent-qualified choices, including zero-count regions.

`NamedPlace` adds optional aliases without modifying the serialized shape of an
old `ReviewedPlace`. The strict loader/producer accepts up to8 bounded aliases
per entry. Region rules, membership checks, read transactions, source freshness,
limits and 409 behavior remain unchanged. Aliases are not returned on the wire;
the service returns only matching existing place labels, IDs and counts.

## Initial catalogue

`place-catalogue-china-starter.json` is public geographic reference data, not a
library index or a list of family locations. The source notes are in
`PLACE_CATALOGUE_SOURCES.md`. It supplies9 cities/districts: Beijing, Tianjin,
Guangzhou, Shenzhen, Chengdu, Shanghai, Beijing Haidian, Beijing Chaoyang and
Liaoning Chaoyang. These are approximate rectangular search areas, not exact
administrative polygons. They can overlap and include nearby municipalities.
The bilingual labels expose this limitation. Missing GPS is never guessed.
This is an extensible starter, not a worldwide address, landmark or street lookup.
Unsupported names return no matches. Caption mentions remain a separate search
criterion and are not treated as geographic evidence.

An operator can pass the public catalogue as `--regions` to
`prepare_access_places.py --refresh-current-library`. The resulting library
artifact contains private membership IDs and remains on its Windows owner.
Qualify actual region counts/runtime budgets before activation. Changes to the
catalogue require a new artifact and explicit reload; uploads and GPS corrections
are handled by the existing per-request current-library refresh.

WebUI and protected phone use the same name query. Anonymous Home/TV publication
is separate and receives neither this protected catalogue nor library access
implicitly. No external geocoder, new worker, database migration or model is used.
