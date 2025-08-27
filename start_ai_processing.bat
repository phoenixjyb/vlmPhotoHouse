@echo off
REM VLM Photo Engine AI Processing Quick Start
REM Make sure to start the backend server first!

echo VLM Photo Engine AI Processing
echo ================================

echo.
echo Starting backend server...
start "VLM Backend" cmd /k "cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo Waiting for backend to start...
timeout /t 10

echo.
echo Running AI processing pipeline...
python ai_orchestrator.py --max-dirs 5 --max-caption-tasks 20 --max-ai-tasks 50

echo.
echo Showing final status...
python ai_orchestrator.py --status

echo.
echo AI processing complete!
pause
