@echo off
title MCP Generation System Launcher
color 0A
echo.
echo ================================================
echo   MCP Server Code Generation System
echo   Production Version - Ready for Client Demo
echo ================================================
echo.

REM Check if .env exists
if not exist .env (
    color 0C
    echo [ERROR] .env file not found!
    echo.
    echo Please create a .env file with:
    echo   OPENAI_API_KEY=sk-your-openai-key-here
    echo.
    pause
    exit /b 1
)

REM Check for OpenAI key in .env
findstr /C:"OPENAI_API_KEY" .env >nul
if errorlevel 1 (
    color 0C
    echo [ERROR] OPENAI_API_KEY not found in .env file!
    echo.
    echo Please add to .env:
    echo   OPENAI_API_KEY=sk-your-openai-key-here
    echo.
    pause
    exit /b 1
)

echo [1/6] Checking dependencies...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.8+
    pause
    exit /b 1
)

echo [2/6] Stopping any existing services...
taskkill /F /FI "WINDOWTITLE eq *Agent*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Backend API*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Frontend*" 2>nul
timeout /t 2 /nobreak >nul

echo [3/6] Starting Backend Agents...
start "Orchestrator Agent" cmd /k "python -m agents.orchestrator.orchestrator_agent"
timeout /t 3 /nobreak >nul
start "Generator Agent (OpenAI)" cmd /k "python -m agents.generator.generator_agent"
timeout /t 3 /nobreak >nul
start "Validator Agent" cmd /k "python -m agents.validator.validator_agent"
timeout /t 3 /nobreak >nul
start "UI Controller Agent" cmd /k "python -m agents.ui_controller.ui_controller_agent"
timeout /t 3 /nobreak >nul

echo [4/6] Starting Backend API...
start "Backend API Server" cmd /k "cd api_collector_backend && uvicorn app:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul

echo [5/6] Starting Frontend...
cd api_collector_frontend
start "Frontend Dev Server" cmd /k "npm run dev"
cd ..
timeout /t 5 /nobreak >nul

echo [6/6] System startup complete!
echo.
color 0A
echo ================================================
echo   System Ready!
echo ================================================
echo.
echo   Frontend UI:     http://localhost:5173
echo   Backend API:     http://localhost:8000
echo   Orchestrator:    http://localhost:8100
echo   Generator:       http://localhost:8101 (OpenAI)
echo   Validator:       http://localhost:8002
echo.
echo   Open your browser to: http://localhost:5173
echo.
echo ================================================
echo.
pause

