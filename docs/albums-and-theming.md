# Albums & Theming

## Types
- Person: rule = person_id
- Time: rule = date range (year/month/day)
- Event: rule = temporal cluster + optional geo cluster label
- Theme: rule = semantic concept (embedding centroid + similarity threshold)
- Manual / Smart: user-specified query DSL

## Event Detection Heuristic (Draft)
- Sort assets by taken_at
- Segment when gap > G minutes (e.g., 180) or location distance > D meters
- Summarize event (dominant location name + top tags + time span)

## Theme Generation
- Periodic clustering (e.g., k-means or HDBSCAN) over recent embeddings sample
- Label via caption keyword extraction + top tags

## Person Albums
- After clustering faces, each Person with label forms album
- Confidence threshold for auto-inclusion; borderline faces queued for review

## Materialization
- Albums may be virtual (query executed at request) or cached snapshot materialized_at

## Query DSL (Early Idea)
JSON structure:
```
{
  "all": [ {"person": "alice"}, {"tag": "beach"} ],
  "any": [ {"year": 2024} ],
  "none": [ {"person": "bob"} ]
}
```

## Open Questions
- UI constraints for album editing
- Event gap & distance thresholds
- Automatic theme count limit
