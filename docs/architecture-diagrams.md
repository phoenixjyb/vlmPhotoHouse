# VLM Photo Engine - Architecture Diagrams

**Visual Architecture Documentation with Mermaid Charts**  
**Date**: 2025-08-16  
**Status**: Production Implementation

---

## 1. System Overview Architecture

```mermaid
graph TB
    subgraph "Production Environment"
        subgraph "Backend Environment (vlmPhotoHouse/.venv)"
            API[FastAPI Server<br/>Port 8001]
            DB[(SQLite Database<br/>Metadata & Tasks)]
            QUEUE[Task Queue<br/>Async Processing]
            VECTOR[FAISS Vector Index<br/>Image & Face Embeddings]
            HEALTH[Health Monitoring<br/>System Status]
        end
        
        subgraph "External Model Environment (vlmCaptionModels/.venv)"
            BLIP2[BLIP2 Model<br/>13.96 GB]
            QWEN[Qwen2.5-VL Model<br/>7.00 GB] 
            INFERENCE[Inference Scripts<br/>JSON Interface]
        end
        
        subgraph "Communication Layer"
            JSON_PROTO[JSON Protocol<br/>stdin/stdout]
            SUBPROCESS[Subprocess Management<br/>Error Handling]
        end
    end
    
    subgraph "External Components"
        USER[User Requests]
        PHOTOS[Photo Collection<br/>Local Files]
        STORAGE[Derived Storage<br/>Embeddings, Thumbnails]
    end
    
    %% Main connections
    USER --> API
    API --> DB
    API --> VECTOR
    API --> QUEUE
    API --> HEALTH
    
    %% Model communication
    QUEUE --> JSON_PROTO
    JSON_PROTO --> SUBPROCESS
    SUBPROCESS --> BLIP2
    SUBPROCESS --> QWEN
    SUBPROCESS --> INFERENCE
    
    %% Data flow
    PHOTOS --> API
    API --> STORAGE
    STORAGE --> VECTOR
    
    %% Styling
    classDef production fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef model fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef communication fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef external fill:#fff3e0,stroke:#e65100,stroke-width:2px
    
    class API,DB,QUEUE,VECTOR,HEALTH production
    class BLIP2,QWEN,INFERENCE model
    class JSON_PROTO,SUBPROCESS communication
    class USER,PHOTOS,STORAGE external
```

## 2. End-to-End Data Flow

```mermaid
flowchart TD
    START([User Uploads Photos]) --> DISCOVER[📁 Photo Discovery<br/>File System Scanning]
    
    DISCOVER --> EXTRACT[🔍 Metadata Extraction<br/>EXIF, Hash, File Info]
    EXTRACT --> DEDUP{🔄 Deduplication Check<br/>SHA256 + Perceptual Hash}
    
    DEDUP -->|New Photo| TASK_QUEUE[📋 Task Queue<br/>Schedule Processing]
    DEDUP -->|Duplicate| SKIP[⏭️ Skip Processing<br/>Link to Existing]
    
    TASK_QUEUE --> PARALLEL{🔀 Parallel Processing}
    
    %% Parallel processing branches
    PARALLEL --> THUMB[🖼️ Thumbnail Generation<br/>Multiple Sizes]
    PARALLEL --> EMBED[🧠 Image Embeddings<br/>CLIP Model]
    PARALLEL --> CAPTION[💬 Caption Generation<br/>BLIP2 Model]
    PARALLEL --> FACES[👤 Face Detection<br/>MTCNN/LVFace]
    
    %% Processing results
    THUMB --> STORAGE1[💾 Store Thumbnails<br/>File System]
    EMBED --> VECTOR_INDEX[📊 Update Vector Index<br/>FAISS]
    CAPTION --> DB_CAPTION[💾 Store Captions<br/>SQLite Database]
    
    %% Face processing flow
    FACES --> FACE_EMBED[🧠 Face Embeddings<br/>LVFace Model]
    FACE_EMBED --> CLUSTER[🎯 Face Clustering<br/>Vector Similarity]
    CLUSTER --> PERSON_DB[👥 Person Management<br/>Database Storage]
    
    %% Final steps
    STORAGE1 --> COMPLETE[✅ Processing Complete]
    VECTOR_INDEX --> COMPLETE
    DB_CAPTION --> COMPLETE
    PERSON_DB --> COMPLETE
    SKIP --> COMPLETE
    
    %% Search availability
    COMPLETE --> SEARCHABLE[🔍 Photo Now Searchable<br/>Via Multiple Methods]
    
    %% Styling
    classDef start fill:#e8f5e8,stroke:#2e7d32,stroke-width:3px
    classDef process fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef model fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef storage fill:#fff8e1,stroke:#f57c00,stroke-width:2px
    classDef complete fill:#e8f5e8,stroke:#388e3c,stroke-width:3px
    
    class START,SEARCHABLE start
    class DISCOVER,EXTRACT,DEDUP,TASK_QUEUE,PARALLEL,THUMB,CLUSTER process
    class EMBED,CAPTION,FACES,FACE_EMBED model
    class STORAGE1,VECTOR_INDEX,DB_CAPTION,PERSON_DB storage
    class COMPLETE complete
```

## 3. Search Architecture Flow

```mermaid
flowchart TD
    USER_QUERY[👤 User Search Query] --> PARSE_TYPE{🔍 Parse Query Type}
    
    %% Query type routing
    PARSE_TYPE -->|Text Query| TEXT_SEARCH[📝 Text-Based Search]
    PARSE_TYPE -->|Image Query| IMAGE_SEARCH[🖼️ Image-Based Search]
    PARSE_TYPE -->|Person Query| PERSON_SEARCH[👤 Person-Based Search]
    PARSE_TYPE -->|Hybrid Query| HYBRID_SEARCH[🔀 Hybrid Search]
    
    %% Text search flow
    TEXT_SEARCH --> TEXT_EMBED[🧠 Generate Text Embedding<br/>CLIP Text Encoder]
    TEXT_EMBED --> VECTOR_SEARCH1[📊 Vector Similarity Search<br/>FAISS Index]
    
    %% Image search flow  
    IMAGE_SEARCH --> IMAGE_EMBED[🧠 Generate Image Embedding<br/>CLIP Image Encoder]
    IMAGE_EMBED --> VECTOR_SEARCH2[📊 Vector Similarity Search<br/>FAISS Index]
    
    %% Person search flow
    PERSON_SEARCH --> PERSON_LOOKUP[👥 Person Database Lookup<br/>By Name or ID]
    PERSON_LOOKUP --> FACE_QUERY[👤 Face Embedding Query<br/>Person Vector Search]
    FACE_QUERY --> ASSET_LOOKUP[🔗 Asset Association<br/>Face → Photo Mapping]
    
    %% Hybrid search flow
    HYBRID_SEARCH --> MULTI_EMBED[🧠 Multiple Embeddings<br/>Text + Image + Person]
    MULTI_EMBED --> WEIGHTED_SEARCH[⚖️ Weighted Vector Search<br/>Combined Similarity]
    
    %% Results processing
    VECTOR_SEARCH1 --> FILTER[🔧 Apply Filters<br/>Date, Location, Tags]
    VECTOR_SEARCH2 --> FILTER
    ASSET_LOOKUP --> FILTER
    WEIGHTED_SEARCH --> FILTER
    
    FILTER --> RANK[📈 Rank & Score Results<br/>Relevance + Metadata]
    RANK --> PAGINATE[📄 Paginate Results<br/>Page Size Control]
    PAGINATE --> RETURN[📤 Return Search Results<br/>JSON Response]
    
    %% Styling
    classDef user fill:#e8f5e8,stroke:#2e7d32,stroke-width:3px
    classDef process fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef model fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef database fill:#fff8e1,stroke:#f57c00,stroke-width:2px
    classDef result fill:#e8f5e8,stroke:#388e3c,stroke-width:3px
    
    class USER_QUERY,RETURN user
    class PARSE_TYPE,TEXT_SEARCH,IMAGE_SEARCH,PERSON_SEARCH,HYBRID_SEARCH,FILTER,RANK,PAGINATE process
    class TEXT_EMBED,IMAGE_EMBED,MULTI_EMBED,VECTOR_SEARCH1,VECTOR_SEARCH2,WEIGHTED_SEARCH model
    class PERSON_LOOKUP,FACE_QUERY,ASSET_LOOKUP database
    class RETURN result
```

## 4. Provider Architecture Diagram

```mermaid
graph TB
    subgraph "Provider Management System"
        FACTORY[Provider Factory<br/>Dynamic Loading]
        CONFIG[Configuration Manager<br/>Environment Variables]
        HEALTH_MGR[Health Manager<br/>Status Monitoring]
    end
    
    subgraph "Caption Providers"
        STUB_CAP[StubCaptionProvider<br/>Filename Heuristics]
        BLIP2_PROV[BLIP2SubprocessProvider<br/>✅ Production Ready]
        QWEN_PROV[Qwen25VLProvider<br/>⚠️ Development]
        LLAVA_PROV[LLaVANextProvider<br/>📋 Future]
    end
    
    subgraph "Face Embedding Providers"
        STUB_FACE[StubFaceProvider<br/>Development Only]
        FACENET[FacenetProvider<br/>Built-in Model]
        INSIGHT[InsightFaceProvider<br/>Built-in Model]
        LVFACE[LVFaceSubprocessProvider<br/>✅ External Model]
    end
    
    subgraph "Face Detection Providers"
        STUB_DETECT[StubFaceDetector<br/>Development Only]
        MTCNN[MTCNNProvider<br/>✅ Production Ready]
        AUTO_DETECT[AutoFaceDetector<br/>Automatic Selection]
    end
    
    subgraph "External Model Environment"
        EXT_ENV[vlmCaptionModels/.venv<br/>Isolated Environment]
        MODELS[Local Model Storage<br/>20.96 GB Total]
        SCRIPTS[Inference Scripts<br/>JSON Interface]
    end
    
    %% Provider registration
    FACTORY --> STUB_CAP
    FACTORY --> BLIP2_PROV
    FACTORY --> QWEN_PROV
    FACTORY --> LLAVA_PROV
    FACTORY --> STUB_FACE
    FACTORY --> FACENET
    FACTORY --> INSIGHT
    FACTORY --> LVFACE
    FACTORY --> STUB_DETECT
    FACTORY --> MTCNN
    FACTORY --> AUTO_DETECT
    
    %% Configuration flow
    CONFIG --> FACTORY
    HEALTH_MGR --> FACTORY
    
    %% External connections
    BLIP2_PROV -.-> EXT_ENV
    QWEN_PROV -.-> EXT_ENV
    LVFACE -.-> EXT_ENV
    EXT_ENV --> MODELS
    EXT_ENV --> SCRIPTS
    
    %% Status indicators
    classDef production fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px
    classDef development fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    classDef future fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef system fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef external fill:#fce4ec,stroke:#c2185b,stroke-width:2px
    
    class BLIP2_PROV,LVFACE,MTCNN production
    class STUB_CAP,STUB_FACE,STUB_DETECT,QWEN_PROV development
    class LLAVA_PROV future
    class FACTORY,CONFIG,HEALTH_MGR,FACENET,INSIGHT,AUTO_DETECT system
    class EXT_ENV,MODELS,SCRIPTS external
```

## 5. Task Processing Flow

```mermaid
sequenceDiagram
    participant U as User/API
    participant Q as Task Queue
    participant W as Worker Pool
    participant M as Model Provider
    participant D as Database
    participant S as Storage
    
    Note over U,S: Photo Processing Workflow
    
    U->>+Q: Submit Photo for Processing
    Q->>Q: Create Tasks (Thumbnail, Embedding, Caption, Faces)
    Q->>+W: Assign Task to Worker
    
    alt Thumbnail Generation
        W->>W: Resize Image
        W->>S: Store Thumbnail
        W->>D: Update Status
    else Image Embedding
        W->>+M: Request CLIP Embedding
        M-->>-W: Return Vector
        W->>S: Store Embedding (.npy)
        W->>D: Update Vector Index
    else Caption Generation
        W->>+M: Request Caption (JSON)
        M->>M: Load BLIP2 Model
        M->>M: Generate Caption
        M-->>-W: Return Caption Text
        W->>D: Store Caption
    else Face Detection & Embedding
        W->>+M: Detect Faces
        M-->>-W: Face Bounding Boxes
        W->>+M: Generate Face Embeddings
        M-->>-W: Face Vectors
        W->>W: Cluster Similar Faces
        W->>D: Update Person Database
    end
    
    W->>Q: Mark Task Complete
    Q->>U: Processing Complete
    
    Note over U,S: Error Handling
    alt Task Failure
        W->>Q: Report Failure
        Q->>Q: Increment Retry Count
        alt Retry Available
            Q->>W: Retry Task
        else Max Retries Exceeded
            Q->>Q: Move to Dead Letter Queue
            Q->>U: Notify Failure
        end
    end
```

## 6. Health Monitoring Architecture

```mermaid
graph LR
    subgraph "Health Check System"
        HEALTH_API[Health API Endpoints]
        MONITORS[Component Monitors]
        VALIDATORS[Configuration Validators]
        ALERTS[Alert System]
    end
    
    subgraph "Monitored Components"
        DB_HEALTH[Database Health<br/>Connection & Performance]
        VECTOR_HEALTH[Vector Index Health<br/>Size & Query Performance]
        MODEL_HEALTH[Model Health<br/>Availability & Performance]
        TASK_HEALTH[Task Queue Health<br/>Backlog & Processing Rate]
        STORAGE_HEALTH[Storage Health<br/>Disk Space & I/O]
    end
    
    subgraph "Health Endpoints"
        GENERAL[/health<br/>General System Status]
        CAPTION_HEALTH[/health/caption<br/>Caption Provider Status]
        FACE_HEALTH[/health/lvface<br/>Face Provider Status]
        METRICS[/metrics<br/>Prometheus Metrics]
    end
    
    %% Monitoring connections
    MONITORS --> DB_HEALTH
    MONITORS --> VECTOR_HEALTH
    MONITORS --> MODEL_HEALTH
    MONITORS --> TASK_HEALTH
    MONITORS --> STORAGE_HEALTH
    
    %% Validation connections
    VALIDATORS --> MODEL_HEALTH
    VALIDATORS --> CAPTION_HEALTH
    VALIDATORS --> FACE_HEALTH
    
    %% API connections
    HEALTH_API --> GENERAL
    HEALTH_API --> CAPTION_HEALTH
    HEALTH_API --> FACE_HEALTH
    HEALTH_API --> METRICS
    
    %% Alert connections
    MONITORS --> ALERTS
    VALIDATORS --> ALERTS
    
    classDef endpoint fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef component fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef system fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    
    class GENERAL,CAPTION_HEALTH,FACE_HEALTH,METRICS endpoint
    class DB_HEALTH,VECTOR_HEALTH,MODEL_HEALTH,TASK_HEALTH,STORAGE_HEALTH component
    class HEALTH_API,MONITORS,VALIDATORS,ALERTS system
```

## 7. Model Communication Protocol

```mermaid
sequenceDiagram
    participant B as Backend Process
    participant S as Subprocess Manager
    participant E as External Environment
    participant M as AI Model (BLIP2/LVFace)
    
    Note over B,M: Model Inference Request Flow
    
    B->>+S: Request Caption/Embedding
    S->>S: Validate Input
    S->>+E: Spawn External Process
    E->>E: Load Virtual Environment
    E->>+M: Initialize Model (if needed)
    M-->>-E: Model Ready
    
    Note over S,M: JSON Communication
    S->>E: Send JSON Request<br/>{"image_path": "...", "provider": "blip2"}
    E->>M: Process Image
    M->>M: Generate Result
    M-->>E: Return Result
    E->>S: JSON Response<br/>{"success": true, "caption": "...", "confidence": 0.95}
    
    Note over B,M: Error Handling
    alt Success Path
        S-->>B: Return Result
    else Model Error
        E->>S: JSON Error<br/>{"success": false, "error": "Model failed"}
        S-->>B: Propagate Error
    else Process Timeout
        S->>S: Kill Process
        S-->>B: Timeout Error
    else Process Crash
        S->>S: Detect Crash
        S-->>B: Process Error
    end
    
    S->>E: Cleanup Process
    E-->>-S: Process Terminated
    S-->>-B: Request Complete
```

## 8. Deployment Architecture

```mermaid
graph TB
    subgraph "Development Environment"
        DEV_API[FastAPI Dev Server<br/>Hot Reload]
        DEV_DB[(SQLite Database<br/>Local Development)]
        DEV_MODELS[Local Model Testing<br/>External Environment]
    end
    
    subgraph "Production Environment"
        PROD_API[FastAPI Production<br/>Uvicorn + Gunicorn]
        PROD_DB[(SQLite/PostgreSQL<br/>Production Database)]
        PROD_MODELS[Production Models<br/>20.96 GB Local Storage]
        PROD_STORAGE[Production Storage<br/>Derived Artifacts]
    end
    
    subgraph "Docker Deployment (Optional)"
        DOCKER_API[API Container<br/>FastAPI + Dependencies]
        DOCKER_WORKER[Worker Container<br/>Task Processing]
        DOCKER_MODELS[Model Volume<br/>Shared Model Storage]
        DOCKER_DB[Database Volume<br/>Persistent Storage]
    end
    
    subgraph "Scaling Architecture (Future)"
        LB[Load Balancer<br/>Multi-Instance API]
        API_CLUSTER[API Cluster<br/>Stateless Services]
        WORKER_POOL[Worker Pool<br/>GPU-Enabled Nodes]
        SHARED_DB[(Shared Database<br/>PostgreSQL Cluster)]
        SHARED_STORAGE[Shared Storage<br/>Network File System]
    end
    
    %% Development flow
    DEV_API --> DEV_DB
    DEV_API --> DEV_MODELS
    
    %% Production flow
    PROD_API --> PROD_DB
    PROD_API --> PROD_MODELS
    PROD_API --> PROD_STORAGE
    
    %% Docker flow
    DOCKER_API --> DOCKER_DB
    DOCKER_API --> DOCKER_MODELS
    DOCKER_WORKER --> DOCKER_MODELS
    DOCKER_WORKER --> DOCKER_DB
    
    %% Scaling flow
    LB --> API_CLUSTER
    API_CLUSTER --> SHARED_DB
    API_CLUSTER --> WORKER_POOL
    WORKER_POOL --> SHARED_STORAGE
    
    %% Environment progression
    DEV_API -.-> PROD_API
    PROD_API -.-> DOCKER_API
    DOCKER_API -.-> API_CLUSTER
    
    classDef dev fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef prod fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef docker fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef scale fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    
    class DEV_API,DEV_DB,DEV_MODELS dev
    class PROD_API,PROD_DB,PROD_MODELS,PROD_STORAGE prod
    class DOCKER_API,DOCKER_WORKER,DOCKER_MODELS,DOCKER_DB docker
    class LB,API_CLUSTER,WORKER_POOL,SHARED_DB,SHARED_STORAGE scale
```

---

## 9. Implementation Status Dashboard

```mermaid
gitgraph
    commit id: "Phase 0: Foundation"
    commit id: "FastAPI + Health Endpoints"
    branch ingestion
    checkout ingestion
    commit id: "Phase 1: Core Ingestion"
    commit id: "EXIF + Hashing + Dedup"
    checkout main
    merge ingestion
    branch embeddings
    checkout embeddings
    commit id: "Phase 2: Embeddings"
    commit id: "CLIP + FAISS Vector Search"
    checkout main
    merge embeddings
    branch captions
    checkout captions
    commit id: "Phase 3: Caption System"
    commit id: "BLIP2 Integration ✅"
    commit id: "External Model Architecture ✅"
    commit id: "JSON IPC Protocol ✅"
    checkout main
    merge captions
    branch faces
    checkout faces
    commit id: "Phase 4: Face Recognition"
    commit id: "LVFace Integration ✅"
    commit id: "Person Management ✅"
    commit id: "Multi-Provider System ✅"
    checkout main
    merge faces
    commit id: "🎉 Production Ready"
    commit id: "Documentation Update v2.0"
```

---

## 10. Performance Metrics Flow

```mermaid
graph LR
    subgraph "Request Flow"
        REQUEST[API Request] --> PROCESSING[Processing Time]
        PROCESSING --> RESPONSE[API Response]
    end
    
    subgraph "Model Performance"
        MODEL_LOAD[Model Loading<br/>~3 seconds cold start]
        INFERENCE[Inference Time<br/>BLIP2: ~2s, CLIP: ~100ms]
        VECTOR_SEARCH[Vector Search<br/>FAISS: ~10-50ms]
    end
    
    subgraph "Performance Targets"
        SEARCH_TARGET[Search: <500ms P95]
        CAPTION_TARGET[Caption: <5s P95]
        FACE_TARGET[Face Detection: <1s P95]
        THROUGHPUT_TARGET[Ingestion: ~1000 photos/min]
    end
    
    %% Performance connections
    REQUEST --> MODEL_LOAD
    MODEL_LOAD --> INFERENCE
    INFERENCE --> VECTOR_SEARCH
    VECTOR_SEARCH --> RESPONSE
    
    %% Target validation
    RESPONSE -.-> SEARCH_TARGET
    INFERENCE -.-> CAPTION_TARGET
    INFERENCE -.-> FACE_TARGET
    PROCESSING -.-> THROUGHPUT_TARGET
    
    classDef flow fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef perf fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef target fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    
    class REQUEST,PROCESSING,RESPONSE flow
    class MODEL_LOAD,INFERENCE,VECTOR_SEARCH perf
    class SEARCH_TARGET,CAPTION_TARGET,FACE_TARGET,THROUGHPUT_TARGET target
```

---

**Status**: ✅ **Comprehensive Visual Architecture Documentation**  
**Features**: System overview, data flows, provider architecture, health monitoring  
**Implementation**: Production-ready with 20.96 GB local models and dual environment  
**Next**: Web UI integration and end-to-end user testing
