#!/usr/bin/env powershell
<#
.SYNOPSIS
Clean and Tidy VLM Photo Engine Project

.DESCRIPTION
Archives unused files, organizes the project structure, and prepares for production batch processing
#>

Write-Host "🧹 VLM Photo Engine - Project Cleanup & Organization" -ForegroundColor Cyan
Write-Host "=" * 60

# Define paths
$projectRoot = "C:\Users\yanbo\wSpace\vlm-photo-engine"
$vlmPhotoHouse = "$projectRoot\vlmPhotoHouse"
$lvFace = "$projectRoot\LVFace"
$archiveDir = "$vlmPhotoHouse\archive"

# Create archive directory
if (-not (Test-Path $archiveDir)) {
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    Write-Host "📁 Created archive directory: $archiveDir" -ForegroundColor Green
}

# Files to archive (no longer needed with SCRFD integration)
$filesToArchive = @(
    "face_processor.py",           # Old OpenCV-based processor
    "face_orchestrator.py",       # Original orchestrator
    "opencv_face_processor.py",   # OpenCV fallback
    "test_face_processing.py",    # Old test scripts
    "debug_task_worker.py",       # Debug scripts
    "download_scrfd_models.py",   # One-time download script
    "check_scrfd_status.py",      # One-time check script
    "monitor_scrfd_download.py"   # One-time monitor script
)

# Archive old files
Write-Host "`n📦 Archiving unused files..." -ForegroundColor Yellow
foreach ($file in $filesToArchive) {
    $sourcePath = "$vlmPhotoHouse\$file"
    if (Test-Path $sourcePath) {
        $destPath = "$archiveDir\$file"
        Move-Item -Path $sourcePath -Destination $destPath -Force
        Write-Host "   ✅ Archived: $file" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️ Not found: $file" -ForegroundColor Yellow
    }
}

# Clean up test files
Write-Host "`n🧽 Cleaning up test and temporary files..." -ForegroundColor Yellow

# Remove visualization files from main directories
Get-ChildItem -Path "E:\01_INCOMING" -Recurse -Filter "*detected*" | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "   ✅ Removed detection visualization files" -ForegroundColor Green

# Clean up log files (keep recent ones)
$logFiles = Get-ChildItem -Path $vlmPhotoHouse -Filter "*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
if ($logFiles) {
    $logFiles | Move-Item -Destination $archiveDir -Force
    Write-Host "   ✅ Archived old log files: $($logFiles.Count)" -ForegroundColor Green
}

# Organize current active files
Write-Host "`n📋 Current Active Project Structure:" -ForegroundColor Cyan
Write-Host "vlmPhotoHouse/" -ForegroundColor White
Write-Host "  ├── 🚀 run_multi_process_ai.ps1         # Multi-process launcher" -ForegroundColor Green
Write-Host "  ├── 🧠 enhanced_face_orchestrator_unified.py  # Batch processor" -ForegroundColor Green
Write-Host "  ├── 🔧 test_unified_service.py          # Service tester" -ForegroundColor Green
Write-Host "  ├── 🎨 visualize_detection.py           # Visual verification" -ForegroundColor Green
Write-Host "  ├── 🔬 analyze_integration.py           # Integration analysis" -ForegroundColor Green
Write-Host "  ├── 🗃️ metadata.sqlite                  # Main database" -ForegroundColor Green
Write-Host "  └── 📁 archive/                         # Archived files" -ForegroundColor Yellow

Write-Host "`nLVFace/" -ForegroundColor White
Write-Host "  ├── 🤖 unified_scrfd_service.py         # SCRFD + LVFace service" -ForegroundColor Green
Write-Host "  ├── 🔧 start_unified_service.sh         # Service startup script" -ForegroundColor Green
Write-Host "  ├── 📁 models/                          # ONNX models" -ForegroundColor Green
Write-Host "  └── 🗂️ embeddings/                      # Face embeddings" -ForegroundColor Green

# Check service status
Write-Host "`n🔍 Checking Service Status..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8003/status" -Method Get -TimeoutSec 5
    Write-Host "   ✅ SCRFD Service is running:" -ForegroundColor Green
    Write-Host "      Detector: $($response.face_detector)" -ForegroundColor White
    Write-Host "      GPU Providers: $($response.providers -join ', ')" -ForegroundColor White
} catch {
    Write-Host "   ❌ SCRFD Service not running" -ForegroundColor Red
    Write-Host "      💡 Start with: wsl -d Ubuntu-22.04 -- bash /mnt/c/Users/yanbo/wSpace/vlm-photo-engine/LVFace/start_unified_service.sh" -ForegroundColor Yellow
}

# Database summary
Write-Host "`n📊 Database Summary..." -ForegroundColor Yellow
try {
    $dbPath = "$vlmPhotoHouse\metadata.sqlite"
    if (Test-Path $dbPath) {
        # You could add SQLite queries here to show stats
        Write-Host "   ✅ Database exists: metadata.sqlite" -ForegroundColor Green
        $dbSize = [math]::Round((Get-Item $dbPath).Length / 1MB, 2)
        Write-Host "      Size: $dbSize MB" -ForegroundColor White
    } else {
        Write-Host "   ⚠️ Database not found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ Database check failed" -ForegroundColor Red
}

Write-Host "`n🎯 Ready for Production!" -ForegroundColor Green
Write-Host "=" * 60
Write-Host "📋 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Ensure SCRFD service is running (check above)" -ForegroundColor White
Write-Host "2. Run: .\run_multi_process_ai.ps1 (multi-process pipeline)" -ForegroundColor White
Write-Host "3. Or run: python enhanced_face_orchestrator_unified.py (batch processing)" -ForegroundColor White
Write-Host "4. Monitor progress in real-time" -ForegroundColor White
