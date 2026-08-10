@echo off
title IAE-AutoMCP Backend
color 0E
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call .venv\Scripts\activate.bat
python -m uvicorn api_collector_backend.app:app --reload --host 127.0.0.1 --port 8000


