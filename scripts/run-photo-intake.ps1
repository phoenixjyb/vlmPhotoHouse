[CmdletBinding()]
param(
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [string]$DatabasePath = '',
    [string]$LvfaceDir = '',
    [string]$CaptionDir = '',
    [string]$CaptionProvider = 'http',
    [string]$LvfaceModelName = 'LVFace-B_Glint360K.onnx',
    [string]$EmbedDevice = 'cuda:0',
    [string]$CaptionDevice = 'cuda:0',
    [ValidateRange(1, 365)]
    [int]$LogRetention = 14,
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

$missing = @(Get-PhotoHouseMissingPaths -Context $context -RequireOriginals)
if ($PreflightOnly) {
    Show-PhotoHouseRuntimeContext -Context $context -Operation 'intake'
    if ($missing.Count -gt 0) {
        foreach ($item in $missing) {
            Write-Host "  MISSING: $item" -ForegroundColor Red
        }
        throw 'Photo intake preflight failed.'
    }
    Write-Host 'Photo intake preflight passed. No files, database rows, or processes were changed.' -ForegroundColor Green
    return
}

if ($missing.Count -gt 0) {
    throw "Photo intake prerequisites are missing: $($missing -join '; ')"
}

Initialize-PhotoHouseRuntimeEnvironment `
    -Context $context `
    -CaptionProvider $CaptionProvider `
    -LvfaceModelName $LvfaceModelName `
    -EmbedDevice $EmbedDevice `
    -CaptionDevice $CaptionDevice

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $context.LogRoot "intake-$stamp.log"
Remove-OldPhotoHouseLogs -LogRoot $context.LogRoot -Prefix 'intake-' -Keep $LogRetention

$mutexName = 'Global\VLMPhotoHouseIntake'
$mutex = [System.Threading.Mutex]::new($false, $mutexName)
$mutexAcquired = $false
$ingestExitCode = $null

try {
    try {
        $mutexAcquired = $mutex.WaitOne([TimeSpan]::FromSeconds(2))
    } catch [System.Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }
    if (-not $mutexAcquired) {
        throw "Another PhotoHouse intake operation holds $mutexName."
    }

    Write-PhotoHouseLog -Path $logPath -Message "Starting ingest scan for $($context.OriginalsPath)."
    Push-Location $context.BackendRoot
    try {
        & $context.PythonExe -m app.cli ingest-scan $context.OriginalsPath
        $ingestExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($ingestExitCode -ne 0) {
        throw "ingest-scan exited with code $ingestExitCode."
    }
    Write-PhotoHouseLog -Path $logPath -Message 'Ingest scan completed successfully.'
} catch {
    if (Test-Path -LiteralPath $logPath) {
        Write-PhotoHouseLog -Path $logPath -Message "Ingest scan failed: $($_.Exception.Message)"
    }
    throw
} finally {
    if ($mutexAcquired) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
