[CmdletBinding()]
param(
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [string]$DatabasePath = '',
    [string]$LvfaceDir = '',
    [string]$CaptionDir = '',
    [string]$CaptionProvider = 'http',
    [string]$CaptionServiceUrl = 'http://127.0.0.1:8102',
    [string]$LvfaceModelName = 'LVFace-B_Glint360K.onnx',
    [string]$EmbedDevice = 'cuda:0',
    [string]$CaptionDevice = 'cuda:0',
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8002,
    [ValidateRange(5, 600)]
    [int]$ReadyTimeoutSec = 120,
    [ValidateRange(1, 30)]
    [int]$HealthTimeoutSec = 5,
    [ValidateRange(1, 365)]
    [int]$LogRetention = 14,
    [switch]$DisableInlineWorker,
    [switch]$NoAutoMigrate,
    [switch]$Detached,
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'photohouse-runtime-common.ps1')

$context = New-PhotoHouseRuntimeContext `
    -RepoRoot $repoRoot `
    -DataRoot $DataRoot `
    -OriginalsPath $OriginalsPath `
    -DatabasePath $DatabasePath `
    -LvfaceDir $LvfaceDir `
    -CaptionDir $CaptionDir

$missing = @(Get-PhotoHouseMissingPaths -Context $context -RequireModels)
$curlAvailable = [bool](Get-Command curl.exe -ErrorAction SilentlyContinue)
$captionPort = ([Uri]$CaptionServiceUrl).Port
$captionHealth = if ($CaptionProvider -eq 'http') {
    Get-PhotoHouseCaptionHealth -Port $captionPort -TimeoutSec $HealthTimeoutSec
} else {
    $null
}

if ($PreflightOnly) {
    Show-PhotoHouseRuntimeContext -Context $context -Operation 'API startup'
    Write-Host "  API endpoint:   http://127.0.0.1:$ApiPort/health" -ForegroundColor Gray
    Write-Host "  Caption path:   $CaptionProvider -> $CaptionServiceUrl" -ForegroundColor Gray
    Write-Host "  Inline worker:  $(-not [bool]$DisableInlineWorker)" -ForegroundColor Gray
    Write-Host "  Auto migrate:   $(-not [bool]$NoAutoMigrate)" -ForegroundColor Gray
    Write-Host "  Run mode:       $(if ($Detached) { 'detached' } else { 'foreground-owned' })" -ForegroundColor Gray
    Write-Host "  curl.exe:       $curlAvailable" -ForegroundColor Gray
    if ($missing.Count -gt 0) {
        foreach ($item in $missing) {
            Write-Host "  MISSING: $item" -ForegroundColor Red
        }
        throw 'API startup preflight failed.'
    }
    if (-not $curlAvailable) {
        throw 'API startup preflight failed: curl.exe is required.'
    }
    if ($CaptionProvider -eq 'http' -and (
        $null -eq $captionHealth -or
        [string]$captionHealth.status -ne 'healthy' -or
        [string]$captionHealth.active_provider -ne 'qwen3-vl' -or
        -not [bool]$captionHealth.model_cache_ready
    )) {
        throw 'API startup preflight failed: the Qwen3-VL caption service is not ready.'
    }
    Write-Host 'API startup preflight passed. No files or processes were changed.' -ForegroundColor Green
    return
}

if ($missing.Count -gt 0) {
    throw "API startup prerequisites are missing: $($missing -join '; ')"
}
if (-not $curlAvailable) {
    throw 'curl.exe is required for proxy-bypassed localhost health checks.'
}
if ($CaptionProvider -eq 'http' -and (
    $null -eq $captionHealth -or
    [string]$captionHealth.status -ne 'healthy' -or
    [string]$captionHealth.active_provider -ne 'qwen3-vl' -or
    -not [bool]$captionHealth.model_cache_ready
)) {
    throw 'The Qwen3-VL caption service must be healthy and model-ready before starting PhotoHouse.'
}

Initialize-PhotoHouseRuntimeEnvironment `
    -Context $context `
    -CaptionProvider $CaptionProvider `
    -CaptionServiceUrl $CaptionServiceUrl `
    -LvfaceModelName $LvfaceModelName `
    -EmbedDevice $EmbedDevice `
    -CaptionDevice $CaptionDevice `
    -EnableInlineWorker (-not [bool]$DisableInlineWorker) `
    -AutoMigrate (-not [bool]$NoAutoMigrate)

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$controlLog = Join-Path $context.LogRoot "api-control-$stamp.log"
$stdoutLog = Join-Path $context.LogRoot "api-stdout-$stamp.log"
$stderrLog = Join-Path $context.LogRoot "api-stderr-$stamp.log"
$pidPath = Join-Path $context.LogRoot 'api.pid'
Remove-OldPhotoHouseLogs -LogRoot $context.LogRoot -Prefix 'api-control-' -Keep $LogRetention
Remove-OldPhotoHouseLogs -LogRoot $context.LogRoot -Prefix 'api-stdout-' -Keep $LogRetention
Remove-OldPhotoHouseLogs -LogRoot $context.LogRoot -Prefix 'api-stderr-' -Keep $LogRetention

$mutexName = "Global\VLMPhotoHouseApi-$ApiPort"
$mutex = [System.Threading.Mutex]::new($false, $mutexName)
$mutexAcquired = $false
$process = $null
$leaveRunning = $false

function Test-PhotoHouseReadyHealth {
    param([object]$Health)

    return (
        $null -ne $Health -and
        [bool]$Health.ok -and
        [bool]$Health.db_ok -and
        [bool]$Health.worker_enabled -eq (-not [bool]$DisableInlineWorker)
    )
}

try {
    $existingHealth = Get-PhotoHouseHealth -Port $ApiPort -TimeoutSec $HealthTimeoutSec
    if (Test-PhotoHouseReadyHealth -Health $existingHealth) {
        Write-PhotoHouseLog -Path $controlLog -Message "PhotoHouse API already healthy on 127.0.0.1:$ApiPort; startup skipped."
        return
    }

    try {
        $mutexAcquired = $mutex.WaitOne([TimeSpan]::FromSeconds(2))
    } catch [System.Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }
    if (-not $mutexAcquired) {
        throw "Another PhotoHouse API startup operation holds $mutexName."
    }

    $existingHealth = Get-PhotoHouseHealth -Port $ApiPort -TimeoutSec $HealthTimeoutSec
    if ($null -ne $existingHealth) {
        if (-not [bool]$existingHealth.ok -or -not [bool]$existingHealth.db_ok) {
            throw "PhotoHouse responded on port $ApiPort but reported an unhealthy database."
        }
        if ([bool]$existingHealth.worker_enabled -ne (-not [bool]$DisableInlineWorker)) {
            throw "PhotoHouse responded on port $ApiPort with a different inline-worker mode."
        }
        Write-PhotoHouseLog -Path $controlLog -Message "PhotoHouse API already healthy on 127.0.0.1:$ApiPort; startup skipped."
        return
    }

    $listener = Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $owners = @($listener | Select-Object -ExpandProperty OwningProcess -Unique)
        throw "Port $ApiPort is occupied by PID(s) $($owners -join ', '), but the PhotoHouse health identity check failed."
    }

    $arguments = @(
        '-m', 'uvicorn', 'app.main:app',
        '--host', '127.0.0.1',
        '--port', $ApiPort.ToString(),
        '--log-level', 'info'
    )
    Write-PhotoHouseLog -Path $controlLog -Message "Starting PhotoHouse API on 127.0.0.1:$ApiPort; worker_enabled=$(-not [bool]$DisableInlineWorker); auto_migrate=$(-not [bool]$NoAutoMigrate)."
    $process = Start-Process `
        -FilePath $context.PythonExe `
        -WorkingDirectory $context.BackendRoot `
        -ArgumentList $arguments `
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
            throw "PhotoHouse API exited before becoming ready with code $($process.ExitCode). See $stderrLog"
        }
        $readyHealth = Get-PhotoHouseHealth -Port $ApiPort -TimeoutSec $HealthTimeoutSec
        if (Test-PhotoHouseReadyHealth -Health $readyHealth) {
            break
        }
        Start-Sleep -Seconds 2
    }

    if (-not (Test-PhotoHouseReadyHealth -Health $readyHealth)) {
        throw "PhotoHouse API did not become healthy within $ReadyTimeoutSec seconds. See $stderrLog"
    }

    Write-PhotoHouseLog -Path $controlLog -Message "PhotoHouse API ready with PID $($process.Id); worker_enabled=$($readyHealth.worker_enabled)."
    if ($Detached) {
        $leaveRunning = $true
        Write-PhotoHouseLog -Path $controlLog -Message 'Detached mode selected; launcher is returning while the API continues.'
        return
    }

    Write-PhotoHouseLog -Path $controlLog -Message 'Foreground-owned mode selected; waiting for the API process to exit.'
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    Write-PhotoHouseLog -Path $controlLog -Message "PhotoHouse API process exited with code $exitCode."
    if ($exitCode -ne 0) {
        throw "PhotoHouse API process exited with code $exitCode."
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
