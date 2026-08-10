@echo off
title IAE-AutoMCP Launcher
color 0A
cd /d "%~dp0"

echo.
echo ================================================================
echo         IAE-AutoMCP System - Starting All Services
echo ================================================================
echo.

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: ── 1. MongoDB ────────────────────────────────────────────────────
echo [1/4] Checking MongoDB...
sc query MongoDB >nul 2>&1
if %errorlevel% equ 0 (
    sc start MongoDB >nul 2>&1
    echo       MongoDB service started.
) else (
    net start MongoDB >nul 2>&1
    if %errorlevel% neq 0 (
        echo       MongoDB already running or managed externally.
    )
)
timeout /t 2 /nobreak >nul

:: ── 2. Backend API (port 8000) ────────────────────────────────────
echo [2/4] Starting Backend API on port 8000...
start "Backend API :8000" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && python -m uvicorn api_collector_backend.app:app --host 127.0.0.1 --port 8000"
timeout /t 5 /nobreak >nul

:: ── 3. All Agents (8100 Orchestrator, 8101 Generator, 8002 Validator, 8102 UI) ──
echo [3/4] Starting Agents (Orchestrator, Generator, Validator, UI Controller)...
start "Agents" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && python launch_agents.py"
timeout /t 8 /nobreak >nul

:: ── 4. Frontend (port 5173) ───────────────────────────────────────
echo [4/4] Starting Frontend on port 5173...
start "Frontend :5173" cmd /k "cd /d "%~dp0\api_collector_frontend" && npm run dev"
timeout /t 8 /nobreak >nul

:: ── Open browser ──────────────────────────────────────────────────
echo.
echo ================================================================
echo   All services started!
echo.
echo   Frontend  →  http://localhost:5173
echo   Backend   →  http://localhost:8000
echo   Agents    →  Orchestrator:8100  Generator:8101  UI:8102
echo ================================================================
echo.
echo Opening browser...
start http://localhost:5173

echo.
echo 4 terminal windows are running. Close this window anytime.
echo To stop everything, close those 4 windows or run STOP_ALL.bat
echo.
pause
