#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Real-time Caption Processing Progress Monitor
.DESCRIPTION
    Comprehensive monitoring of BLIP2 caption generation progress including:
    - GPU utilization and memory usage
    - Task queue status and completion rates
    - Recent caption samples
    - Database progress statistics
    - Performance metrics
.PARAMETER RefreshInterval
    Seconds between updates (default: 5)
.PARAMETER ShowSamples
    Number of recent captions to display (default: 3)
.PARAMETER Continuous
    Run continuously until Ctrl+C (default: false)
#>

param(
    [int]$RefreshInterval = 5,
    [int]$ShowSamples = 3,
    [switch]$Continuous = $false
)

# Configuration
$ApiBaseUrl = "http://127.0.0.1:8002"
$BackendDir = "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\backend"

function Get-GPUStatus {
    try {
        $nvidiaOutput = nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits 2>$null
        if ($nvidiaOutput) {
            $lines = $nvidiaOutput -split "`n"
            $gpus = @()
            foreach ($line in $lines) {
                if ($line.Trim()) {
                    $parts = $line -split ", "
                    if ($parts.Length -ge 6) {
                        $gpus += [PSCustomObject]@{
                            Name = $parts[0].Trim()
                            Temperature = [int]$parts[1]
                            Utilization = [int]$parts[2]
                            MemoryUsed = [int]$parts[3]
                            MemoryTotal = [int]$parts[4]
                            PowerDraw = [float]$parts[5]
                            MemoryPercent = [math]::Round(([int]$parts[3] / [int]$parts[4]) * 100, 1)
                        }
                    }
                }
            }
            return $gpus
        }
    } catch {
        return @()
    }
}

function Get-TaskQueueStatus {
    try {
        $response = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -Method Get -TimeoutSec 5
        return $response
    } catch {
        return $null
    }
}

function Get-DatabaseProgress {
    try {
        # Use CLI to get database statistics
        $env:PYTHONPATH = $BackendDir
        $output = & "$BackendDir\.venv\Scripts\python.exe" -c @"
import sys
sys.path.insert(0, '$BackendDir')
from app.db import Asset, Caption, Task
from app.main import SessionLocal
import json
from sqlalchemy import func, text

with SessionLocal() as session:
    # Asset statistics
    total_assets = session.query(Asset).count()
    
    # Caption statistics
    assets_with_captions = session.query(func.count(func.distinct(Caption.asset_id))).scalar()
    total_captions = session.query(Caption).count()
    user_edited_captions = session.query(Caption).filter(Caption.user_edited == True).count()
    
    # Task statistics
    pending_caption_tasks = session.query(Task).filter(
        Task.type == 'caption',
        Task.state == 'pending'
    ).count()
    
    running_caption_tasks = session.query(Task).filter(
        Task.type == 'caption', 
        Task.state == 'running'
    ).count()
    
    completed_caption_tasks = session.query(Task).filter(
        Task.type == 'caption',
        Task.state == 'completed'
    ).count()
    
    failed_caption_tasks = session.query(Task).filter(
        Task.type == 'caption',
        Task.state == 'failed'
    ).count()
    
    # Assets without captions
    assets_without_captions = total_assets - assets_with_captions
    
    # Recent completed tasks for performance metrics
    recent_completed = session.execute(text('''
        SELECT created_at, updated_at, payload_json 
        FROM tasks 
        WHERE type = 'caption' AND state = 'completed' 
        ORDER BY updated_at DESC 
        LIMIT 10
    '')).fetchall()
    
    # Calculate average processing time for recent tasks
    avg_processing_time = 0
    if recent_completed:
        total_time = 0
        count = 0
        for task in recent_completed:
            if task.created_at and task.updated_at:
                delta = (task.updated_at - task.created_at).total_seconds()
                if delta > 0 and delta < 3600:  # Reasonable processing time (< 1 hour)
                    total_time += delta
                    count += 1
        if count > 0:
            avg_processing_time = total_time / count
    
    result = {
        'total_assets': total_assets,
        'assets_with_captions': assets_with_captions,
        'assets_without_captions': assets_without_captions,
        'total_captions': total_captions,
        'user_edited_captions': user_edited_captions,
        'pending_tasks': pending_caption_tasks,
        'running_tasks': running_caption_tasks,
        'completed_tasks': completed_caption_tasks,
        'failed_tasks': failed_caption_tasks,
        'avg_processing_time': round(avg_processing_time, 2),
        'completion_percentage': round((assets_with_captions / total_assets * 100), 2) if total_assets > 0 else 0
    }
    
    print(json.dumps(result))
"@
        
        if ($output) {
            return $output | ConvertFrom-Json
        }
    } catch {
        return $null
    }
}

function Get-RecentCaptions {
    param([int]$Count = 3)
    
    try {
        $env:PYTHONPATH = $BackendDir
        $output = & "$BackendDir\.venv\Scripts\python.exe" -c @"
import sys
sys.path.insert(0, r'$($BackendDir.Replace('\', '\\'))')
from app.db import Asset, Caption
from app.main import SessionLocal
import json
from sqlalchemy import desc

with SessionLocal() as session:
    recent_captions = session.query(
        Caption.text, 
        Caption.created_at,
        Caption.model_name,
        Asset.file_path
    ).join(Asset).filter(
        Caption.text.isnot(None),
        Caption.text != '',
        ~Caption.text.like('%stub%'),
        ~Caption.text.like('%not available%')
    ).order_by(desc(Caption.created_at)).limit($Count).all()
    
    results = []
    for caption in recent_captions:
        results.append({
            'text': caption.text,
            'created_at': caption.created_at.isoformat() if caption.created_at else None,
            'model': caption.model_name or 'unknown',
            'file_path': caption.file_path
        })
    
    print(json.dumps(results))
"@
        
        if ($output) {
            return $output | ConvertFrom-Json
        }
    } catch {
        return @()
    }
}

function Show-ProgressDashboard {
    Clear-Host
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "🖼️  VLM Photo Engine - Caption Processing Monitor" -ForegroundColor Green
    Write-Host "📊 Real-time Progress Dashboard - $timestamp" -ForegroundColor Cyan
    Write-Host ("=" * 80) -ForegroundColor Gray
    
    # GPU Status
    Write-Host "`n🎯 GPU Status:" -ForegroundColor Yellow
    $gpus = Get-GPUStatus
    if ($gpus) {
        foreach ($gpu in $gpus) {
            $utilColor = if ($gpu.Utilization -gt 50) { "Green" } elseif ($gpu.Utilization -gt 20) { "Yellow" } else { "White" }
            $tempColor = if ($gpu.Temperature -gt 80) { "Red" } elseif ($gpu.Temperature -gt 70) { "Yellow" } else { "Green" }
            
            Write-Host "  $($gpu.Name)" -ForegroundColor White
            Write-Host "    Utilization: " -NoNewline; Write-Host "$($gpu.Utilization)%" -ForegroundColor $utilColor
            Write-Host "    Memory: " -NoNewline; Write-Host "$($gpu.MemoryUsed)MB / $($gpu.MemoryTotal)MB ($($gpu.MemoryPercent)%)" -ForegroundColor White
            Write-Host "    Temperature: " -NoNewline; Write-Host "$($gpu.Temperature)°C" -ForegroundColor $tempColor
            Write-Host "    Power: $($gpu.PowerDraw)W" -ForegroundColor White
        }
    } else {
        Write-Host "  ❌ Unable to retrieve GPU status" -ForegroundColor Red
    }
    
    # Database Progress
    Write-Host "`n📈 Database Progress:" -ForegroundColor Yellow
    $dbStats = Get-DatabaseProgress
    if ($dbStats) {
        $completionColor = if ($dbStats.completion_percentage -gt 80) { "Green" } elseif ($dbStats.completion_percentage -gt 50) { "Yellow" } else { "Red" }
        
        Write-Host "  Total Assets: " -NoNewline; Write-Host $dbStats.total_assets -ForegroundColor White
        Write-Host "  Assets with Captions: " -NoNewline; Write-Host $dbStats.assets_with_captions -ForegroundColor Green
        Write-Host "  Assets without Captions: " -NoNewline; Write-Host $dbStats.assets_without_captions -ForegroundColor Red
        Write-Host "  Completion: " -NoNewline; Write-Host "$($dbStats.completion_percentage)%" -ForegroundColor $completionColor
        Write-Host "  Total Captions Generated: " -NoNewline; Write-Host $dbStats.total_captions -ForegroundColor White
        Write-Host "  User-Edited Captions: " -NoNewline; Write-Host $dbStats.user_edited_captions -ForegroundColor Cyan
    } else {
        Write-Host "  ❌ Unable to retrieve database statistics" -ForegroundColor Red
    }
    
    # Task Queue Status
    Write-Host "`n⚡ Task Queue Status:" -ForegroundColor Yellow
    if ($dbStats) {
        $activeColor = if (($dbStats.running_tasks + $dbStats.pending_tasks) -gt 0) { "Green" } else { "Gray" }
        
        Write-Host "  Pending Tasks: " -NoNewline; Write-Host $dbStats.pending_tasks -ForegroundColor Yellow
        Write-Host "  Running Tasks: " -NoNewline; Write-Host $dbStats.running_tasks -ForegroundColor $activeColor
        Write-Host "  Completed Tasks: " -NoNewline; Write-Host $dbStats.completed_tasks -ForegroundColor Green
        Write-Host "  Failed Tasks: " -NoNewline; Write-Host $dbStats.failed_tasks -ForegroundColor Red
        
        if ($dbStats.avg_processing_time -gt 0) {
            Write-Host "  Avg Processing Time: " -NoNewline; Write-Host "$($dbStats.avg_processing_time)s per caption" -ForegroundColor Cyan
        }
        
        # Estimate completion time
        if ($dbStats.pending_tasks -gt 0 -and $dbStats.avg_processing_time -gt 0) {
            $estimatedMinutes = ($dbStats.pending_tasks * $dbStats.avg_processing_time) / 60
            $estimatedTime = if ($estimatedMinutes -gt 60) { 
                "$([math]::Round($estimatedMinutes / 60, 1)) hours" 
            } else { 
                "$([math]::Round($estimatedMinutes, 1)) minutes" 
            }
            Write-Host "  Estimated Completion: " -NoNewline; Write-Host $estimatedTime -ForegroundColor Magenta
        }
    }
    
    # Recent Captions
    Write-Host "`n📝 Recent Generated Captions:" -ForegroundColor Yellow
    $recentCaptions = Get-RecentCaptions -Count $ShowSamples
    if ($recentCaptions -and $recentCaptions.Count -gt 0) {
        foreach ($caption in $recentCaptions) {
            $fileName = if ($caption.file_path) { [System.IO.Path]::GetFileName($caption.file_path) } else { "unknown" }
            $timeAgo = if ($caption.created_at) {
                try {
                    $created = [DateTime]::Parse($caption.created_at)
                    $diff = (Get-Date) - $created
                    if ($diff.TotalMinutes -lt 1) { 
                        "$([math]::Round($diff.TotalSeconds))s ago" 
                    } elseif ($diff.TotalHours -lt 1) { 
                        "$([math]::Round($diff.TotalMinutes))m ago" 
                    } else { 
                        "$([math]::Round($diff.TotalHours, 1))h ago" 
                    }
                } catch {
                    "recently"
                }
            } else { 
                "recently" 
            }
            
            Write-Host "  📷 $fileName" -ForegroundColor Gray
            Write-Host "     " -NoNewline; Write-Host "`"$($caption.text)`"" -ForegroundColor White
            Write-Host "     Model: $($caption.model) | $timeAgo" -ForegroundColor Gray
        }
    } else {
        Write-Host "  No recent captions found" -ForegroundColor Gray
    }
    
    # API Status
    Write-Host "`n🌐 Backend API Status:" -ForegroundColor Yellow
    $apiStatus = Get-TaskQueueStatus
    if ($apiStatus) {
        Write-Host "  ✅ API Online - Backend responding" -ForegroundColor Green
    } else {
        Write-Host "  ❌ API Offline - Backend not responding" -ForegroundColor Red
    }
    
    Write-Host "`n" -NoNewline
    if ($Continuous) {
        Write-Host "🔄 Refreshing in $RefreshInterval seconds... (Press Ctrl+C to stop)" -ForegroundColor Gray
    } else {
        Write-Host "💡 Use -Continuous to auto-refresh every $RefreshInterval seconds" -ForegroundColor Gray
    }
}

# Main execution
if ($Continuous) {
    try {
        while ($true) {
            Show-ProgressDashboard
            Start-Sleep -Seconds $RefreshInterval
        }
    } catch {
        Write-Host "`n👋 Monitoring stopped." -ForegroundColor Yellow
    }
} else {
    Show-ProgressDashboard
}
