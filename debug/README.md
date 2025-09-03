# Debug Directory

This directory contains debugging, analysis, and experimental scripts for development and troubleshooting.

## File Categories:

### Face Processing Debug
- `debug_bbox_format.py` - Bounding box format debugging
- `debug_connectivity.py` - Service connectivity debugging  
- `debug_embeddings.py` - Face embedding debugging
- `debug_opencv_face.py` - OpenCV face detection debugging
- `debug_opencv_face_viz.py` - OpenCV face detection visualization

### System Analysis
- `analyze_integration.py` - Integration analysis and diagnostics
- `analyze_processing_status.py` - Processing status analysis
- `analyze_scrfd_coordinates.py` - SCRFD coordinate system analysis

### Experimental Processing
- `fresh_scrfd_test.py` - Fresh SCRFD testing implementation
- `fresh_start_processing.py` - Clean processing restart scripts
- `direct_windows_scrfd.py` - Direct Windows SCRFD implementation
- `wsl_direct_processing.py` - Direct WSL processing implementation

### Database Debugging
- `inspect_database.py` - Database inspection and debugging
- `face_readiness.py` - Face processing readiness checking

### Alternative Implementations
- `inference_local.py` - Local inference implementation

## Usage

### Debugging Face Processing
```bash
# Debug bounding box formats
python debug/debug_bbox_format.py

# Debug face embeddings
python debug/debug_embeddings.py

# Analyze coordinate systems
python debug/analyze_scrfd_coordinates.py
```

### System Analysis
```bash
# Analyze integration status
python debug/analyze_integration.py

# Check processing status
python debug/analyze_processing_status.py
```

### Experimental Scripts
```bash
# Test fresh SCRFD implementation
python debug/fresh_scrfd_test.py

# Direct Windows processing
python debug/direct_windows_scrfd.py
```

## Development Workflow

1. **Issue Identification**: Use analysis scripts to identify problems
2. **Debugging**: Use debug scripts to isolate specific issues
3. **Experimentation**: Test alternative implementations
4. **Validation**: Use verification scripts to confirm fixes

## Integration with Main System

These debug scripts helped develop and troubleshoot:
- Coordinate system issues (bbox format debugging)
- Service connectivity problems (connectivity debugging)
- Face embedding generation (embedding debugging)
- Database integration issues (database inspection)

Many successful debug patterns were integrated into the main processing pipeline.
