# Drive E Photo and Video Processor

Comprehensive tool to process photos and videos from Drive E using your running vlmPhotoHouse services.

## Features

- 🔍 **Auto-discovery** of photos and videos on Drive E
- 📝 **Caption generation** using Qwen2.5-VL + BLIP2 fallback  
- 👤 **Face detection** and embedding with LVFace
- 📊 **Metadata extraction** from EXIF and file properties
- 🗄️ **Asset management** with deduplication
- ⚡ **Concurrent processing** with configurable workers
- 📈 **Detailed reporting** and progress tracking
- 🛡️ **Error handling** and recovery
- ✅ **Smart bookkeeping** - automatically skips already processed files
- 🔄 **Resume capability** - continue where you left off after interruption
- 💾 **Checkpoint system** - saves progress every N files
- 📋 **Processing history** - tracks all file processing attempts

## Prerequisites

Ensure your services are running:
```powershell
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
```

Verify services are responding:
- Main API: http://127.0.0.1:8002/health
- Caption Service: http://127.0.0.1:8002/caption/health  
- Face Service: http://127.0.0.1:8002/face/health
- Voice Service: http://127.0.0.1:8001/api/voice-chat/health

## Quick Start

### Option 1: PowerShell Script (Recommended)

```powershell
# Quick test with 10 files
.\tools\process_drive_e.ps1 -QuickTest

# Process only images
.\tools\process_drive_e.ps1 -FileTypes images -MaxFiles 1000

# Full processing 
.\tools\process_drive_e.ps1 -DriveRoot "E:\" -Workers 4
```

### Option 2: Python Script Directly

```bash
# Discovery only (dry run)
python tools/drive_e_processor.py --dry-run

# Process images only
python tools/drive_e_processor.py --file-types images --max-files 100

# Full processing with custom settings
python tools/drive_e_processor.py --drive-root "E:/" --workers 6 --batch-size 50
```

## Command Line Options

### PowerShell Script (`process_drive_e.ps1`)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `-DriveRoot` | Drive E root path | `E:\` |
| `-MaxFiles` | Maximum files to process | unlimited |
| `-FileTypes` | `images`, `videos`, or `all` | `all` |
| `-Workers` | Number of worker threads | `4` |
| `-BatchSize` | Files per batch | `100` |
| `-ReportPath` | Output report file | `drive_e_processing_report.json` |
| `-DryRun` | Discover files only | `false` |
| `-QuickTest` | Test with 10 files | `false` |

### Python Script (`drive_e_processor.py`)

```bash
python tools/drive_e_processor.py --help
```

| Option | Description |
|--------|-------------|
| `--drive-root` | Drive E root path |
| `--max-files` | Maximum files to process |
| `--file-types` | Types of files: images, videos, all |
| `--workers` | Number of worker threads |
| `--batch-size` | Batch size for processing |
| `--report-path` | Output path for report |
| `--dry-run` | Discover files but don't process |

## Processing Pipeline

1. **Discovery**: Scan Drive E for supported files
2. **Metadata Extraction**: EXIF data, file properties, dimensions
3. **Asset Ingestion**: Create database entries with deduplication
4. **Caption Generation**: AI-powered image descriptions
5. **Face Detection**: Detect and embed faces for person search
6. **Reporting**: Generate detailed processing reports

## Supported File Types

### Images
- `.jpg`, `.jpeg`, `.png`, `.heic`, `.webp`, `.tiff`, `.bmp`, `.gif`

### Videos  
- `.mp4`, `.avi`, `.mov`, `.mkv`, `.wmv`, `.flv`, `.webm`, `.m4v`

## Output Reports

Processing generates detailed JSON reports including:

```json
{
  "timestamp": "2025-08-27T22:30:00",
  "total_files": 1250,
  "successful": 1200,
  "failed": 50,
  "success_rate": 96.0,
  "total_faces_detected": 3450,
  "files_with_captions": 1180,
  "total_processing_time": 1800.5,
  "average_processing_time": 1.44,
  "failed_files": ["E:/path/to/corrupted.jpg"]
}
```

## Configuration

Copy and customize the configuration:
```bash
cp tools/drive_e_config.env.example tools/drive_e_config.env
```

Edit settings for:
- File type filtering
- Performance tuning  
- Processing options
- Exclusion patterns
- Safety features

## Performance Tips

1. **Start Small**: Use `-QuickTest` or `-MaxFiles 100` first
2. **Monitor Resources**: Watch CPU, memory, and GPU usage
3. **Adjust Workers**: Reduce if system becomes unresponsive
4. **Batch Size**: Smaller batches for better progress tracking
5. **File Types**: Process images first, then videos separately

## Troubleshooting

### Services Not Responding
```powershell
# Restart services
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting

# Check service status
Invoke-WebRequest -Uri 'http://127.0.0.1:8002/health'
```

### Memory Issues
- Reduce worker count: `-Workers 2`
- Smaller batches: `-BatchSize 25`  
- Process file types separately

### Large Drive E
- Use `-MaxFiles` to process incrementally
- Process by subdirectories
- Run overnight with logging

### Failed Files
Check the generated report for `failed_files` list and error details in the log file.

## Examples

```powershell
# Test run - 10 files only
.\tools\process_drive_e.ps1 -QuickTest

# Process photos from wedding folder
python tools/drive_e_processor.py --drive-root "E:/Photos/Wedding2024" --file-types images

# Large batch processing overnight
.\tools\process_drive_e.ps1 -DriveRoot "E:\" -Workers 6 -BatchSize 200 -MaxFiles 10000

# Dry run to see what would be processed
.\tools\process_drive_e.ps1 -DryRun

# Videos only with detailed reporting
.\tools\process_drive_e.ps1 -FileTypes videos -ReportPath "video_processing_report.json"
```

## Integration with vlmPhotoHouse

The processor integrates seamlessly with your existing vlmPhotoHouse services:

- **Assets API**: Creates asset records with metadata
- **Caption Service**: Generates AI descriptions
- **Face Service**: Detects faces and creates embeddings
- **Search API**: Makes processed content searchable
- **UI**: Processed files appear in the web interface

After processing, you can search your Drive E content through:
- Web UI: http://127.0.0.1:8002/ui
- API: http://127.0.0.1:8002/docs

## Logs and Monitoring

- **Console Output**: Real-time progress and status
- **Log File**: `drive_e_processing.log` with detailed information
- **JSON Report**: Comprehensive processing statistics
- **Service Logs**: Check individual service outputs for errors

---

**Happy Processing! 📸🎥**
