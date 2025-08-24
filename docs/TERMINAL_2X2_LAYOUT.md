# Windows Terminal 2x2 Layout Configuration

## 🎯 Visual Layout

```
┌─────────────────────────┬─────────────────────────┐
│    VLM Photo Engine     │    Voice Service ASR    │
│      (Port 8002)        │      (Port 8001)        │
│                         │                         │
│ Python 3.12.10          │ Python 3.11.9           │
│ PyTorch 2.8.0+cu126     │ PyTorch 2.8.0+cu126     │
│ RTX 3090 CUDA:0         │ RTX 3090 CUDA:0         │
│                         │                         │
│ • FastAPI Backend       │ • OpenAI Whisper        │
│ • Face Recognition      │ • LLMyTranslate          │
│ • BLIP2 Caption         │ • ASR Processing         │
│ • Vector Search         │ • Audio Pipeline         │
├─────────────────────────┼─────────────────────────┤
│   LVFace Environment    │   TTS Environment       │
│      (Isolated)         │   (RTX 3090 Optimized)  │
│                         │                         │
│ Python 3.11.9           │ Python 3.12.10          │
│ PyTorch 2.6.0+cu124     │ PyTorch 2.8.0+cu126     │
│ Legacy Compatible       │ RTX 3090 CUDA:0         │
│                         │                         │
│ • ONNX Runtime          │ • Coqui TTS 0.27.0      │
│ • InsightFace           │ • RTX 3090 Synthesis    │
│ • Face Embeddings       │ • RTF 0.267              │
│ • 128-dim Output        │ • Audio Generation       │
└─────────────────────────┴─────────────────────────┘
```

## 🚀 Launch Command

```powershell
.\scripts\start-dev-multiproc.ps1 -Preset RTX3090 -UseWindowsTerminal
```

## 🎛️ Environment Details

### Top Left: VLM Photo Engine
- **Purpose**: Main API server and ML pipeline
- **Port**: 8002 (configurable with -ApiPort)
- **Environment**: Optimized for LLMs + BLIP-2 + CLIP workload
- **GPU Usage**: RTX 3090 (cuda:0) for all ML operations

### Top Right: Voice Service ASR  
- **Purpose**: Speech recognition and translation
- **Port**: 8001 (configurable with -VoicePort)
- **Environment**: Optimized for Whisper ASR workload
- **GPU Usage**: RTX 3090 (cuda:0) for audio processing

### Bottom Left: LVFace Environment
- **Purpose**: Isolated face recognition testing
- **Environment**: Legacy-compatible for ONNX operations
- **GPU Usage**: RTX 3090 with CUDA 12.4 compatibility

### Bottom Right: TTS Environment
- **Purpose**: Text-to-speech synthesis
- **Environment**: Optimized for Coqui TTS workload  
- **GPU Usage**: RTX 3090 (cuda:0) for neural synthesis

## 🔧 Workspace Management

### Switch Between Panes
- **Alt + Arrow Keys**: Navigate between panes
- **Ctrl + Shift + Arrow**: Move panes
- **Ctrl + Shift + D**: Duplicate pane

### Environment Activation
Each pane automatically activates its optimized virtual environment:
- `.venv` (VLM Photo Engine)
- `.venv-asr-311` (Voice Service)  
- `.venv-lvface-311` (LVFace)
- `.venv-tts` (TTS Service)

### Service Status Check
All services can be monitored via their respective terminals and APIs.
