param(
    [string]$Preset = 'RTX3090',  # RTX3090 | LowVRAM | CPU
    [switch]$UseWindowsTerminal,
    [switch]$KillExisting,
    [switch]$NoCleanup,
    [switch]$RunPreCheck,
    [int]$GpuMonitorInterval = 3
)

# Default to using Windows Terminal and killing existing
if (-not $PSBoundParameters.ContainsKey('UseWindowsTerminal')) { $UseWindowsTerminal = $true }
if (-not $PSBoundParameters.ContainsKey('KillExisting')) { $KillExisting = $true }
if (-not $PSBoundParameters.ContainsKey('RunPreCheck')) { $RunPreCheck = $true }

$ErrorActionPreference = 'Stop'

Write-Host "🚀 Starting VLM Photo Engine AI Monitoring (tmux-style)" -ForegroundColor Cyan
Write-Host "Configuration: $Preset preset with RTX 3090 GPU validation" -ForegroundColor Yellow

# GPU Pre-Check Integration
if ($RunPreCheck) {
    Write-Host ""
    Write-Host "🔍 Running GPU Pre-Check Validation..." -ForegroundColor Green
    
    try {
        $preCheckResult = & .\.venv\Scripts\python.exe gpu_precheck_validation.py
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ GPU Pre-Check FAILED!" -ForegroundColor Red
            Write-Host "Cannot proceed with AI processing until GPU issues are resolved" -ForegroundColor Yellow
            Write-Host "Run manually: .\.venv\Scripts\python.exe gpu_precheck_validation.py" -ForegroundColor Gray
            exit 1
        }
        
        Write-Host "✅ GPU Pre-Check PASSED - All environments validated for RTX 3090" -ForegroundColor Green
        
    } catch {
        Write-Host "❌ GPU Pre-Check execution failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Continuing with manual GPU detection..." -ForegroundColor Yellow
    }
}

# Clean up existing processes if requested
if ($KillExisting -and -not $NoCleanup) {
    try {
        Write-Host "🔄 Cleaning up existing processes..." -ForegroundColor Yellow
        
        # Stop Windows Terminal instances
        $wt = Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue
        if ($wt) {
            $wt | Stop-Process -Force -ErrorAction SilentlyContinue
            Write-Host "✅ Closed $($wt.Count) existing Windows Terminal instance(s)" -ForegroundColor Green
            Start-Sleep -Seconds 2
        }
        
        # Stop Python processes (backend, orchestrator)
        $python = Get-Process -Name python -ErrorAction SilentlyContinue
        if ($python) {
            $python | Stop-Process -Force -ErrorAction SilentlyContinue
            Write-Host "✅ Stopped $($python.Count) Python process(es)" -ForegroundColor Green
        }
        
        # Clean up ports 8000, 8001, 8002
        $portsToCheck = @(8000, 8001, 8002)
        foreach ($port in $portsToCheck) {
            try {
                $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
                if ($connections) {
                    foreach ($conn in $connections) {
                        $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                        if ($process) {
                            Write-Host "🔴 Stopping process '$($process.ProcessName)' on port $port" -ForegroundColor Red
                            $process | Stop-Process -Force -ErrorAction SilentlyContinue
                        }
                    }
                }
            } catch { }
        }
        Write-Host "✅ Port cleanup completed" -ForegroundColor Green
    } catch {
        Write-Warning "Could not perform cleanup: $($_.Exception.Message)"
    }
}

# Set up paths
$repoRoot = (Resolve-Path $PSScriptRoot).Path
$backendRoot = Join-Path $repoRoot 'backend'
$pyExe = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pyExe)) {
    $pyExe = 'python'
}

# Function to detect RTX 3090 GPU ID with CUDA mapping validation
function Get-RTX3090-GpuId {
    try {
        Write-Host "🔍 Detecting RTX 3090 GPU configuration..." -ForegroundColor Yellow
        
        # Get nvidia-smi GPU list
        $gpuInfo = nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits
        $rtx3090NvidiaIndex = $null
        $quadroIndex = $null
        
        Write-Host "Available GPUs:" -ForegroundColor White
        foreach ($line in $gpuInfo) {
            $parts = $line.Split(',')
            $index = $parts[0].Trim()
            $name = $parts[1].Trim()
            $memory = $parts[2].Trim()
            
            Write-Host "  GPU $index`: $name ($memory MB)" -ForegroundColor Cyan
            
            if ($name -like "*RTX 3090*") {
                $rtx3090NvidiaIndex = $index
            } elseif ($name -like "*Quadro*") {
                $quadroIndex = $index
            }
        }
        
        if ($null -eq $rtx3090NvidiaIndex) {
            Write-Host "❌ RTX 3090 not found in nvidia-smi output!" -ForegroundColor Red
            return $null
        }
        
        Write-Host "🎯 RTX 3090 found at nvidia-smi index: $rtx3090NvidiaIndex" -ForegroundColor Green
        
        # CRITICAL: Based on our discovery, CUDA device mapping is REVERSED
        # nvidia-smi GPU 1 (RTX 3090) → CUDA_VISIBLE_DEVICES=0 → cuda:0 in PyTorch
        # nvidia-smi GPU 0 (Quadro)  → CUDA_VISIBLE_DEVICES=1 → cuda:0 in PyTorch
        
        $cudaVisibleDevices = if ($rtx3090NvidiaIndex -eq "1") { "0" } else { "1" }
        
        Write-Host "🔄 GPU Mapping (nvidia-smi → CUDA):" -ForegroundColor Yellow
        Write-Host "   nvidia-smi GPU $rtx3090NvidiaIndex (RTX 3090) → CUDA_VISIBLE_DEVICES=$cudaVisibleDevices → cuda:0" -ForegroundColor Cyan
        
        return @{
            NvidiaIndex = $rtx3090NvidiaIndex
            CudaVisibleDevices = $cudaVisibleDevices
            DeviceName = "RTX 3090"
            MemoryGB = if ($rtx3090NvidiaIndex -eq "1") { 24 } else { 5 }
        }
        
    } catch {
        Write-Host "❌ Error detecting RTX 3090: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

# Configure environment based on preset
if ($Preset -eq 'RTX3090') {
    # Dynamically detect RTX 3090 with corrected CUDA mapping
    $rtxConfig = Get-RTX3090-GpuId
    if ($null -eq $rtxConfig) {
        Write-Host "❌ Cannot proceed without RTX 3090 detection" -ForegroundColor Red
        Write-Host "💡 Try running with -Preset LowVRAM to use Quadro P2000" -ForegroundColor Yellow
        exit 1
    }
    
    # Correct CUDA environment configuration based on our mapping discovery
    $env:CUDA_VISIBLE_DEVICES = $rtxConfig.CudaVisibleDevices  # 0 for RTX 3090, not 1!
    $env:EMBED_DEVICE = 'cuda:0'                               # RTX 3090 as cuda:0
    $env:CAPTION_DEVICE = 'cuda:0'                             # RTX 3090 as cuda:0
    $env:FACE_EMBED_PROVIDER = 'lvface'
    $env:FACE_DETECT_PROVIDER = 'auto'
    $env:CAPTION_PROVIDER = 'blip2'
    
    # External model directories (validated paths)
    $env:LVFACE_EXTERNAL_DIR = 'C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace'
    $env:CAPTION_EXTERNAL_DIR = 'C:\Users\yanbo\wSpace\vlm-photo-engine\vlmCaptionModels'
    $env:LVFACE_MODEL_NAME = 'LVFace-B_Glint360K.onnx'
    $env:CAPTION_MODEL = 'auto'
    
    $gpuDevice = "RTX 3090 ($($rtxConfig.MemoryGB)GB) [nvidia-smi:$($rtxConfig.NvidiaIndex) → cuda:0]"
    
    Write-Host "🎯 RTX 3090 Configuration Applied:" -ForegroundColor Green
    Write-Host "   CUDA_VISIBLE_DEVICES=$($env:CUDA_VISIBLE_DEVICES) (corrected mapping)" -ForegroundColor Cyan
    Write-Host "   Device Target: cuda:0 → RTX 3090 24GB" -ForegroundColor Cyan
    
} elseif ($Preset -eq 'LowVRAM') {
    # Quadro P2000 configuration
    $env:CUDA_VISIBLE_DEVICES = '1'  # Quadro at nvidia-smi index 0 → CUDA_VISIBLE_DEVICES=1
    $env:EMBED_DEVICE = 'cuda:0'
    $env:CAPTION_DEVICE = 'cuda:0'
    $env:FACE_EMBED_PROVIDER = 'facenet'
    $env:CAPTION_PROVIDER = 'vitgpt2'
    $gpuDevice = 'Quadro P2000 (5GB) [nvidia-smi:0 → cuda:0]'
    
} else {
    # CPU fallback
    $env:EMBED_DEVICE = 'cpu'
    $env:CAPTION_DEVICE = 'cpu'
    $env:FACE_EMBED_PROVIDER = 'lvface'
    $env:CAPTION_PROVIDER = 'blip2'
    $gpuDevice = 'CPU (No GPU)'
    Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
}

$env:VIDEO_ENABLED = 'true'
$env:ENABLE_INLINE_WORKER = 'true'

Write-Host "🎯 Configuration Applied:" -ForegroundColor Green
Write-Host "  Device: $gpuDevice" -ForegroundColor Cyan
Write-Host "  Face Provider: $($env:FACE_EMBED_PROVIDER)" -ForegroundColor Cyan
Write-Host "  Caption Provider: $($env:CAPTION_PROVIDER)" -ForegroundColor Cyan
Write-Host "  Video Processing: Enabled" -ForegroundColor Cyan

# Create pane scripts
function New-BackendPane {
    $content = @(
        "Set-Location -LiteralPath `"$backendRoot`"",
        "Write-Host '=== BACKEND WITH EXTERNAL MODEL GPU CONFIGURATION ===' -ForegroundColor Green",
        "Write-Host 'Device: $gpuDevice' -ForegroundColor Yellow",
        "Write-Host 'Configuring external model GPU access...' -ForegroundColor Yellow",
        "",
        "# Set environment variables for external subprocess models",
        "`$env:CUDA_VISIBLE_DEVICES = '$($env:CUDA_VISIBLE_DEVICES)'",
        "`$env:EMBED_DEVICE = '$($env:EMBED_DEVICE)'", 
        "`$env:CAPTION_DEVICE = '$($env:CAPTION_DEVICE)'",
        "`$env:FACE_EMBED_PROVIDER = '$($env:FACE_EMBED_PROVIDER)'",
        "`$env:CAPTION_PROVIDER = '$($env:CAPTION_PROVIDER)'",
        "`$env:LVFACE_EXTERNAL_DIR = '$($env:LVFACE_EXTERNAL_DIR)'",
        "`$env:CAPTION_EXTERNAL_DIR = '$($env:CAPTION_EXTERNAL_DIR)'",
        "",
        "Write-Host 'Environment variables configured:' -ForegroundColor Cyan",
        "Write-Host '  CUDA_VISIBLE_DEVICES: '$($env:CUDA_VISIBLE_DEVICES) -ForegroundColor Cyan",
        "Write-Host '  EMBED_DEVICE: '$($env:EMBED_DEVICE) -ForegroundColor Cyan", 
        "Write-Host '  CAPTION_DEVICE: '$($env:CAPTION_DEVICE) -ForegroundColor Cyan",
        "Write-Host '  FACE_EMBED_PROVIDER: '$($env:FACE_EMBED_PROVIDER) -ForegroundColor Cyan",
        "Write-Host '  CAPTION_PROVIDER: '$($env:CAPTION_PROVIDER) -ForegroundColor Cyan",
        "Write-Host ''",
        "Write-Host 'Pre-validating external model access...' -ForegroundColor Yellow",
        "try {",
        "    Write-Host 'Testing LVFace external directory...' -ForegroundColor Gray",
        "    if (Test-Path '$($env:LVFACE_EXTERNAL_DIR)') {",
        "        Write-Host '  ✅ LVFace directory found' -ForegroundColor Green",
        "    } else {",
        "        Write-Host '  ❌ LVFace directory missing: $($env:LVFACE_EXTERNAL_DIR)' -ForegroundColor Red",
        "    }",
        "    ",
        "    Write-Host 'Testing BLIP2 external directory...' -ForegroundColor Gray",
        "    if (Test-Path '$($env:CAPTION_EXTERNAL_DIR)') {",
        "        Write-Host '  ✅ BLIP2 directory found' -ForegroundColor Green",
        "    } else {",
        "        Write-Host '  ❌ BLIP2 directory missing: $($env:CAPTION_EXTERNAL_DIR)' -ForegroundColor Red",
        "    }",
        "} catch {",
        "    Write-Host '  ⚠️  Directory validation failed' -ForegroundColor Yellow",
        "}",
        "Write-Host ''",
        "Write-Host 'Starting backend with RTX 3090 external model configuration...' -ForegroundColor Green",
        "& `"$pyExe`" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info"
    ) -join "`n"
    $path = Join-Path $env:TEMP "backend-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $backendRoot; Title = "Backend + External Models ($gpuDevice)" }
}

function New-GpuMonitorPane {
    $content = @(
        "Write-Host '=== RTX 3090 REAL-TIME GPU MONITORING ===' -ForegroundColor Cyan",
        "Write-Host 'Monitoring: $gpuDevice' -ForegroundColor Yellow",
        "Write-Host 'Update Interval: $GpuMonitorInterval seconds' -ForegroundColor Gray",
        "Write-Host 'Press Ctrl+C to stop monitoring' -ForegroundColor Gray",
        "Write-Host ''",
        "",
        "# Function to get specific GPU stats",
        "function Get-TargetGpuStats {",
        "    try {",
        "        `$result = nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,utilization.memory,temperature.gpu --format=csv,noheader,nounits",
        "        foreach (`$line in `$result) {",
        "            `$parts = `$line.Split(',')",
        "            `$index = `$parts[0].Trim()",
        "            `$name = `$parts[1].Trim()",
        "            if (`$name -like '*RTX 3090*') {",
        "                return @{",
        "                    Index = `$index",
        "                    Name = `$name",
        "                    MemoryUsed = [int]`$parts[2].Trim()",
        "                    MemoryTotal = [int]`$parts[3].Trim()",
        "                    GpuUtil = [int]`$parts[4].Trim()",
        "                    MemUtil = [int]`$parts[5].Trim()",
        "                    Temp = [int]`$parts[6].Trim()",
        "                    MemoryUsedGB = [math]::Round([int]`$parts[2].Trim() / 1024, 2)",
        "                    MemoryTotalGB = [math]::Round([int]`$parts[3].Trim() / 1024, 1)",
        "                    MemoryPercent = [math]::Round(([int]`$parts[2].Trim() / [int]`$parts[3].Trim()) * 100, 1)",
        "                }",
        "            }",
        "        }",
        "        return `$null",
        "    } catch {",
        "        return `$null",
        "    }",
        "}",
        "",
        "`$maxMemoryUsed = 0",
        "`$maxGpuUtil = 0",
        "`$memoryActive = `$false",
        "",
        "while(`$true) {",
        "    Clear-Host",
        "    Write-Host '=== RTX 3090 GPU MONITOR - ' -NoNewline -ForegroundColor Cyan",
        "    Write-Host (Get-Date -Format 'HH:mm:ss') -NoNewline -ForegroundColor Cyan", 
        "    Write-Host ' ===' -ForegroundColor Cyan",
        "    Write-Host ''",
        "    ",
        "    `$gpu = Get-TargetGpuStats",
        "    if (`$gpu) {",
        "        # Update maximums",
        "        `$maxMemoryUsed = [math]::Max(`$maxMemoryUsed, `$gpu.MemoryUsedGB)",
        "        `$maxGpuUtil = [math]::Max(`$maxGpuUtil, `$gpu.GpuUtil)",
        "        ",
        "        # Determine status",
        "        if (`$gpu.MemoryUsedGB -gt 1.0) { `$memoryActive = `$true }",
        "        ",
        "        `$status = if (`$gpu.GpuUtil -gt 50) { '🔥 HEAVY LOAD' }",
        "                 elseif (`$gpu.GpuUtil -gt 10) { '⚡ PROCESSING' }",
        "                 elseif (`$gpu.MemoryUsedGB -gt 2.0) { '📊 MODEL LOADED' }",
        "                 elseif (`$gpu.MemoryUsedGB -gt 0.5) { '💾 LIGHT USAGE' }",
        "                 else { '💤 IDLE' }",
        "        ",
        "        `$statusColor = if (`$gpu.GpuUtil -gt 50) { 'Red' }",
        "                       elseif (`$gpu.GpuUtil -gt 10) { 'Yellow' }",
        "                       elseif (`$gpu.MemoryUsedGB -gt 1.0) { 'Green' }",
        "                       else { 'Gray' }",
        "        ",
        "        Write-Host '🎯 TARGET GPU: RTX 3090 (nvidia-smi GPU ' -NoNewline -ForegroundColor White",
        "        Write-Host `$gpu.Index -NoNewline -ForegroundColor Cyan",
        "        Write-Host ')' -ForegroundColor White",
        "        Write-Host ''",
        "        Write-Host '📊 CURRENT STATUS: ' -NoNewline -ForegroundColor White",
        "        Write-Host `$status -ForegroundColor `$statusColor",
        "        Write-Host ''",
        "        Write-Host '💾 MEMORY:' -ForegroundColor White",
        "        Write-Host `"   Used: `$(`$gpu.MemoryUsedGB) GB / `$(`$gpu.MemoryTotalGB) GB (`$(`$gpu.MemoryPercent)%)`" -ForegroundColor Cyan",
        "        Write-Host `"   Peak: `$maxMemoryUsed GB`" -ForegroundColor Yellow",
        "        Write-Host ''",
        "        Write-Host '⚡ UTILIZATION:' -ForegroundColor White",
        "        Write-Host `"   GPU: `$(`$gpu.GpuUtil)% (Peak: `$maxGpuUtil%)`" -ForegroundColor Cyan",
        "        Write-Host `"   Memory: `$(`$gpu.MemUtil)%`" -ForegroundColor Cyan",
        "        Write-Host `"   Temperature: `$(`$gpu.Temp)°C`" -ForegroundColor Cyan",
        "        Write-Host ''",
        "        ",
        "        # Activity indicator",
        "        if (`$memoryActive) {",
        "            Write-Host '✅ RTX 3090 HAS BEEN ACTIVE (Models have loaded)' -ForegroundColor Green",
        "        } else {",
        "            Write-Host '⏳ Waiting for model loading... (Memory usage will spike)' -ForegroundColor Yellow",
        "        }",
        "        ",
        "    } else {",
        "        Write-Host '❌ RTX 3090 not found or nvidia-smi error!' -ForegroundColor Red",
        "    }",
        "    ",
        "    Write-Host ''",
        "    Write-Host '🔧 CONFIGURATION:' -ForegroundColor White",
        "    Write-Host `"   CUDA_VISIBLE_DEVICES: `$env:CUDA_VISIBLE_DEVICES`" -ForegroundColor Gray",
        "    Write-Host `"   Target Device: cuda:0 → RTX 3090`" -ForegroundColor Gray",
        "    Write-Host ''",
        "    Write-Host `"🔄 Refreshing every $GpuMonitorInterval seconds...`" -ForegroundColor Gray",
        "    Start-Sleep $GpuMonitorInterval",
        "}"
    ) -join "`n"
    $path = Join-Path $env:TEMP "gpu-monitor-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $repoRoot; Title = "RTX 3090 Monitor" }
}

function New-OrchestratorPane {
    $content = @(
        "Set-Location -LiteralPath `"$repoRoot`"",
        "Write-Host '=== AI ORCHESTRATOR WITH PROGRESS MONITORING ===' -ForegroundColor Magenta",
        "Write-Host 'Starting AI processing with real-time progress tracking...' -ForegroundColor Yellow",
        "Write-Host 'Device: $gpuDevice | Processing Drive E integration' -ForegroundColor Cyan",
        "Write-Host ''",
        "Write-Host 'Waiting for backend to initialize...' -ForegroundColor Gray",
        "Start-Sleep 20",
        "Write-Host 'Testing backend connection...' -ForegroundColor Yellow",
        "for (`$i = 1; `$i -le 10; `$i++) {",
        "    try {",
        "        `$response = Invoke-WebRequest -Uri 'http://localhost:8000/health' -TimeoutSec 5 -ErrorAction Stop",
        "        Write-Host '✅ Backend is ready!' -ForegroundColor Green",
        "        break",
        "    } catch {",
        "        Write-Host `"⏳ Attempt `$i/10: Backend not ready, waiting...`" -ForegroundColor Yellow",
        "        Start-Sleep 5",
        "    }",
        "}",
        "Write-Host 'Starting AI orchestrator with GPU validation...' -ForegroundColor Green",
        "Write-Host ''",
        "Write-Host '🧪 Testing RTX 3090 access before processing...' -ForegroundColor Yellow",
        "& `"$pyExe`" -c `"",
        "import os, torch",
        "print(f'CUDA_VISIBLE_DEVICES: {os.environ.get(\\`"CUDA_VISIBLE_DEVICES\\`", \\`"Not set\\`")}')  ",
        "print(f'PyTorch CUDA available: {torch.cuda.is_available()}')",
        "if torch.cuda.is_available():",
        "    print(f'Device name: {torch.cuda.get_device_name(0)}') ",
        "    x = torch.randn(1000, 1000).cuda()",
        "    print(f'✅ RTX 3090 tensor allocation successful!')",
        "    del x",
        "    torch.cuda.empty_cache()",
        "else:",
        "    print('❌ CUDA not available!')",
        "`"",
        "Write-Host ''",
        "Write-Host '🚀 Starting AI orchestrator...' -ForegroundColor Green",
        "& `"$pyExe`" ai_orchestrator.py"
    ) -join "`n"
    $path = Join-Path $env:TEMP "orchestrator-pane-$PID.ps1"
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return @{ File = $path; Dir = $repoRoot; Title = "AI Orchestrator" }
}

# Create all pane specifications
$backendSpec = New-BackendPane
$gpuSpec = New-GpuMonitorPane  
$orchestratorSpec = New-OrchestratorPane

if ($UseWindowsTerminal) {
    # Create 3-pane layout: Backend (left), GPU Monitor (top right), Orchestrator (bottom right)
    $wtArgs = @(
        'new-tab', '--title', "`"$($backendSpec.Title)`"", '-d', "`"$($backendSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($backendSpec.File)`"",
        ';', 'split-pane', '-H', '--title', "`"$($gpuSpec.Title)`"", '-d', "`"$($gpuSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($gpuSpec.File)`"",
        ';', 'split-pane', '-V', '--title', "`"$($orchestratorSpec.Title)`"", '-d', "`"$($orchestratorSpec.Dir)`"", 'pwsh', '-NoExit', '-File', "`"$($orchestratorSpec.File)`""
    )
    
    Write-Host "🖥️ Launching Windows Terminal with 3-pane layout..." -ForegroundColor Green
    Start-Process wt -ArgumentList $wtArgs
    
    # Give Windows Terminal time to start
    Start-Sleep 3
} else {
    # Fallback: separate windows
    Write-Host "🖥️ Launching separate PowerShell windows..." -ForegroundColor Green
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $backendSpec.File) -WorkingDirectory $backendSpec.Dir
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $gpuSpec.File) -WorkingDirectory $gpuSpec.Dir
    Start-Process pwsh -ArgumentList @('-NoExit','-File', $orchestratorSpec.File) -WorkingDirectory $orchestratorSpec.Dir
}

Write-Host ""
Write-Host "🎯 VLM Photo Engine AI Monitoring Launched:" -ForegroundColor Green
Write-Host "  📊 Left Pane: Backend with Model Validation ($gpuDevice)" -ForegroundColor Cyan
Write-Host "  🖥️ Top Right: RTX 3090 Real-time Monitoring" -ForegroundColor Cyan
Write-Host "  🤖 Bottom Right: AI Orchestrator with GPU Testing" -ForegroundColor Cyan
Write-Host ""
Write-Host "📈 What to Watch For RTX 3090 Usage:" -ForegroundColor Yellow
Write-Host "  • Backend: LVFace/BLIP2 model loading messages" -ForegroundColor Gray
Write-Host "  • GPU Monitor: Memory spike from ~276MiB to 2-8GB during model loading" -ForegroundColor Gray
Write-Host "  • GPU Monitor: 🔥 HEAVY LOAD status during inference" -ForegroundColor Gray
Write-Host "  • Orchestrator: GPU validation test before processing starts" -ForegroundColor Gray
Write-Host ""
Write-Host "🔧 Current Configuration:" -ForegroundColor White
Write-Host "  CUDA_VISIBLE_DEVICES=$($env:CUDA_VISIBLE_DEVICES) (nvidia-smi RTX 3090 → cuda:0)" -ForegroundColor Cyan
Write-Host "  External Models: LVFace + BLIP2 with RTX 3090 targeting" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ Enhanced Monitoring Setup Complete! Watch RTX 3090 utilization! 🚀" -ForegroundColor Green
