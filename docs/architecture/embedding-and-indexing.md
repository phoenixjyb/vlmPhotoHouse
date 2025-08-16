# Embedding & Indexing Strategy

## Modalities
- Image Embedding: CLIP ViT-B/32 (initial) → upgrade path to ViT-L/14 or SigLIP
- Caption Text Embedding: same CLIP text tower or sentence-transformer
- Face Embeddings: InsightFace model (ArcFace) small variant

## Generation Workflow
1. Queue embedding task after Asset creation
2. Batch N images for GPU pass
3. Store raw vector (.npy) + metadata row (model, dim, checksum)
4. Update vector index (append & rebuild or incremental add)

## Vector Index Options
- Phase 1: FAISS (Flat / IVFFlat) local file
- Phase 2: Qdrant container (HNSW) with persistence

## Hybrid Ranking
score = α * image_sim + β * text_sim + γ * metadata_boost
- metadata_boost derived from recency, person match, tag exact match
- weights configurable in settings

## Maintenance
- Rebuild index command (export embeddings → build new file → swap)
- Model upgrade: compute new embeddings side-by-side (new model version) then re-point active index

## Face Pipeline
- Detect faces (retinaface) → crop → embed → cluster
- Clustering: incremental DBSCAN/HDBSCAN or hierarchical clustering over new faces
- Person assignment: user labels cluster; propagate person_id

## Storage
```
embeddings/{model_version}/{asset_id}.npy
faces/{asset_id}/{face_idx}.json (with bbox + embedding ref)
```

## Open Decisions
- Which sentence transformer for caption text? (all-MiniLM vs CLIP text)
- Index quantization (PQ) when > 5M vectors (future)
