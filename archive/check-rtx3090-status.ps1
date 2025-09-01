param(
    [switch]$Continuous,
    [int]$Interval = 5
)

Write-Host "🎯 RTX 3090 Quick Status Check" -ForegroundColor Cyan
Write-Host "=" * 50

function Get-RTX3090Status {
    # Check GPU status
    try {
        $gpuResult = nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits
        $rtx3090Found = $false
        
        foreach ($line in $gpuResult) {
            $parts = $line.Split(',')
            $index = $parts[0].Trim()
            $name = $parts[1].Trim()
            
            if ($name -like "*RTX 3090*") {
                $rtx3090Found = $true
                $memUsed = [int]$parts[2].Trim()
                $memTotal = [int]$parts[3].Trim()
                $gpuUtil = [int]$parts[4].Trim()
                $temp = [int]$parts[5].Trim()
                $memUsedGB = [math]::Round($memUsed / 1024, 2)
                $memTotalGB = [math]::Round($memTotal / 1024, 1)
                $memPercent = [math]::Round(($memUsed / $memTotal) * 100, 1)
                
                $status = if ($gpuUtil -gt 50) { "🔥 HEAVY LOAD" }
                         elseif ($gpuUtil -gt 10) { "⚡ PROCESSING" }
                         elseif ($memUsedGB -gt 2.0) { "📊 MODEL LOADED" }
                         elseif ($memUsedGB -gt 0.5) { "💾 LIGHT USAGE" }
                         else { "💤 IDLE" }
                
                Write-Host ""
                Write-Host "🎯 RTX 3090 Status (nvidia-smi GPU $index):" -ForegroundColor Green
                Write-Host "   Status: $status" -ForegroundColor Yellow
                Write-Host "   Memory: $memUsedGB GB / $memTotalGB GB ($memPercent%)" -ForegroundColor Cyan
                Write-Host "   GPU Utilization: $gpuUtil%" -ForegroundColor Cyan
                Write-Host "   Temperature: $temp°C" -ForegroundColor Cyan
                
                return @{
                    Found = $true
                    MemoryGB = $memUsedGB
                    Utilization = $gpuUtil
                    Status = $status
                }
            }
        }
        
        if (-not $rtx3090Found) {
            Write-Host "❌ RTX 3090 not found!" -ForegroundColor Red
            return @{ Found = $false }
        }
        
    } catch {
        Write-Host "❌ Error checking GPU: $($_.Exception.Message)" -ForegroundColor Red
        return @{ Found = $false; Error = $_.Exception.Message }
    }
}

function Get-ProcessStatus {
    # Check for AI processes
    Write-Host ""
    Write-Host "🔍 AI Process Status:" -ForegroundColor Green
    
    $backendProcess = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" }
    $orchestratorProcess = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*ai_orchestrator*" }
    
    if ($backendProcess) {
        Write-Host "   ✅ Backend running (PID: $($backendProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Backend not running" -ForegroundColor Red
    }
    
    if ($orchestratorProcess) {
        Write-Host "   ✅ AI Orchestrator running (PID: $($orchestratorProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "   ❌ AI Orchestrator not running" -ForegroundColor Red
    }
}

function Get-EnvironmentStatus {
    Write-Host ""
    Write-Host "⚙️ Environment Configuration:" -ForegroundColor Green
    Write-Host "   CUDA_VISIBLE_DEVICES: $($env:CUDA_VISIBLE_DEVICES ?? 'Not set')" -ForegroundColor Cyan
    Write-Host "   EMBED_DEVICE: $($env:EMBED_DEVICE ?? 'Not set')" -ForegroundColor Cyan
    Write-Host "   CAPTION_DEVICE: $($env:CAPTION_DEVICE ?? 'Not set')" -ForegroundColor Cyan
    Write-Host "   FACE_EMBED_PROVIDER: $($env:FACE_EMBED_PROVIDER ?? 'Not set')" -ForegroundColor Cyan
    Write-Host "   CAPTION_PROVIDER: $($env:CAPTION_PROVIDER ?? 'Not set')" -ForegroundColor Cyan
}

if ($Continuous) {
    Write-Host "Starting continuous monitoring (Ctrl+C to stop)..." -ForegroundColor Yellow
    Write-Host ""
    
    while ($true) {
        Clear-Host
        Write-Host "🎯 RTX 3090 Continuous Monitor - $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
        Write-Host "=" * 60
        
        $gpuStatus = Get-RTX3090Status
        Get-ProcessStatus
        Get-EnvironmentStatus
        
        Write-Host ""
        Write-Host "🔄 Refreshing in $Interval seconds..." -ForegroundColor Gray
        Start-Sleep $Interval
    }
} else {
    # Single check
    $gpuStatus = Get-RTX3090Status
    Get-ProcessStatus  
    Get-EnvironmentStatus
    
    Write-Host ""
    if ($gpuStatus.Found -and $gpuStatus.MemoryGB -gt 1.0) {
        Write-Host "✅ RTX 3090 is actively being used!" -ForegroundColor Green
    } elseif ($gpuStatus.Found) {
        Write-Host "⚠️  RTX 3090 detected but minimal usage" -ForegroundColor Yellow
    } else {
        Write-Host "❌ RTX 3090 issues detected" -ForegroundColor Red
    }
}
