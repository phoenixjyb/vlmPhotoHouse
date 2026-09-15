# Home discovery v2 with current media delivery

Opt-in source candidate. No launcher, live index, listener, assignment approval or
publication change is included. The existing discovery/v1 files and examples stay
unchanged. Protected account APIs remain separate.

`create_home_discovery_delivery(config, sources, cache, index_path, index_sha256)`
composes a reviewed discovery index with `create_home_originals` using the same
Publication object, source policy, config and actual-peer/TLS boundary. A different
media configuration is rejected. Metadata and source indexes bind the exact catalog;
source-index replacement invalidates discovery as well as media. Shared disable
revokes both. Results never export filesystem paths or invent original permission.

- GET `/home/discovery/v2/facets`: same parameters, capabilities, pinned-person
  ordering, roster pagination and provenance as discovery/v1; response version 2.
- POST `/home/discovery/v2/search`: same exact request, filter meanings, fingerprint,
  revision and pagination checks as v1; response version 2, with v3 media items.
- Search items match `/home/v3/catalog` item shape: on-demand previews, permitted
  original quality, prepared and explicitly admitted direct video. Their URLs use
  `/home/v3/assets/...`. No older-route fallback or implicit original grant.
- Search result paging is independent of readiness browsing. The v1 filter schema
  has no ready-only/order field; clients must not silently apply a page-local filter
  or claim ready-first ordering for the full search. Themes/topics remain disabled.

All existing discovery limits apply: 16 KiB request, 512 KiB reply, two matching
slots, bounded immutable index and matching deadline. This candidate does not solve
full-library initialization, slow-body admission or network deployment qualification.
There is no persistent cache change, live database export or identity inference.
Family aliases/order and reviewed person assignments must come from a privately
reviewed index. Caption/tag/region coverage must be measured for that publication.

`home-discovery-delivery-examples-v2.json` is generated from the actual synthetic
composition and checked by `test_home_discovery_delivery.py`. It contains two
prepared items, an on-demand photo and an admitted direct video. Run with the CPU
access-test lock plus the pinned Pillow preparation dependency:

```
python -m unittest discover -s tests/security -p 'test_home_discovery*.py'
python -m unittest discover -s tests/security -p test_on_demand_delivery.py
```

Acceptance remains tiered: synthetic in-process routes and native Android tests do
not establish a live reviewed metadata publication, actual LAN access, phone or
projector playback. The current media preparation/captioning runtime is unchanged.
