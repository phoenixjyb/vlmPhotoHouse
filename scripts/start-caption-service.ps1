[CmdletBinding()]
param(
    [string]$CaptionDir = '',
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$ModelPath = '',
    [string]$Provider = 'qwen3-vl',
    [string]$GpuName = 'RTX 3090',
    [ValidateRange(1, 65535)]
    [int]$Port = 8102,
    [ValidateRange(30, 1800)]
    [int]$ReadyTimeoutSec = 900,
    [ValidateRange(1, 30)]
    [int]$HealthTimeoutSec = 5,
    [ValidateRange(1, 365)]
    [int]$LogRetention = 14,
    [ValidateRange(64, 1024)]
    [int]$MaxNewTokens = 512,
    [ValidateRange(448, 4096)]
    [int]$MaxImageEdge = 1536,
    [string]$Prompt = '',
    [switch]$Detached,
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stackRoot = Split-Path -Parent $repoRoot
$promptPath = Join-Path $repoRoot 'config\detailed-caption-prompt.txt'
if ([string]::IsNullOrWhiteSpace($Prompt)) {
    if (-not (Test-Path -LiteralPath $promptPath -PathType Leaf)) {
        throw "Detailed caption prompt not found: $promptPath"
    }
    $Prompt = (Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8).Trim()
}
if ([string]::IsNullOrWhiteSpace($CaptionDir)) {
    $CaptionDir = Join-Path $stackRoot 'vlmCaptionModels'
}
if ([string]::IsNullOrWhiteSpace($ModelPath)) {
    $ModelPath = Join-Path $CaptionDir 'models\qwen3-vl-8b-instruct'
}

$pythonExe = Join-Path $CaptionDir '.venv\Scripts\python.exe'
$serverScript = Join-Path $CaptionDir 'caption_server.py'
$logRoot = Join-Path $DataRoot 'logs\photohouse'
$hfHome = Join-Path $DataRoot 'hf_home'
$curlAvailable = [bool](Get-Command curl.exe -ErrorAction SilentlyContinue)

function Resolve-NvidiaGpuIndex {
    param([string]$NameHint)

    $rows = @(& nvidia-smi --query-gpu=index,name --format=csv,noheader,nounits 2>$null)
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    foreach ($row in $rows) {
        $parts = $row -split ',', 2
        if ($parts.Count -eq 2 -and $parts[1].Trim() -match [Regex]::Escape($NameHint)) {
            return $parts[0].Trim()
        }
    }
    return $null
}

function Get-CaptionHealth {
    if (-not $curlAvailable) {
        return $null
    }
    try {
        $body = & curl.exe --silent --show-error --noproxy '*' --max-time $HealthTimeoutSec "http://127.0.0.1:$Port/health" 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($body -join ''))) {
            return $null
        }
        return (($body -join "`n") | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Test-CaptionReady {
    param([object]$Health)

    return (
        $null -ne $Health -and
        [string]$Health.status -eq 'healthy' -and
        [string]$Health.active_provider -eq $Provider -and
        [bool]$Health.model_cache_ready -and
        [string]$Health.gpu_device -match [Regex]::Escape($GpuName)
    )
}

$gpuIndex = Resolve-NvidiaGpuIndex -NameHint $GpuName
$missing = @()
foreach ($check in @(
    [pscustomobject]@{ Name = 'Caption repository'; Path = $CaptionDir },
    [pscustomobject]@{ Name = 'Caption Python'; Path = $pythonExe },
    [pscustomobject]@{ Name = 'Caption server'; Path = $serverScript },
    [pscustomobject]@{ Name = 'Qwen3-VL model'; Path = $ModelPath }
)) {
    if (-not (Test-Path -LiteralPath $check.Path)) {
        $missing += "$($check.Name): $($check.Path)"
    }
}

if ($PreflightOnly) {
    Write-Host 'Qwen3-VL caption-service preflight (read-only)' -ForegroundColor Cyan
    Write-Host "  Caption repo:   $CaptionDir" -ForegroundColor Gray
    Write-Host "  Python:         $pythonExe" -ForegroundColor Gray
    Write-Host "  Model:          $ModelPath" -ForegroundColor Gray
    Write-Host "  Endpoint:       http://127.0.0.1:$Port/health" -ForegroundColor Gray
    Write-Host "  GPU selector:   $GpuName -> physical index $gpuIndex" -ForegroundColor Gray
    Write-Host '  Quantization:   4-bit NF4' -ForegroundColor Gray
    Write-Host "  Caption budget: $MaxNewTokens tokens, image edge $MaxImageEdge" -ForegroundColor Gray
    if ($missing.Count -gt 0) {
        throw "Caption-service preflight failed: $($missing -join '; ')"
    }
    if (-not $curlAvailable) {
        throw 'Caption-service preflight failed: curl.exe is required.'
    }
    if ($null -eq $gpuIndex) {
        throw "Caption-service preflight failed: GPU matching '$GpuName' was not found."
    }
    Write-Host 'Caption-service preflight passed. No files or processes were changed.' -ForegroundColor Green
    return
}

if ($missing.Count -gt 0) {
    throw "Caption-service prerequisites are missing: $($missing -join '; ')"
}
if (-not $curlAvailable) {
    throw 'curl.exe is required for proxy-bypassed localhost health checks.'
}
if ($null -eq $gpuIndex) {
    throw "GPU matching '$GpuName' was not found."
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
New-Item -ItemType Directory -Path $hfHome -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$controlLog = Join-Path $logRoot "caption-control-$stamp.log"
$stdoutLog = Join-Path $logRoot "caption-stdout-$stamp.log"
$stderrLog = Join-Path $logRoot "caption-stderr-$stamp.log"
$pidPath = Join-Path $logRoot 'caption.pid'

Get-ChildItem -LiteralPath $logRoot -Filter 'caption-*.log' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip ($LogRetention * 3) |
    Remove-Item -Force -ErrorAction SilentlyContinue

$env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'
$env:CUDA_VISIBLE_DEVICES = [string]$gpuIndex
$env:CAPTION_HTTP_PROVIDER = $Provider
$env:CAPTION_HTTP_MODEL = $ModelPath
$env:QWEN3VL_MODEL_NAME = $ModelPath
$env:QWEN2VL_MODEL_NAME = $ModelPath
$env:QWEN2VL_LOAD_IN_4BIT = 'true'
$env:QWEN2VL_4BIT_QUANT_TYPE = 'nf4'
$env:QWEN2VL_MAX_NEW_TOKENS = [string]$MaxNewTokens
$env:QWEN2VL_MAX_IMAGE_EDGE = [string]$MaxImageEdge
$env:QWEN2VL_PROMPT = $Prompt
$env:CAPTION_SERVER_MAX_CONCURRENCY = '1'
$env:HF_HOME = $hfHome
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:PYTHONUTF8 = '1'

$mutex = [System.Threading.Mutex]::new($false, "Global\VLMPhotoHouseCaption-$Port")
$mutexAcquired = $false
$process = $null
$leaveRunning = $false

try {
    $existingHealth = Get-CaptionHealth
    if (Test-CaptionReady -Health $existingHealth) {
        Write-Host "Qwen3-VL caption service is already ready on 127.0.0.1:$Port." -ForegroundColor Green
        return
    }

    try {
        $mutexAcquired = $mutex.WaitOne([TimeSpan]::FromSeconds(2))
    } catch [System.Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }
    if (-not $mutexAcquired) {
        throw "Another caption-service startup operation holds the port-$Port mutex."
    }

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $owners = @($listener | Select-Object -ExpandProperty OwningProcess -Unique)
        throw "Port $Port is occupied by PID(s) $($owners -join ', '), but the Qwen3-VL health identity check failed."
    }

    Add-Content -LiteralPath $controlLog -Value "$(Get-Date -Format s) Starting Qwen3-VL on physical GPU $gpuIndex ($GpuName)." -Encoding UTF8
    $process = Start-Process `
        -FilePath $pythonExe `
        -WorkingDirectory $CaptionDir `
        -ArgumentList @('caption_server.py', '--host', '127.0.0.1', '--port', $Port.ToString(), '--provider', $Provider, '--model', $ModelPath) `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
    Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ASCII

    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
    $readyHealth = $null
    while ((Get-Date) -lt $deadline) {
        $process.Refresh()
        if ($process.HasExited) {
            throw "Caption service exited before readiness with code $($process.ExitCode). See $stderrLog"
        }
        $readyHealth = Get-CaptionHealth
        if (Test-CaptionReady -Health $readyHealth) {
            break
        }
        Start-Sleep -Seconds 3
    }
    if (-not (Test-CaptionReady -Health $readyHealth)) {
        throw "Caption service did not become Qwen3-VL/RTX-3090 ready within $ReadyTimeoutSec seconds. See $stderrLog"
    }

    Add-Content -LiteralPath $controlLog -Value "$(Get-Date -Format s) Ready PID $($process.Id); provider=$($readyHealth.active_provider); device=$($readyHealth.gpu_device)." -Encoding UTF8
    Write-Host "Qwen3-VL caption service ready with PID $($process.Id) on $($readyHealth.gpu_device)." -ForegroundColor Green
    if ($Detached) {
        $leaveRunning = $true
        return
    }

    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Caption service exited with code $($process.ExitCode)."
    }
} finally {
    if ($null -ne $process -and -not $process.HasExited -and -not $leaveRunning) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.WaitForExit(10000) | Out-Null
    }
    if ($null -ne $process -and $process.HasExited -and (Test-Path -LiteralPath $pidPath)) {
        $recordedPid = (Get-Content -LiteralPath $pidPath -Raw).Trim()
        if ($recordedPid -eq [string]$process.Id) {
            Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        }
    }
    if ($mutexAcquired) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
