# LVFace Integration Summary

## What's Implemented

✅ **Dual LVFace Support**: The system now supports both built-in and external LVFace models:

1. **Built-in Mode** (Default)
   - Uses `models/lvface.onnx` with current project's `.venv`
   - Good for testing and CI with dummy models
   - Simpler deployment

2. **Subprocess Mode** (Production)
   - Uses external LVFace installation with its own `.venv`
   - Calls real LVFace models via subprocess
   - Keeps environments isolated
   - Better for production with real models

## Configuration

### Built-in Mode
```bash
FACE_EMBED_PROVIDER=lvface
LVFACE_MODEL_PATH=models/lvface.onnx
FACE_EMBED_DIM=256  # or your model's dimension
```

### Subprocess Mode (for real models)
```bash
FACE_EMBED_PROVIDER=lvface
LVFACE_EXTERNAL_DIR=C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace
LVFACE_MODEL_NAME=your_real_model.onnx
FACE_EMBED_DIM=512  # or your model's dimension
```

## Files Created/Modified

### New Files:
- `backend/app/lvface_subprocess.py` - Subprocess provider implementation
- `backend/tests/test_lvface_subprocess.py` - Tests for subprocess mode
- `test_lvface_integration.py` - Demo script for both modes

### Modified Files:
- `backend/app/face_embedding_service.py` - Added subprocess provider selection
- `backend/app/config.py` - Added external dir and model name settings
- `backend/app/main.py` - Updated health endpoint to show LVFace config
- `backend/tests/test_face_embedding_lvface.py` - Fixed settings cache clearing
- `models/README.md` - Updated documentation

## Testing

✅ **All Tests Passing:**

```bash
# Test built-in mode (dummy model)
FACE_EMBED_PROVIDER=lvface LVFACE_MODEL_PATH=models/lvface.onnx pytest -k lvface

# Test subprocess mode (real model)
FACE_EMBED_PROVIDER=lvface LVFACE_EXTERNAL_DIR=../LVFace LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx FACE_EMBED_DIM=512 pytest backend/tests/test_lvface_subprocess.py -v

# Demo both modes
FACE_EMBED_PROVIDER=lvface LVFACE_EXTERNAL_DIR=../LVFace LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx FACE_EMBED_DIM=512 python test_lvface_integration.py
```

**Test Results:**
- ✅ Built-in mode: Uses dummy model, 256-dim embeddings
- ✅ Subprocess mode: Uses real LVFace model, 512-dim embeddings  
- ✅ Both modes generate normalized embeddings (norm ≈ 1.0)
- ✅ Integration with face embedding service works correctly

## Health Endpoint

The `/health` endpoint now shows LVFace configuration:
```json
{
  "face": {
    "embed_provider": "lvface",
    "embed_dim": 512,
    "lvface_model_path": "models/lvface.onnx",
    "lvface_external_dir": "/path/to/external/LVFace",
    "lvface_model_name": "real_model.onnx"
  }
}
```

## Next Steps

To use real LVFace models:

1. **Ensure External Setup**:
   - LVFace directory with `.venv` and dependencies
   - Real ONNX models in `models/` subdirectory
   - `inference.py` with `get_embedding(image_path, model_path)` function

2. **Set Environment Variables**:
   ```bash
   FACE_EMBED_PROVIDER=lvface
   LVFACE_EXTERNAL_DIR=C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace
   LVFACE_MODEL_NAME=your_model.onnx
   FACE_EMBED_DIM=512
   ```

3. **Test Integration**:
   ```bash
   python test_lvface_integration.py
   ```

The system will automatically choose subprocess mode when `LVFACE_EXTERNAL_DIR` is set, otherwise it uses built-in mode.
