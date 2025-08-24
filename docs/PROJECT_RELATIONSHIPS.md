# Project Relationships and Architecture

## Overview
The VLM Photo House project is an AI-powered photo management system that integrates with the independent LLMyTranslate project to provide voice and speech capabilities.

## Project Structure

### VLM Photo House (Primary Project)
- **Repository**: `vlm-photo-engine/vlmPhotoHouse`
- **Purpose**: AI-powered photo management with computer vision and natural language processing
- **Core Features**:
  - Photo ingestion and indexing
  - Face recognition and clustering
  - Caption generation using vision-language models
  - Vector search and semantic photo retrieval
  - Person management and tagging

### LLMyTranslate (Independent Service Provider)
- **Repository**: `llmytranslate`
- **Purpose**: Independent AI translation and voice processing service
- **Relationship**: "Lends" ASR (Automatic Speech Recognition) and TTS (Text-to-Speech) services to VLM Photo House
- **Services Provided**:
  - Voice-to-text conversion (ASR)
  - Text-to-speech synthesis (TTS)
  - Language translation capabilities

## Integration Architecture

### Service Communication
- **VLM Photo House** runs on port `8000` (main FastAPI service)
- **LLMyTranslate ASR** runs on port `8001` (voice processing)
- **LLMyTranslate TTS** runs on port `8002` (speech synthesis)

### Integration Points
1. **Voice Photo Search**: Users can search photos using voice commands
2. **Audio Feedback**: TTS provides spoken responses for photo search results
3. **Accessibility**: Voice interface for hands-free photo management

### Environment Optimization
Both projects use RTX 3090 GPU optimization:
- **VLM Photo House**: CUDA 12.6 environment (Python 3.12.10, PyTorch 2.8.0+cu126)
- **LLMyTranslate**: CUDA 12.4 environment (Python 3.11.9, PyTorch 2.6.0+cu124)

## Development Workflow

### Multi-Service Development
The enhanced development script (`scripts/start-dev-multiproc.ps1`) orchestrates both projects:
1. Starts VLM Photo House main service
2. Launches LLMyTranslate ASR service
3. Activates LLMyTranslate TTS service
4. Configures 2x2 Windows Terminal layout for monitoring

### Independent Deployment
Each project can be deployed independently:
- **VLM Photo House**: Standalone photo management system
- **LLMyTranslate**: Reusable voice processing service for other applications

## Project Dependencies

### VLM Photo House Dependencies
- FastAPI, Pydantic, SQLAlchemy (web framework)
- OpenCV, Pillow (image processing)
- Transformers, torch (AI models)
- chromadb (vector database)
- Specific integration with LLMyTranslate API endpoints

### LLMyTranslate Dependencies
- FastAPI (service framework)
- torch, transformers (AI models)
- Various TTS/ASR libraries
- Mobile deployment capabilities (Android/QNN)

## Maintenance Strategy

### Independent Maintenance
- Each project maintains its own git repository
- Version control is independent
- Breaking changes in one project don't directly affect the other

### Integration Testing
- Cross-service testing ensures API compatibility
- Voice functionality testing validates end-to-end workflows
- Performance testing with RTX 3090 optimization

## Future Expansion
The architecture supports:
- Additional voice processing services
- Multi-language photo descriptions
- Voice-guided photo organization
- Integration with other AI services following the same pattern

---
*Last Updated: August 24, 2025*
*Version: 1.0*
