@echo off
title IAE-AutoMCP Agents
color 0B
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call .venv\Scripts\activate.bat
python launch_agents.py


