Set-StrictMode -Version Latest

function New-PhotoHouseRuntimeContext {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$DataRoot = 'E:\VLM_DATA',
        [string]$OriginalsPath = 'E:\01_INCOMING',
        [string]$DatabasePath = '',
        [string]$LvfaceDir = '',
        [string]$CaptionDir = ''
    )

    $resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
    $stackRoot = Split-Path -Parent $resolvedRepoRoot
    if ([string]::IsNullOrWhiteSpace($LvfaceDir)) {
        $LvfaceDir = Join-Path $stackRoot 'LVFace'
    }
    if ([string]::IsNullOrWhiteSpace($CaptionDir)) {
        $CaptionDir = Join-Path $stackRoot 'vlmCaptionModels'
    }
    if ([string]::IsNullOrWhiteSpace($DatabasePath)) {
        $DatabasePath = Join-Path $DataRoot 'databases\metadata.sqlite'
    }

    return [pscustomobject]@{
        RepoRoot = $resolvedRepoRoot
        BackendRoot = Join-Path $resolvedRepoRoot 'backend'
        PythonExe = Join-Path $resolvedRepoRoot '.venv\Scripts\python.exe'
        StackRoot = $stackRoot
        LvfaceDir = $LvfaceDir
        LvfacePythonExe = Join-Path $LvfaceDir '.venv\Scripts\python.exe'
        CaptionDir = $CaptionDir
        CaptionPythonExe = Join-Path $CaptionDir '.venv\Scripts\python.exe'
        DataRoot = $DataRoot
        OriginalsPath = $OriginalsPath
        DatabasePath = $DatabasePath
        DerivedPath = Join-Path $DataRoot 'derived'
        TempPath = Join-Path $DataRoot 'tmp'
        HfHome = Join-Path $DataRoot 'hf_home'
        LogRoot = Join-Path $DataRoot 'logs\photohouse'
    }
}

function Get-PhotoHouseMissingPaths {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Context,
        [switch]$RequireModels,
        [switch]$RequireOriginals
    )

    $checks = @(
        [pscustomobject]@{ Name = 'PhotoHouse repository'; Path = $Context.RepoRoot; Required = $true },
        [pscustomobject]@{ Name = 'Backend directory'; Path = $Context.BackendRoot; Required = $true },
        [pscustomobject]@{ Name = 'Repo-root Python'; Path = $Context.PythonExe; Required = $true },
        [pscustomobject]@{ Name = 'LVFace repository'; Path = $Context.LvfaceDir; Required = [bool]$RequireModels },
        [pscustomobject]@{ Name = 'LVFace Python'; Path = $Context.LvfacePythonExe; Required = [bool]$RequireModels },
        [pscustomobject]@{ Name = 'Caption repository'; Path = $Context.CaptionDir; Required = [bool]$RequireModels },
        [pscustomobject]@{ Name = 'Caption Python'; Path = $Context.CaptionPythonExe; Required = [bool]$RequireModels },
        [pscustomobject]@{ Name = 'Originals directory'; Path = $Context.OriginalsPath; Required = [bool]$RequireOriginals }
    )

    $missing = @()
    foreach ($check in $checks) {
        if ($check.Required -and -not (Test-Path -LiteralPath $check.Path)) {
            $missing += "$($check.Name): $($check.Path)"
        }
    }
    return $missing
}

function Show-PhotoHouseRuntimeContext {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Context,
        [string]$Operation
    )

    Write-Host "PhotoHouse $Operation preflight (read-only)" -ForegroundColor Cyan
    Write-Host "  Repository:     $($Context.RepoRoot)" -ForegroundColor Gray
    Write-Host "  Backend:        $($Context.BackendRoot)" -ForegroundColor Gray
    Write-Host "  Python:         $($Context.PythonExe)" -ForegroundColor Gray
    Write-Host "  LVFace:         $($Context.LvfaceDir)" -ForegroundColor Gray
    Write-Host "  Caption models: $($Context.CaptionDir)" -ForegroundColor Gray
    Write-Host "  Data root:      $($Context.DataRoot)" -ForegroundColor Gray
    Write-Host "  Originals:      $($Context.OriginalsPath)" -ForegroundColor Gray
    Write-Host "  Database:       $($Context.DatabasePath)" -ForegroundColor Gray
    Write-Host "  Log root:       $($Context.LogRoot)" -ForegroundColor Gray
}

function Initialize-PhotoHouseRuntimeEnvironment {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Context,
        [string]$CaptionProvider = 'http',
        [string]$CaptionServiceUrl = 'http://127.0.0.1:8102',
        [string]$LvfaceModelName = 'LVFace-B_Glint360K.onnx',
        [string]$EmbedDevice = 'cuda:0',
        [string]$CaptionDevice = 'cuda:0',
        [bool]$EnableInlineWorker = $true,
        [bool]$AutoMigrate = $true
    )

    $databaseUriPath = ($Context.DatabasePath -replace '\\', '/')
    $env:RUN_MODE = 'api'
    $env:PYTHONPATH = $Context.BackendRoot
    $env:ENABLE_INLINE_WORKER = if ($EnableInlineWorker) { 'true' } else { 'false' }
    $env:AUTO_MIGRATE = if ($AutoMigrate) { 'true' } else { 'false' }
    $env:FACE_EMBED_PROVIDER = 'lvface'
    $env:FACE_DETECT_PROVIDER = 'scrfd'
    $env:FACE_EMBED_DIM = '128'
    $env:LVFACE_EXTERNAL_DIR = $Context.LvfaceDir
    $env:LVFACE_PYTHON_EXE = $Context.LvfacePythonExe
    $env:LVFACE_MODEL_NAME = $LvfaceModelName
    $env:CAPTION_PROVIDER = $CaptionProvider
    $env:CAPTION_SERVICE_URL = $CaptionServiceUrl
    $env:CAPTION_HTTP_TIMEOUT_SEC = if ($env:CAPTION_HTTP_TIMEOUT_SEC) { $env:CAPTION_HTTP_TIMEOUT_SEC } else { '180' }
    $env:CAPTION_EXTERNAL_DIR = $Context.CaptionDir
    $env:CAPTION_MODEL = 'auto'
    $localQwen3Model = Join-Path $Context.CaptionDir 'models\qwen3-vl-8b-instruct'
    $env:QWEN2VL_MODEL_NAME = if (Test-Path -LiteralPath $localQwen3Model) { $localQwen3Model } else { 'Qwen/Qwen3-VL-8B-Instruct' }
    $env:QWEN2VL_LOAD_IN_4BIT = 'true'
    $env:QWEN2VL_4BIT_QUANT_TYPE = 'nf4'
    $env:DATABASE_URL = "sqlite:///$databaseUriPath"
    $env:VLM_DATA_ROOT = $Context.DataRoot
    $env:DERIVED_PATH = $Context.DerivedPath
    $env:VECTOR_INDEX_PATH = Join-Path $Context.DerivedPath 'vector.index'
    $env:ORIGINALS_PATH = $Context.OriginalsPath
    $env:VLM_TMP_DIR = $Context.TempPath
    $env:HF_HOME = $Context.HfHome
    $env:TMP = $Context.TempPath
    $env:TEMP = $Context.TempPath
    $env:EMBED_DEVICE = $EmbedDevice
    $env:CAPTION_DEVICE = $CaptionDevice

    foreach ($path in @(
        (Split-Path -Parent $Context.DatabasePath),
        $Context.DerivedPath,
        $Context.TempPath,
        $Context.HfHome,
        $Context.LogRoot
    )) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

function Get-PhotoHouseCaptionHealth {
    [CmdletBinding()]
    param(
        [ValidateRange(1, 65535)]
        [int]$Port = 8102,
        [ValidateRange(1, 30)]
        [int]$TimeoutSec = 5
    )

    if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
        throw 'curl.exe is required for proxy-bypassed localhost health checks.'
    }

    try {
        $body = & curl.exe --silent --show-error --noproxy '*' --max-time $TimeoutSec "http://127.0.0.1:$Port/health" 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($body -join ''))) {
            return $null
        }
        $health = ($body -join "`n") | ConvertFrom-Json
        $propertyNames = @($health.PSObject.Properties.Name)
        if (
            $propertyNames -notcontains 'status' -or
            $propertyNames -notcontains 'active_provider' -or
            $propertyNames -notcontains 'model_cache_ready'
        ) {
            return $null
        }
        return $health
    } catch {
        return $null
    }
}

function Get-PhotoHouseHealth {
    [CmdletBinding()]
    param(
        [ValidateRange(1, 65535)]
        [int]$Port = 8002,
        [ValidateRange(1, 30)]
        [int]$TimeoutSec = 5,
        [string]$ExpectedApiVersion = '1.0'
    )

    if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
        throw 'curl.exe is required for proxy-bypassed localhost health checks.'
    }

    try {
        $body = & curl.exe --silent --show-error --noproxy '*' --max-time $TimeoutSec "http://127.0.0.1:$Port/health" 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($body -join ''))) {
            return $null
        }
        $health = ($body -join "`n") | ConvertFrom-Json
        $propertyNames = @($health.PSObject.Properties.Name)
        if (
            $propertyNames -notcontains 'ok' -or
            $propertyNames -notcontains 'db_ok' -or
            $propertyNames -notcontains 'worker_enabled' -or
            [string]$health.api_version -ne $ExpectedApiVersion
        ) {
            return $null
        }
        return $health
    } catch {
        return $null
    }
}

function Write-PhotoHouseLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $line = "{0} {1}" -f (Get-Date -Format 's'), $Message
    Add-Content -LiteralPath $Path -Value $line -Encoding UTF8
    Write-Host $line
}

function Remove-OldPhotoHouseLogs {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogRoot,
        [Parameter(Mandatory = $true)]
        [string]$Prefix,
        [ValidateRange(1, 365)]
        [int]$Keep = 14
    )

    Get-ChildItem -LiteralPath $LogRoot -Filter "$Prefix*.log" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Keep |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
