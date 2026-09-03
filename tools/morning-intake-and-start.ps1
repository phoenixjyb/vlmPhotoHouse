[CmdletBinding()]
param(
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [string]$DatabasePath = '',
    [string]$LvfaceDir = '',
    [string]$CaptionDir = '',
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8002,
    [ValidateRange(1, 65535)]
    [int]$CaptionPort = 8102,
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$intakeScript = Join-Path $repoRoot 'scripts\run-photo-intake.ps1'
$apiScript = Join-Path $repoRoot 'scripts\start-photohouse-api.ps1'
$captionScript = Join-Path $repoRoot 'scripts\start-caption-service.ps1'

if (-not (Test-Path -LiteralPath $intakeScript -PathType Leaf)) {
    throw "Intake script not found: $intakeScript"
}
if (-not (Test-Path -LiteralPath $apiScript -PathType Leaf)) {
    throw "API startup script not found: $apiScript"
}
if (-not (Test-Path -LiteralPath $captionScript -PathType Leaf)) {
    throw "Caption-service startup script not found: $captionScript"
}

$commonArgs = @{
    DataRoot = $DataRoot
    OriginalsPath = $OriginalsPath
    DatabasePath = $DatabasePath
    LvfaceDir = $LvfaceDir
    CaptionDir = $CaptionDir
}

Write-Warning 'morning-intake-and-start.ps1 is a compatibility coordinator. Use separate scheduled tasks for run-photo-intake.ps1 and start-photohouse-api.ps1.'

if ($PreflightOnly) {
    & $captionScript -CaptionDir $CaptionDir -DataRoot $DataRoot -Port $CaptionPort -PreflightOnly
    & $intakeScript @commonArgs -PreflightOnly
    Write-Host 'API preflight requires the caption service to be running; it is intentionally skipped by this all-read-only compatibility preflight.' -ForegroundColor Yellow
    Write-Host 'Compatibility preflight passed. No intake or startup action was performed.' -ForegroundColor Green
    return
}

& $captionScript -CaptionDir $CaptionDir -DataRoot $DataRoot -Port $CaptionPort -Detached
& $intakeScript @commonArgs
$captionServiceUrl = "http://127.0.0.1:$CaptionPort"
& $apiScript @commonArgs -CaptionProvider 'http' -CaptionServiceUrl $captionServiceUrl -ApiPort $ApiPort -Detached
