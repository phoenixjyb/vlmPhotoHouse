# Data Model (Initial Draft)

## Entities
- Asset(id, path, hash_sha256, perceptual_hash, mime, width, height, orientation, taken_at, camera_make, camera_model, lens, iso, f_stop, exposure, focal_length, gps_lat, gps_lon, file_size, created_at, imported_at, status)
	- Planned additions: media_type('image'|'video'), duration_seconds, fps, video_codec, audio_codec
- DerivedArtifact(id, asset_id, kind, path, size_bytes, width, height, version, created_at)
- Embedding(id, asset_id, modality, model, dim, storage_path, vector_checksum, created_at)
- Caption(asset_id, text, model, user_edited, created_at, updated_at)
- FaceDetection(id, asset_id, bbox_x, bbox_y, bbox_w, bbox_h, embedding_path, person_id, confidence, created_at)
- Person(id, label, seed_count, cluster_id, active, created_at, updated_at)
- VideoSegment(id, asset_id, t_start_seconds, t_end_seconds, keyframe_path, caption, transcript_slice, embedding_path, created_at)  <!-- planned -->
- Transcript(asset_id, text, model, language, created_at)  <!-- planned -->
- Tag(id, name, type, created_at)
- AssetTag(asset_id, tag_id, confidence, source, created_at)
- Album(id, type, name, rule_json, last_materialized_at, created_at)
- Task(id, type, payload_json, state, priority, retry_count, last_error, created_at, updated_at, scheduled_at)
- Setting(key, value_json, updated_at)

## Indexing Considerations
- Composite indices: (hash_sha256), (perceptual_hash), (taken_at), (type,name) on Tag, (asset_id, modality) on Embedding.

## Notes
- Embeddings stored as files to keep DB slim; DB stores metadata & checksum.
- rule_json in Album stores query DSL (future design in `albums-and-theming.md`).
 - Video frames/embeddings stored under derived/video_frames and derived/video_embeddings (planned).
