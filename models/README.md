# Models Directory

This directory contains ONNX models for face embedding.

## LVFace Models

### Built-in Model (Dummy)
- `lvface.onnx`: A dummy model for testing/CI (256-dimensional output)
- Generated via `tools/generate_dummy_lvface_model.py`
- Only suitable for testing, not real face recognition

### Real LVFace Models (External)
To use real LVFace models with their dedicated environment:

1. **Set up external LVFace directory** (e.g., `C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace`)
   - Should contain `.venv` with LVFace dependencies
   - Should contain `models/` with real ONNX models
   - Should have `inference.py` with `get_embedding(image_path, model_path)` function

2. **Configure environment variables:**
   ```bash
   FACE_EMBED_PROVIDER=lvface
   LVFACE_EXTERNAL_DIR=C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace
   LVFACE_MODEL_NAME=your_model.onnx
   FACE_EMBED_DIM=512  # or your model's dimension
   ```

3. **Verification:**
   ```python
   import onnxruntime as ort
   session = ort.InferenceSession('lvface.onnx')
   print("Input shape:", session.get_inputs()[0].shape)
   print("Output shape:", session.get_outputs()[0].shape)
   ```

## Model Requirements

LVFace ONNX models should:
- Accept input shape `[1, 3, 112, 112]` (NCHW format, RGB)
- Produce output shape `[1, D]` where D is embedding dimension
- Input range: `[0, 1]` (normalized RGB values)
- Output: Raw embedding (will be L2 normalized by the provider)

## Testing

```bash
# Test with built-in dummy model
FACE_EMBED_PROVIDER=lvface LVFACE_MODEL_PATH=models/lvface.onnx pytest -k lvface

# Test with external real model
FACE_EMBED_PROVIDER=lvface LVFACE_EXTERNAL_DIR=/path/to/LVFace LVFACE_MODEL_NAME=real_model.onnx pytest -k subprocess
```
