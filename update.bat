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

REM This folder must be a Git clone. A ZIP extract has no .git, and
REM "git pull" there fails with a confusing message - say it plainly
REM instead of scheduling/looping a task that can never work.
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo This folder is not a Git clone, so it cannot auto-update.
    echo.
    echo Fix it once:
    echo   1. Clone the repo next to this folder:
    echo        git clone https://github.com/Itx-Munawar/NOOBRA.git NOOBRA-new
    echo   2. Copy your .env into NOOBRA-new\
    echo   3. Run setup.bat inside NOOBRA-new\
    echo   4. Use that folder from now on.
    if not "%~1"=="--silent" pause
    exit /b 1
)

echo Updating NOOBRA from GitHub...
REM --ff-only refuses to create a merge commit; if it fails, the folder has
REM local edits or diverged history and needs attention, not a silent pull.
git pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo Update failed. Usual causes:
    echo   - No internet connection
    echo   - You edited files in this folder ^(commit or discard them^):
    echo       git status
    echo       git checkout -- .
    echo   - GitHub asked for a login: run "gh auth login"
    if not "%~1"=="--silent" pause
    exit /b 1
)

echo.
echo NOOBRA is up to date. Restart NOOBRA to use the new code.
if not "%~1"=="--silent" pause
endlocal
exit /b 0
