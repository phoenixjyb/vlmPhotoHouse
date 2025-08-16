# Setup & Installation

This section contains setup guides for developers and operators.

## 🚀 Quick Start

### Prerequisites
- Python 3.9+ 
- Git
- NVIDIA GPU (recommended for AI models)
- 25+ GB free disk space for AI models

### Development Setup

1. **Clone Repository**
   ```bash
   git clone https://github.com/phoenixjyb/vlmPhotoHouse.git
   cd vlmPhotoHouse
   ```

2. **Setup Backend Environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/Mac
   pip install -r backend/requirements.txt
   ```

3. **Setup External Models Environment**
   ```bash
   cd ../vlmCaptionModels  # Create this directory alongside vlmPhotoHouse
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install transformers torch torchvision
   ```

4. **Start Development Server**
   ```bash
   cd vlmPhotoHouse
   .venv\Scripts\activate
   cd backend
   python -m app.main
   ```

   Server runs at: http://localhost:8001

## 📋 Setup Guides

### AI Models
- **[Caption Models Setup](./caption-models-external-setup.md)** - Configure BLIP2, Qwen2.5-VL models

### Environment Configuration
- **Backend Environment**: FastAPI server, database, task queue
- **External Models Environment**: AI model inference, 20.96 GB storage

## 🔧 Configuration

### Environment Variables

**Backend (.env in vlmPhotoHouse/)**
```bash
# Database
DATABASE_URL=sqlite:///./app.db

# Paths
PHOTOS_PATH=/path/to/your/photos
DERIVED_PATH=/path/to/derived/data

# External Models
EXTERNAL_CAPTION_ENV_PATH=../vlmCaptionModels/.venv
EXTERNAL_CAPTION_ENABLED=true

# AI Providers
CAPTION_PROVIDER=blip2  # or qwen2.5-vl
FACE_PROVIDER=lvface    # or mtcnn, facenet, insightface
```

**External Models (.env in vlmCaptionModels/)**
```bash
# Model Configuration
BLIP2_MODEL_SIZE=base    # base, large
QWEN_MODEL_SIZE=7b       # 7b, 14b
GPU_DEVICE=cuda:0        # or cpu

# Model Storage
MODELS_CACHE_DIR=./models
HF_HOME=./huggingface_cache
```

## 🗂️ Directory Structure

### Development Layout
```
workspace/
├── vlmPhotoHouse/           # Main backend application
│   ├── .venv/              # Backend Python environment
│   ├── backend/            # FastAPI application
│   ├── docs/               # Documentation
│   └── app.db              # SQLite database
│
├── vlmCaptionModels/       # External AI models
│   ├── .venv/              # ML models Python environment  
│   ├── models/             # Downloaded AI models (20.96 GB)
│   ├── scripts/            # Model inference scripts
│   └── test_images/        # Test images for validation
│
└── photos/                 # Your photo collection
    ├── 2023/
    ├── 2024/
    └── ...
```

### Production Layout
```
/opt/vlm-photo-engine/
├── vlmPhotoHouse/
├── vlmCaptionModels/
├── photos/ -> /mnt/photos  # NAS or network storage
└── derived/ -> /mnt/derived # Fast local storage
```

## 🧪 Verification

### Health Checks
```bash
# Backend health
curl http://localhost:8001/health

# Caption model health  
curl http://localhost:8001/health/caption

# Face recognition health
curl http://localhost:8001/health/lvface
```

### Test Model Loading
```bash
cd vlmCaptionModels
.venv\Scripts\activate
python scripts/test_blip2.py path/to/test/image.jpg
```

## 🔄 Model Management

### Download Models
Models are downloaded automatically on first use, but you can pre-download:

```bash
cd vlmCaptionModels
.venv\Scripts\activate
python scripts/download_models.py --model blip2 --size base
python scripts/download_models.py --model qwen2.5-vl --size 7b
```

### Model Storage
- **BLIP2 Base**: ~13.96 GB
- **Qwen2.5-VL 7B**: ~7.00 GB  
- **Total**: ~20.96 GB local storage

## 🐛 Troubleshooting

### Common Issues

**ModuleNotFoundError**
```bash
# Ensure correct environment is activated
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

**CUDA/GPU Issues**
```bash
# Check GPU availability
python -c "import torch; print(torch.cuda.is_available())"

# Use CPU if GPU unavailable
export GPU_DEVICE=cpu
```

**Model Download Failures**
```bash
# Clear cache and retry
rm -rf models/ huggingface_cache/
python scripts/download_models.py --model blip2
```

**Port Conflicts**
```bash
# Change port in backend/app/main.py
uvicorn app.main:app --host 0.0.0.0 --port 8002
```

### Debug Commands

```bash
# Check environments
which python
pip list

# Test model loading
python scripts/test_caption_models.py

# Check database
sqlite3 app.db ".tables"
```

## 📖 Next Steps

After setup completion:

1. **[Architecture Overview](../architecture/README.md)** - Understand the system design
2. **[API Documentation](../api/README.md)** - Integrate with the REST API
3. **[Deployment Guide](../deployment/README.md)** - Production deployment options

---

*For model-specific setup, see the caption models setup guide above.*
