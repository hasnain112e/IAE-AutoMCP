@echo off
setlocal enabledelayedexpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
pushd "%ROOT%"

::: =============================================================================
::: IAE-AutoMCP Integrated System - Simplified One-Click Launcher
::: =============================================================================

title IAE-AutoMCP System Launcher

echo.
echo ================================================================================
echo                    IAE-AutoMCP Integrated Agentic System
echo                          One-Click Automatic Launcher
echo ================================================================================
echo.

::: Check if Python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10 or higher.
    pause
    exit /b 1
)

::: Check if Node.js is installed
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found! Please install Node.js 18+ LTS.
    pause
    exit /b 1
)

::: Check if Virtual Environment exists (create if missing)
if exist ".venv\Scripts\activate.bat" (
    echo [STEP 1/7] Virtual environment found.
) else (
    echo [STEP 1/7] Virtual environment not found. Creating .venv...
    python -m venv .venv
)

::: Activate virtual environment
echo [STEP 2/7] Activating Python virtual environment...
call .venv\Scripts\activate.bat

::: Upgrade pip
echo [STEP 3/7] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

::: Install Python dependencies
echo [STEP 4/7] Checking Python dependencies...
if exist ".venv\Scripts\uvicorn.exe" (
    echo Python dependencies already installed. Skipping pip install.
) else (
    echo Installing Python dependencies...
    pip install -r requirements.txt
)


::: Check if .env file exists
if not exist ".env" (
    echo [WARNING] .env file not found. Creating template...
    (
        echo # API Keys for IAE-AutoMCP System
        echo GOOGLE_API_KEY=your-google-api-key-here
        echo OPENAI_API_KEY=your-openai-api-key-here
    ) > .env
    echo [INFO] Please edit .env file with your API keys, then run this script again.
    notepad .env
    pause
    exit /b 1
)

::: Check if node_modules exists
if not exist "api_collector_frontend\node_modules\" (
    echo [INFO] Installing frontend dependencies...
    cd api_collector_frontend
    call npm install
    cd ..
)

echo.
echo ================================================================================
echo                     Starting Services (4 Terminals)
echo ================================================================================
echo.

::: Start all agents in ONE terminal
echo [STEP 5/7] Starting All Agents (Orchestrator, Generator, Validator, UI Controller)...
set "AGENTS_BAT=%ROOT%\_start_agents.bat"
start "IAE-AutoMCP Agents" cmd /k "!AGENTS_BAT!"
ping -n 4 127.0.0.1 >nul

::: Start backend API
echo [STEP 6/7] Starting Backend API (Port 8000)...
set "BACKEND_BAT=%ROOT%\_start_backend.bat"
start "IAE-AutoMCP Backend" cmd /k "!BACKEND_BAT!"
ping -n 4 127.0.0.1 >nul

::: Wait for backend to be ready
echo Waiting for backend to be ready...
set BACKEND_READY=0
set MAX_ATTEMPTS=30
set ATTEMPT=0

:check_backend
set /a ATTEMPT+=1
echo Checking backend readiness (attempt %ATTEMPT%/%MAX_ATTEMPTS%)...

::: Try using PowerShell Invoke-WebRequest (works on Windows)
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2 -UseBasicParsing; if ($response.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1

if %errorlevel% equ 0 (
    echo [SUCCESS] Backend is ready!
    set BACKEND_READY=1
    goto backend_ready
)

if %ATTEMPT% geq %MAX_ATTEMPTS% (
    echo [WARNING] Backend not ready after %MAX_ATTEMPTS% attempts. Continuing anyway...
    goto backend_ready
)

ping -n 2 127.0.0.1 >nul
goto check_backend

:backend_ready
echo.

::: Start frontend (this will auto-open browser)
echo [STEP 7/7] Starting Frontend (Port 5173)...
set "FRONTEND_BAT=%ROOT%\_start_frontend.bat"
start "IAE-AutoMCP Frontend" cmd /k "!FRONTEND_BAT!"

::: Wait for frontend to be ready
echo Waiting for frontend to be ready...
set FRONTEND_READY=0
set FRONTEND_MAX_ATTEMPTS=30
set FRONTEND_ATTEMPT=0

:check_frontend
set /a FRONTEND_ATTEMPT+=1
echo Checking frontend readiness (attempt %FRONTEND_ATTEMPT%/%FRONTEND_MAX_ATTEMPTS%)...

::: Try using PowerShell Invoke-WebRequest (works on Windows)
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -TimeoutSec 2 -UseBasicParsing; if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1

if %errorlevel% equ 0 (
    echo [SUCCESS] Frontend is ready!
    set FRONTEND_READY=1
    goto frontend_ready
)

if %FRONTEND_ATTEMPT% geq %FRONTEND_MAX_ATTEMPTS% (
    echo [WARNING] Frontend not ready after %FRONTEND_MAX_ATTEMPTS% attempts.
    echo [WARNING] Check the "IAE-AutoMCP Frontend" window for errors.
    goto frontend_ready
)

ping -n 2 127.0.0.1 >nul
goto check_frontend

:frontend_ready

echo.
echo ================================================================================
echo                          ALL SERVICES STARTED!
echo ================================================================================
echo.
echo   🤖 All Agents:       Running (Orchestrator, Generator, Validator, UI Controller)
echo   🔌 Backend API:      http://localhost:8000
echo   🌐 Frontend UI:      http://localhost:5173
echo.
echo   Note: 4 terminal windows opened (Agents, Backend, Frontend, Launcher)!
echo.
echo ================================================================================
echo.
echo Opening browser...
start http://localhost:5173

echo.
echo ================================================================================
echo                     System is Ready!
echo ================================================================================
echo.
echo The web UI will show you everything happening in real-time.
echo Just click "Start Pipeline" and watch the magic!
echo.
echo To stop all services: Run STOP_EVERYTHING.bat
echo.
popd


