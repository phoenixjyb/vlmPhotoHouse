# External Caption Models Setup Guide

This guide explains how to set up a separate virtual environment for state-of-the-art caption models (Qwen2.5-VL, LLaVA-NeXT, BLIP2) following the same pattern as LVFace integration.

## Why External Setup?

Similar to LVFace face recognition, we recommend using an external directory for caption models because:

1. **Dependency Isolation**: Keep heavy ML dependencies separate from the main application
2. **Flexibility**: Easy to switch between different model environments  
3. **Performance**: Only load model dependencies when needed
4. **GPU Support**: Dedicated environment for CUDA/GPU acceleration
5. **Model Storage**: Centralized location for large model files

## Quick Setup

### Option 1: Automated Setup (Recommended)

Use the provided setup script:

```bash
cd vlmPhotoHouse
python tools/setup_caption_models.py --dir ../vlmCaptionModels --provider qwen2.5-vl
```

This creates the complete directory structure with virtual environment and dependencies.

### Option 2: Manual Setup

1. **Create directory structure:**
```bash
mkdir ../vlmCaptionModels
cd ../vlmCaptionModels
```

2. **Create virtual environment:**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install torch transformers qwen-vl-utils pillow numpy accelerate
```

4. **Copy inference script:**
```bash
cp ../vlmPhotoHouse/caption_inference_template.py ./inference.py
```

## Configuration

Set environment variables to use external caption models:

```bash
# Environment variables
export CAPTION_EXTERNAL_DIR=/path/to/vlmCaptionModels
export CAPTION_PROVIDER=qwen2.5-vl
export CAPTION_MODEL=auto  # or specific model name
```

Or in your `.env` file:
```env
CAPTION_EXTERNAL_DIR=C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels
CAPTION_PROVIDER=qwen2.5-vl
CAPTION_MODEL=auto
```

## Supported Models

### Qwen2.5-VL (Recommended - August 2024 SOTA)
- **Provider**: `qwen2.5-vl`
- **Default Model**: `Qwen/Qwen2.5-VL-7B-Instruct`
- **Description**: Latest state-of-the-art vision-language model
- **Requirements**: `transformers>=4.37.0`, `qwen-vl-utils`

### LLaVA-NeXT (LLaVA-1.6)
- **Provider**: `llava-next`  
- **Default Model**: `llava-hf/llava-v1.6-mistral-7b-hf`
- **Description**: Popular multimodal model with good performance
- **Requirements**: `transformers>=4.37.0`

### BLIP2 (Baseline)
- **Provider**: `blip2`
- **Default Model**: `Salesforce/blip2-opt-2.7b`
- **Description**: Reliable baseline option, smaller size
- **Requirements**: `transformers>=4.37.0`

## Directory Structure

After setup, your directory should look like:

```
vlmCaptionModels/
├── .venv/                           # Virtual environment
│   ├── Scripts/python.exe           # Windows
│   └── bin/python                   # Unix/Linux
├── inference.py                     # Caption generation script
├── requirements.txt                 # Model dependencies  
├── README.md                        # Setup documentation
├── models/                          # Optional: model cache
├── .cache/                          # Optional: transformers cache
└── logs/                            # Optional: inference logs
```

## Testing

Test your external setup:

```bash
cd ../vlmCaptionModels
.venv/bin/python inference.py --provider qwen2.5-vl --model auto --image /path/to/test/image.jpg
```

Expected output:
```json
{
  "caption": "A detailed description of the image showing...",
  "model": "Qwen/Qwen2.5-VL-7B-Instruct", 
  "provider": "qwen2.5-vl"
}
```

## Health Monitoring

Check caption service status:

```bash
curl http://localhost:8000/health/caption
```

Example response:
```json
{
  "provider": "Qwen2VLSubprocessProvider",
  "model": "qwen2.5-vl-external (Qwen/Qwen2.5-VL-7B-Instruct)",
  "mode": "external",
  "external_validation": {
    "dir_exists": true,
    "python_exists": true,
    "inference_script_exists": true
  }
}
```

## GPU Support

For GPU acceleration, install PyTorch with CUDA support in the external environment:

```bash
cd ../vlmCaptionModels
source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

Then set:
```bash
export CAPTION_DEVICE=cuda
```

## Model Storage and Caching

Models are automatically downloaded on first use. Storage locations:

1. **Local cache**: `vlmCaptionModels/.cache/` (recommended)
2. **Models directory**: `vlmCaptionModels/models/` (optional)  
3. **System cache**: `~/.cache/huggingface/` (default)

Large models (7B+) require:
- **Disk Space**: 15-30GB per model
- **Memory**: 16GB+ RAM, 8GB+ VRAM for GPU

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure dependencies are installed in external venv
2. **CUDA errors**: Check PyTorch CUDA compatibility  
3. **Memory errors**: Use smaller models or increase system memory
4. **Permission errors**: Check directory write permissions

### Debug Commands

```bash
# Check external environment
cd ../vlmCaptionModels
.venv/bin/python -c "import transformers; print(transformers.__version__)"

# Test model loading
.venv/bin/python -c "
from transformers import AutoProcessor
processor = AutoProcessor.from_pretrained('Qwen/Qwen2.5-VL-7B-Instruct')
print('Model loading successful')
"

# Check GPU availability
.venv/bin/python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

### Fallback Behavior

If external models fail:
1. System logs the error
2. Falls back to built-in providers
3. Ultimate fallback to stub provider (filename-based)

## Performance Considerations

### Model Loading Time
- **First run**: 30-60 seconds (model download + loading)
- **Subsequent runs**: 10-30 seconds (loading only)
- **Optimization**: Models stay loaded in subprocess

### Memory Usage
- **Qwen2.5-VL 7B**: ~15GB RAM, ~8GB VRAM
- **LLaVA-NeXT 7B**: ~14GB RAM, ~7GB VRAM  
- **BLIP2 2.7B**: ~6GB RAM, ~3GB VRAM

### Inference Speed
- **GPU**: 2-5 seconds per image
- **CPU**: 15-60 seconds per image (depending on model size)

## Security Notes

- External directories run with same permissions as main application
- Model downloads come from HuggingFace Hub (verify model sources)
- Consider firewall rules for model downloads
- Subprocess isolation provides some security boundaries

## Migration from Built-in Models

To migrate from built-in to external models:

1. Set up external directory (see above)
2. Update environment variables
3. Restart application
4. Verify with `/health/caption` endpoint
5. Remove built-in model dependencies if desired

Built-in models remain available as fallback even with external setup configured.
