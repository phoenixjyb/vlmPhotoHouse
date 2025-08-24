# Enhanced tmux-style Script with Auto-Cleanup

## 🚀 Quick Start Commands

```powershell
# Standard launch with auto-cleanup (RECOMMENDED)
.\scripts\start-dev-multiproc.ps1 -Preset RTX3090 -UseWindowsTerminal

# Launch without cleanup (if you want to keep existing services)
.\scripts\start-dev-multiproc.ps1 -Preset RTX3090 -UseWindowsTerminal -NoCleanup

# Custom ports with cleanup
.\scripts\start-dev-multiproc.ps1 -Preset RTX3090 -UseWindowsTerminal -ApiPort 8003 -VoicePort 8004
```

## 🧹 Auto-Cleanup Features

### What Gets Cleaned Up Automatically:
1. **All Windows Terminal instances** - Ensures fresh window layout
2. **Processes using target ports** - Prevents port conflicts
3. **Background services** - Cleans up previous dev sessions

### Ports Checked for Cleanup:
- API Port (default: 8002, configurable with `-ApiPort`)
- Voice Port (default: 8001, configurable with `-VoicePort`)  
- Alternative port 8000 (common fallback)

### Process Cleanup:
- **WindowsTerminal.exe** - All instances closed
- **python.exe** - Any processes using target ports
- **uvicorn** - Previous API server instances

## 🎛️ Script Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `-Preset` | None | `RTX3090` or `LowVRAM` optimization |
| `-UseWindowsTerminal` | False | Enable 2x2 terminal layout |
| `-NoCleanup` | False | Skip automatic cleanup |
| `-ApiPort` | 8002 | VLM Photo Engine port |
| `-VoicePort` | 8001 | Voice service port |
| `-KillExisting` | N/A | Deprecated (cleanup is now automatic) |

## 🔄 Cleanup Process Flow

```
1. 🔄 Scanning for Windows Terminal instances...
2. ✅ Closed X existing instances  
3. 🔄 Checking ports 8001, 8002, 8000...
4. 🔴 Stopping conflicting processes...
5. ✅ Port cleanup completed
6. 🚀 Launching fresh 2x2 layout...
```

## 🛠️ Troubleshooting

### If cleanup fails:
```powershell
# Manual cleanup commands
Get-Process WindowsTerminal | Stop-Process -Force
Get-Process python | Where-Object {$_.ProcessName -like "*uvicorn*"} | Stop-Process -Force

# Check what's using a port
Get-NetTCPConnection -LocalPort 8002 -State Listen
```

### If you need to preserve existing services:
```powershell
.\scripts\start-dev-multiproc.ps1 -Preset RTX3090 -UseWindowsTerminal -NoCleanup
```

## 🎯 Layout Result

After successful launch, you'll have a clean 2x2 Windows Terminal layout:

```
┌─────────────────────────┬─────────────────────────┐
│    VLM Photo Engine     │    Voice Service ASR    │
│      (Port 8002)        │      (Port 8001)        │
│ ✅ Fresh Instance       │ 🎙️ Clean Environment    │
├─────────────────────────┼─────────────────────────┤
│   LVFace Environment    │   TTS Environment       │
│      (Isolated)         │   (RTX 3090 Optimized)  │
│ 🧠 Ready for Testing    │ ⚡ Ready for Synthesis   │
└─────────────────────────┴─────────────────────────┘
```

All environments use the optimized workload-specific Python/PyTorch configurations from your completed upgrade matrix!
