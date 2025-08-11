# API Outline (Draft)

## Health
- GET /health -> { ok }

## Assets
- POST /ingest/scan { root_paths:[...]} (async trigger)
- GET /assets/{id}
- GET /assets?query params (filters)

## Search
- POST /search { query:"beach", filters:{person:[], date_range:[], tags:[]}, limit }

## Embeddings
- POST /assets/{id}/embed (force regenerate)

## Thumbnails
- GET /assets/{id}/thumbnail?size=256

## Captions
- GET /assets/{id}/caption
- POST /assets/{id}/caption { text } (user edit)

## Faces
- GET /assets/{id}/faces
- POST /faces/{person_id}/label { label }

## Albums
- GET /albums
- GET /albums/{id}
- POST /albums (manual smart album)

## Admin
- POST /tasks/retry-failed
- GET /metrics

## Auth (future)
- Basic token header

## Notes
- All POST endpoints return task id if asynchronous
- Pagination via cursor or offset/limit
