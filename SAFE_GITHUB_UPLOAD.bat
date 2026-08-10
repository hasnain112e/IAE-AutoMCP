@echo off
REM Safe GitHub Upload - Ensures .env and venv are NOT uploaded
echo ============================================================
echo Safe GitHub Upload Script
echo Ensures .env and venv are NOT uploaded
echo ============================================================
echo.

REM Check if .env is tracked
git ls-files | findstr /i ".env" >nul
if %errorlevel% == 0 (
    echo [WARNING] .env is tracked in git. Removing from tracking...
    git rm --cached .env 2>nul
    echo .env removed from tracking (file kept locally)
    echo.
)

REM Check if venv is tracked
git ls-files | findstr /i "venv" >nul
if %errorlevel% == 0 (
    echo [WARNING] venv is tracked in git. Removing from tracking...
    git rm --cached -r .venv 2>nul
    git rm --cached -r venv 2>nul
    echo venv removed from tracking (directory kept locally)
    echo.
)

REM Verify .env is ignored
echo [1/5] Verifying .env is ignored...
git check-ignore .env >nul
if %errorlevel% == 0 (
    echo [OK] .env is properly ignored
) else (
    echo [ERROR] .env is NOT ignored! Check .gitignore
    pause
    exit /b 1
)

REM Verify venv is ignored
echo [2/5] Verifying venv is ignored...
git check-ignore venv .venv >nul
if %errorlevel% == 0 (
    echo [OK] venv is properly ignored
) else (
    echo [WARNING] venv might not be ignored (check .gitignore)
)

REM Show what will be committed
echo.
echo [3/5] Files to be committed (excluding .env and venv):
git status --short | findstr /v /i ".env venv node_modules"
echo.

REM Ask for confirmation
echo [4/5] Ready to commit and push?
echo Press any key to continue, or Ctrl+C to cancel...
pause >nul

REM Add all files (respects .gitignore)
echo.
echo [5/5] Adding files (respects .gitignore)...
git add .

REM Verify .env is NOT in staging
git diff --cached --name-only | findstr /i ".env" >nul
if %errorlevel% == 0 (
    echo [ERROR] .env is in staging area! Aborting.
    git reset
    pause
    exit /b 1
)

REM Commit
echo Committing changes...
git commit -m "Add Super Validator with LLM support, workflow guides, and QA results" -m "Added Super Validator with three-layer validation (Static, LLM, Dynamic)" -m "Added comprehensive workflow guides and documentation" -m "Added QA testing results and test guides" -m "Updated MCP generator with validator integration" -m "Fixed model compatibility issues" -m "Added complete workflow from URL to MCP server"

REM Get current branch name
for /f "tokens=*" %%i in ('git branch --show-current') do set CURRENT_BRANCH=%%i
if "%CURRENT_BRANCH%"=="" (
    echo [WARNING] Could not detect current branch. Trying to get from git status...
    for /f "tokens=2" %%i in ('git status ^| findstr /i "On branch"') do set CURRENT_BRANCH=%%i
)

if "%CURRENT_BRANCH%"=="" (
    echo [ERROR] Could not determine current branch. Please push manually.
    echo.
    echo To push manually, run:
    echo    git push -u origin YOUR_BRANCH_NAME
    pause
    exit /b 1
)

REM Push
echo.
echo Pushing to GitHub...
echo Current branch: %CURRENT_BRANCH%
echo.
git push -u origin %CURRENT_BRANCH% 2>nul
if %errorlevel% == 0 (
    echo [SUCCESS] Code pushed to GitHub!
    echo.
    echo View your branch at:
    echo https://github.com/arshadujala/IAE-AutoMCP/tree/%CURRENT_BRANCH%
) else (
    echo [ERROR] Failed to push. Possible reasons:
    echo 1. Authentication required - you may need to enter credentials
    echo 2. Branch conflicts - the remote branch may have different commits
    echo 3. Network issue - check your internet connection
    echo.
    echo You can try pushing manually with:
    echo    git push -u origin %CURRENT_BRANCH%
    echo.
    echo Or if you need to force push (use with caution):
    echo    git push -u origin %CURRENT_BRANCH% --force
)

echo.
echo ============================================================
echo Upload complete!
echo ============================================================
pause

