# Contributing to VLM Photo Engine

This section contains guides for contributors and developers working on the VLM Photo Engine project.

## 🤝 How to Contribute

### Ways to Contribute
- **Code Contributions**: Features, bug fixes, performance improvements
- **Documentation**: Improve guides, add examples, fix typos
- **Testing**: Report bugs, test new features, write automated tests
- **Design**: UI/UX improvements, visual design, user experience
- **Community**: Help other users, answer questions, share knowledge

## 🛠️ Development Workflow

### Getting Started

**1. Fork and Clone**
```bash
# Fork the repository on GitHub
git clone https://github.com/yourusername/vlmPhotoHouse.git
cd vlmPhotoHouse
```

**2. Set Up Development Environment**
```bash
# Backend environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r backend/requirements-dev.txt

# External models environment (for AI development)
cd ../vlmCaptionModels
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**3. Run Tests**
```bash
# Unit tests
cd backend
python -m pytest

# Integration tests  
cd ../integration_tests
python test_caption_integration.py
python test_lvface_integration.py
```

**4. Start Development Server**
```bash
cd backend
python -m app.main
# Server runs at http://localhost:8001
```

### Development Guidelines

**Code Style**
- **Python**: Follow PEP 8, use `black` for formatting
- **TypeScript**: Use ESLint and Prettier (for future frontend)
- **Documentation**: Write clear docstrings and comments
- **Tests**: Write tests for new features and bug fixes

**Git Workflow**
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make commits with clear messages
git commit -m "Add caption generation for BLIP2 model"

# Push and create pull request
git push origin feature/your-feature-name
```

**Commit Message Format**
```
<type>(<scope>): <subject>

Types: feat, fix, docs, style, refactor, test, chore
Scope: api, ui, models, tests, docs
Subject: Brief description in present tense
```

Examples:
```
feat(api): add person search endpoint
fix(models): resolve BLIP2 memory leak  
docs(setup): update installation instructions
test(integration): add end-to-end search tests
```

## 🏗️ Architecture for Contributors

### Project Structure
```
vlmPhotoHouse/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py         # Application entry point
│   │   ├── config.py       # Configuration management
│   │   ├── db.py           # Database models and connection
│   │   ├── schemas.py      # Pydantic models
│   │   ├── routers/        # API endpoint routers
│   │   └── services/       # Business logic services
│   ├── requirements.txt    # Backend dependencies
│   └── tests/              # Backend tests
├── docs/                   # Documentation
├── integration_tests/      # End-to-end tests
├── development/           # Development utilities
└── tools/                 # Setup and utility scripts

vlmCaptionModels/          # External AI models environment
├── scripts/               # Model inference scripts
├── models/                # Downloaded AI models (20.96 GB)
└── test_images/           # Test images for validation
```

### Key Components

**Backend Services**
- **FastAPI App**: REST API server
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Task Queue**: Background job processing
- **Health Monitoring**: System status validation

**AI Model Integration**
- **Caption Providers**: BLIP2, Qwen2.5-VL
- **Face Providers**: LVFace, MTCNN, Facenet
- **Provider Pattern**: Pluggable AI model architecture
- **JSON IPC**: Subprocess communication protocol

**External Dependencies**
- **Vector Database**: FAISS (local) / Qdrant (optional)
- **Image Processing**: PIL, OpenCV
- **ML Frameworks**: PyTorch, Transformers, NumPy

## 🧪 Testing

### Test Types

**Unit Tests**
```bash
# Run all unit tests
cd backend
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_models.py

# Run with coverage
python -m pytest --cov=app tests/
```

**Integration Tests**
```bash
# End-to-end workflow tests
cd integration_tests
python test_caption_integration.py
python test_person_flow.py
python test_search_workflow.py
```

**Model Tests**
```bash
# AI model validation
cd vlmCaptionModels
python scripts/test_blip2.py test_images/sample.jpg
python scripts/test_lvface.py test_images/faces.jpg
```

**Performance Tests**
```bash
# Search performance benchmarks
python scripts/performance_benchmarks.py
```

### Test Data
- **Test Images**: Use `vlmCaptionModels/test_images/` for validation
- **Mock Data**: Create realistic test databases for development
- **Fixtures**: Use pytest fixtures for reusable test setup

### Continuous Integration
- Tests run automatically on pull requests
- Coverage reports generated and tracked
- Performance regressions detected

## 📝 Documentation

### Documentation Standards

**Code Documentation**
```python
def generate_caption(image_path: str, provider: str = "blip2") -> str:
    """Generate a descriptive caption for an image.
    
    Args:
        image_path: Path to the image file
        provider: AI model provider ("blip2" or "qwen2.5-vl")
        
    Returns:
        Generated caption text
        
    Raises:
        FileNotFoundError: If image file doesn't exist
        ModelLoadError: If AI model fails to load
    """
```

**API Documentation**
- All endpoints documented with OpenAPI/Swagger
- Include request/response examples
- Document error codes and handling
- Provide client integration examples

**Architecture Documentation**
- Update Mermaid diagrams for architectural changes
- Document design decisions and trade-offs
- Include performance considerations
- Explain integration patterns

### Documentation Workflow
```bash
# Update documentation
git checkout -b docs/update-api-guide
# Edit documentation files
git commit -m "docs(api): update search endpoint examples"
git push origin docs/update-api-guide
```

## 🚀 Feature Development

### Feature Request Process

**1. Discussion**
- Open GitHub issue with feature proposal
- Discuss requirements and design approach
- Get feedback from maintainers and community

**2. Design**
- Create design document for complex features
- Update architecture diagrams if needed
- Consider backwards compatibility

**3. Implementation**
- Create feature branch
- Implement with tests and documentation
- Follow coding standards and best practices

**4. Review**
- Submit pull request with clear description
- Address review feedback
- Ensure all tests pass

### Common Development Tasks

**Adding New AI Model Provider**
1. Create provider class implementing base interface
2. Add health check endpoint
3. Update configuration options
4. Write integration tests
5. Update documentation

**Adding New API Endpoint**
1. Define Pydantic schemas for request/response
2. Implement router function with proper error handling
3. Add authentication/authorization if needed
4. Write unit and integration tests
5. Update API documentation

**Database Schema Changes**
1. Create Alembic migration script
2. Update SQLAlchemy models
3. Update Pydantic schemas
4. Test migration on sample data
5. Document breaking changes

## 🐛 Bug Reports

### Reporting Bugs

**Bug Report Template**
```markdown
## Bug Description
Brief description of the issue

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- OS: Windows 11 / Ubuntu 22.04 / macOS 13
- Python version: 3.9.x
- GPU: NVIDIA RTX 3090
- Browser: Chrome 116.x (if web interface issue)

## Logs
```
Include relevant log output
```

## Additional Context
Any other relevant information
```

### Bug Fixing Workflow
1. **Reproduce**: Confirm the bug locally
2. **Investigate**: Find root cause
3. **Fix**: Implement minimal fix
4. **Test**: Add test case to prevent regression
5. **Document**: Update documentation if needed

## 🔍 Code Review

### Review Guidelines

**For Authors**
- Keep changes focused and small
- Write clear commit messages
- Include tests for new functionality
- Update documentation as needed
- Respond promptly to feedback

**For Reviewers**
- Be constructive and respectful
- Focus on code quality and maintainability
- Test functionality when possible
- Suggest improvements, not just problems
- Approve when ready, don't over-optimize

### Review Checklist
- [ ] Code follows project style guidelines
- [ ] Tests included and passing
- [ ] Documentation updated
- [ ] No breaking changes (or properly documented)
- [ ] Performance impact considered
- [ ] Security implications reviewed

## 📊 Performance

### Performance Guidelines

**Optimization Priorities**
1. **Search Performance**: <500ms response time
2. **Model Loading**: Minimize startup time
3. **Memory Usage**: Efficient model memory management
4. **Database Queries**: Optimize for large photo collections

**Profiling Tools**
```bash
# Python profiling
python -m cProfile -o profile.stats app/main.py

# Memory profiling
pip install memory-profiler
python -m memory_profiler script.py

# GPU monitoring
nvidia-smi -l 1
```

**Performance Testing**
```bash
# Load testing
pip install locust
locust -f performance_tests/search_load_test.py

# Database performance
python scripts/db_performance_test.py

# Model inference benchmarks
python scripts/model_benchmarks.py
```

## 🏷️ Release Process

### Versioning
- Follow Semantic Versioning (SemVer)
- `MAJOR.MINOR.PATCH` format
- Tag releases in git

### Release Checklist
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Version numbers updated
- [ ] Changelog updated
- [ ] Migration scripts tested
- [ ] Performance regression check
- [ ] Security review completed

## 💬 Community

### Communication Channels
- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and ideas
- **Pull Requests**: Code contributions and reviews

### Code of Conduct
- Be respectful and inclusive
- Focus on constructive feedback
- Help newcomers get started
- Follow project guidelines

### Getting Help
- Check existing documentation first
- Search GitHub issues for similar problems
- Ask specific questions with context
- Provide reproducible examples when possible

---

*Thank you for contributing to VLM Photo Engine! Every contribution helps make photo management better for everyone.*
