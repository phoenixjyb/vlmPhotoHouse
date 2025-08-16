# Initial Backlog (Prioritized)

## P1 (Immediate)
- Add logging setup (structlog or stdlib) in API
- Design SQLite schema DDL script
- Implement config loader (env + defaults)
- Implement hashing + EXIF extraction function
- Implement simple ingestion CLI (scan + persist + schedule tasks table entries)

## P2 (Next)
- Implement task processing loop (in API process initially)
- Thumbnail generation module
- CLIP embedding stub (random vector) → real model loader
- Vector index abstraction + FAISS flat index
- /search endpoint (text only returning empty for now)

## P3
- Integrate real CLIP model
- Populate embeddings and enable similarity search
- Implement caption generation stub
- Add migration/version tracking table

## P4
- Real BLIP2 caption integration
- Text embedding index + hybrid scoring
- Face detection & embedding pipeline (stub)

## P5
- Face clustering logic + person labeling endpoints
- Event segmentation job
- Smart album rule parser

## P6
- Whisper integration for voice annotations
- Album summarization prototype
- Relevance feedback adjustments

## Continuous
- Improve test coverage
- Performance instrumentation
- Documentation refinement
