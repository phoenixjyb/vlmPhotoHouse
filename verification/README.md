# Verification Directory

This directory contains verification and validation scripts for the VLM Photo Engine.

## File Categories:

### Database Verification
- `verify_database_status.py` - Complete database status verification and statistics
- `check_db_schema.py` - Database schema validation
- `check_metadata.py` - Metadata integrity checking

### Face Processing Verification
- `verify_face_detection.py` - Face detection results validation
- `verify_50_results.py` - Sample face processing verification
- `detailed_verification.py` - Visual face detection verification with bounding boxes
- `check_face_results.py` - Face processing results validation
- `check_face_status.py` - Face processing status checking
- `check_fixed_coordinates.py` - Coordinate system validation

### System Status Checking
- `check_gpu_services.py` - GPU service health checking
- `check_image_paths.py` - Image path validation
- `check_progress.py` - Processing progress monitoring
- `check_recent_processing.py` - Recent processing status

## Usage

### Database Status
```bash
# Complete database verification
python verification/verify_database_status.py

# Check database schema
python verification/check_db_schema.py
```

### Face Processing Verification  
```bash
# Visual verification with bounding boxes
python verification/detailed_verification.py --count 10

# Check face processing status
python verification/check_face_status.py

# Verify face detection results
python verification/verify_face_detection.py
```

### System Health Checks
```bash
# Check GPU services
python verification/check_gpu_services.py

# Check processing progress
python verification/check_progress.py
```

## Integration with start-multi-proc.ps1

These verification scripts are integrated into the interactive command system:

- `Check-Face-Status` → `verification/verify_database_status.py`
- `Verify-Face-Results` → `verification/detailed_verification.py`
- `Test-Services` → Various check scripts

## Output Formats

- Colored console output with status indicators (✅❌⚠️)
- Statistics and progress reporting
- Visual verification with image displays
- Comprehensive error reporting and diagnostics
