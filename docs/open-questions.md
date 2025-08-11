# Open Questions

| Area | Question | Notes |
|------|----------|-------|
| Vector DB | Start FAISS only or include Qdrant container now? | Simplicity vs future incremental updates |
| Metadata DB | Remain on SQLite until what scale? | Possibly switch at >5 concurrent writers |
| Perceptual Hash | Which algorithm pHash/aHash/dHash or CNN? | Start simple pHash |
| Face Clustering | Algorithm choice? | HDBSCAN good for variable density |
| Event Segmentation | Time gap G? Distance D? | Need empirical tuning |
| Text Embedding | Use CLIP text vs sentence-transformer? | Evaluate retrieval quality |
| GPU Strategy | Single vs multi-GPU scheduling? | Depends on hardware |
| Privacy | Encrypt metadata DB? | Optional feature flag |
| Backups | Snapshot frequency? | Weekly default |
| Near-Duplicate | Visual similarity threshold? | Hamming distance, later embedding sim |
