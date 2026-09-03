[CmdletBinding()]
param(
    [string]$InputRoot = 'E:\01_INCOMING',
    [string]$OutputRoot = 'E:\VLM_DATA\logs\photohouse',
    [string]$CaptionServiceUrl = 'http://127.0.0.1:8102',
    [ValidateRange(1, 100)]
    [int]$SampleSize = 12,
    [ValidateRange(30, 600)]
    [int]$TimeoutSec = 180,
    [ValidateRange(1, 30)]
    [int]$GpuQueryTimeoutSec = 5,
    [ValidateRange(1, 1024)]
    [int]$MaxFileMiB = 40,
    [string[]]$ExcludedDirectoryNames = @('.thumbnails', 'thumbnails', '@eadir', '$recycle.bin', 'system volume information'),
    [string]$Prompt = (
        'Write a factual, search-friendly description of this photo in 80 to 120 words. ' +
        'Use only directly visible evidence. Describe the main subjects, actions, setting, important objects, ' +
        'clothing, colors, lighting, composition, and clearly readable text. Do not identify people or infer ' +
        'relationships, protected or sensitive traits, events, occasions, locations, landmarks, or organizations. ' +
        'Name a brand, model, place, landmark, or organization only when its exact name or logo is clearly legible ' +
        'and unambiguous; otherwise use a generic description. Transcribe text only when confident and call it ' +
        'partial or unclear instead of guessing. For phones or devices, describe visible color, case, controls, ' +
        'screen content, and use, but do not guess the brand or model. Avoid speculative words such as likely, ' +
        'probably, suggests, or appears to be. Return one coherent paragraph without hidden context.'
    ),
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-LocalJsonGet {
    param([string]$Url)

    try {
        $body = & curl.exe --silent --noproxy '*' --max-time 10 $Url 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($body -join ''))) {
        return $null
    }
    try {
        return (($body -join "`n") | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Get-TimeSpreadSample {
    param(
        [object[]]$Files,
        [int]$Count
    )

    $ordered = @($Files | Sort-Object LastWriteTime, FullName)
    if ($ordered.Count -le $Count) {
        return $ordered
    }

    $indices = [System.Collections.Generic.HashSet[int]]::new()
    for ($i = 0; $i -lt $Count; $i++) {
        $index = if ($Count -eq 1) {
            [int][Math]::Floor(($ordered.Count - 1) / 2)
        } else {
            [int][Math]::Round(($i * ($ordered.Count - 1)) / ($Count - 1))
        }
        [void]$indices.Add($index)
    }
    return @($indices | Sort-Object | ForEach-Object { $ordered[$_] })
}

function Get-Rtx3090State {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = 'nvidia-smi.exe'
    $startInfo.Arguments = '--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            return 'nvidia-smi-start-failed'
        }
        if (-not $process.WaitForExit($GpuQueryTimeoutSec * 1000)) {
            try { $process.Kill() } catch {}
            return 'nvidia-smi-timeout'
        }
        $output = $process.StandardOutput.ReadToEnd()
        $row = @(($output -split "`r?`n") | Where-Object { $_ -match 'RTX 3090' } | Select-Object -First 1)
        return ($row -join '')
    } catch {
        return "nvidia-smi-error: $($_.Exception.Message)"
    } finally {
        $process.Dispose()
    }
}

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    throw 'curl.exe is required for proxy-bypassed localhost requests.'
}
if (-not (Test-Path -LiteralPath $InputRoot -PathType Container)) {
    throw "Input root not found: $InputRoot"
}

$supportedExtensions = @('.jpg', '.jpeg', '.png', '.webp')
$excludedNames = @($ExcludedDirectoryNames | ForEach-Object { $_.ToLowerInvariant() })
$maxBytes = [int64]$MaxFileMiB * 1MB
$candidates = @(Get-ChildItem -LiteralPath $InputRoot -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object {
        $relativeParts = $_.FullName.Substring($InputRoot.TrimEnd('\').Length).TrimStart('\') -split '\\'
        $isExcluded = @($relativeParts | Where-Object { $excludedNames -contains $_.ToLowerInvariant() }).Count -gt 0
        $supportedExtensions -contains $_.Extension.ToLowerInvariant() -and
        -not $isExcluded -and
        $_.Length -ge 16384 -and
        $_.Length -le $maxBytes
    })
if ($candidates.Count -eq 0) {
    throw "No supported image files found under $InputRoot."
}
$samples = @(Get-TimeSpreadSample -Files $candidates -Count $SampleSize)

$health = Invoke-LocalJsonGet -Url "$CaptionServiceUrl/health"
$modelInfo = Invoke-LocalJsonGet -Url "$CaptionServiceUrl/model-info"
$serviceReady = (
    $null -ne $health -and
    [string]$health.status -eq 'healthy' -and
    [string]$health.active_provider -eq 'qwen3-vl' -and
    [bool]$health.model_cache_ready -and
    [string]$health.gpu_device -match 'RTX 3090' -and
    $null -ne $modelInfo -and
    [string]$modelInfo.model_class -eq 'Qwen3VLForConditionalGeneration' -and
    [bool]$modelInfo.load_in_4bit
)

if ($PreflightOnly) {
    Write-Host 'PhotoHouse Qwen3-VL shadow canary preflight (read-only)' -ForegroundColor Cyan
    Write-Host "  Input root:       $InputRoot" -ForegroundColor Gray
    Write-Host "  Candidate images: $($candidates.Count)" -ForegroundColor Gray
    Write-Host "  Selected images:  $($samples.Count)" -ForegroundColor Gray
    Write-Host "  Selection:        deterministic time-spread quantiles" -ForegroundColor Gray
    Write-Host "  Service ready:    $serviceReady" -ForegroundColor Gray
    foreach ($sample in $samples) {
        $relative = $sample.FullName.Substring($InputRoot.TrimEnd('\').Length).TrimStart('\')
        Write-Host ("  SAMPLE {0:o} {1,8:N1} MiB  {2}" -f $sample.LastWriteTime, ($sample.Length / 1MB), $relative) -ForegroundColor DarkGray
    }
    Write-Host 'No photos, database rows, services, or scheduled tasks were changed.' -ForegroundColor Green
    return
}

if (-not $serviceReady) {
    throw 'Expected Qwen3-VL 4-bit service on the RTX 3090 is not ready.'
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$receiptPath = Join-Path $OutputRoot "qwen3-vl-shadow-receipt-$stamp.json"
$results = [System.Collections.Generic.List[object]]::new()
$gpuBefore = Get-Rtx3090State

foreach ($sample in $samples) {
    $relative = $sample.FullName.Substring($InputRoot.TrimEnd('\').Length).TrimStart('\')
    $tempResponse = Join-Path ([System.IO.Path]::GetTempPath()) ("photohouse-caption-{0}.json" -f [Guid]::NewGuid().ToString('N'))
    $record = [ordered]@{
        relative_path = $relative
        last_write_time = $sample.LastWriteTime.ToString('o')
        bytes = [int64]$sample.Length
        sha256 = $null
        status = 'error'
        http_code = $null
        http_total_seconds = $null
        generation_time_seconds = $null
        word_count = 0
        provider = $null
        model = $null
        caption = $null
        error = $null
        gpu_after = $null
    }

    try {
        $record.sha256 = (Get-FileHash -LiteralPath $sample.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $mime = switch ($sample.Extension.ToLowerInvariant()) {
            '.png' { 'image/png' }
            '.webp' { 'image/webp' }
            default { 'image/jpeg' }
        }
        $writeOut = & curl.exe `
            --silent --show-error --fail --noproxy '*' `
            --max-time $TimeoutSec `
            --output $tempResponse `
            --write-out '%{http_code}|%{time_total}' `
            --form "file=@$($sample.FullName);type=$mime" `
            --form "prompt=$Prompt" `
            "$CaptionServiceUrl/caption" 2>&1
        $curlExit = $LASTEXITCODE
        $parts = (($writeOut -join '') -split '\|', 2)
        if ($parts.Count -eq 2) {
            $record.http_code = $parts[0]
            $record.http_total_seconds = [double]$parts[1]
        }
        if ($curlExit -ne 0) {
            throw "curl.exe exited with code ${curlExit}: $($writeOut -join ' ')"
        }

        $response = Get-Content -LiteralPath $tempResponse -Raw -Encoding UTF8 | ConvertFrom-Json
        $record.status = 'ok'
        $record.generation_time_seconds = [double]$response.generation_time_seconds
        $record.provider = [string]$response.provider
        $record.model = [string]$response.model
        $record.caption = [string]$response.caption
        $record.word_count = @(($record.caption -split '\s+' | Where-Object { $_ })).Count
    } catch {
        $record.error = $_.Exception.Message
    } finally {
        $record.gpu_after = Get-Rtx3090State
        Remove-Item -LiteralPath $tempResponse -Force -ErrorAction SilentlyContinue
    }
    $results.Add([pscustomobject]$record)
    $elapsedForDisplay = if ($null -ne $record.http_total_seconds) { [double]$record.http_total_seconds } else { 0.0 }
    Write-Host ("[{0}/{1}] {2} {3:N2}s {4} words  {5}" -f $results.Count, $samples.Count, $record.status, $elapsedForDisplay, $record.word_count, $relative)
}

$successful = @($results | Where-Object { $_.status -eq 'ok' })
$latencies = @($successful | ForEach-Object { [double]$_.http_total_seconds } | Sort-Object)
$p95 = if ($latencies.Count -gt 0) {
    $latencies[[Math]::Max(0, [Math]::Ceiling($latencies.Count * 0.95) - 1)]
} else {
    $null
}
$meanLatency = if ($latencies.Count -gt 0) { ($latencies | Measure-Object -Average).Average } else { $null }
$wordCounts = @($successful | ForEach-Object { [int]$_.word_count })
$meanWords = if ($wordCounts.Count -gt 0) { ($wordCounts | Measure-Object -Average).Average } else { $null }

$receipt = [ordered]@{
    schema = 'photohouse.qwen3_vl_shadow.v1'
    timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    production_database_touched = $false
    production_intake_touched = $false
    scheduled_tasks_changed = $false
    photos_copied_or_modified = $false
    input_root = $InputRoot
    candidate_count = $candidates.Count
    selected_count = $samples.Count
    selection = 'deterministic time-spread quantiles'
    max_file_mib = $MaxFileMiB
    prompt = $Prompt
    health = $health
    model_info = $modelInfo
    gpu_before = $gpuBefore
    gpu_after = Get-Rtx3090State
    summary = [ordered]@{
        success_count = $successful.Count
        failure_count = $results.Count - $successful.Count
        mean_http_seconds = $meanLatency
        p95_http_seconds = $p95
        mean_word_count = $meanWords
    }
    results = $results
}

$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Write-Host "Shadow receipt: $receiptPath" -ForegroundColor Cyan
$meanForDisplay = if ($null -ne $meanLatency) { [double]$meanLatency } else { 0.0 }
$p95ForDisplay = if ($null -ne $p95) { [double]$p95 } else { 0.0 }
$wordsForDisplay = if ($null -ne $meanWords) { [double]$meanWords } else { 0.0 }
Write-Host ("Success={0}/{1}; mean={2:N2}s; p95={3:N2}s; mean_words={4:N1}" -f $successful.Count, $results.Count, $meanForDisplay, $p95ForDisplay, $wordsForDisplay) -ForegroundColor Green

if ($successful.Count -ne $results.Count) {
    throw "Shadow canary completed with $($results.Count - $successful.Count) failure(s)."
}
