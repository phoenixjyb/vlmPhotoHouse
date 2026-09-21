# Protected discovery review input

`scripts/prepare_access_discovery_index.py` keeps its default output limited to
`date` and `media`. An operator may pass `--review /absolute/path/review.json`
to add explicit reviewed records. The file is read once, must be a direct local
regular file, and is never written back.

The JSON object must contain exactly these keys:

```json
{
  "library_id": "family-a",
  "source_digest": "<sha256 from a current default preparation>",
  "indexed_ids": ["101"],
  "enabled": ["people", "date", "caption", "tags", "locations", "media"],
  "people": [{"id": "301", "label": "Reviewed person", "aliases": ["name"], "allow_zero": false}],
  "pinned_ids": ["301"],
  "assignments": [{"id": "1", "asset_id": "101", "person_id": "301", "source": "manual"}],
  "places": [{"id": "601", "label": "Reviewed region"}],
  "regions": [["101", "601"]],
  "source_fields": {"caption": "current_source", "tags": "current_source"}
}
```

`indexed_ids` may select a subset of the current visible scope. People
assignments must refer to existing face rows and use `manual` provenance;
unreviewed detections, inferred names, and invented IDs are rejected by the
same `ReviewedIndex` validator used by the service. `allow_zero` is an explicit
roster decision for a person with no assigned face.

`caption` and `tags` can be enabled only when their corresponding
`source_fields` value is exactly `current_source`. This declares use of the
service's current bounded caption/tag projection; it does not approve or infer
new metadata. Omit `--review` to retain the date/media-only behavior.

The file's `library_id` and `source_digest` must match the invocation and the
current read-only database projection. Any ingest, metadata, tag, or reviewed
assignment change therefore requires a newly prepared digest and review file.
