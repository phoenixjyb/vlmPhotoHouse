# Drive E Photo and Video Processing Script
# PowerShell wrapper for the Python Drive E processor

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
    [switch]$ForceReprocess,
    [switch]$NoResume,
    [switch]$ShowProcessed,
    [int]$CheckpointInterval = 10
)

# Script configuration
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$PythonScript = Join-Path $ScriptDir "drive_e_processor.py"

Write-Host "🚀 Drive E Photo/Video Processor" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan

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

$PythonCmd = "python"
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

# Check required packages
Write-Host "📦 Checking required packages..." -ForegroundColor Yellow
$RequiredPackages = @("requests", "pillow", "exifread")

foreach ($package in $RequiredPackages) {
    try {
        & $PythonCmd -c "import $($package.ToLower())" 2>$null
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

# Quick test mode - process just a few files
if ($QuickTest) {
    Write-Host "🧪 Running quick test (max 10 files)..." -ForegroundColor Cyan
    $MaxFiles = 10
    $DryRun = $false
}

# Build Python command arguments
$PythonArgs = @()
$PythonArgs += "--drive-root", $DriveRoot
if ($MaxFiles) { $PythonArgs += "--max-files", $MaxFiles }
$PythonArgs += "--file-types", $FileTypes
$PythonArgs += "--workers", $Workers
$PythonArgs += "--batch-size", $BatchSize
$PythonArgs += "--report-path", $ReportPath
$PythonArgs += "--checkpoint-interval", $CheckpointInterval
if ($DryRun) { $PythonArgs += "--dry-run" }
if ($ForceReprocess) { $PythonArgs += "--force-reprocess" }
if ($NoResume) { $PythonArgs += "--no-resume" }
if ($ShowProcessed) { $PythonArgs += "--show-processed" }

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
Write-Host "   Force Reprocess: $ForceReprocess" -ForegroundColor White
Write-Host "   Resume from Checkpoint: $(-not $NoResume)" -ForegroundColor White
Write-Host "   Checkpoint Interval: $CheckpointInterval files" -ForegroundColor White
Write-Host ""

# Confirm before processing
if (-not $DryRun -and -not $QuickTest) {
    $confirm = Read-Host "Proceed with processing? (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "❌ Processing cancelled" -ForegroundColor Red
        exit 0
    }
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
                Write-Host ""
                Write-Host "📈 Quick Summary:" -ForegroundColor Cyan
                Write-Host "   Total files: $($report.total_files)" -ForegroundColor White
                Write-Host "   Successful: $($report.successful)" -ForegroundColor Green
                Write-Host "   Failed: $($report.failed)" -ForegroundColor Red
                Write-Host "   Success rate: $($report.success_rate.ToString('F1'))%" -ForegroundColor White
                Write-Host "   Faces detected: $($report.total_faces_detected)" -ForegroundColor White
                Write-Host "   Files with captions: $($report.files_with_captions)" -ForegroundColor White
            } catch {
                Write-Host "📊 Report generated but couldn't parse summary" -ForegroundColor Yellow
            }
        }
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
