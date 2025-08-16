# VLM Photo Engine - Documentation Index

Welcome to the VLM Photo Engine documentation! This local-first AI photo engine provides semantic search, automated captioning, and person recognition for your photo collection.

## 🚀 Quick Start

### For Developers
1. **[Setup Guide](./setup/README.md)** - Get the development environment running
2. **[Architecture Overview](./architecture/README.md)** - Understand the system design
3. **[API Documentation](./api/README.md)** - Integrate with the REST API

### For Users
1. **[User Guide](./user/README.md)** - How to use the photo engine
2. **[Deployment Guide](./deployment/README.md)** - Production deployment options

### For Contributors
1. **[Contributing Guide](./contributing/README.md)** - Development workflow and standards
2. **[Project Status](./project/roadmap.md)** - Current progress and next steps

---

## 📁 Documentation Structure

### Core Documentation
| Document | Purpose | Audience |
|----------|---------|----------|
| **[Product Requirements](./project/prd-v02.md)** | What we're building and why | All |
| **[Architecture](./architecture/architecture-v2.md)** | System design and implementation | Developers |
| **[Roadmap](./project/roadmap.md)** | Project progress and next steps | All |

### Implementation Guides
| Document | Purpose | Audience |
|----------|---------|----------|
| **[Setup Guide](./setup/README.md)** | Development environment setup | Developers |
| **[Caption Models Setup](./setup/caption-models-external-setup.md)** | AI model configuration | Developers/Operators |
| **[Person Search API](./api/person-based-search-api.md)** | Person recognition API usage | Developers |

### Architecture Deep Dive
| Document | Purpose | Audience |
|----------|---------|----------|
| **[Visual Architecture](./architecture/architecture-diagrams.md)** | Mermaid diagrams of system design | All |
| **[AI Components](./architecture/ai-components.md)** | AI model integration patterns | Developers |
| **[Data Model](./architecture/data-model.md)** | Database schema and relationships | Developers |
| **[Storage Strategy](./architecture/storage-strategy.md)** | File organization and caching | Developers/Operators |

### Operations & Deployment
| Document | Purpose | Audience |
|----------|---------|----------|
| **[Deployment Guide](./deployment/README.md)** | Production deployment | Operators |
| **[Operations Runbook](./operations/README.md)** | Daily operations and troubleshooting | Operators |
| **[Security Guide](./security/README.md)** | Security considerations | Operators |

---

## 🎯 Current System Status (August 2025)

### ✅ Production Ready
- **Caption Generation**: BLIP2 model integrated and working
- **Person Recognition**: LVFace model with face detection
- **Dual Environment**: Backend + External AI models architecture
- **Health Monitoring**: Comprehensive system status validation
- **Local Storage**: 20.96 GB of AI models stored locally

### 🚧 In Development
- End-to-end photo ingestion pipeline
- Vector search integration
- Person album generation
- Event and theme detection

### 📋 Planned
- Advanced search ranking
- Video analysis
- Mobile client support
- Multi-user collaboration

---

## 🔗 Key System Characteristics

- **Local-First**: No cloud dependencies, runs entirely on your hardware
- **Privacy-Preserving**: All AI processing happens locally
- **Fast Search**: Sub-500ms search performance target
- **Modular**: Pluggable AI model providers
- **Scalable**: From single-user to family deployment

---

## 📖 Document Version History

| Version | Date | Major Changes |
|---------|------|---------------|
| v2.0 | Aug 2025 | Complete architecture overhaul with dual environment |
| v1.0 | Aug 2025 | Initial documentation structure |

---

## 🆘 Need Help?

- **Issues**: Check the troubleshooting sections in each guide
- **Questions**: Review the [open questions](./project/open-questions.md) document
- **Contributing**: See the [contributing guide](./contributing/README.md)

---

*Last updated: August 16, 2025*
