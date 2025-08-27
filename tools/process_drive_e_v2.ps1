# Enhanced Drive E Photo and Video Processing Script
# PowerShell wrapper for the incremental Python Drive E processor v2

param(
    [string]$DriveRoot = "E:\",
    [int]$MaxFiles,
    [ValidateSet("images", "videos", "all")]
    [string]$FileTypes = "all",
    [int]$Workers = 4,
    [int]$BatchSize = 100,
    [string]$ReportPath = "drive_e_processing_report.json",
    [switch]$DryRun,
    [switch]$QuickTest,
    [switch]$FocusIncoming,
    [switch]$ForceReprocess,
    [switch]$Resume,
    [switch]$ShowStats,
    [switch]$StartWatcher,
    [switch]$StopWatcher
)

# Script configuration
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$PythonScript = Join-Path $ScriptDir "drive_e_processor_v2.py"
$WatcherScript = Join-Path $ScriptDir "drive_e_watcher.py"

Write-Host "🚀 Enhanced Drive E Photo/Video Processor" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan

# Handle special commands first
if ($ShowStats) {
    Write-Host "📊 Showing processing statistics..." -ForegroundColor Yellow
    try {
        & python $PythonScript --show-stats
        exit 0
    } catch {
        Write-Host "❌ Failed to get statistics: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

if ($StartWatcher) {
    Write-Host "👁️ Starting file watcher service..." -ForegroundColor Yellow
    Write-Host "   This will monitor Drive E for new files and process them automatically." -ForegroundColor Gray
    Write-Host "   Press Ctrl+C to stop the watcher." -ForegroundColor Gray
    Write-Host ""
    
    try {
        & python $WatcherScript --drive-root $DriveRoot
        exit 0
    } catch {
        Write-Host "❌ Failed to start watcher: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

# Check if services are running
Write-Host "🔍 Checking services..." -ForegroundColor Yellow

$MainAPI = "http://127.0.0.1:8002/health"
$VoiceAPI = "http://127.0.0.1:8001/api/voice-chat/health"

try {
    $response = Invoke-WebRequest -Uri $MainAPI -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Main API service is running" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Main API service not responding. Please start services first:" -ForegroundColor Red
    Write-Host "   .\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting" -ForegroundColor Yellow
    exit 1
}

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8002/caption/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ Caption service is available" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Caption service may not be available" -ForegroundColor Yellow
}

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8002/face/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ Face detection service is available" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Face detection service may not be available" -ForegroundColor Yellow
}

try {
    $response = Invoke-WebRequest -Uri $VoiceAPI -UseBasicParsing -TimeoutSec 5
    Write-Host "✅ Voice service is available" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Voice service may not be available" -ForegroundColor Yellow
}

# Check Python environment
Write-Host "🐍 Checking Python environment..." -ForegroundColor Yellow

# Check for virtual environment
$VenvPath = Join-Path $RootDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPath) {
    $PythonCmd = $VenvPath
    Write-Host "✅ Using virtual environment: $VenvPath" -ForegroundColor Green
} else {
    $PythonCmd = "python"
    Write-Host "⚠️  Using system Python (venv not found)" -ForegroundColor Yellow
}

try {
    $pythonVersion = & $PythonCmd --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green
    } else {
        throw "Python not found"
    }
} catch {
    Write-Host "❌ Python not found or not working" -ForegroundColor Red
    exit 1
}

# Check required packages (only if using system Python)
if ($PythonCmd -eq "python") {
    Write-Host "📦 Checking required packages..." -ForegroundColor Yellow
    $RequiredPackages = @("requests", "pillow", "exifread", "watchdog")

    foreach ($package in $RequiredPackages) {
        try {
            & $PythonCmd -c "import $($package.ToLower().Replace('pillow', 'PIL'))" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ $package is installed" -ForegroundColor Green
            } else {
                Write-Host "❌ $package is missing. Installing..." -ForegroundColor Yellow
                & $PythonCmd -m pip install $package
            }
        } catch {
            Write-Host "❌ Failed to check/install $package" -ForegroundColor Red
        }
    }
} else {
    Write-Host "📦 Using virtual environment (assuming packages are installed)" -ForegroundColor Green
}

# Quick test mode - process just a few files
if ($QuickTest) {
    Write-Host "🧪 Running quick test (max 10 files, focus incoming)..." -ForegroundColor Cyan
    $MaxFiles = 10
    $DryRun = $false
    $FocusIncoming = $true
}

# Set default for FocusIncoming if not specified
if (-not $ForceReprocess -and -not $Resume) {
    $FocusIncoming = $true
}

# Build Python command arguments
$PythonArgs = @()
$PythonArgs += "--drive-root", $DriveRoot
if ($MaxFiles) { $PythonArgs += "--max-files", $MaxFiles }
$PythonArgs += "--file-types", $FileTypes
$PythonArgs += "--workers", $Workers
$PythonArgs += "--batch-size", $BatchSize
$PythonArgs += "--report-path", $ReportPath
if ($DryRun) { $PythonArgs += "--dry-run" }
if ($FocusIncoming) { $PythonArgs += "--focus-incoming" }
if ($ForceReprocess) { $PythonArgs += "--force-reprocess" }
if ($Resume) { $PythonArgs += "--resume" }

# Display configuration
Write-Host ""
Write-Host "🔧 Configuration:" -ForegroundColor Cyan
Write-Host "   Drive Root: $DriveRoot" -ForegroundColor White
Write-Host "   Max Files: $(if ($MaxFiles) { $MaxFiles } else { 'unlimited' })" -ForegroundColor White
Write-Host "   File Types: $FileTypes" -ForegroundColor White
Write-Host "   Workers: $Workers" -ForegroundColor White
Write-Host "   Batch Size: $BatchSize" -ForegroundColor White
Write-Host "   Report Path: $ReportPath" -ForegroundColor White
Write-Host "   Dry Run: $DryRun" -ForegroundColor White
Write-Host "   Focus Incoming: $FocusIncoming" -ForegroundColor White
Write-Host "   Force Reprocess: $ForceReprocess" -ForegroundColor White
Write-Host "   Resume: $Resume" -ForegroundColor White
Write-Host ""

# Show incremental processing info
Write-Host "🔄 Incremental Processing Features:" -ForegroundColor Green
Write-Host "   ✅ Only processes new/changed files" -ForegroundColor Gray
Write-Host "   ✅ Maintains processing history database" -ForegroundColor Gray
Write-Host "   ✅ Automatic checkpoint and resume" -ForegroundColor Gray
Write-Host "   ✅ Prioritizes 01_INCOMING folder" -ForegroundColor Gray
Write-Host "   ✅ Tracks processing sessions" -ForegroundColor Gray
Write-Host ""

# Confirm before processing
if (-not $DryRun -and -not $QuickTest -and -not $Resume) {
    $confirm = Read-Host "Proceed with processing? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "❌ Processing cancelled" -ForegroundColor Red
        exit 0
    }
}

# Show helpful commands
if ($DryRun) {
    Write-Host "💡 After dry run, you can:" -ForegroundColor Cyan
    Write-Host "   • Start processing: .\tools\process_drive_e_v2.ps1" -ForegroundColor Yellow
    Write-Host "   • Resume processing: .\tools\process_drive_e_v2.ps1 -Resume" -ForegroundColor Yellow
    Write-Host "   • Start file watcher: .\tools\process_drive_e_v2.ps1 -StartWatcher" -ForegroundColor Yellow
    Write-Host ""
}

# Run the Python script
Write-Host "🚀 Starting processing..." -ForegroundColor Green
Write-Host "Command: $PythonCmd $PythonScript $($PythonArgs -join ' ')" -ForegroundColor Gray

try {
    $startTime = Get-Date
    
    # Change to script directory to ensure relative paths work
    Push-Location $RootDir
    
    # Execute Python script
    & $PythonCmd $PythonScript @PythonArgs
    
    $endTime = Get-Date
    $duration = $endTime - $startTime
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Processing completed successfully!" -ForegroundColor Green
        Write-Host "⏱️  Total time: $($duration.ToString('hh\:mm\:ss'))" -ForegroundColor Green
        
        if (Test-Path $ReportPath) {
            Write-Host "📊 Report saved to: $ReportPath" -ForegroundColor Green
            
            # Show quick summary
            try {
                $report = Get-Content $ReportPath | ConvertFrom-Json
                $batchStats = $report.batch_stats
                $overallStats = $report.overall_stats
                
                Write-Host ""
                Write-Host "📈 Session Summary:" -ForegroundColor Cyan
                Write-Host "   Files in this session: $($batchStats.total_files)" -ForegroundColor White
                Write-Host "   Successful: $($batchStats.successful)" -ForegroundColor Green
                Write-Host "   Failed: $($batchStats.failed)" -ForegroundColor Red
                Write-Host "   Success rate: $($batchStats.success_rate.ToString('F1'))%" -ForegroundColor White
                Write-Host "   Faces detected: $($batchStats.total_faces_detected)" -ForegroundColor White
                Write-Host "   Files with captions: $($batchStats.files_with_captions)" -ForegroundColor White
                Write-Host ""
                Write-Host "📊 Overall Database:" -ForegroundColor Cyan
                Write-Host "   Total files tracked: $($overallStats.total_files)" -ForegroundColor White
                
                if ($overallStats.status_counts) {
                    foreach ($status in $overallStats.status_counts.PSObject.Properties) {
                        Write-Host "   $($status.Name): $($status.Value)" -ForegroundColor Gray
                    }
                }
                
            } catch {
                Write-Host "📊 Report generated but couldn't parse summary" -ForegroundColor Yellow
            }
        }
        
        # Show next steps
        Write-Host ""
        Write-Host "🔄 Next Steps:" -ForegroundColor Cyan
        Write-Host "   • View detailed stats: .\tools\process_drive_e_v2.ps1 -ShowStats" -ForegroundColor Yellow
        Write-Host "   • Start file watcher: .\tools\process_drive_e_v2.ps1 -StartWatcher" -ForegroundColor Yellow
        Write-Host "   • Resume processing: .\tools\process_drive_e_v2.ps1 -Resume" -ForegroundColor Yellow
        
    } else {
        Write-Host "❌ Processing failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    }
    
} catch {
    Write-Host "💥 Error occurred: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "🏁 Script completed" -ForegroundColor Cyan
