[CmdletBinding()]
param(
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [ValidateRange(30, 600)]
    [int]$CaptionTimeoutSec = 180
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logRoot = Join-Path $DataRoot 'logs\photohouse'
$databasePath = Join-Path $DataRoot 'databases\metadata.sqlite'
$apiPidPath = Join-Path $logRoot 'api.pid'
$captionPidPath = Join-Path $logRoot 'caption.pid'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$receiptPath = Join-Path $logRoot "runtime-canary-receipt-$stamp.json"

function Get-ListeningProcessId {
    param([int]$Port)

    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Stop-CanaryProcess {
    param(
        [AllowNull()]
        [Nullable[int]]$ExpectedProcessId,
        [int]$Port,
        [string]$PidPath
    )

    if ($null -eq $ExpectedProcessId) { return }
    $listenerPid = Get-ListeningProcessId -Port $Port
    if ($null -ne $listenerPid -and $listenerPid -ne $ExpectedProcessId) {
        throw "Refusing cleanup: port $Port is now owned by unexpected PID $listenerPid."
    }
    $process = Get-Process -Id $ExpectedProcessId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $ExpectedProcessId -Force -ErrorAction Stop
        try {
            Wait-Process -Id $ExpectedProcessId -Timeout 15 -ErrorAction SilentlyContinue
        } catch {}
    }
    if (Test-Path -LiteralPath $PidPath) {
        $recorded = (Get-Content -LiteralPath $PidPath -Raw).Trim()
        if ($recorded -eq [string]$ExpectedProcessId) {
            Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        }
    }
}

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
    throw "Database not found: $databasePath"
}
if ((Get-ListeningProcessId -Port 8002) -or (Get-ListeningProcessId -Port 8102)) {
    throw 'Canary ports 8002 and 8102 must both be closed initially.'
}

$databaseBefore = [ordered]@{
    bytes = (Get-Item -LiteralPath $databasePath).Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $databasePath).Hash
    wal_present = Test-Path -LiteralPath ($databasePath + '-wal')
    wal_bytes = if (Test-Path -LiteralPath ($databasePath + '-wal')) {
        (Get-Item -LiteralPath ($databasePath + '-wal')).Length
    } else { 0 }
    shm_present = Test-Path -LiteralPath ($databasePath + '-shm')
}
$apiPid = $null
$captionPid = $null
$apiHealth = $null
$captionHealth = $null
$captionSummary = $null
$captionReceipt = $null
$uiCode = $null
$operationError = $null

try {
    Set-Location $repoRoot
    & '.\scripts\start-caption-service.ps1' -DataRoot $DataRoot -Detached
    if ($LASTEXITCODE -ne 0) { throw 'Caption launcher failed.' }
    $captionPid = Get-ListeningProcessId -Port 8102
    if ($null -eq $captionPid) { throw 'Caption service is not listening after readiness.' }

    & '.\scripts\start-photohouse-api.ps1' `
        -DataRoot $DataRoot `
        -OriginalsPath $OriginalsPath `
        -DisableInlineWorker `
        -NoAutoMigrate `
        -Detached
    if ($LASTEXITCODE -ne 0) { throw 'API launcher failed.' }
    $apiPid = Get-ListeningProcessId -Port 8002
    if ($null -eq $apiPid) { throw 'PhotoHouse API is not listening after readiness.' }

    $apiHealth = (& curl.exe --silent --show-error --noproxy '*' --max-time 10 `
        'http://127.0.0.1:8002/health' | ConvertFrom-Json)
    $captionHealth = (& curl.exe --silent --show-error --noproxy '*' --max-time 10 `
        'http://127.0.0.1:8002/health/caption' | ConvertFrom-Json)
    $uiCode = & curl.exe --silent --show-error --noproxy '*' --max-time 10 `
        --output NUL --write-out '%{http_code}' 'http://127.0.0.1:8002/ui'
    if ($LASTEXITCODE -ne 0) { throw 'UI request failed.' }
    if (
        -not [bool]$apiHealth.ok -or
        -not [bool]$apiHealth.db_ok -or
        [bool]$apiHealth.worker_enabled
    ) {
        throw 'API health identity or no-worker invariant failed.'
    }
    if ([string]$uiCode -ne '200') { throw "UI returned HTTP $uiCode." }

    $beforeReceipt = Get-ChildItem -LiteralPath $logRoot `
        -Filter 'qwen3-vl-shadow-receipt-*.json' -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    $beforeName = if ($beforeReceipt) { $beforeReceipt.Name } else { '' }
    & '.\scripts\run-caption-shadow-canary.ps1' `
        -InputRoot $OriginalsPath `
        -OutputRoot $logRoot `
        -SampleSize 1 `
        -TimeoutSec $CaptionTimeoutSec | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Caption request canary failed.' }

    $captionReceipt = Get-ChildItem -LiteralPath $logRoot `
        -Filter 'qwen3-vl-shadow-receipt-*.json' -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $captionReceipt -or $captionReceipt.Name -eq $beforeName) {
        throw 'A new caption receipt was not created.'
    }
    $captionResult = Get-Content -LiteralPath $captionReceipt.FullName `
        -Raw -Encoding UTF8 | ConvertFrom-Json
    $captionSummary = $captionResult.summary
    if (
        [int]$captionSummary.success_count -ne 1 -or
        [int]$captionSummary.failure_count -ne 0
    ) {
        throw 'Caption receipt did not contain exactly one successful result.'
    }
} catch {
    $operationError = $_
} finally {
    Stop-CanaryProcess -ExpectedProcessId $apiPid -Port 8002 -PidPath $apiPidPath
    Stop-CanaryProcess -ExpectedProcessId $captionPid -Port 8102 -PidPath $captionPidPath
    Start-Sleep -Seconds 5
}

$databaseAfter = [ordered]@{
    bytes = (Get-Item -LiteralPath $databasePath).Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $databasePath).Hash
    wal_present = Test-Path -LiteralPath ($databasePath + '-wal')
    wal_bytes = if (Test-Path -LiteralPath ($databasePath + '-wal')) {
        (Get-Item -LiteralPath ($databasePath + '-wal')).Length
    } else { 0 }
    shm_present = Test-Path -LiteralPath ($databasePath + '-shm')
}
$apiStillListening = $null -ne (Get-ListeningProcessId -Port 8002)
$captionStillListening = $null -ne (Get-ListeningProcessId -Port 8102)
$databaseUnchanged = (
    $databaseBefore.bytes -eq $databaseAfter.bytes -and
    $databaseBefore.sha256 -eq $databaseAfter.sha256 -and
    $databaseAfter.wal_bytes -eq 0
)
$captionReceiptHash = if ($captionReceipt) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $captionReceipt.FullName).Hash
} else {
    $null
}

$receipt = [ordered]@{
    schema = 'photohouse.runtime_canary.v1'
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    success = $null -eq $operationError
    error = if ($operationError) { $operationError.Exception.Message } else { $null }
    api_health = $apiHealth
    caption_health_via_api = $captionHealth
    ui_http_code = [string]$uiCode
    caption_receipt = if ($captionReceipt) { $captionReceipt.FullName } else { $null }
    caption_receipt_sha256 = $captionReceiptHash
    caption_summary = $captionSummary
    worker_expected = $false
    auto_migrate_expected = $false
    database_before = $databaseBefore
    database_after = $databaseAfter
    database_unchanged = $databaseUnchanged
    api_still_listening = $apiStillListening
    caption_still_listening = $captionStillListening
    gpu_after = @(& nvidia-smi --query-gpu=index,name,memory.used,memory.total `
        --format=csv,noheader)
}
$receipt | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $receiptPath -Encoding UTF8

if ($operationError) { throw $operationError }
if (-not $databaseUnchanged) { throw 'Database changed during no-worker canary.' }
if ($apiStillListening -or $captionStillListening) {
    throw 'A canary service is still listening after cleanup.'
}

[pscustomobject]@{
    success = $true
    api_ok = [bool]$apiHealth.ok
    db_ok = [bool]$apiHealth.db_ok
    worker_enabled = [bool]$apiHealth.worker_enabled
    ui_http_code = [string]$uiCode
    caption_success = [int]$captionSummary.success_count
    caption_failures = [int]$captionSummary.failure_count
    caption_mean_seconds = [double]$captionSummary.mean_http_seconds
    caption_mean_words = [double]$captionSummary.mean_word_count
    database_unchanged = $databaseUnchanged
    api_still_listening = $apiStillListening
    caption_still_listening = $captionStillListening
    runtime_receipt = $receiptPath
} | ConvertTo-Json -Compress
