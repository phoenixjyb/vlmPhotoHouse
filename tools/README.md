# Tools Directory

This directory contains utility scripts, monitoring tools, and administrative utilities for the VLM Photo Engine.

## File Categories:

### Monitoring & Performance
- `monitor_gpu_usage.py` - Real-time GPU utilization monitoring
- `monitor_video_processing.py` - Video processing progress monitoring
- `monitor_video_progress.py` - Video processing progress tracking
- `gpu_monitor_plot.py` - GPU usage visualization and plotting
- `quick_gpu_check.py` - Quick GPU status checking
- `quick_status.py` - Quick system status overview
- `system_overview.py` - Comprehensive system status overview

### Database Management
- `add_face_processing_status.py` - Add face processing columns to database
- `update_face_schema.py` - Database schema update utilities
- `import_assets.py` - Asset import and ingestion utilities
- `fix_view.py` - Database view fixes and repairs

### Visualization & Analysis
- `visualize_detection.py` - Face detection result visualization
- `visualize_face_detections.py` - Face detection bounding box visualization
- `visualize_face_results.py` - Comprehensive face processing visualization
- `progress_diary.py` - Processing progress tracking and reporting

### System Administration
- `gpu_precheck_validation.py` - GPU setup validation and checking
- `photo_ingestion_guide.py` - Photo ingestion workflow utilities
- `photo_organization_strategy.py` - Photo organization tools
- `reset_processing_dirs.py` - Processing directory cleanup
- `reset_video_dirs.py` - Video processing directory cleanup
- `simple_drive_e_integration_prep.py` - Drive E integration preparation

## Usage

### Monitoring
```bash
# Real-time GPU monitoring
python tools/monitor_gpu_usage.py

# System status overview
python tools/system_overview.py

# Quick status check
python tools/quick_status.py
```

### Database Management
```bash
# Add face processing status tracking
python tools/add_face_processing_status.py

# Update database schema
python tools/update_face_schema.py

# Import new assets
python tools/import_assets.py
```

### Visualization
```bash
# Visualize face detection results
python tools/visualize_face_detections.py

# Plot GPU usage over time
python tools/gpu_monitor_plot.py
```

### Administration
```bash
# Validate GPU setup
python tools/gpu_precheck_validation.py

# Reset processing directories
python tools/reset_processing_dirs.py

# Clean video processing directories
python tools/reset_video_dirs.py
```

## Integration with start-multi-proc.ps1

Many tools are integrated into the interactive command system and monitoring dashboard:

- GPU monitoring tools provide real-time performance metrics
- Database tools enable schema management and maintenance
- Visualization tools support quality assurance workflows
- Administrative tools enable system maintenance and cleanup

## Tool Categories by Function

### Performance & Monitoring
- Real-time system monitoring
- Performance visualization
- Progress tracking

### Data Management
- Database schema management
- Asset import/export
- Data integrity tools

### Quality Assurance
- Result visualization
- Status verification
- System validation

### System Maintenance
- Directory cleanup
- Environment validation
- Configuration management
