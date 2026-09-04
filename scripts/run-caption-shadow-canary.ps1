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
    [string]$Prompt = '',
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$promptPath = Join-Path $repoRoot 'config\detailed-caption-prompt.txt'
if ([string]::IsNullOrWhiteSpace($Prompt)) {
    if (-not (Test-Path -LiteralPath $promptPath -PathType Leaf)) {
        throw "Detailed caption prompt not found: $promptPath"
    }
    $Prompt = (Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8).Trim()
}

function Get-BilingualCaptionParts {
    param([string]$Caption)

    $match = [regex]::Match(
        [string]$Caption,
        '^\s*EN:\s*(?<english>.+?)\s*\r?\n\s*\r?\n\s*ZH-CN:\s*(?<chinese>.+?)\s*$',
        ([System.Text.RegularExpressions.RegexOptions]::Singleline -bor [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    )
    if (-not $match.Success) { return $null }
    return [pscustomobject]@{
        English = $match.Groups['english'].Value.Trim()
        Chinese = $match.Groups['chinese'].Value.Trim()
    }
}

function ConvertTo-NeutralPersonTerms {
    param([string]$Caption)

    $neutral = [regex]::Replace([string]$Caption, '\bwomen\b', 'people', 'IgnoreCase')
    $neutral = [regex]::Replace($neutral, '\bwoman\b', 'person', 'IgnoreCase')
    $neutral = [regex]::Replace($neutral, '\bmen\b', 'people', 'IgnoreCase')
    $neutral = [regex]::Replace($neutral, '\bman\b', 'person', 'IgnoreCase')
    $neutral = [regex]::Replace($neutral, '\bgirls\b', 'children', 'IgnoreCase')
    $neutral = [regex]::Replace($neutral, '\bgirl\b', 'child', 'IgnoreCase')
    $neutral = [regex]::Replace($neutral, '\bboys\b', 'children', 'IgnoreCase')
    $neutral = [regex]::Replace($neutral, '\bboy\b', 'child', 'IgnoreCase')
    $childTerms = '\u7537\u5b69|\u5973\u5b69'
    $adultTerms = '\u7537\u4eba|\u5973\u4eba|\u7537\u5b50|\u5973\u5b50|\u7537\u6027|\u5973\u6027'
    $childReplacement = [string][char]0x513F + [char]0x7AE5
    $adultReplacement = [string][char]0x6210 + [char]0x4EBA
    $neutral = $neutral -replace $childTerms, $childReplacement
    return ($neutral -replace $adultTerms, $adultReplacement)
}

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
$promptFormPath = Join-Path ([System.IO.Path]::GetTempPath()) ("photohouse-prompt-{0}.txt" -f [Guid]::NewGuid().ToString('N'))
[System.IO.File]::WriteAllText(
    $promptFormPath,
    $Prompt,
    [System.Text.UTF8Encoding]::new($false)
)
$retryPromptFormPath = Join-Path ([System.IO.Path]::GetTempPath()) ("photohouse-prompt-retry-{0}.txt" -f [Guid]::NewGuid().ToString('N'))
$retryInstruction = 'CORRECTION REQUIRED: Start the response with "EN:", write 60 to 120 factual English words and target 75 to 95 words so the result is safely inside the accepted range. Then insert exactly one blank line and write "ZH-CN:" followed by a complete natural Simplified Chinese rendering of the same visible facts. Include both paragraphs and return no other text. Use only person, adult, or child for people. Describe visible poses and device details without saying or implying taking photos, capturing, recording, calling, or messaging. In Chinese, use neutral person terms and avoid speculative wording or claims of photographing or recording.'
[System.IO.File]::WriteAllText(
    $retryPromptFormPath,
    "$Prompt`n`n$retryInstruction",
    [System.Text.UTF8Encoding]::new($false)
)

foreach ($sample in $samples) {
    $relative = $sample.FullName.Substring($InputRoot.TrimEnd('\').Length).TrimStart('\')
    $tempResponse = Join-Path ([System.IO.Path]::GetTempPath()) ("photohouse-caption-{0}.json" -f [Guid]::NewGuid().ToString('N'))
    $record = [ordered]@{
        relative_path = $relative
        last_write_time = $sample.LastWriteTime.ToString('o')
        bytes = [int64]$sample.Length
        sha256 = $null
        status = 'error'
        attempt_count = 0
        neutralization_applied = $false
        http_code = $null
        http_total_seconds = $null
        generation_time_seconds = $null
        word_count = 0
        english_word_count = 0
        chinese_character_count = 0
        chinese_script_ok = $false
        bilingual_format_ok = $false
        policy_violation_terms = @()
        chinese_policy_violation_terms = @()
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
        $totalHttpSeconds = 0.0
        foreach ($activePromptFormPath in @($promptFormPath, $retryPromptFormPath, $retryPromptFormPath, $retryPromptFormPath)) {
            $record.attempt_count++
            $record.bilingual_format_ok = $false
            $record.chinese_script_ok = $false
            $record.english_word_count = 0
            $record.chinese_character_count = 0
            $record.word_count = 0
            $record.policy_violation_terms = @()
            $record.chinese_policy_violation_terms = @()
            $writeOut = & curl.exe `
                --silent --show-error --fail --globoff --noproxy '*' `
                --max-time $TimeoutSec `
                --output $tempResponse `
                --write-out '%{http_code}|%{time_total}' `
                --form "file=@$($sample.FullName);type=$mime" `
                --form "prompt=<$activePromptFormPath" `
                "$CaptionServiceUrl/caption" 2>&1
            $curlExit = $LASTEXITCODE
            $responseParts = (($writeOut -join '') -split '\|', 2)
            if ($responseParts.Count -eq 2) {
                $record.http_code = $responseParts[0]
                $totalHttpSeconds += [double]$responseParts[1]
                $record.http_total_seconds = $totalHttpSeconds
            }
            if ($curlExit -ne 0) {
                throw "curl.exe exited with code ${curlExit}: $($writeOut -join ' ')"
            }

            $response = Get-Content -LiteralPath $tempResponse -Raw -Encoding UTF8 | ConvertFrom-Json
            $record.status = 'ok'
            $record.generation_time_seconds = [double]$response.generation_time_seconds
            $record.provider = [string]$response.provider
            $record.model = [string]$response.model
            $rawCaption = [string]$response.caption
            $record.caption = ConvertTo-NeutralPersonTerms -Caption $rawCaption
            $record.neutralization_applied = ($record.caption -cne $rawCaption)
            $captionParts = Get-BilingualCaptionParts -Caption $record.caption
            if ($captionParts) {
                $record.bilingual_format_ok = $true
                $record.english_word_count = @(($captionParts.English -split '\s+' | Where-Object { $_ })).Count
                $record.chinese_character_count = ($captionParts.Chinese -replace '\s', '').Length
                $record.chinese_script_ok = [regex]::IsMatch($captionParts.Chinese, '[\u4e00-\u9fff]')
                $policyPattern = '(?i)\b(seemingly|apparently|likely|probably|possibly|perhaps|maybe|suggests|man|woman|boy|girl|nude|naked|diaper|underwear|capturing|recording|photographing)\b|looks like|no clothing|without clothing|taking (a |the )?(photo|picture|video)|appear(s|ing)? to (capture|take|record|photograph|call|message)|seem(s|ing)? to (capture|take|record|photograph|call|message)'
                $record.policy_violation_terms = @(
                    [regex]::Matches($captionParts.English, $policyPattern) |
                        ForEach-Object { $_.Value.ToLowerInvariant() } |
                        Sort-Object -Unique
                )
                $chinesePolicyPattern = '似乎|好像|可能|看起来|大概|或许|推测|拍摄|拍照|录像|录制|男人|女人|男子|女子|男孩|女孩|男性|女性|裸体|赤裸|尿布|内衣|没穿衣服'
                $record.chinese_policy_violation_terms = @(
                    [regex]::Matches($captionParts.Chinese, $chinesePolicyPattern) |
                        ForEach-Object { $_.Value } |
                        Sort-Object -Unique
                )
                $record.word_count = $record.english_word_count
            }
            $qualityOk = (
                [bool]$record.bilingual_format_ok -and
                [bool]$record.chinese_script_ok -and
                [int]$record.english_word_count -ge 60 -and
                [int]$record.english_word_count -le 120 -and
                @($record.policy_violation_terms).Count -eq 0 -and
                @($record.chinese_policy_violation_terms).Count -eq 0
            )
            if ($qualityOk) { break }
        }
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
Remove-Item -LiteralPath $promptFormPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $retryPromptFormPath -Force -ErrorAction SilentlyContinue

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
$formatFailures = @($successful | Where-Object { -not [bool]$_.bilingual_format_ok }).Count
$chineseScriptFailures = @($successful | Where-Object { -not [bool]$_.chinese_script_ok }).Count
$lengthFailures = @($successful | Where-Object {
    [int]$_.english_word_count -lt 60 -or [int]$_.english_word_count -gt 120
}).Count
$policyViolationCount = @($successful | Where-Object { @($_.policy_violation_terms).Count -gt 0 }).Count
$chinesePolicyViolationCount = @($successful | Where-Object {
    @($_.chinese_policy_violation_terms).Count -gt 0
}).Count
$chineseCounts = @($successful | ForEach-Object { [int]$_.chinese_character_count })
$retryCount = @($results | Where-Object { [int]$_.attempt_count -gt 1 }).Count
$neutralizationCount = @($results | Where-Object { [bool]$_.neutralization_applied }).Count
$meanChineseCharacters = if ($chineseCounts.Count -gt 0) {
    ($chineseCounts | Measure-Object -Average).Average
} else { $null }

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
        mean_english_word_count = $meanWords
        mean_chinese_character_count = $meanChineseCharacters
        bilingual_format_failure_count = $formatFailures
        chinese_script_failure_count = $chineseScriptFailures
        english_length_failure_count = $lengthFailures
        policy_violation_count = $policyViolationCount
        chinese_policy_violation_count = $chinesePolicyViolationCount
        corrective_retry_count = $retryCount
        neutralization_count = $neutralizationCount
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
if (
    $formatFailures -ne 0 -or
    $chineseScriptFailures -ne 0 -or
    $lengthFailures -ne 0 -or
    $policyViolationCount -ne 0 -or
    $chinesePolicyViolationCount -ne 0
) {
    throw (
        "Shadow canary quality gate failed: bilingual_format=$formatFailures " +
        "chinese_script=$chineseScriptFailures english_length=$lengthFailures " +
        "policy_violations=$policyViolationCount " +
        "chinese_policy_violations=$chinesePolicyViolationCount."
    )
}
