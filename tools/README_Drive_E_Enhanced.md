# Enhanced Drive E Photo and Video Processor

🚀 **Comprehensive incremental processing system** for photos and videos on Drive E with automatic bookkeeping, checkpoint system, and file watching capabilities.

## ✨ Key Features

### 🔄 **Incremental Processing**
- ✅ **Smart file tracking** - Only processes new/changed files
- ✅ **Processing history database** - SQLite database tracks all file states
- ✅ **Automatic checkpoints** - Resume processing from where you left off
- ✅ **Duplicate detection** - Prevents reprocessing of unchanged files
- ✅ **Error recovery** - Retry failed files with configurable limits

### 📁 **Intelligent File Discovery**
- ✅ **Prioritizes 01_INCOMING folder** - New files processed first
- ✅ **File change detection** - Hash comparison and modification time tracking
- ✅ **Comprehensive file support** - Images, videos, and future audio support
- ✅ **Exclusion patterns** - Skip temporary and system files

### 👁️ **Automatic File Watching**
- ✅ **Real-time monitoring** - Detects new files as they're added
- ✅ **Batch processing** - Groups files for efficient processing
- ✅ **File settling** - Waits for file copying to complete
- ✅ **Background service** - Runs continuously as a daemon

### 📊 **Advanced Reporting & Analytics**
- ✅ **Session tracking** - Detailed logs of each processing run
- ✅ **Processing statistics** - Success rates, timing, and error analysis
- ✅ **Progress monitoring** - Real-time status updates
- ✅ **Comprehensive reports** - JSON output with full processing details

## 🚀 Quick Start

### 1. Ensure Services Are Running
```powershell
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
```

### 2. Test the System
```powershell
# Quick test with 10 files
.\tools\process_drive_e_v2.ps1 -QuickTest

# Dry run to see what would be processed
.\tools\process_drive_e_v2.ps1 -DryRun
```

### 3. Start Processing
```powershell
# Process new files (recommended for daily use)
.\tools\process_drive_e_v2.ps1

# Resume from where you left off
.\tools\process_drive_e_v2.ps1 -Resume

# Force reprocess all files
.\tools\process_drive_e_v2.ps1 -ForceReprocess
```

### 4. Enable Automatic Processing
```powershell
# Start file watcher for automatic processing
.\tools\process_drive_e_v2.ps1 -StartWatcher
```

## 📋 Command Reference

### PowerShell Script (`process_drive_e_v2.ps1`)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `-DriveRoot` | Drive E root path | `E:\` |
| `-MaxFiles` | Maximum files to process | unlimited |
| `-FileTypes` | `images`, `videos`, or `all` | `all` |
| `-Workers` | Number of worker threads | `4` |
| `-BatchSize` | Files per batch | `100` |
| `-ReportPath` | Output report file | `drive_e_processing_report.json` |
| `-DryRun` | Discover files only, don't process | `false` |
| `-QuickTest` | Test with 10 files | `false` |
| `-FocusIncoming` | Prioritize 01_INCOMING folder | auto-enabled |
| `-ForceReprocess` | Ignore checkpoints, reprocess all | `false` |
| `-Resume` | Resume processing pending files | `false` |
| `-ShowStats` | Display statistics and exit | `false` |
| `-StartWatcher` | Start automatic file watcher | `false` |

### Python Script (`drive_e_processor_v2.py`)

```bash
# Show detailed help
python tools/drive_e_processor_v2.py --help

# Common commands
python tools/drive_e_processor_v2.py --dry-run --max-files 100
python tools/drive_e_processor_v2.py --resume
python tools/drive_e_processor_v2.py --show-stats
python tools/drive_e_processor_v2.py --force-reprocess --file-types images
```

## 🗄️ Database Schema

The system maintains a SQLite database (`drive_e_processing.db`) with:

### Processing History Table
- **File tracking**: Path, hash, size, modification time
- **Processing status**: pending, processing, completed, failed, skipped
- **Error handling**: Error count, retry logic
- **Asset linking**: Connection to main vlmPhotoHouse database

### Processing Sessions Table
- **Session management**: UUID-based session tracking
- **Statistics**: Files processed, success rates, timing
- **Configuration**: Processing parameters for each run

## 📊 Processing States

| State | Description | Next Action |
|-------|-------------|-------------|
| `pending` | File discovered, waiting to process | Will be processed |
| `processing` | Currently being processed | Wait for completion |
| `completed` | Successfully processed | Skip (unless forced) |
| `failed` | Processing failed | Retry (if error count < 3) |
| `skipped` | Intentionally skipped | No action needed |

## 🔍 File Discovery Logic

1. **Scan 01_INCOMING folder first** (highest priority)
2. **Check processing database** for existing records
3. **Compare file hashes** to detect changes
4. **Check modification times** for quick change detection
5. **Scan remaining Drive E** if capacity allows
6. **Respect exclusion patterns** (temp files, system folders)

## 👁️ File Watcher Service

### Starting the Watcher
```powershell
# Interactive mode
.\tools\process_drive_e_v2.ps1 -StartWatcher

# Daemon mode (background)
python tools/drive_e_watcher.py --daemon
```

### Watcher Features
- **Real-time monitoring** of entire Drive E
- **File settling detection** (waits for copying to complete)
- **Batch processing** (groups files for efficiency)
- **Automatic retry** for failed processing
- **Statistics logging** and monitoring

### Watcher Commands (Interactive Mode)
- `stats` - Show current statistics
- `quit` - Stop watcher and exit

## 📈 Monitoring & Statistics

### Show Current Statistics
```powershell
.\tools\process_drive_e_v2.ps1 -ShowStats
```

### Sample Statistics Output
```json
{
  "total_files": 12450,
  "status_counts": {
    "completed": 11800,
    "pending": 450,
    "failed": 150,
    "skipped": 50
  },
  "active_sessions": 0
}
```

### Processing Report Structure
```json
{
  "session_id": "uuid-here",
  "timestamp": "2025-08-27T22:30:00",
  "batch_stats": {
    "total_files": 100,
    "successful": 95,
    "failed": 5,
    "success_rate": 95.0,
    "total_faces_detected": 234,
    "files_with_captions": 90,
    "total_processing_time": 450.5,
    "average_processing_time": 4.5
  },
  "overall_stats": {
    "total_files": 12450,
    "status_counts": {...}
  },
  "failed_files": [...],
  "skipped_files": [...]
}
```

## 🛠️ Configuration

### Environment Variables
Create `tools/drive_e_config.env` from the example:
```bash
cp tools/drive_e_config.env.example tools/drive_e_config.env
```

### Key Settings
```env
# Processing
MAX_WORKERS=4
BATCH_SIZE=100
SETTLE_TIME=30

# File Types
PROCESS_IMAGES=true
PROCESS_VIDEOS=true

# Features
GENERATE_CAPTIONS=true
DETECT_FACES=true
EXTRACT_EXIF=true
```

## 🔄 Workflow Examples

### Daily Processing Workflow
```powershell
# 1. Quick check of new files
.\tools\process_drive_e_v2.ps1 -DryRun -MaxFiles 50

# 2. Process new files in incoming folder
.\tools\process_drive_e_v2.ps1 -MaxFiles 200

# 3. Start watcher for automatic processing
.\tools\process_drive_e_v2.ps1 -StartWatcher
```

### Recovery from Interruption
```powershell
# Resume processing from last checkpoint
.\tools\process_drive_e_v2.ps1 -Resume

# Check what failed
.\tools\process_drive_e_v2.ps1 -ShowStats

# Retry failed files
.\tools\process_drive_e_v2.ps1 -Resume -MaxFiles 100
```

### Large Drive Processing
```powershell
# Process in chunks
.\tools\process_drive_e_v2.ps1 -MaxFiles 1000 -Workers 6

# Check progress
.\tools\process_drive_e_v2.ps1 -ShowStats

# Continue processing
.\tools\process_drive_e_v2.ps1 -Resume -MaxFiles 1000
```

## 🔧 Troubleshooting

### Services Not Responding
```powershell
# Restart services
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting

# Check individual services
Invoke-WebRequest -Uri 'http://127.0.0.1:8002/health'
Invoke-WebRequest -Uri 'http://127.0.0.1:8002/caption/health'
Invoke-WebRequest -Uri 'http://127.0.0.1:8002/face/health'
```

### Processing Issues
```powershell
# Check processing database
.\tools\process_drive_e_v2.ps1 -ShowStats

# View failed files
python -c "
import sqlite3
conn = sqlite3.connect('drive_e_processing.db')
cursor = conn.cursor()
cursor.execute('SELECT file_path, last_error FROM processing_history WHERE processing_status = \"failed\"')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]}')
"
```

### Database Issues
```powershell
# Reset processing database (⚠️ loses history)
Remove-Item drive_e_processing.db -Force

# Backup database
Copy-Item drive_e_processing.db drive_e_processing_backup.db
```

## 🔮 Future Enhancements

### Planned Features
- **Smart organization** - Automatic folder structure based on date/content
- **Duplicate management** - Advanced duplicate detection and handling
- **Content-based search** - Search processed files by visual content
- **Batch operations** - Move, copy, organize files based on processing results
- **Web dashboard** - Browser-based monitoring and control interface
- **Cloud integration** - Sync processing status across devices

### Integration Points
- **vlmPhotoHouse API** - Seamless integration with existing asset management
- **Search interface** - Processed files appear in web UI immediately
- **Person management** - Face detection feeds into person-based search
- **Voice services** - Future audio/video transcription capabilities

## 📝 Logs and Files

### Generated Files
- `drive_e_processing.log` - Detailed processing log
- `drive_e_processing.db` - SQLite processing database
- `drive_e_processing_report.json` - Latest processing report
- `drive_e_watcher.log` - File watcher service log

### Log Locations
- **Console output** - Real-time progress
- **Processing log** - Detailed file-level operations
- **Service logs** - Individual service outputs
- **Database** - Persistent processing history

---

## 🎯 Perfect for Your Use Case

This enhanced system is specifically designed for your scenario:

✅ **Handles new files in 01_INCOMING** - Prioritizes newly added content  
✅ **Incremental processing** - Only processes what's new/changed  
✅ **Automatic detection** - File watcher monitors for new additions  
✅ **Robust bookkeeping** - Never loses track of processing state  
✅ **Seamless integration** - Works with your existing vlmPhotoHouse services  
✅ **Production ready** - Error handling, recovery, and monitoring built-in  

**Ready to transform your Drive E into a fully managed, AI-powered media library! 🚀📸🎥**
