# Home search deployment support

This additive source slice preserves current readiness browsing by integrating the
current default branch before deployment. `home_search_app.py` explicitly composes
reviewed discovery/v2 with v3 media; `home_feed_background.py --kind v3-search`
requires an index and checksum, keeps no-console bounded logging and the existing
TLS/audience/options. Older kinds reject discovery flags.

Discovery POST bodies now have two admission slots, a 16 KiB bound and a five-second
body deadline. Saturation returns 429; slow bodies return 408 and release admission.
The separate existing matching-slot and two-second matching budget remain unchanged.

`export_home_search_metadata.py` is an explicit metadata-only exporter for an
existing exact catalog. It uses one read-only SQLite transaction, fixed queries,
4 MiB SQLite cache, one-million scanned-row budget, 120-second cooperative deadline,
64 MiB index output bound, and one fresh exclusive output. It reads no media or
face data, creates no database snapshot, and changes no publication or live DB.
Real execution must additionally use the tested 2 GiB Windows process-tree envelope
and 8 GiB free-memory floor; cooperative limits alone are not a hard memory guard.

Caption ambiguity, user edits/superseded status, tag conflicts/blocks/provenance and
recorded dates retain the existing reviewed export policy. People and coarse regions
remain disabled until separately reviewed mappings and assignments are available.
If the selected tag roster exceeds the current 5,000-entry contract, the entire tag
capability is disabled with an explicit coverage count; it is never silently truncated.
Current catalog selection and original/prepared media descriptors are unchanged.

The index is an immutable metadata snapshot, not an automatically refreshing view
of ongoing captions. The deployment operator reviews its aggregate coverage, binds
its exact checksum, qualifies current scope/media/metadata and saves rollback before
switching the existing service action. Later catalog publications require a matching
new metadata snapshot; catalog/index mismatch must fail closed. Native qualification,
trusted HTTPS from an actually allowed peer and physical-device acceptance are
separate evidence. Credentials and real metadata stay in private Windows stages.
