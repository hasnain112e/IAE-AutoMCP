@echo off
title AutoMCP – Full System Launcher
echo ============================================
echo  Starting AutoMCP Services
echo ============================================

REM -------------------------------------------------------
REM 1. Create Python virtual environment if not present
REM -------------------------------------------------------
IF NOT EXIST ".venv" (
    echo Creating Python virtual environment...
    python -m venv .venv
)

REM -------------------------------------------------------
REM 2. Activate Python virtual environment
REM -------------------------------------------------------
SET VENV_ACTIVATE=%CD%\.venv\Scripts\activate.bat

IF EXIST "%VENV_ACTIVATE%" (
    echo Activating virtual environment...
    CALL "%VENV_ACTIVATE%"
) ELSE (
    echo ERROR: Virtual environment activation script not found!
    PAUSE
    EXIT /B
)

REM -------------------------------------------------------
REM 3. Install Python dependencies
REM -------------------------------------------------------
REM Upgrade pip, setuptools, and wheel
python -m pip install --upgrade pip setuptools wheel
echo Installing required Python packages...
pip install fastapi uvicorn requests python-dotenv openai pyyaml beautifulsoup4 python-multipart streamlit pip pandas playwright


REM -------------------------------------------------------
REM 3.5 Install Playwright browsers (crucial for JavaScript websites)
REM -------------------------------------------------------
echo Installing Playwright browsers (this may take a minute)...
playwright install chromium
echo Playwright browsers installed.


REM -------------------------------------------------------
REM 4. Check Node.js installation for frontend
REM -------------------------------------------------------
node -v >nul 2>&1
IF ERRORLEVEL 1 (
    echo.
    echo  ERROR: Node.js is NOT installed!
    echo  Please install Node.js from https://nodejs.org/
    echo  Then re-run this script.
    echo.
    PAUSE
    EXIT /B
)

REM -------------------------------------------------------
REM 5. Start FastAPI backend in NEW window
REM -------------------------------------------------------
echo Starting FastAPI backend...
start cmd /k "CALL %VENV_ACTIVATE% && set PYTHONPATH=%CD% && uvicorn api_collector_backend.app:app --reload --port 8000"

REM -------------------------------------------------------
REM 6. Start Frontend in NEW window
REM -------------------------------------------------------
echo Starting frontend...
start cmd /k "cd api_collector_frontend && npm install && npm run dev"

REM -------------------------------------------------------
REM 7. Start Streamlit UI in NEW window
REM -------------------------------------------------------
echo Starting Streamlit UI...
start cmd /k "streamlit run chat_ui.py"

REM -------------------------------------------------------
REM 8. Open URLs AFTER everything has started
REM -------------------------------------------------------
echo Waiting 5 seconds for services to boot...
timeout /t 5 >nul

start "" http://localhost:5173

echo ============================================
echo  All services started successfully!
echo ============================================

pause

