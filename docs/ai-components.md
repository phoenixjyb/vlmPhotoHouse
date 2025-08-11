# AI Components

| Component | Role | Initial Model | Upgrade Path |
|-----------|------|---------------|--------------|
| Image Embedding | Semantic search | CLIP ViT-B/32 | SigLIP / CLIP ViT-L/14 |
| Captioning | Descriptions | BLIP2 VICUNA / OPT small | LLaVA / InternVL |
| Face Detection | Locate faces | RetinaFace (light) | More accurate variant |
| Face Embedding | Person clustering | ArcFace (InsightFace) | Higher-dim variant |
| OCR (future) | Text-in-image | Tesseract / EasyOCR | TrOCR / Donut |
| Speech-to-Text (future) | Voice annotations | Whisper small | Faster-whisper large |
| Summarization (future) | Album summaries | Local LLM (7B) | 13B w/ quantization |

## Tiered Inference
- Tier 1 (fast path): lightweight models for immediate features
- Tier 2 (refine): heavier models scheduled during idle

## Optimization
- Mixed precision (FP16) on GPU
- Batch size autodetect based on VRAM
- Embedding cache keyed by (model_version, hash_sha256)

## Replacement Policy
- Maintain registry: model_name → version, path, checksum
- Allow rollback by keeping previous version artifacts
