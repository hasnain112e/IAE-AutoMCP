@echo off
title AI Database Exploration Agent (port 8010)
color 0A
cd /d "%~dp0"

echo ============================================================
echo  AI Database Exploration Agent
echo  Starting on http://127.0.0.1:8010
echo  Docs: http://127.0.0.1:8010/ai-agent/docs
echo ============================================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo WARNING: .venv not found, using system Python
)

python -m uvicorn ai_agent.main:app --host 127.0.0.1 --port 8010 --workers 1
pause
