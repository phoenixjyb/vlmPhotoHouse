# PowerShell Service Command Reference

## ✅ Correct Command Patterns

### 1. Single Directory + Command
```powershell
# CORRECT: Change directory first, then run command
Set-Location "C:\path\to\directory"
.\script.exe args

# OR use full path
C:\path\to\directory\script.exe args
```

### 2. Compound Commands (Environment + Service)
```powershell
# CORRECT: Separate statements with semicolons
$env:VAR1="value1"; $env:VAR2="value2"; .\script.exe

# WRONG: Don't mix assignment operators
$env:VAR="value" && .\script.exe  # This fails in PowerShell
```

### 3. Background Services
```powershell
# CORRECT: Use Start-Process for true background
Start-Process -FilePath "python.exe" -ArgumentList "script.py" -WorkingDirectory "C:\path"

# OR: Use & operator for job-like behavior
& python.exe script.py
```

## 🚀 Working Service Commands

### VLM Photo Engine (Port 8000)
```powershell
Set-Location "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse"
$env:VOICE_ENABLED="true"
$env:VOICE_EXTERNAL_BASE_URL="http://127.0.0.1:8001"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### LLMyTranslate Main Service (Port 8001)
```powershell
Set-Location "C:\Users\yanbo\wSpace\llmytranslate"
.\.venv-asr-311\Scripts\python.exe run.py
```

### LVFace Service (if needed)
```powershell
Set-Location "C:\Users\yanbo\wSpace\vlm-photo-engine\LVFace"
.\.venv-lvface-311\Scripts\python.exe main.py
```

## 🔧 Common Issues Fixed

1. **Directory Context**: Always use `Set-Location` first
2. **Environment Variables**: Set them before the command, not in compound statements  
3. **Path Separators**: Use backslashes in Windows paths
4. **Relative Paths**: Use `.\` prefix for executables in current directory
