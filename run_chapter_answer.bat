@echo off
cd /d "%~dp0"
echo ============================================================
echo   Chaoxing Chapter AI Answer Helper
echo ============================================================
echo.
echo   Starting... Browser will open shortly.
echo   DO NOT close this window.
echo.
python chaoxing_ai_answer.py --mode answer
echo.
echo ============================================================
echo   Script ended. Press any key to close.
echo ============================================================
pause >nul
