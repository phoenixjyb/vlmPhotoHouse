# VLM Photo Engine AI Processing Quick Start
Write-Host "VLM Photo Engine AI Processing" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

Write-Host "`nStarting backend server..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

Write-Host "Waiting for backend to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host "`nRunning AI processing pipeline..." -ForegroundColor Yellow
python ai_orchestrator.py --max-dirs 5 --max-caption-tasks 20 --max-ai-tasks 50

Write-Host "`nShowing final status..." -ForegroundColor Yellow
python ai_orchestrator.py --status

Write-Host "`nAI processing complete!" -ForegroundColor Green
Read-Host "Press Enter to exit"
