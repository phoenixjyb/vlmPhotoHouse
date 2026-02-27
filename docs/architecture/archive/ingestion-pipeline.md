# Ingestion Pipeline

## Stages
1. Discovery: walk roots; maintain seen set & modification cursor
2. Filtering: extension whitelist (jpg,jpeg,png,heic,mp4,mov,mkv), min/max size
3. Hashing: compute SHA256 (stream) + perceptual hash (fast pHash placeholder)
4. Metadata Extraction: EXIF (timestamp, camera, GPS), fallback to file mtime
5. Dedup: if SHA256 exists → link/skip; else create Asset
6. Scheduling: create tasks for thumbnails, embeddings, caption, faces (configurable)
	- Video (planned): probe → segment → keyframes → caption/embed/transcribe per segment
7. Persistence: commit in single transaction (Asset + tasks) for atomicity

## Idempotency
- Asset uniqueness by SHA256; near duplicate detection (future) via perceptual hash Hamming distance threshold.

## Rescan Strategy
- Track per-root last scan snapshot (list of (path, mtime, size, hash?)) minimal; recalc when mtime/size changed

## CLI (planned)
```
photoengine ingest --root /mnt/nas/photos --threads 8 --dry-run
```
Outputs summary: new, updated, duplicates, errors.

## Error Handling
- Failed task → retry with exponential backoff up to N times
- Hash errors (I/O) → logged and skipped

## Future Enhancements
- Watch mode (inotify / fswatch) for incremental updates
- Rate limiting for IO burst control
 - Scene/shot boundary detection for video segmentation (planned)
