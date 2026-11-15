@echo off
REM NOOBRA auto-update — pulls the latest code from GitHub (main branch).
REM
REM Manual use: double-click this file.
REM Automatic use: run scripts\setup-auto-update.ps1 once — it creates a
REM Windows Task Scheduler task that runs this file every 30 minutes.
REM
REM Usage: update.bat [--silent]
REM   --silent  : no pause at the end (for Task Scheduler).
REM
REM Notes:
REM - This only works if this folder is a real Git clone of
REM   https://github.com/Itx-Munawar/NOOBRA (not a ZIP extract).
REM   If "git pull" says "not a git repository", follow the setup in
REM   README.md ("Keeping NOOBRA up to date").
REM - Your .env is never touched by git pull (it is gitignored).
REM - After an update, restart NOOBRA to use the new code.

setlocal
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
    echo Git is not installed. Install it from https://git-scm.com/download/win
    echo and then run this file again.
    if not "%~1"=="--silent" pause
    exit /b 1
)

echo Updating NOOBRA from GitHub...
git pull origin main
if errorlevel 1 (
    echo.
    echo Update failed. Check your internet connection and your GitHub
    echo login (run "gh auth login" or check Windows Credential Manager).
    if not "%~1"=="--silent" pause
    exit /b 1
)

echo.
echo NOOBRA is up to date. Restart NOOBRA to use the new code.
if not "%~1"=="--silent" pause
endlocal
exit /b 0
