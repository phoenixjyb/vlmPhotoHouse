# VLM Photo Engine - Interactive Command Reference

## 🎮 Interactive Shell Commands

The interactive shell provides easy access to common VLM Photo Engine operations while your services run in the background.

### 🔍 **Service Management**
```powershell
Test-Services                    # Check if Main API (8002) and Voice API (8001) are ready
```

### 📁 **Photo/Video Ingestion**
```powershell
Ingest-Photos                    # Scan default path (E:\photos)
Ingest-Photos "C:\MyPhotos"      # Scan custom path
```

### 🖼️ **Caption Generation**
```powershell
Generate-Captions               # Generate captions for asset ID 1
Generate-Captions "5"           # Generate captions for asset ID 5
```

**Available Caption Models:**
- **BLIP2-OPT-2.7B**: Fast, good quality, lower VRAM usage
- **Qwen2.5-VL-3B**: Slower, high quality, more detailed descriptions

### 🔍 **Smart Search**
```powershell
Search-Photos                   # Search for "sunset" (default)
Search-Photos "beach"           # Search for beach photos
Search-Photos "person smiling"  # Search for people smiling
```

### 🗣️ **Voice Services**
```powershell
Test-TTS                                    # Test with default text
Test-TTS "Hello from RTX 3090 TTS system"  # Test with custom text
```

### 🌐 **Direct API Access**
- **Main API**: http://127.0.0.1:8002
- **Voice API**: http://127.0.0.1:8001
- **Health Check**: http://127.0.0.1:8002/health
- **API Docs**: http://127.0.0.1:8002/docs

### 📊 **Example Workflow**
```powershell
# 1. Check services are ready
Test-Services

# 2. Ingest photos from your directory
Ingest-Photos "E:\MyPhotos"

# 3. Generate captions for the first photo
Generate-Captions "1"

# 4. Search for specific content
Search-Photos "sunset landscape"

# 5. Test voice synthesis
Test-TTS "Photo processing complete"
```

### 🚀 **RTX 3090 Benefits**
- **BLIP2 Captions**: ~3-5x faster than CPU
- **LVFace Processing**: 5-10x faster (55ms → 5-10ms)  
- **TTS Synthesis**: GPU-accelerated Coqui TTS
- **Concurrent Processing**: All models can run simultaneously in 24GB VRAM

### 🎯 **Usage Tips**
1. **Wait for Services**: Interactive shell waits 10 seconds for services to start
2. **Batch Processing**: Use the Main API's task system for large datasets
3. **Monitor RTX 3090**: Watch the GPU Monitor pane during operations
4. **Caption Quality**: Use BLIP2 for speed, Qwen2.5-VL for detailed descriptions
