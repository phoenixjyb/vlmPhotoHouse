# Production Deployment Guide

## Quick Setup

### 1. Environment Configuration

Copy and customize the environment file:
```bash
cd deploy/
cp env.sample .env
```

Edit `.env` with your paths:
```bash
# Basic paths
PHOTOS_PATH=/path/to/your/photos
DERIVED_PATH=/path/to/derived/data

# LVFace Configuration (optional)
FACE_EMBED_PROVIDER=lvface
LVFACE_PATH=/path/to/your/LVFace
LVFACE_EXTERNAL_DIR=/lvface
LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx
FACE_EMBED_DIM=512

# Build with ML dependencies
INCLUDE_ML=true
```

### 2. Start Services

```bash
# Basic setup (stub providers)
docker-compose up -d

# With LVFace (requires LVFACE_PATH in .env)
docker-compose up -d
```

### 3. Health Check

```bash
# Basic health
curl http://localhost:8000/health

# LVFace specific
curl http://localhost:8000/health/lvface
```

## LVFace Setup Options

### Option 1: Built-in Mode (Development)
- Uses dummy models within container
- Good for testing and CI
- No external dependencies

```bash
FACE_EMBED_PROVIDER=lvface
# LVFACE_EXTERNAL_DIR= (leave empty)
```

### Option 2: External Mode (Production)
- Uses real LVFace models from host
- Requires mounting LVFace directory
- Best embedding quality

```bash
FACE_EMBED_PROVIDER=lvface
LVFACE_PATH=/host/path/to/LVFace
LVFACE_EXTERNAL_DIR=/lvface
LVFACE_MODEL_NAME=LVFace-B_Glint360K.onnx
FACE_EMBED_DIM=512
```

## Validation

The system validates LVFace configuration at startup:

✅ **Successful startup logs:**
```
INFO:app.lvface_validation:Validating LVFace configuration...
INFO:app.lvface_validation:✓ External LVFace setup validated: /lvface
INFO:app.lvface_validation:✓ Model: /lvface/models/LVFace-B_Glint360K.onnx
INFO:app.lvface_validation:✓ Target dimension: 512
```

⚠️ **Fallback warnings:**
```
WARNING:app.lvface_validation:LVFace: Built-in LVFace model not found: models/lvface.onnx
ERROR:app.lvface_validation:LVFace configuration error: External dir not found
ERROR:app.lvface_validation:System will fallback to stub face embedding provider.
```

## Troubleshooting

### LVFace Not Working?

1. **Check configuration:**
   ```bash
   curl http://localhost:8000/health/lvface
   ```

2. **Check logs:**
   ```bash
   docker-compose logs api | grep -i lvface
   ```

3. **Verify mount:**
   ```bash
   docker-compose exec api ls -la /lvface/
   ```

4. **Test manually:**
   ```bash
   docker-compose exec api python -c "
   from app.lvface_validation import validate_lvface_config
   print(validate_lvface_config())
   "
   ```

### Common Issues

- **Mount path wrong:** Check `LVFACE_PATH` in `.env` matches your host path
- **Model not found:** Verify `LVFACE_MODEL_NAME` matches actual file
- **Python env missing:** Ensure LVFace directory has `.venv/Scripts/python.exe`
- **No inference.py:** LVFace directory must have inference script

### Performance Tuning

For production workloads:
```bash
# Increase worker concurrency
WORKER_CONCURRENCY=4

# Enable inline worker
ENABLE_INLINE_WORKER=true

# Use GPU if available
API_GPU=0
```
