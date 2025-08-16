# Legacy Documentation

This folder contains outdated documentation that has been superseded by newer versions. These files are kept for historical reference and to track the evolution of the project.

## 📚 Legacy Files

### Superseded Documentation
- **[prd.md](./prd.md)** → Replaced by [prd-v02.md](../project/prd-v02.md)
- **[architecture.md](./architecture.md)** → Replaced by [architecture-v2.md](../architecture/architecture-v2.md)
- **[ops-and-maintenance.md](./ops-and-maintenance.md)** → Replaced by [operations.md](../operations/operations.md)
- **[security-privacy.md](./security-privacy.md)** → Replaced by [security.md](../security/security.md)

### Historical Documents
- **[assumptions.md](./assumptions.md)** - Early project assumptions (many now obsolete)
- **[nonfunctional.md](./nonfunctional.md)** - Non-functional requirements (incorporated into PRD v2)

## ⚠️ Important Note

**These files are outdated and should not be used for current development or deployment.**

For current documentation, please see:
- **[Project Documentation](../project/README.md)** - Current requirements and roadmap
- **[Architecture Documentation](../architecture/README.md)** - Current system design
- **[Operations Documentation](../operations/README.md)** - Current operational procedures
- **[Security Documentation](../security/README.md)** - Current security guidelines

## 📈 Evolution Summary

### Major Changes Since Legacy Versions

**Architecture Evolution**
- **v1**: Single environment, monolithic design
- **v2**: Dual environment architecture (backend + external AI models)
- **Current**: Pluggable provider pattern with health monitoring

**Requirements Evolution**
- **v1**: Basic photo indexing and search
- **v2**: Production-ready AI integration with local model storage
- **Current**: Privacy-first, local-only processing with comprehensive feature set

**Operations Evolution**
- **v1**: Development-only setup
- **v2**: Docker-based deployment with monitoring
- **Current**: Production-ready operations with comprehensive tooling

### Key Lessons Learned
1. **Dual Environment Architecture**: Critical for maintainability and performance
2. **Local Model Storage**: Essential for privacy and offline operation
3. **Provider Pattern**: Enables easy AI model upgrades and experimentation
4. **Health Monitoring**: Crucial for production reliability

---

*For current and accurate information, always refer to the main documentation sections outside this legacy folder.*
