param(
    [switch]$StartMonitoring,
    [switch]$SkipPreCheck
)

Write-Host "=== VLM PHOTO ENGINE - GPU PRE-CHECK & AI STARTER ===" -ForegroundColor Cyan
Write-Host "RTX 3090 Multi-Environment Validation & AI Pipeline Launch" -ForegroundColor Yellow

if (-not $SkipPreCheck) {
    Write-Host ""
    Write-Host "🔍 Phase 1: Comprehensive GPU Pre-Check" -ForegroundColor Green
    
    # Run the GPU validation
    try {
        $preCheckResult = & .\.venv\Scripts\python.exe gpu_precheck_validation.py
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ GPU Pre-Check FAILED!" -ForegroundColor Red
            Write-Host "Cannot proceed with AI processing until GPU issues are resolved" -ForegroundColor Yellow
            exit 1
        }
        
        Write-Host "✅ GPU Pre-Check PASSED - All environments can access RTX 3090" -ForegroundColor Green
        
    } catch {
        Write-Host "❌ GPU Pre-Check execution failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "⚠️  Skipping GPU Pre-Check (--SkipPreCheck specified)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "⚙️  Phase 2: Environment Configuration" -ForegroundColor Green

# Set optimal GPU configuration based on pre-check results
Write-Host "Setting RTX 3090 configuration..." -ForegroundColor White
$env:CUDA_VISIBLE_DEVICES = "0"
$env:EMBED_DEVICE = "cuda:0"  
$env:CAPTION_DEVICE = "cuda:0"
$env:FACE_EMBED_PROVIDER = "lvface"
$env:CAPTION_PROVIDER = "blip2"
$env:LVFACE_EXTERNAL_DIR = "C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace"
$env:CAPTION_EXTERNAL_DIR = "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels"

Write-Host "✅ Environment configured for RTX 3090 (cuda:0)" -ForegroundColor Green
Write-Host "   CUDA_VISIBLE_DEVICES=0" -ForegroundColor Cyan
Write-Host "   EMBED_DEVICE=cuda:0" -ForegroundColor Cyan
Write-Host "   CAPTION_DEVICE=cuda:0" -ForegroundColor Cyan

Write-Host ""
Write-Host "🧹 Phase 3: System Cleanup" -ForegroundColor Green

# Clear any stuck tasks before starting
Write-Host "Checking for stuck AI tasks..." -ForegroundColor White
try {
    $stuckTasks = & .\.venv\Scripts\python.exe -c "
from backend.app.database import SessionLocal
from backend.app.models import Task
from sqlalchemy import text

db = SessionLocal()
try:
    # Check for tasks stuck in running state
    stuck_count = db.execute(text('SELECT COUNT(*) FROM tasks WHERE status = ''running''')).scalar()
    pending_count = db.execute(text('SELECT COUNT(*) FROM tasks WHERE status = ''pending''')).scalar()
    print(f'Stuck running tasks: {stuck_count}')
    print(f'Pending tasks: {pending_count}')
    
    if stuck_count > 0:
        print('Resetting stuck tasks to pending...')
        db.execute(text('UPDATE tasks SET status = ''pending'' WHERE status = ''running'''))
        db.commit()
        print(f'Reset {stuck_count} stuck tasks')
    
finally:
    db.close()
"
    
    Write-Host $stuckTasks -ForegroundColor Gray
    
} catch {
    Write-Host "⚠️  Could not check/reset stuck tasks: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🚀 Phase 4: AI Pipeline Launch" -ForegroundColor Green

if ($StartMonitoring) {
    Write-Host "Starting tmux-style monitoring system..." -ForegroundColor White
    
    # Launch the monitoring system
    & .\start-ai-monitoring.ps1
    
} else {
    Write-Host "💡 Ready to start AI processing!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "1. Run: .\start-ai-processing-and-monitoring.ps1     # Start enhanced monitoring" -ForegroundColor Gray
    Write-Host "2. Monitor GPU usage with nvidia-smi or .\check-rtx3090-status.ps1" -ForegroundColor Gray
    Write-Host "3. Check logs for actual processing and external model loading" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Environment variables set for this session:" -ForegroundColor White
    Write-Host "  CUDA_VISIBLE_DEVICES=$env:CUDA_VISIBLE_DEVICES" -ForegroundColor Cyan
    Write-Host "  EMBED_DEVICE=$env:EMBED_DEVICE" -ForegroundColor Cyan
    Write-Host "  CAPTION_DEVICE=$env:CAPTION_DEVICE" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "✅ GPU Pre-Check & AI Configuration Complete!" -ForegroundColor Green
