@echo off
title Stopping All Services

echo.
echo ================================================================================
echo                    Stopping IAE-AutoMCP System
echo ================================================================================
echo.

echo Stopping all services...
echo.

:: Kill the 3 main terminal windows
echo [1/3] Stopping All Agents...
for /f "tokens=2" %%i in ('tasklist /fi "windowtitle eq IAE-AutoMCP Agents" ^| find "cmd.exe"') do taskkill /pid %%i /f >nul 2>&1

echo [2/3] Stopping Backend API...
for /f "tokens=2" %%i in ('tasklist /fi "windowtitle eq IAE-AutoMCP Backend" ^| find "cmd.exe"') do taskkill /pid %%i /f >nul 2>&1

echo [3/3] Stopping Frontend...
for /f "tokens=2" %%i in ('tasklist /fi "windowtitle eq IAE-AutoMCP Frontend" ^| find "cmd.exe"') do taskkill /pid %%i /f >nul 2>&1

:: Also kill any remaining Python/Node processes on those ports (backup)
echo.
echo Cleaning up any remaining processes...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8100') do taskkill /pid %%a /f >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8101') do taskkill /pid %%a /f >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8102') do taskkill /pid %%a /f >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8002') do taskkill /pid %%a /f >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /pid %%a /f >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173') do taskkill /pid %%a /f >nul 2>&1

echo.
echo [SUCCESS] All services stopped!
echo.
pause
