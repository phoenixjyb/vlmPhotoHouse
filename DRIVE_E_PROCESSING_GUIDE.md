# Drive E Photo Processing Guide

## Current Status (August 27, 2025)

### Processing Progress
- **Total Files Discovered**: 7,891 photos and videos
- **Currently Processing**: In progress (started at file 1/7,891)
- **Previous Batch Completed**: 1,035 files successfully processed
- **Total Expected**: ~8,926 files when complete
- **State File**: `tools/simple_drive_e_state.json`

### Active Processing Session
- **Command**: `python tools\simple_drive_e_processor.py --drive-root "E:\"`
- **Started**: 2025-08-27 00:56:57
- **Terminal ID**: e9a61f16-35ab-42e8-bf47-e71be76adb12
- **Status**: Running in background, processing incrementally

## Project Overview

### Purpose
Comprehensive cataloguing system for Drive E photo and video collections with:
- Incremental processing (no duplicate work)
- Hash-based change detection
- Local state persistence
- Metadata extraction
- Support for all major photo/video formats

### Key Components

#### 1. Main Processor Script
- **Location**: `tools/simple_drive_e_processor.py`
- **Function**: Standalone photo/video cataloguing system
- **Dependencies**: Python 3.x, pathlib, hashlib, mimetypes, datetime, json

#### 2. State Management
- **File**: `tools/simple_drive_e_state.json`
- **Purpose**: Tracks all processed files with metadata
- **Structure**: 
  ```json
  {
    "files": {
      "file_path": {
        "hash": "sha256_hash",
        "size": file_size_bytes,
        "mime_type": "image/jpeg",
        "processed_at": "2025-08-27T00:56:57.123456"
      }
    },
    "last_updated": "timestamp",
    "total_files": count
  }
  ```

#### 3. Supported File Types
- **Images**: JPG, JPEG, PNG, GIF, BMP, TIFF, WEBP, HEIC
- **Videos**: MP4, AVI, MOV, MKV, WMV, FLV, WEBM, M4V

## Environment Setup

### Python Environment
- **Version**: Python 3.12.10.final.0
- **Type**: Virtual environment (already configured)
- **Location**: `C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe`
- **Junction Link**: `H:\wSpace` → `C:\Users\yanbo\wSpace` (both paths work)

```powershell
# Check current Python version
python --version

# Verify we're in the correct workspace
cd C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse

# Use project virtual environment (actual path)
C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe --version

# Or using junction link (equivalent)
H:\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe --version

# The processor uses only standard library modules, no additional dependencies needed
```

### Virtual Environment (Already Configured)
The project has a virtual environment with comprehensive ML/AI packages:
- FastAPI backend framework
- PyTorch and ML libraries
- Image processing tools (Pillow, ImageHash)
- Vector search capabilities (faiss-cpu)
- CLIP models and transformers

```powershell
# Activate if needed (actual path)
C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\Activate.ps1

# Or using junction link (equivalent)
H:\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\Activate.ps1

# Verify activation
where python
```

## Usage Commands

### Basic Processing
```powershell
# Process all files (unlimited) - Current session command
python tools\simple_drive_e_processor.py --drive-root "E:\"

# Or using virtual environment explicitly (actual path)
C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe tools\simple_drive_e_processor.py --drive-root "E:\"

# Or using junction link (equivalent)
H:\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe tools\simple_drive_e_processor.py --drive-root "E:\"

# Process with file limit
python tools\simple_drive_e_processor.py --drive-root "E:\" --max-files 1000

# Dry run (check what would be processed)
python tools\simple_drive_e_processor.py --drive-root "E:\" --dry-run

# Process specific number with dry run first
python tools\simple_drive_e_processor.py --drive-root "E:\" --max-files 50 --dry-run
```

### Monitoring Progress
```powershell
# Check processor output (replace with actual terminal ID)
# Use VS Code terminal output viewer or:
Get-Process python | Where-Object {$_.ProcessName -eq "python"}
```

### State File Management
```powershell
# View state file summary
Get-Content tools\simple_drive_e_state.json | ConvertFrom-Json | Select-Object total_files, last_updated

# Backup state file
Copy-Item tools\simple_drive_e_state.json tools\simple_drive_e_state_backup_$(Get-Date -Format "yyyyMMdd_HHmmss").json
```

## Backend Integration

### VLM Photo Engine Backend

#### Starting the Backend Server
```powershell
# Navigate to backend directory
cd backend

# Check Python environment
python --version
# Or explicitly: C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe --version

# Dependencies already installed in virtual environment

# Start simple server (actual path)
C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe simple_server.py

# Or using junction link (equivalent)
H:\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe simple_server.py

# Or start full backend server (actual path)
C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe -m app.main

# Or using junction link (equivalent)
H:\wSpace\vlm-photo-engine\vlmPhotoHouse\.venv\Scripts\python.exe -m app.main
```

#### Backend API Issues (Historical)
- **Problem**: Database lock errors when attempting direct API integration
- **Solution**: Created standalone processor that bypasses API
- **Status**: API integration postponed, local processing working perfectly

#### Future Integration Path
1. Complete Drive E cataloguing with standalone processor
2. Export state data to backend-compatible format
3. Bulk import processed metadata into VLM backend
4. Enable search and AI features on catalogued content

## Directory Structure

### Source Directory (Drive E)
```
E:\
├── 01_INCOMING\
│   ├── Jane\                    # Jane's photo collections (2022-2023)
│   ├── wechatExport\           # WeChat exported media
│   ├── yjcc_wedding_photos\    # Wedding photography
│   ├── 大兴动物园\              # Beijing Zoo photos
│   ├── 小溪\                   # Creek photos
│   ├── 长隆大马戏\              # Changlong Circus videos
│   └── print-batch2-to-do\     # Recent photos for printing
```

### Processing Files
```
C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\
├── tools\
│   ├── simple_drive_e_processor.py      # Main processor script
│   └── simple_drive_e_state.json        # Processing state
├── backend\                             # VLM backend (separate)
└── DRIVE_E_PROCESSING_GUIDE.md         # This guide
```

## Troubleshooting

### Common Issues

#### 1. Processing Stops/Hangs
```powershell
# Check if process is still running
Get-Process python

# If hung, restart processing (incremental, won't duplicate work)
python tools\simple_drive_e_processor.py --drive-root "E:\"
```

#### 2. Permission Errors
```powershell
# Run PowerShell as Administrator if needed
# Check Drive E access
Test-Path "E:\"
Get-ChildItem "E:\" -Force
```

#### 3. State File Corruption
```powershell
# Restore from backup
Copy-Item tools\simple_drive_e_state_backup_YYYYMMDD_HHMMSS.json tools\simple_drive_e_state.json

# Or start fresh (will reprocess all files)
Remove-Item tools\simple_drive_e_state.json
```

#### 4. Memory Issues (Large Files)
- Processor handles files individually to minimize memory usage
- Large video files are processed with minimal memory footprint
- If issues persist, process in smaller batches using `--max-files`

## Performance Characteristics

### Processing Speed
- **Images**: ~50-100 files per minute (depending on size)
- **Videos**: ~10-30 files per minute (depending on size and encoding)
- **Large videos (>500MB)**: 1-5 minutes each

### Resource Usage
- **CPU**: Moderate usage for hash calculation
- **Memory**: Low (processes one file at a time)
- **Disk I/O**: Sequential read access to source files
- **Storage**: Minimal (only JSON state file)

## Continuation and Recovery

### Resuming Processing
The system is designed for seamless continuation:
1. **Always incremental**: Never reprocesses existing files
2. **Hash verification**: Detects changed files automatically
3. **State persistence**: Survives reboots and interruptions
4. **No configuration needed**: Just run the same command

### Data Safety
- **Non-destructive**: Only reads source files, never modifies
- **Atomic operations**: State updates are atomic
- **Backup friendly**: State file can be backed up/restored easily

## Next Steps

### Immediate (Current Session)
1. ✅ Continue processing all 7,891 discovered files
2. ⏳ Monitor completion and final statistics
3. ⏳ Verify all collections are included

### Short Term
1. Document final processing statistics
2. Create backup of complete state file
3. Plan backend integration strategy

### Long Term
1. Integrate processed metadata with VLM backend
2. Enable AI-powered search and organization
3. Implement face recognition and person-based search
4. Create automated processing pipeline for new photos

## Contact and Support

- **Repository**: vlmPhotoHouse (phoenixjyb/vlmPhotoHouse)
- **Branch**: master
- **Processing Started**: August 27, 2025
- **Documentation Updated**: Real-time during processing

---
*This guide is updated as processing continues. Check terminal output for real-time progress.*
