# Quick Start: Dev Stack (Windows)

Bring up API, model helpers, and voice (LLMyTranslate) with one command.

## Prerequisites
- Windows Terminal installed (optional but recommended)
- Python envs ready:
  - Backend deps installed (see `backend/requirements.txt`)
  - LLMyTranslate checked out at `C:\Users\yanbo\wSpace\llmytranslate` (or installed as a package)
- Free ports: API 8002, Voice 8001
- Localhost excluded from VPN/proxy (127.0.0.1 DIRECT)

## One‑liner (recommended)
This opens a tmux‑like Windows Terminal with 4 panes: API, LVFace, Caption, Voice.

```powershell
# From repo root: C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
```

Defaults:
- API at http://127.0.0.1:8002
- Voice (LLMyTranslate) at http://127.0.0.1:8001
- API pane env auto-set if not present:
  - `VOICE_ENABLED=true`
  - `VOICE_EXTERNAL_BASE_URL=http://127.0.0.1:8001`
  - `VOICE_TTS_PATH=/api/tts/synthesize`

Verify:
```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8002/health' -UseBasicParsing
Invoke-WebRequest -Uri 'http://127.0.0.1:8001/api/voice-chat/health' -UseBasicParsing
Invoke-WebRequest -Uri 'http://127.0.0.1:8002/voice/health' -UseBasicParsing
```

Open UI:
- Main: http://127.0.0.1:8002/ui
- Voice demo: http://127.0.0.1:8002/voice/demo

## Enable TTS
By default, if the upstream service doesn't return audio, the API falls back to JSON. You can enable audio in two ways:

1) Upstream LLMyTranslate TTS
- Ensure LLMyTranslate exposes TTS at `/api/tts/synthesize` (default). If different, set `VOICE_TTS_PATH` accordingly.
- Verify capabilities show `tts.available=true`:
```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8001/api/voice-chat/capabilities' -UseBasicParsing | Select-Object -ExpandProperty Content
```

2) Local Piper fallback (Windows)
- Install Piper (download piper.exe) and a voice model `.onnx`.
- Add to repo root `.env` (or export in the API pane):
```ini
TTS_FALLBACK_PROVIDER=piper
PIPER_EXE_PATH=C:\path\to\piper.exe
PIPER_MODEL_PATH=C:\path\to\voices\en_US-libritts-high.onnx
```
- Restart the API pane. When external TTS has no audio, the API will synthesize WAV via Piper.

Verify TTS (expect audio):
```powershell
$body = @{ text = 'Hello from PhotoHouse'; language = 'en'; speed = 1.0 } | ConvertTo-Json
Invoke-WebRequest -Uri 'http://127.0.0.1:8002/voice/tts' -Method Post -ContentType 'application/json' -Body $body -OutFile .\tts.wav
Test-Path .\tts.wav; (Get-Item .\tts.wav).Length
```

## Verify ASR (Speech-to-Text)
- Browser: open the Voice demo and use the “Microphone Transcribe” section; results appear as JSON.
- API: send a short audio sample (webm/wav) to /voice/transcribe:
```powershell
# Example using a local file sample.webm
$fd = New-Object System.Net.Http.MultipartFormDataContent
$fileContent = New-Object System.Net.Http.StreamContent([System.IO.File]::OpenRead("sample.webm"))
$fileContent.Headers.ContentType = 'audio/webm'
$fd.Add($fileContent, 'file', 'sample.webm')
$client = New-Object System.Net.Http.HttpClient
($client.PostAsync('http://127.0.0.1:8002/voice/transcribe', $fd).Result.Content.ReadAsStringAsync().Result)
```

## Manual startup (no Windows Terminal)
1) LLMyTranslate (choose one):
```powershell
# Repo mode (preferred if src\main.py exists)
cd C:\Users\yanbo\wSpace\llmytranslate
.\.venv\Scripts\Activate.ps1
$py = ".\.venv\Scripts\python.exe"
& "$py" -m uvicorn src.main:app --host 127.0.0.1 --port 8001

# Package mode
# & "$py" -m llmytranslate --host 127.0.0.1 --port 8001
```

2) Backend API:
```powershell
cd C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse\backend
$env:VOICE_ENABLED = 'true'
$env:VOICE_EXTERNAL_BASE_URL = 'http://127.0.0.1:8001'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

## .env settings (repo root)
```ini
VOICE_ENABLED=true
VOICE_EXTERNAL_BASE_URL=http://127.0.0.1:8001
VOICE_TTS_PATH=/api/tts/synthesize
TTS_FALLBACK_PROVIDER=none
# For Piper fallback on Windows (optional)
# TTS_FALLBACK_PROVIDER=piper
# PIPER_EXE_PATH=C:\tools\piper\piper.exe
# PIPER_MODEL_PATH=C:\tools\piper\voices\en_US-libritts-high.onnx
```

## Troubleshooting
- “-m not recognized”: ensure `$py` is set before `-m`.
```powershell
$py = ".\.venv\Scripts\python.exe"; & "$py" -m uvicorn src.main:app --host 127.0.0.1 --port 8001
```
- Port busy: choose another `-VoicePort` and the launcher sets VOICE_EXTERNAL_BASE_URL for API automatically.
- VPN/Clash: make 127.0.0.1 DIRECT (add 127.0.0.0/8, ::1 to DIRECT). Set `no_proxy=127.0.0.1,localhost` if you export HTTP(S)_PROXY for model downloads.
- Clean restart:
```powershell
foreach ($p in 8002,8001) { try { Get-NetTCPConnection -LocalPort $p -State Listen | Select -Expand OwningProcess -Unique | % { Stop-Process -Id $_ -Force } } catch {} }
.\scripts\start-dev-multiproc.ps1 -UseWindowsTerminal -KillExisting
```
