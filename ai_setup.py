#!/usr/bin/env python3
"""
AI Processing Setup and Quick Start

This script sets up the AI processing environment and provides quick-start commands.
"""

import json
import os
from pathlib import Path

def create_default_configs():
    """Create default configuration files for all AI components."""
    
    # AI Task Manager Config
    ai_task_config = {
        "backend_url": "http://localhost:8000",
        "state_file": "ai_task_state.json",
        "log_file": "ai_task_manager.log",
        "log_level": "INFO",
        "max_retries": 3,
        "batch_size": 50,
        "task_priorities": {
            "ingest": 10,
            "thumb": 20,
            "phash": 30,
            "embed": 40,
            "caption": 50,
            "face": 60,
            "video_probe": 70,
            "video_keyframes": 80,
            "video_embed": 90
        },
        "enabled_tasks": [
            "ingest", "thumb", "phash", "embed", "caption", "face"
        ],
        "processing_limits": {
            "max_concurrent_tasks": 5,
            "max_daily_tasks": 10000,
            "memory_threshold_mb": 8000
        }
    }
    
    with open('ai_task_config.json', 'w') as f:
        json.dump(ai_task_config, f, indent=2)
    
    print("✓ Created ai_task_config.json")

def create_quick_start_scripts():
    """Create quick-start scripts for common operations."""
    
    # Windows batch file
    batch_script = """@echo off
REM VLM Photo Engine AI Processing Quick Start
REM Make sure to start the backend server first!

echo VLM Photo Engine AI Processing
echo ================================

echo.
echo Starting backend server...
start "VLM Backend" cmd /k "cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo Waiting for backend to start...
timeout /t 10

echo.
echo Running AI processing pipeline...
python ai_orchestrator.py --max-dirs 5 --max-caption-tasks 20 --max-ai-tasks 50

echo.
echo Showing final status...
python ai_orchestrator.py --status

echo.
echo AI processing complete!
pause
"""
    
    with open('start_ai_processing.bat', 'w') as f:
        f.write(batch_script)
    
    print("✓ Created start_ai_processing.bat")
    
    # PowerShell script
    ps_script = """# VLM Photo Engine AI Processing Quick Start
Write-Host "VLM Photo Engine AI Processing" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

Write-Host "`nStarting backend server..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

Write-Host "Waiting for backend to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host "`nRunning AI processing pipeline..." -ForegroundColor Yellow
python ai_orchestrator.py --max-dirs 5 --max-caption-tasks 20 --max-ai-tasks 50

Write-Host "`nShowing final status..." -ForegroundColor Yellow
python ai_orchestrator.py --status

Write-Host "`nAI processing complete!" -ForegroundColor Green
Read-Host "Press Enter to exit"
"""
    
    with open('start_ai_processing.ps1', 'w') as f:
        f.write(ps_script)
    
    print("✓ Created start_ai_processing.ps1")

def create_readme():
    """Create comprehensive README for AI processing."""
    
    readme_content = """# VLM Photo Engine - AI Processing System

## Overview

This AI processing system provides comprehensive automated processing for your Drive E photos and videos:

- **Image Caption Generation** - AI-powered descriptions
- **Face Detection & Recognition** - Person identification
- **Vector Embeddings** - Semantic search capabilities  
- **Duplicate Detection** - Perceptual hash matching
- **Video Processing** - Keyframe extraction and analysis
- **Incremental Processing** - Only processes new content

## Components

### Core Scripts

1. **`ai_orchestrator.py`** - Master orchestrator that runs the complete pipeline
2. **`drive_e_backend_integrator.py`** - Handles ingestion of Drive E files into backend
3. **`caption_processor.py`** - Specialized caption generation processor
4. **`ai_task_manager.py`** - General AI task management system

### Quick Start Scripts

- **`start_ai_processing.bat`** - Windows batch file for easy startup
- **`start_ai_processing.ps1`** - PowerShell script for easy startup

## Setup

1. **Ensure Backend is Ready**:
   ```bash
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **Run Setup** (first time only):
   ```bash
   python ai_setup.py
   ```

## Usage

### Quick Start (Recommended)

**Windows:**
```cmd
start_ai_processing.bat
```

**PowerShell:**
```powershell
.\\start_ai_processing.ps1
```

### Manual Control

**Full Pipeline:**
```bash
python ai_orchestrator.py
```

**Individual Phases:**
```bash
# Ingestion only
python ai_orchestrator.py --ingestion-only --max-dirs 10

# Captions only  
python ai_orchestrator.py --captions-only --max-caption-tasks 50

# AI tasks only
python ai_orchestrator.py --ai-tasks-only --max-ai-tasks 100
```

**Continuous Processing:**
```bash
python ai_orchestrator.py --continuous --interval 1800
```

**Status Reports:**
```bash
python ai_orchestrator.py --status
```

### Component-Specific Usage

**Drive E Integration:**
```bash
python drive_e_backend_integrator.py --batch-size 5 --max-dirs 20
python drive_e_backend_integrator.py --status
```

**Caption Generation:**
```bash
python caption_processor.py --max-tasks 100
python caption_processor.py --continuous --interval 300
python caption_processor.py --status
```

**AI Task Management:**
```bash
python ai_task_manager.py --max-tasks 50
python ai_task_manager.py --task-type caption --max-tasks 20
python ai_task_manager.py --status
```

## State Files

The system maintains state in JSON files for incremental processing:

- **`ai_orchestrator_state.json`** - Overall orchestration state
- **`drive_e_ingestion_state.json`** - Directory ingestion tracking  
- **`caption_processing_state.json`** - Caption task states
- **`ai_task_state.json`** - General AI task states

## Configuration

Edit **`ai_task_config.json`** to customize:

- Task priorities and enabled tasks
- Processing limits and batch sizes
- Backend URL and timeouts
- Logging levels

## Monitoring

### Real-time Logs
- **`ai_orchestrator.log`** - Master orchestration log
- **`drive_e_integration.log`** - Ingestion process log
- **`caption_processor.log`** - Caption generation log
- **`ai_task_manager.log`** - General AI tasks log

### Status Commands
```bash
# Comprehensive status
python ai_orchestrator.py --status

# Component-specific status  
python drive_e_backend_integrator.py --status
python caption_processor.py --status
python ai_task_manager.py --status
```

### Backend Metrics
```bash
curl http://localhost:8000/metrics
```

## Processing Pipeline

1. **Ingestion Phase**
   - Scans Drive E directories
   - Adds new files to backend database
   - Creates thumbnail and metadata tasks

2. **Caption Generation Phase**
   - Discovers images needing captions
   - Generates AI-powered descriptions
   - Stores results with confidence scores

3. **AI Tasks Phase**
   - Face detection and recognition
   - Vector embedding generation
   - Perceptual hash calculation
   - Video processing (if enabled)

## Performance Tips

- Start with small batches (`--max-dirs 5`) to test the system
- Use `--continuous` mode for ongoing processing
- Monitor system resources during processing
- Adjust batch sizes based on available memory/GPU

## Troubleshooting

### Backend Not Available
```bash
# Check if backend is running
curl http://localhost:8000/health

# Restart backend
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Processing Stuck
```bash
# Check status
python ai_orchestrator.py --status

# Reset failed tasks (edit state files)
# Or restart from clean state
```

### Memory Issues
- Reduce batch sizes in configuration
- Process fewer tasks per run
- Monitor system memory usage

## Example Workflows

### Initial Setup (Process Everything)
```bash
# 1. Start backend
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Run full pipeline with conservative limits
python ai_orchestrator.py --max-dirs 20 --max-caption-tasks 100 --max-ai-tasks 200

# 3. Monitor progress
python ai_orchestrator.py --status
```

### Daily Processing (Incremental)
```bash
# Process new content only
python ai_orchestrator.py --max-dirs 5 --max-caption-tasks 50 --max-ai-tasks 100
```

### Continuous Processing
```bash
# Run every 30 minutes
python ai_orchestrator.py --continuous --interval 1800
```

## Integration with Drive E

The system automatically integrates with your Drive E processing:

1. Reads `simple_drive_e_state.json` for processed files
2. Maps files to directories for efficient ingestion
3. Tracks which directories have been processed
4. Only processes new or failed directories

Total Drive E files ready for AI processing: **8,926 files (204.48 GB)**

## Expected Processing Times

- **Ingestion**: ~1-2 minutes per 1000 files
- **Caption Generation**: ~2-5 seconds per image
- **Face Detection**: ~1-3 seconds per image  
- **Embeddings**: ~0.5-1 seconds per image
- **Video Processing**: ~10-30 seconds per video

For your 6,562 images + 2,357 videos, expect:
- **Total processing time**: 4-8 hours (depending on hardware)
- **GPU utilization**: High during caption/face processing
- **Storage**: Additional ~2-5GB for thumbnails, embeddings, etc.
"""
    
    with open('AI_PROCESSING_README.md', 'w') as f:
        f.write(readme_content)
    
    print("✓ Created AI_PROCESSING_README.md")

def main():
    """Main setup function."""
    print("VLM Photo Engine - AI Processing Setup")
    print("=" * 40)
    
    print("\nCreating configuration files...")
    create_default_configs()
    
    print("\nCreating quick-start scripts...")
    create_quick_start_scripts()
    
    print("\nCreating documentation...")
    create_readme()
    
    print("\n" + "=" * 40)
    print("Setup complete! 🎉")
    print("\nNext steps:")
    print("1. Start the backend server:")
    print("   cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
    print("\n2. Run AI processing:")
    print("   python ai_orchestrator.py --max-dirs 5")
    print("\n   OR use quick-start script:")
    print("   start_ai_processing.bat")
    print("\n3. Monitor progress:")
    print("   python ai_orchestrator.py --status")
    print("\nFor detailed instructions, see: AI_PROCESSING_README.md")

if __name__ == "__main__":
    main()
