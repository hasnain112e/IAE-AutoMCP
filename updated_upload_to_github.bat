@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Always run in this script's directory (repo root recommended)
cd /d "%~dp0"

set "LOG=%~dp0upload_log.txt"
echo ============================================================ > "%LOG%"
echo SAFE PUSH QUIET - LOG (%date% %time%)>> "%LOG%"
echo ============================================================>> "%LOG%"

echo [1/4] Preflight...
call :Run "where git"
if errorlevel 1 goto FAIL

call :Run "git rev-parse --is-inside-work-tree"
if errorlevel 1 goto FAIL

echo [2/4] Index clean (no delete)...
REM ensure .gitignore exists + minimum rules
if not exist .gitignore type nul > .gitignore
call :EnsureGitignoreLine ".env"
call :EnsureGitignoreLine ".env.*"
call :EnsureGitignoreLine "**/.env"
call :EnsureGitignoreLine "**/.env.*"
call :EnsureGitignoreLine "node_modules/"
call :EnsureGitignoreLine "**/node_modules/"
call :EnsureGitignoreLine ".venv/"
call :EnsureGitignoreLine "venv/"
call :EnsureGitignoreLine "env/"
call :EnsureGitignoreLine "ENV/"

REM untrack (NO deletion)
call :Run "git rm -r --cached node_modules"
call :Run "git rm -r --cached api_collector_frontend\node_modules"
call :Run "git rm -r --cached .venv"
call :Run "git rm -r --cached venv"
call :Run "git rm -r --cached env"
call :Run "git rm -r --cached ENV"
call :Run "git rm --cached .env"

REM reset staging
call :Run "git reset --mixed"
if errorlevel 1 goto FAIL

echo [3/4] Add + safety check...
call :Run "git add ."
if errorlevel 1 goto FAIL

REM block risky staged files
call :Run "git diff --cached --name-only"
type "%LOG%" | findstr /I /R "\\node_modules\\ \\.venv\\ \\venv\\ \\env\\ \\.env$ \\.env\." >nul 2>&1
if %errorlevel%==0 (
  echo [ERROR] Risky files staged! See upload_log.txt
  >> "%LOG%" echo [BLOCK] Risky items found in staging (see above list).
  goto FAIL
)

echo [4/4] Commit + push...
set /p MSG=Commit message (Enter = Safe update): 
if "%MSG%"=="" set "MSG=Safe update (no secrets)"

call :Run "git commit -m ""%MSG%"""
if errorlevel 1 (
  echo [ERROR] Commit failed (maybe nothing to commit). See upload_log.txt
  goto FAIL
)

for /f "tokens=*" %%i in ('git branch --show-current') do set "BR=%%i"
if "%BR%"=="" (
  echo [ERROR] Cannot detect branch. See upload_log.txt
  >> "%LOG%" echo [ERROR] Branch detection failed.
  goto FAIL
)

call :Run "git push -u origin %BR%"
if errorlevel 1 goto FAIL

echo [SUCCESS] Pushed on branch: %BR%
echo Log saved: %LOG%
pause
exit /b 0

:FAIL
echo.
echo [FAILED] Something failed. Log saved: %LOG%
echo Open upload_log.txt and paste last 20 lines here.
pause
exit /b 1

REM ---------------- Helpers ----------------
:Run
REM Runs a command, logs output+errors to file, returns same errorlevel
>> "%LOG%" echo.
>> "%LOG%" echo === RUN: %~1
cmd /c %~1 >> "%LOG%" 2>&1
exit /b %errorlevel%

:EnsureGitignoreLine
set "LINE=%~1"
findstr /x /c:"%LINE%" .gitignore >nul 2>&1
if %errorlevel% neq 0 echo %LINE%>> .gitignore
exit /b 0
