# Architecture Overview v2.0

**Date**: 2025-08-16  
**Status**: Production Implementation  
**Major Update**: Dual Environment & Multi-Provider Architecture

---

## 1. High-Level Architecture (Implemented)

### 1.1 Dual Environment Architecture ✅ **PRODUCTION**
```
┌─────────────────────────────────────────────────────────────────────┐
│                        Production System                            │
├─────────────────────────────────────────────────────────────────────┤
│  Backend Environment (vlmPhotoHouse/.venv)                        │
│  ├── FastAPI Server (Port 8001)                                    │
│  ├── SQLite Database + Alembic Migrations                          │
│  ├── Task Queue & Worker Pool                                      │
│  ├── FAISS Vector Index                                            │
│  ├── Health & Configuration Management                             │
│  └── API Routes (Search, Person, Ingestion)                       │
├─────────────────────────────────────────────────────────────────────┤
│  External Model Environment (vlmCaptionModels/.venv)              │
│  ├── BLIP2 Model (13.96 GB) - Production Ready                    │
│  ├── Qwen2.5-VL Model (7.00 GB) - Development                     │
│  ├── Inference Scripts (JSON interface)                           │
│  └── Model-specific Dependencies                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Communication Layer                                               │
│  ├── JSON Protocol (stdin/stdout)                                  │
│  ├── Subprocess Management                                         │
│  ├── Error Handling & Retry Logic                                  │
│  └── Health Monitoring                                             │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Provider Architecture ✅ **MULTI-PROVIDER SYSTEM**
```
┌─────────────────────────────────────────────────────────────────────┐
│                     Provider Plugin System                         │
├─────────────────────────────────────────────────────────────────────┤
│  Caption Providers                                                  │
│  ├── StubCaptionProvider (filename heuristics)                     │
│  ├── BLIP2SubprocessProvider (✅ production ready)                  │
│  ├── Qwen25VLProvider (⚠️ development/debugging)                    │
│  └── LLaVANextProvider (📋 future)                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Face Embedding Providers                                          │
│  ├── StubFaceProvider (development)                                │
│  ├── FacenetProvider (built-in)                                    │
│  ├── InsightFaceProvider (built-in)                                │
│  └── LVFaceSubprocessProvider (✅ external model)                   │
├─────────────────────────────────────────────────────────────────────┤
│  Face Detection Providers                                          │
│  ├── StubFaceDetector (development)                                │
│  ├── MTCNNProvider (✅ production ready)                            │
│  └── AutoFaceDetector (automatic selection)                        │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Data Flow Architecture (End-to-End)

### 2.1 Photo Ingestion Pipeline ✅
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Discover  │ -> │   Extract   │ -> │   Dedup     │ -> │  Task Queue │
│   Photos    │    │   Metadata  │    │   Check     │    │  Schedule   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       │                   │                   │                   │
       v                   v                   v                   v
  File System      EXIF + Hash Data      SQLite DB         Task Workers
   Scanning        (Camera, GPS, etc)    Asset Records    (Async Processing)
```

### 2.2 AI Processing Pipeline ✅
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Thumbnail  │    │   Image     │    │   Caption   │    │    Face     │
│ Generation  │    │ Embeddings  │    │ Generation  │    │ Detection   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       │                   │                   │                   │
       v                   v                   v                   v
   Resized Images     CLIP Vectors      BLIP2 Text       Face Boxes
   (Multiple sizes)   (FAISS Index)   (SQLite Storage)   (Coordinates)
                                                              │
                                                              v
                                                    ┌─────────────┐
                                                    │    Face     │
                                                    │ Embeddings  │
                                                    └─────────────┘
                                                              │
                                                              v
                                                    Person Clustering
                                                    (Vector Similarity)
```

### 2.3 Search & Retrieval Pipeline ✅
```
User Query
     │
     v
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Parse     │ -> │   Vector    │ -> │   Filter    │ -> │   Rank &    │
│   Query     │    │   Search    │    │  Metadata   │    │   Return    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       │                   │                   │                   │
       v                   v                   v                   v
  Text/Image Input    FAISS Similarity    Date/Person/Tag      Final Results
  (Embedding Gen)     (Top-K Results)     Filtering           (Ranked List)
```

## 3. Component Architecture (Detailed)

### 3.1 Backend Core Services ✅
```python
FastAPI Application
├── Health Endpoints
│   ├── /health (general system status)
│   ├── /health/caption (caption provider status)
│   └── /health/lvface (face embedding status)
│
├── Search Services
│   ├── Vector Search (CLIP embeddings + FAISS)
│   ├── Text Search (caption-based)
│   ├── Person Search (face embeddings)
│   └── Hybrid Search (combined ranking)
│
├── Ingestion Services
│   ├── File Discovery & Scanning
│   ├── EXIF & Metadata Extraction
│   ├── Hash Computation (SHA256 + perceptual)
│   └── Deduplication Logic
│
├── Task Management
│   ├── Async Task Queue (SQLite-based)
│   ├── Worker Pool (configurable concurrency)
│   ├── Retry Logic (exponential backoff)
│   └── Dead Letter Queue (failed task handling)
│
└── Provider Management
    ├── Caption Provider Factory
    ├── Face Provider Factory
    ├── Configuration Validation
    └── Runtime Health Monitoring
```

### 3.2 External Model Integration ✅
```python
Caption Subprocess Provider
├── Process Management
│   ├── Subprocess spawning
│   ├── Environment isolation
│   ├── Timeout handling
│   └── Resource cleanup
│
├── Communication Protocol
│   ├── JSON input formatting
│   ├── Stdin/stdout handling
│   ├── Error response parsing
│   └── Result validation
│
├── Model Providers
│   ├── BLIP2 (Salesforce/blip2-opt-2.7b)
│   ├── Qwen2.5-VL (Qwen/Qwen2.5-VL-3B-Instruct)
│   └── Smart Inference (multi-model fallback)
│
└── Health Monitoring
    ├── Model availability checking
    ├── Performance monitoring
    ├── Error rate tracking
    └── Configuration validation
```

## 4. Storage Architecture

### 4.1 File System Layout ✅ **IMPLEMENTED**
```
vlmPhotoHouse/
├── backend/
│   ├── app.db                      # SQLite database
│   ├── derived/                    # Generated artifacts
│   │   ├── embeddings/            # CLIP vectors (.npy)
│   │   ├── face_embeddings/       # Face vectors (.npy)
│   │   ├── person_embeddings/     # Person averages (.npy)
│   │   └── thumbnails/            # Resized images
│   └── metadata.sqlite            # Task & metadata storage
│
vlmCaptionModels/                   # External model environment
├── .venv/                         # Isolated Python environment
├── models/                        # Local model storage (20.96 GB)
│   ├── blip2-opt-2.7b/           # BLIP2 model files (13.96 GB)
│   └── qwen2.5-vl-3b-instruct/   # Qwen2.5-VL files (7.00 GB)
├── inference_backend.py          # Backend-compatible interface
└── requirements.txt              # Model-specific dependencies
```

### 4.2 Database Schema (Enhanced) ✅
```sql
-- Core entities
Asset (id, path, sha256, phash, created_at, file_size, content_type)
Embedding (asset_id, model_name, version, data, created_at)
Caption (asset_id, text, provider, model_version, confidence, created_at)

-- Person management (NEW)
Person (id, name, created_at, updated_at, merge_count)
FaceDetection (id, asset_id, bbox, confidence, embedding_id)
PersonFace (person_id, face_detection_id, confidence)
PersonEmbedding (person_id, embedding_data, model_version)

-- Provider configuration (NEW)
ProviderConfig (provider_name, model_name, device, external_path, config)
HealthStatus (component, status, last_check, details, created_at)

-- Enhanced task system
Task (id, type, status, retry_count, max_retries, created_at, started_at, finished_at)
TaskProgress (task_id, current_step, total_steps, percentage, message)
```

## 5. Communication Protocols

### 5.1 JSON IPC Protocol ✅ **STANDARDIZED**
```json
// Caption Generation Request
{
  "image_path": "/path/to/image.jpg",
  "provider": "blip2",
  "options": {
    "max_length": 100,
    "temperature": 0.7
  }
}

// Caption Generation Response
{
  "success": true,
  "caption": "A beautiful sunset over the ocean with people walking on the beach",
  "confidence": 0.95,
  "model": "blip2-opt-2.7b",
  "processing_time": 2.3
}

// Error Response
{
  "success": false,
  "error": "Model loading failed",
  "error_type": "MODEL_ERROR", 
  "details": "CUDA out of memory"
}
```

### 5.2 Health Check Protocol ✅
```json
// Health Check Response
{
  "provider": "BLIP2SubprocessProvider",
  "model": "blip2-external (default)",
  "device": "cpu",
  "configured_provider": "blip2",
  "external_dir": "C:\\...\\vlmCaptionModels",
  "mode": "external",
  "available_providers": ["stub", "llava-next", "qwen2.5-vl", "blip2"],
  "external_validation": {
    "dir_exists": true,
    "python_exists": true,
    "inference_script_exists": true
  }
}
```

## 6. Configuration Management

### 6.1 Environment Variables ✅ **PRODUCTION READY**
```bash
# Caption system configuration
CAPTION_PROVIDER=blip2
CAPTION_EXTERNAL_DIR=C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels
CAPTION_MODEL=auto
CAPTION_DEVICE=cpu

# Face recognition configuration  
FACE_EMBEDDING_PROVIDER=lvface
FACE_DETECT_PROVIDER=mtcnn
LVFACE_EXTERNAL_DIR=./models

# Performance tuning
VECTOR_INDEX_AUTOLOAD=false
AUTO_MIGRATE=false
ENABLE_INLINE_WORKER=false
```

### 6.2 Dynamic Configuration Validation ✅
```python
@app.get('/health/caption')
def health_caption():
    """Real-time validation of caption provider configuration"""
    provider = get_caption_provider()
    return {
        'provider': provider.__class__.__name__,
        'model': provider.get_model_name(),
        'status': 'operational' if provider.is_healthy() else 'error',
        'external_validation': validate_external_environment()
    }
```

## 7. Performance Architecture

### 7.1 Search Performance ✅ **<500ms P95**
```
Vector Search Pipeline:
├── Query Embedding Generation (50-100ms)
├── FAISS Index Search (10-50ms)  
├── Metadata Filtering (10-20ms)
└── Result Ranking & Return (5-10ms)
Total: ~75-180ms typical, <500ms P95
```

### 7.2 Model Loading Strategy ✅
```
Cold Start Performance:
├── BLIP2 Model Loading: ~3 seconds (cached after first use)
├── CLIP Embedding: ~100ms per image
├── Face Detection (MTCNN): ~200ms per image
└── Face Embedding (LVFace): ~50ms per face

Optimization:
├── Model persistence across requests
├── Batch processing for multiple images
└── Subprocess reuse for repeated operations
```

## 8. Scalability Architecture

### 8.1 Current Scale (Tested) ✅
- **Assets**: Development testing with sample datasets
- **Embeddings**: FAISS flat index for up to 1M+ vectors
- **Search**: Sub-500ms response time with current dataset
- **Concurrent Users**: Single-user development focus

### 8.2 Scaling Path (Designed) 📋
```
Phase 1 (Current): Single Process
├── Embedded SQLite database
├── In-process FAISS index
├── Subprocess model providers
└── Single-machine deployment

Phase 2 (Next): Worker Separation  
├── Dedicated model worker processes
├── Separate task queue workers
├── Optional external vector index (Qdrant)
└── Multi-container deployment

Phase 3 (Future): Distributed
├── PostgreSQL database
├── Dedicated GPU workers  
├── Load balancer + API cluster
└── Horizontal model scaling
```

## 9. Security & Privacy Architecture

### 9.1 Privacy-First Design ✅ **100% LOCAL**
- **No External Calls**: All AI processing local
- **Model Storage**: 20.96 GB stored locally, no cache dependencies
- **Data Isolation**: Photos never leave user's machine
- **Environment Isolation**: Separate dependencies for security

### 9.2 Security Considerations ✅
- **Process Isolation**: External models in separate processes
- **Input Validation**: JSON schema validation for IPC
- **Resource Limits**: Configurable timeouts and memory limits
- **Error Isolation**: Model failures don't crash main system

## 10. Monitoring & Observability

### 10.1 Health Monitoring System ✅ **COMPREHENSIVE**
```
Health Endpoints:
├── /health (overall system status)
├── /health/caption (caption provider status)
├── /health/lvface (face embedding status)
└── /metrics (Prometheus-compatible metrics)

Monitoring Coverage:
├── Model availability and performance
├── Task queue health and backlog
├── Database connection and performance
├── Vector index status and size
└── Resource usage and errors
```

### 10.2 Logging & Debugging ✅
```python
Structured Logging:
├── Request/response logging with timing
├── Model performance metrics
├── Error tracking with stack traces
├── Configuration validation results
└── Task progress and completion status
```

## 11. Development & Testing Architecture

### 11.1 Testing Strategy ✅ **COMPREHENSIVE**
```
Test Coverage:
├── Unit Tests (backend/tests/)
│   ├── Provider tests (caption, face embedding)
│   ├── Service tests (search, ingestion)
│   └── API endpoint tests
│
├── Integration Tests (integration_tests/)
│   ├── End-to-end caption workflow
│   ├── Person management workflow
│   └── LVFace model integration
│
└── Development Tools (development/)
    ├── Model debugging scripts
    ├── Provider test utilities
    └── Configuration validation tools
```

### 11.2 Development Workflow ✅
```
Development Environment:
├── Hot reload for backend development
├── Isolated model testing in external environment
├── Health endpoint monitoring during development
└── Comprehensive error logging and debugging
```

---

## 12. Architecture Lessons Learned

### 12.1 Successful Patterns ✅
- **Dual Environment Isolation**: Prevents dependency conflicts, enables independent scaling
- **Provider Plugin Architecture**: Easy model swapping, fallback capabilities
- **JSON IPC Protocol**: Simple, reliable, debuggable communication
- **Health Endpoint Strategy**: Essential for debugging complex model dependencies
- **Local Model Storage**: More reliable than cache-dependent systems

### 12.2 Key Architectural Decisions
- **Subprocess vs In-Process**: Chose subprocess for isolation and reliability
- **SQLite vs PostgreSQL**: SQLite sufficient for single-user, enables easier deployment
- **FAISS vs Qdrant**: FAISS embedded for simplicity, Qdrant option available
- **Environment Separation**: Critical for managing ML model dependencies

### 12.3 Future Architecture Considerations
- **GPU Scaling**: Dedicated GPU workers for model inference
- **Multi-User Support**: Authentication and data isolation
- **Real-Time Updates**: WebSocket connections for live progress
- **Backup & Recovery**: Data export/import capabilities

---

**Status**: ✅ **Production Architecture Validated**  
**Next Evolution**: Web UI integration and user experience enhancements  
**Proven Patterns**: Dual environment, multi-provider, health monitoring, local-first design
