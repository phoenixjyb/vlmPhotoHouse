@echo off
echo Starting caption pipeline test...
cd /d "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse"
call .venv\Scripts\activate.bat
python test_caption_pipeline.py
echo.
echo Test completed. Press any key to close...
pause > nul
