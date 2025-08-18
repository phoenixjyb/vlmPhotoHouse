# Architecture Documentation

This section contains the technical architecture documentation for the VLM Photo Engine.

## 📋 Quick Reference

### Core Architecture
- **[Architecture Overview](./architecture-v2.md)** - Main system design document
- **[Visual Architecture](./architecture-diagrams.md)** - Mermaid diagrams showing system flows
- **[Data Model](./data-model.md)** - Database schema and relationships

### AI Components
- **[AI Components](./ai-components.md)** - AI model integration patterns
- **[Face Recognition](./face-recognition.md)** - Face detection and recognition system
- **[Captioning & Annotations](./captioning-and-annotations.md)** - Image captioning architecture

### Data Processing
- **[Ingestion Pipeline](./ingestion-pipeline.md)** - Photo ingestion and processing workflow
- **[Embedding & Indexing](./embedding-and-indexing.md)** - Vector embedding and search indexing
- **[Search & Ranking](./search-and-ranking.md)** - Search algorithms and ranking strategies
- **[Task Queue & Workers](./tasks-queue-and-workers.md)** - Async task processing system

### Infrastructure
- **[Storage Strategy](./storage-strategy.md)** - File organization and caching
- **[Hardware Architecture](./hardware-architecture.md)** - Hardware requirements and scaling

### Visual References
- **[Hardware Graph](./hardware-graph.mmd)** - Hardware component diagram
- **[Navigation Flow](./navigation.mmd)** - User interface navigation flow

---

## 🏗️ System Overview

The VLM Photo Engine uses a **dual environment architecture**:

### Backend Environment (`vlmPhotoHouse/.venv`)
- FastAPI server on port 8002
- Database operations (SQLite)
- Task queue management
- Health monitoring
- API endpoints

### Voice Integration (via external service)
- Thin proxy endpoints under `/voice/*` in the backend
- Proxies to LLMyTranslate (default: `http://127.0.0.1:8001`)
- Env-configurable base URL and paths; proxy bypasses system proxies

### External Models Environment (`vlmCaptionModels/.venv`)
- AI model inference (BLIP2, Qwen2.5-VL)
- Face recognition (LVFace, MTCNN)
- 20.96 GB of local model storage
- JSON IPC communication with backend

### Key Architectural Principles
1. **Local-First**: All processing happens on user hardware
2. **Privacy-Preserving**: No data leaves the local system
3. **Modular**: Pluggable AI model providers
4. **Scalable**: From development to production deployment
5. **Fast**: Sub-500ms search performance target

---

## 🔄 Data Flow Summary

```
Photos → Scan → Hash → Metadata → Queue Tasks
                                      ↓
                            [Thumbnails, Embeddings, Captions, Faces]
                                      ↓
                              Vector Index + Search API
```

---

## 🧩 Provider Architecture

The system uses a **pluggable provider pattern** for AI models:

- **Caption Providers**: BLIP2 (production), Qwen2.5-VL (development)
- **Face Providers**: LVFace, MTCNN, Facenet, InsightFace
- **Health Monitoring**: Each provider has dedicated health endpoints
- **JSON IPC**: Subprocess communication for external model integration

---

## 📊 Current Implementation Status

### ✅ Completed
- Dual environment setup
- BLIP2 caption generation
- LVFace integration
- Health monitoring framework
- Multi-provider architecture

### 🚧 In Progress
- End-to-end photo ingestion
- Vector search integration
- Person album generation

### 📋 Planned
- Event detection
- Theme-based albums
- Advanced search ranking

---

*For implementation details, see the individual architecture documents listed above.*

---

## 🚀 Developer Experience

- Windows Terminal multi-pane launcher starts API, LVFace, Caption, and Voice panes in one window
- Standard ports: API 8002; Voice 8001 (overridable)
- See Quick Start: [../quick-start-dev.md](../quick-start-dev.md)
