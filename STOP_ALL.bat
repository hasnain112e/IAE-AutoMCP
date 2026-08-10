@echo off
title Stop All Services
color 0C
echo.
echo Stopping all IAE-AutoMCP services...
echo.

:: Kill Python processes (Backend + Agents)
taskkill /f /im python.exe >nul 2>&1
echo [OK] Python processes stopped.

:: Kill Node.js (Frontend)
taskkill /f /im node.exe >nul 2>&1
echo [OK] Node.js stopped.

echo.
echo All services stopped.
pause
