@echo off
cd /d "%~dp0"
echo ============================================================
echo   超星学习通 考试 AI 答题助手
echo ============================================================
echo.
echo   正在启动，浏览器窗口即将弹出...
echo   不要关闭此窗口！
echo.
echo   使用前请确保：
echo   1. 已安装依赖: pip install -r requirements.txt
echo   2. 已安装浏览器: playwright install chromium
echo   3. 已设置 API Key 和考试 URL（编辑脚本或环境变量）
echo.
echo   注意：答题完成后不会自动交卷，
echo   请在浏览器中手动检查答案后再点击"交卷"。
echo.
python chaoxing_exam_answer.py --mode answer
echo.
echo ============================================================
echo   脚本已结束。按任意键关闭此窗口。
echo ============================================================
pause >nul
