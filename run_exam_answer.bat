@echo off
cd /d "%~dp0"
echo ============================================================
echo   Chaoxing Exam AI Answer Helper
echo ============================================================
echo.
echo   Starting... Browser will open shortly.
echo   DO NOT close this window.
echo.
echo   Note: Exam will NOT be auto-submitted.
echo   Check answers in browser before clicking submit.
echo.
python chaoxing_exam_answer.py --mode answer
echo.
echo ============================================================
echo   Script ended. Press any key to close.
echo ============================================================
pause >nul
