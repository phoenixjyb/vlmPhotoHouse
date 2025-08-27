#Requires -Version 7
<#
.SYNOPSIS
    Launches AI processing services in a multi-pane Windows Terminal layout

.DESCRIPTION
    Starts AI automation components in separate PowerShell panes:
    - VLM Photo Engine Backend (API server)
    - AI Orchestrator (master pipeline)
    - Caption Processor (specialized AI captions)
    - Drive E Backend Integrator (ingestion with state tracking)

.PARAMETER ApiPort
    Port for the VLM Photo Engine API server (default: 8000)

.PARAMETER NoCleanup
    Skip automatic cleanup of existing instances

.PARAMETER UseWindowsTerminal
    Use Windows Terminal for pane management (default: true)

.PARAMETER SingleMode
    Launch only the AI Orchestrator (simplified startup)

.EXAMPLE
    .\start-ai-multiproc.ps1
    Launches all AI services in 2x2 grid layout

.EXAMPLE
    .\start-ai-multiproc.ps1 -SingleMode
    Launches only the AI Orchestrator for complete pipeline processing

.EXAMPLE
    .\start-ai-multiproc.ps1 -ApiPort 8001 -NoCleanup
    Launches with custom API port and skips cleanup
#>

[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [switch]$NoCleanup,
    [bool]$UseWindowsTerminal = $true,
    [switch]$SingleMode
)

# Environment and Path Resolution
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $workspaceRoot "backend"

# Validate workspace structure
if (!(Test-Path $backendRoot -PathType Container)) {
    Write-Error "Backend directory not found: $backendRoot"
}

# AI Script paths
$aiOrchestratorScript = Join-Path $workspaceRoot "ai_orchestrator.py"
$captionProcessorScript = Join-Path $workspaceRoot "caption_processor.py"
$driveEIntegratorScript = Join-Path $workspaceRoot "drive_e_backend_integrator.py"

# Validate AI scripts exist
$requiredScripts = @($aiOrchestratorScript, $captionProcessorScript, $driveEIntegratorScript)
foreach ($script in $requiredScripts) {
    if (!(Test-Path $script -PathType Leaf)) {
        Write-Error "Required AI script not found: $script"
    }
}

Write-Host "🔍 AI Processing Environment Check:" -ForegroundColor Cyan
Write-Host "  Workspace Root: $workspaceRoot" -ForegroundColor Gray
Write-Host "  Backend Root: $backendRoot" -ForegroundColor Gray
Write-Host "  AI Scripts: ✅ All found" -ForegroundColor Green

# Python executable resolution (from original start-dev-multiproc.ps1 pattern)
function Get-PythonExecutable {
    [CmdletBinding()]
    param([string]$SearchRoot = $backendRoot)
    
    $candidates = @(
        (Join-Path $SearchRoot ".venv\Scripts\python.exe"),
        (Join-Path $SearchRoot ".venv\Scripts\python3.exe"),
        (Join-Path $workspaceRoot ".venv\Scripts\python.exe"),
        "python",
        "python3"
    )
    
    foreach ($candidate in $candidates) {
        if ($candidate -match '^[a-zA-Z]') {
            # Relative or command name
            try {
                $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
                if ($resolved) {
                    Write-Host "  Python: $($resolved.Source) (system)" -ForegroundColor Gray
                    return $resolved.Source
                }
            } catch {}
        } else {
            # Absolute path
            if (Test-Path $candidate -PathType Leaf) {
                Write-Host "  Python: $candidate (venv)" -ForegroundColor Green
                return $candidate
            }
        }
    }
    
    Write-Error "No suitable Python executable found. Tried: $($candidates -join ', ')"
}

$pyExe = Get-PythonExecutable

# Cleanup existing instances (following original pattern)
if (!$NoCleanup) {
    Write-Host "🧹 Cleaning up existing AI service instances..." -ForegroundColor Yellow
    
    # Kill uvicorn processes on our port
    $uvicornProcs = Get-Process uvicorn -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*--port $ApiPort*" -or $_.CommandLine -like "*app.main:app*"
    }
    if ($uvicornProcs) {
        $uvicornProcs | Stop-Process -Force
        Write-Host "  Stopped uvicorn processes on port $ApiPort" -ForegroundColor Gray
    }
    
    # Kill AI script processes
    $aiProcs = Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*ai_orchestrator.py*" -or 
        $_.CommandLine -like "*caption_processor.py*" -or
        $_.CommandLine -like "*drive_e_backend_integrator.py*"
    }
    if ($aiProcs) {
        $aiProcs | Stop-Process -Force
        Write-Host "  Stopped AI processing scripts" -ForegroundColor Gray
    }
    
    # Clean temp pane files
    Get-ChildItem $env:TEMP -Filter "ai-*-pane-*.ps1" -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host "  Cleaned temporary pane files" -ForegroundColor Gray
}

# Service startup functions (following original pattern)
function Start-ApiTab {
    $content = @(
        "Set-Location -LiteralPath `"$backendRoot`"",
        "Write-Host 'Starting VLM Photo Engine Backend API...' -ForegroundColor Cyan",
        "Write-Host 'API will be available at: http://127.0.0.1:$ApiPort' -ForegroundColor Yellow",
        "& `"$pyExe`" -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort --reload"
    ) -join "`n"
    $path = Join-Path $env:TEMP "ai-api-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $backendRoot; Title = "VLM API ($ApiPort)" }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $backendRoot
        return $null
    }
}

function Start-OrchestratorTab {
    $content = @(
        "Set-Location -LiteralPath `"$workspaceRoot`"",
        "Write-Host 'AI Orchestrator - Master Pipeline Controller' -ForegroundColor Green",
        "Write-Host 'Commands:' -ForegroundColor Yellow",
        "Write-Host '  Full Pipeline: & `"$pyExe`" ai_orchestrator.py --mode=continuous' -ForegroundColor Gray",
        "Write-Host '  Drive E Only: & `"$pyExe`" ai_orchestrator.py --phase=drive_e' -ForegroundColor Gray",
        "Write-Host '  Captions Only: & `"$pyExe`" ai_orchestrator.py --phase=captions' -ForegroundColor Gray",
        "Write-Host '  Status Check: & `"$pyExe`" ai_orchestrator.py --mode=status' -ForegroundColor Gray",
        "Write-Host '',",
        "Write-Host 'Ready for commands. Starting with status check...' -ForegroundColor Cyan",
        "& `"$pyExe`" ai_orchestrator.py --mode=status"
    ) -join "`n"
    $path = Join-Path $env:TEMP "ai-orchestrator-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $workspaceRoot; Title = "AI Orchestrator" }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $workspaceRoot
        return $null
    }
}

function Start-CaptionTab {
    $content = @(
        "Set-Location -LiteralPath `"$workspaceRoot`"",
        "Write-Host 'Caption Processor - Specialized AI Caption Generation' -ForegroundColor Magenta",
        "Write-Host 'Commands:' -ForegroundColor Yellow",
        "Write-Host '  Process All: & `"$pyExe`" caption_processor.py --mode=continuous' -ForegroundColor Gray",
        "Write-Host '  Single Batch: & `"$pyExe`" caption_processor.py --batch-size=50' -ForegroundColor Gray",
        "Write-Host '  Status Check: & `"$pyExe`" caption_processor.py --mode=status' -ForegroundColor Gray",
        "Write-Host '',",
        "Write-Host 'Ready for caption processing commands...' -ForegroundColor Cyan"
    ) -join "`n"
    $path = Join-Path $env:TEMP "ai-caption-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $workspaceRoot; Title = "Caption Processor" }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $workspaceRoot
        return $null
    }
}

function Start-DriveETab {
    $content = @(
        "Set-Location -LiteralPath `"$workspaceRoot`"",
        "Write-Host 'Drive E Backend Integrator - Ingestion with State Tracking' -ForegroundColor Blue",
        "Write-Host 'Commands:' -ForegroundColor Yellow",
        "Write-Host '  Full Integration: & `"$pyExe`" drive_e_backend_integrator.py --mode=continuous' -ForegroundColor Gray",
        "Write-Host '  Single Directory: & `"$pyExe`" drive_e_backend_integrator.py --batch-size=100' -ForegroundColor Gray",
        "Write-Host '  Status Check: & `"$pyExe`" drive_e_backend_integrator.py --mode=status' -ForegroundColor Gray",
        "Write-Host '',",
        "Write-Host 'Ready for Drive E integration commands...' -ForegroundColor Cyan"
    ) -join "`n"
    $path = Join-Path $env:TEMP "ai-drivee-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    if ($UseWindowsTerminal) {
        return @{ File = $path; Dir = $workspaceRoot; Title = "Drive E Integrator" }
    } else {
        Start-Process pwsh -ArgumentList @('-NoExit','-File', $path) -WorkingDirectory $workspaceRoot
        return $null
    }
}

# Single mode startup
if ($SingleMode) {
    Write-Host "🎯 Single Mode: Launching AI Orchestrator only..." -ForegroundColor Green
    $orchSpec = Start-OrchestratorTab
    
    if ($UseWindowsTerminal) {
        $wtArgs = @(
            'new-tab', '--title', "`"AI Orchestrator - Master Pipeline`"", 
            '-d', "`"$($orchSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($orchSpec.File)`""
        )
        Start-Process wt -ArgumentList $wtArgs
    }
    
    Write-Host "✅ AI Orchestrator launched - Use this for complete pipeline processing" -ForegroundColor Green
    Write-Host "💡 Commands available in the new terminal tab" -ForegroundColor Yellow
    return
}

# Full multi-service startup
Write-Host "🚀 Launching AI Processing Services..." -ForegroundColor Green

$apiSpec = Start-ApiTab
$orchSpec = Start-OrchestratorTab  
$captionSpec = Start-CaptionTab
$driveESpec = Start-DriveETab

if ($UseWindowsTerminal) {
    # Build a clean 2x2 grid layout for AI processing services
    # Top Left: VLM API | Top Right: AI Orchestrator
    # Bottom Left: Caption Processor | Bottom Right: Drive E Integrator
    $wtArgs = @(
        'new-tab', '--title', "`"$($apiSpec.Title)`"", '-d', "`"$($apiSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($apiSpec.File)`"",
        ';', 'split-pane', '-H', '--title', "`"$($orchSpec.Title)`"", '-d', "`"$($orchSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($orchSpec.File)`"",
        ';', 'move-focus', 'left',
        ';', 'split-pane', '-V', '--title', "`"$($captionSpec.Title)`"", '-d', "`"$($captionSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($captionSpec.File)`"",
        ';', 'move-focus', 'up', ';', 'move-focus', 'right',
        ';', 'split-pane', '-V', '--title', "`"$($driveESpec.Title)`"", '-d', "`"$($driveESpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($driveESpec.File)`""
    )
    Write-Host "Executing Windows Terminal with AI services layout..." -ForegroundColor Gray
    Start-Process wt -ArgumentList $wtArgs
}

Write-Host ""
Write-Host "🎯 Launched AI Processing Services 2x2 Grid:" -ForegroundColor Green
Write-Host "  Top Left: VLM Photo Engine API (port $ApiPort)" -ForegroundColor Cyan  
Write-Host "  Top Right: AI Orchestrator (master pipeline)" -ForegroundColor Cyan
Write-Host "  Bottom Left: Caption Processor (specialized AI)" -ForegroundColor Cyan
Write-Host "  Bottom Right: Drive E Integrator (state tracking)" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ All AI automation services ready for processing" -ForegroundColor Green
Write-Host "🧹 Previous instances automatically cleaned up" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 Usage Tips:" -ForegroundColor Yellow
Write-Host "   • Start with AI Orchestrator status check" -ForegroundColor Gray
Write-Host "   • Use continuous mode for full automation" -ForegroundColor Gray
Write-Host "   • Individual services can run independently" -ForegroundColor Gray
Write-Host "   • API server must be running for caption processing" -ForegroundColor Gray
Write-Host ""
Write-Host "🔧 Quick Commands:" -ForegroundColor Yellow
Write-Host "   Full Pipeline: In AI Orchestrator tab, run the continuous mode command" -ForegroundColor Gray
Write-Host "   Test Setup: Use --mode=status in any service tab" -ForegroundColor Gray
