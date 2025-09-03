# Tests Directory

This directory contains all test files for the VLM Photo Engine project.

## File Categories:

### Face Processing Tests
- `test_face_recognition.py` - Face recognition system testing
- `test_embedding_fix.py` - Face embedding generation testing
- `test_multiple_faces_database.py` - Multi-face detection testing

### Service Integration Tests  
- `test_unified_service.py` - SCRFD+LVFace service testing
- `test_connection_bypass.py` - Network connectivity testing
- `test_proxy_bypass.py` - Proxy configuration testing
- `test_interactive_face_commands.py` - Interactive command testing

### Performance Tests
- `test_gpu_inference.py` - GPU acceleration testing
- `test_gpu_performance.py` - Performance benchmarking
- `test_rtx3090_performance.py` - RTX 3090 specific testing
- `test_live_inference.py` - Real-time inference testing

### Data Processing Tests
- `test_bbox_formats.py` - Bounding box format validation
- `test_bbox_permutations.py` - Coordinate system testing
- `test_sample_images.py` - Image processing validation
- `test_path_conversion.py` - WSL path conversion testing

### Computer Vision Tests
- `test_scrfd_direct.py` - SCRFD model testing
- `test_yolo_face.py` - YOLO face detection testing

## Usage

Run tests from the project root directory:

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_face_recognition.py

# Run with coverage
python -m pytest tests/ --cov=.
```

## Test Configuration

- Uses pytest framework
- Configuration in `pytest.ini` at project root
- Coverage reports available via pytest-cov
